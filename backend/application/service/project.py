import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import List, Tuple

from loguru import logger
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from backend.common.db import begin_transaction
from backend.common.error_code import ErrorCode
from backend.common.error_code import YoloMcpException
from backend.domain.models.user import User
from backend.domain.models.project import Project
from backend.domain.models.attachment import ProjectAttachment
from backend.common.storage import get_storage
from backend.domain.models.project import ProjectStatus
from backend.domain.models.sample import SampleState
from backend.application.service.access import assert_project_access, assert_owner
from backend.application.service.dataset import dataset_classes
from backend.adapter.persistence import crud_project, crud_user
from backend.adapter.persistence import crud_sample
from backend.application.command.project import BasicConfigCommand
from backend.application.command.project import UpdateCommand
from backend.application.response.base import UserResp
from backend.application.response.user import UserResponse
from backend.application.response.base import CommonDataResp
from backend.application.response.project import ProjectStatics
from backend.application.response.project import ProjectResponse
from backend.application.response.project import ProjectResponseWithStatics
from backend.inference import ANNOTATION_WEIGHTS
from backend.clients.ws import sampleConnectionManager


async def create(
    db: Session, cmd: BasicConfigCommand, current_user: User
) -> ProjectResponse:
    if cmd.media_type != "IMAGE":
        raise HTTPException(422, "YOLO 数据集项目使用图片标注")

    # 1. 数据库分配项目 ID，再创建该项目的本地目录。
    storage = get_storage()
    created_directories = []
    try:
        with begin_transaction(db):
            new_project = crud_project.create(
                db=db,
                project=Project(
                    status=ProjectStatus.DRAFT.value,
                    name=cmd.name,
                    description=cmd.description,
                    media_type=cmd.media_type,
                    tips=cmd.tips,
                    created_by=current_user.id,
                    updated_by=current_user.id,
                ),
            )
            project_directory = storage.path(new_project.dataset_prefix)
            project_directory.mkdir(parents=True, exist_ok=False)
            created_directories.append(project_directory)
            for name in ("images", "thumbnails", "models", "runs"):
                directory = project_directory / name
                directory.mkdir()
                created_directories.append(directory)
    except Exception as error:
        # 2. 失败时只移除本次新建的空目录，保留已有文件。
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError:
                logger.error("Project directory cleanup failed: path={}", directory)
        if isinstance(error, OSError):
            raise HTTPException(500, "本地项目目录创建失败，项目未创建") from None
        raise

    # response
    return ProjectResponse(
        id=new_project.id,
        ai_model_name=new_project.ai_model_name,
        ai_algorithm=new_project.ai_algorithm,
        training_config=new_project.training_config,
        dataset_prefix=new_project.dataset_prefix,
        name=new_project.name,
        description=new_project.description,
        tips=new_project.tips,
        status=new_project.status,
        media_type=new_project.media_type,
        created_at=new_project.created_at,
        created_by=UserResp(
            id=new_project.owner.id,
            username=new_project.owner.username,
        ),
    )


async def list_by(
    db: Session,
    current_user: User,
    page: int,
    size: int,
) -> Tuple[List[ProjectResponseWithStatics], int]:
    # get project list
    projects, total_project = crud_project.list_by(
        db=db,
        owner_id=None if current_user.is_admin else current_user.id,
        page=page,
        size=size,
    )

    # get progress
    project_ids = [project.id for project in projects]
    statics = crud_sample.statics(db=db, project_ids=project_ids)

    # response
    projects_with_statics = [
        ProjectResponseWithStatics(
            id=project.id,
            ai_model_name=project.ai_model_name,
            ai_algorithm=project.ai_algorithm,
            training_config=project.training_config,
            dataset_prefix=project.dataset_prefix,
            name=project.name,
            description=project.description,
            tips=project.tips,
            media_type=project.media_type,
            config=project.config,
            status=project.status,
            created_at=project.created_at,
            created_by=UserResp(
                id=project.owner.id,
                username=project.owner.username,
            ),
            stats=ProjectStatics(
                train=statics.get(f"{project.id}_split_train", 0),
                test=statics.get(f"{project.id}_split_test", 0),
                new=statics.get(f"{project.id}_{SampleState.NEW.value}", 0),
                done=statics.get(f"{project.id}_{SampleState.DONE.value}", 0),
                skipped=statics.get(f"{project.id}_{SampleState.SKIPPED.value}", 0),
            ),
        )
        for project in projects
    ]
    return projects_with_statics, total_project


