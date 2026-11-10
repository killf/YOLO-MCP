from sqlalchemy.orm import Session
from fastapi import APIRouter, status, Depends, Security
from fastapi import File, UploadFile
from fastapi import HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials

from backend.common import db as db_module
from backend.common.security import security
from backend.domain.models.user import User
from backend.dependencies.user import get_current_user
from backend.application.service import attachment as service
from backend.application.command.attachment import AttachmentCommand
from backend.application.command.attachment import AttachmentDeleteCommand
from backend.application.response.base import OkResp
from backend.application.response.base import CommonDataResp
from backend.application.response.attachment import AttachmentResponse

router = APIRouter(prefix="/projects", tags=["attachments"])


@router.get("/{project_id}/files/{filename:path}", response_class=FileResponse)
async def preview(
    project_id: int,
    filename: str,
    expires: int = Query(...),
    signature: str = Query(...),
    user_id: int = Query(...),
    auth_version: int = Query(...),
    db: Session = Depends(db_module.get_db),
):
    """用文件限定的短时签名读取本地图片，拒绝路径越界和签名篡改。"""
    from backend.common.storage import get_storage

    storage = get_storage()
    key = f"projects/{project_id}/{filename}"
    try:
        allowed = storage.verify_read_url(
            key, expires, signature, user_id, auth_version
        )
        path = storage.path(key)
    except ValueError:
        raise HTTPException(403, "无效的图片访问地址") from None
    if not allowed:
        raise HTTPException(403, "图片访问地址无效或已过期")
    from backend.adapter.persistence import crud_project
    from backend.application.service.access import assert_project_access

    user = db.get(User, user_id)
    project = crud_project.get(db, project_id)
    if (
        user is None
        or not user.is_active
        or user.auth_version != auth_version
        or project is None
    ):
        raise HTTPException(403, "图片访问权限已失效")
    assert_project_access(project, user)
    if not path.is_file():
        raise HTTPException(404, "图片不存在")
    return FileResponse(path, headers={"Cache-Control": "private, no-store"})


@router.post(
    "/{project_id}/attachments",
    response_model=OkResp[AttachmentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create(
    project_id: int,
    file: UploadFile = File(...),
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create attechment as annnotation sample.
    """
    # business logic
    cmd = AttachmentCommand(file=file)
    data = await service.create(
        db=db, project_id=project_id, cmd=cmd, current_user=current_user
    )

    # response
    return OkResp[AttachmentResponse](data=data)


@router.delete(
    "/{project_id}/attachments",
    response_model=OkResp[CommonDataResp],
    status_code=status.HTTP_200_OK,
)
async def delete(
    project_id: int,
    cmd: AttachmentDeleteCommand,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    delete project.
    """

    # business logic
    data = await service.delete(
        db=db, project_id=project_id, cmd=cmd, current_user=current_user
    )

    # response
    return OkResp[CommonDataResp](data=data)
