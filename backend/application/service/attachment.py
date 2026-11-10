import re
import aiofiles
import tempfile
from pathlib import Path, PurePosixPath

from loguru import logger
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.application.service.access import assert_project_access
from backend.common.db import begin_transaction
from backend.common.config import settings
from backend.common.error_code import ErrorCode
from backend.common.error_code import YoloMcpException
from backend.common.storage import (
    build_thumbnail_key,
    create_thumbnail_bytes,
    get_storage,
)
from backend.domain.models.user import User
from backend.domain.models.attachment import ProjectAttachment
from backend.domain.models.sample import ProjectSample
from backend.adapter.persistence import crud_project
from backend.adapter.persistence import crud_attachment
from backend.application.command.attachment import AttachmentCommand
from backend.application.command.attachment import AttachmentDeleteCommand
from backend.application.response.base import CommonDataResp
from backend.application.response.attachment import AttachmentResponse


def build_attachment_response(
    attachment: ProjectAttachment | None,
    current_user: User,
) -> AttachmentResponse | None:
    """为项目上传图片签发预览地址，空附件返回 None。"""
    if attachment is None:
        return None

    # 全部附件使用服务端统一的本地目录。
    storage = get_storage()
    url = storage.get_read_url(
        attachment.path, current_user.id, current_user.auth_version
    )
    thumbnail_key = storage.thumbnail_key(attachment.path)
    thumbnail_url = (
        storage.get_read_url(thumbnail_key, current_user.id, current_user.auth_version)
        if storage.exists(thumbnail_key)
        else None
    )
    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        url=url,
        thumbnail_url=thumbnail_url,
    )


def _upload_key(project_id: int, filename: str) -> str:
    """清理上传文件名，返回项目目录内使用正斜杠的相对路径。"""
    parts = [
        re.sub(r'[\\/*?:"<>|#]', "_", part.replace("%", "_pct_"))
        for part in filename.split("/")
    ]
    if parts[-1] in ("", ".", ".."):
        raise HTTPException(422, "上传文件必须提供有效文件名")
    if any(
        re.match(r"(?i)^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part)
        for part in parts
    ):
        raise HTTPException(422, "上传文件名包含系统保留名称")
    directories = [part for part in parts[:-1] if part not in ("", ".", "..")]
    return str(
        PurePosixPath("projects", str(project_id), "images", *directories, parts[-1])
    )


async def create(
    db: Session, project_id: int, cmd: AttachmentCommand, current_user: User
) -> AttachmentResponse:
    """验证项目访问权，将上传文件和缩略图写入本地目录，并保存附件记录。"""
    # 1. 先验证项目，再访问存储；对象键只来自清理后的相对路径。
    project = crud_project.get(db=db, project_id=project_id)
    if project is None:
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )
    assert_project_access(project, current_user)
    key = _upload_key(project_id, cmd.file.filename or "")
    if PurePosixPath(key).suffix.lower() not in {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }:
        raise HTTPException(422, "仅支持上传图片文件")
    storage = get_storage()
    thumbnail_key = build_thumbnail_key(key)
    if storage.exists(key) or storage.exists(thumbnail_key):
        raise YoloMcpException(
            code=ErrorCode.CODE_51002_PROJECT_ATTACHMENT_ALREADY_EXISTS,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    attempted_keys = []
    thumbnail_bytes = None
    try:
        # 2. 分块写入临时目录，离开上下文时统一清理本地文件。
        with tempfile.TemporaryDirectory(prefix="yolo-mcp-upload-") as directory:
            local_path = Path(directory) / ("upload" + PurePosixPath(key).suffix)
            total_size = 0
            async with aiofiles.open(local_path, "wb") as output:
                while chunk := await cmd.file.read(8 * 1024 * 1024):
                    total_size += len(chunk)
                    if total_size > settings.UPLOAD_FILE_MAX_SIZE:
                        raise HTTPException(413, "上传文件超过允许的大小")
                    await output.write(chunk)

            try:
                thumbnail_bytes = create_thumbnail_bytes(local_path)
            except (OSError, ValueError):
                raise HTTPException(422, "上传内容不是有效图片") from None
            attempted_keys.append(key)
            storage.save_file(local_path, key)
            if thumbnail_bytes:
                attempted_keys.append(thumbnail_key)
                storage.save_bytes(thumbnail_bytes, thumbnail_key)

        # 3. 存储写入成功后保存记录；数据库失败也清理本次对象。
        with begin_transaction(db):
            attachment = crud_attachment.create(
                db=db,
                attachment=ProjectAttachment(
                    path=key,
                    filename=PurePosixPath(key).name,
                    created_by=current_user.id,
                    updated_by=current_user.id,
                    project_id=project_id,
                ),
            )
    except Exception as error:
        for object_key in reversed(attempted_keys):
            try:
                storage.delete(object_key)
            except Exception as cleanup_error:
                logger.error(
                    "Upload cleanup failed: project_id={}, error={}",
                    project_id,
                    type(cleanup_error).__name__,
                )
        if isinstance(error, HTTPException):
            raise
        logger.error(
            "Upload failed: project_id={}, error={}", project_id, type(error).__name__
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_51000_CREATE_ATTACHMENT_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        ) from None

    # 4. 使用本次写入结果构造响应，不重复查询对象是否存在。
    logger.info("File saved: project_id={}, size={}", project_id, total_size)
    url = storage.get_read_url(key, current_user.id, current_user.auth_version)
    return AttachmentResponse(
        id=attachment.id,
        filename=attachment.filename,
        url=url,
        thumbnail_url=(
            storage.get_read_url(
                thumbnail_key, current_user.id, current_user.auth_version
            )
            if thumbnail_bytes
            else None
        ),
    )


async def delete(
    db: Session, project_id: int, cmd: AttachmentDeleteCommand, current_user: User
) -> CommonDataResp:
    """撤回尚未关联样本的上传图片和缩略图；已提交的图片走样本删除。"""
    # 1. 验证项目访问权与待删除附件的归属。
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_51001_PROJECT_ATTACHMENT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    assert_project_access(project, current_user)
    attachments = crud_attachment.get_by_ids(db=db, attachment_ids=cmd.attachment_ids)
    if any(attachment.project_id != project_id for attachment in attachments):
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    can_manage = project.created_by == current_user.id or current_user.is_admin
    referenced = (
        db.query(ProjectSample.id)
        .filter(
            ProjectSample.file_id.in_(cmd.attachment_ids),
            ProjectSample.deleted_at.is_(None),
        )
        .first()
    )
    if not can_manage:
        if (
            referenced
            or not attachments
            or any(item.created_by != current_user.id for item in attachments)
        ):
            raise YoloMcpException(
                code=ErrorCode.CODE_30001_NO_PERMISSION, status_code=403
            )
    if referenced:
        raise HTTPException(409, "附件已创建样本，请从样本列表删除")

    # 2. 先清理自有对象，成功后再移除数据库引用。
    storage = get_storage()
    for attachment in attachments:
        storage.delete(attachment.path)
        thumbnail_key = storage.thumbnail_key(attachment.path)
        if storage.exists(thumbnail_key):
            storage.delete(thumbnail_key)

    # delete
    with begin_transaction(db):
        crud_attachment.delete(
            db=db, attachment_ids=[attachment.id for attachment in attachments]
        )

    # response
    return CommonDataResp(ok=True)