async def get(
    db: Session, project_id: int, current_user: User
) -> ProjectResponseWithStatics:

    # get project detail
    project = crud_project.get(db=db, project_id=project_id)

    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # not the collaborators
    if (
        not current_user.is_admin
        and project.created_by != current_user.id
        and current_user not in project.collaborators
    ):
        logger.error(
            "cannot get project, the project owner is:{}, the get operator is:{}",
            project.created_by,
            current_user.id,
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # get progress
    statics = crud_sample.statics(
        db=db,
        project_ids=[project.id],
    )

    # response
    return ProjectResponseWithStatics(
        id=project.id,
        ai_model_name=project.ai_model_name,
        ai_algorithm=project.ai_algorithm,
        training_config=project.training_config,
        dataset_prefix=project.dataset_prefix,
        name=project.name,
        description=project.description,
        tips=project.tips,
        media_type=project.media_type,
        config=project.config,
        status=project.status,
        created_at=project.created_at,
        created_by=UserResp(
            id=project.owner.id,
            username=project.owner.username,
        ),
        stats=ProjectStatics(
            train=statics.get(f"{project.id}_split_train", 0),
            test=statics.get(f"{project.id}_split_test", 0),
            new=statics.get(f"{project.id}_{SampleState.NEW.value}", 0),
            done=statics.get(f"{project.id}_{SampleState.DONE.value}", 0),
            skipped=statics.get(f"{project.id}_{SampleState.SKIPPED.value}", 0),
        ),
    )


async def get_collaborators(db: Session, project_id: int, current_user: User):
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    assert_project_access(project, current_user)
    return [UserResponse.model_validate(user) for user in project.collaborators]


async def add_collaborator(
    db: Session, project_id: int, user_id: int, current_user: User
):
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if project.created_by != current_user.id and not current_user.is_admin:
        logger.error(
            "cannot add collaborator, the project owner is:{}, the add operator is:{}",
            project.created_by,
            current_user.id,
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    user = crud_user.get(db=db, id=user_id)
    if not user or not user.is_active:
        logger.error("cannot find user:{}", user_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_40002_USER_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # collaborator exists
    if user.id == project.created_by or user in project.collaborators:
        logger.error("collaborator already exists:{}", user_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50003_COLLABORATOR_ALREADY_EXISTS,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    with begin_transaction(db):
        project.collaborators.append(user)

    return UserResponse.model_validate(user)


async def batch_add_collaborators(
    db: Session, project_id: int, user_ids: List[int], current_user: User
):
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if project.created_by != current_user.id and not current_user.is_admin:
        logger.error(
            "cannot add collaborator, the project owner is:{}, the add operator is:{}",
            project.created_by,
            current_user.id,
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    user_ids = (
        set(user_ids)
        - set([user.id for user in project.collaborators])
        - set([project.created_by])
    )
    users = crud_user.list_by_ids(db=db, ids=user_ids)
    if len(users) != len(user_ids) or any(not user.is_active for user in users):
        logger.error("cannot find users:{}", user_ids)
        raise YoloMcpException(
            code=ErrorCode.CODE_40002_USER_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    with begin_transaction(db):
        project.collaborators.extend(users)

    return [UserResponse.model_validate(user) for user in users]


async def remove_collaborator(
    db: Session, project_id: int, user_id: int, current_user: User
):
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if project.created_by != current_user.id and not current_user.is_admin:
        logger.error(
            "cannot remove collaborator, project owner:{}, operator:{}",
            project.created_by,
            current_user.id,
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    user = crud_user.get(db=db, id=user_id)
    if not user:
        logger.error("cannot find user:{}", user_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_40002_USER_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if user not in project.collaborators:
        logger.error("cannot find collaborator:{}", user_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50004_COLLABORATOR_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    with begin_transaction(db):
        project.collaborators.remove(user)

    await sampleConnectionManager.close_user_connections(user_id, project_id)
    return CommonDataResp(ok=True)


async def batch_remove_collaborators(
    db: Session, project_id: int, user_ids: List[int], current_user: User
):
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if project.created_by != current_user.id and not current_user.is_admin:
        logger.error(
            "cannot remove collaborator, project owner:{}, operator:{}",
            project.created_by,
            current_user.id,
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    users = crud_user.list_by_ids(db=db, ids=user_ids)
    if len(users) != len(user_ids):
        logger.error("cannot find users:{}", user_ids)
        raise YoloMcpException(
            code=ErrorCode.CODE_40002_USER_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    with begin_transaction(db):
        for user in users:
            if user in project.collaborators:
                project.collaborators.remove(user)

    for user in users:
        await sampleConnectionManager.close_user_connections(user.id, project_id)
    return CommonDataResp(ok=True)


async def update(
    db: Session, project_id: int, cmd: UpdateCommand, current_user: User
) -> ProjectResponse:

    # get project
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    assert_owner(project, current_user)

    # update
    obj_in = cmd.model_dump(exclude_unset=True)
    algorithm = obj_in.get("ai_algorithm", project.ai_algorithm)
    model_name = obj_in.get("ai_model_name", project.ai_model_name)
    if (
        model_name
        and algorithm == "yolo"
        and (
            PurePosixPath(model_name).name != model_name
            or PureWindowsPath(model_name).name != model_name
            or not model_name.endswith(".pt")
        )
    ):
        raise HTTPException(422, "YOLO 自动标注请选择项目内的 .pt 权重")
    if (
        model_name
        and algorithm != "yolo"
        and model_name not in ANNOTATION_WEIGHTS[algorithm]
    ):
        raise HTTPException(422, "所选权重不属于当前自动标注算法")
    if cmd.config:
        dataset_classes(json.loads(cmd.config))
    if cmd.media_type and cmd.media_type != "IMAGE":
        raise HTTPException(422, "YOLO 数据集项目使用图片标注")
    if cmd.config:
        obj_in[Project.status.key] = ProjectStatus.CONFIGURED
    with begin_transaction(db):
        updated_project = crud_project.update(db=db, db_obj=project, obj_in=obj_in)

    # response
    return ProjectResponse(
        id=updated_project.id,
        ai_model_name=updated_project.ai_model_name,
        ai_algorithm=updated_project.ai_algorithm,
        training_config=updated_project.training_config,
        dataset_prefix=updated_project.dataset_prefix,
        name=updated_project.name,
        description=updated_project.description,
        tips=updated_project.tips,
        media_type=updated_project.media_type,
        config=updated_project.config,
        status=updated_project.status,
        created_at=updated_project.created_at,
        created_by=UserResp(
            id=updated_project.owner.id,
            username=updated_project.owner.username,
        ),
    )


async def delete(db: Session, project_id: int, current_user: User) -> CommonDataResp:

    # get project
    project = crud_project.get(db=db, project_id=project_id)
    if not project:
        logger.error("cannot find project:{}", project_id)
        raise YoloMcpException(
            code=ErrorCode.CODE_50002_PROJECT_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if project.created_by != current_user.id and not current_user.is_admin:
        logger.error(
            "cannot delete project, the project owner is:{}, the delete operator is:{}",
            project.created_by,
            current_user.id,
        )
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )

    # 删除上传附件与缩略图，保留数据集、模型和训练日志。
    storage = get_storage()
    attachments = (
        db.query(ProjectAttachment)
        .filter(
            ProjectAttachment.project_id == project_id,
            ProjectAttachment.deleted_at.is_(None),
        )
        .all()
    )
    for attachment in attachments:
        storage.delete(attachment.path)
        storage.delete(storage.thumbnail_key(attachment.path))

    # delete
    with begin_transaction(db):
        crud_project.delete(db=db, db_obj=project)

    # response
    return CommonDataResp(ok=True)
