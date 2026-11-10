from typing import List

from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
from fastapi import APIRouter, status, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials

from backend.application.response.user import UserResponse
from backend.common import db as db_module
from backend.common.security import security
from backend.domain.models.user import User
from backend.dependencies.user import get_current_user
from backend.application.service import project as service
from backend.application.command.project import (
    BasicConfigCommand,
    CollaboratorBatchCommand,
    CollaboratorUpdateCommand,
)
from backend.application.command.project import UpdateCommand
from backend.application.response.base import OkResp
from backend.application.response.base import MetaData
from backend.application.response.base import CommonDataResp
from backend.application.response.base import OkRespWithMeta
from backend.application.response.project import ProjectResponse
from backend.application.response.project import ProjectResponseWithStatics
from backend.inference import AnnotationAlgorithm

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/{project_id}/models/{model_name}", response_class=FileResponse)
async def download_model(
    project_id: int,
    model_name: str,
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """以附件形式下载本项目权重，不暴露本地目录或无关文件。"""
    from backend.application.service.training import model_file

    path = model_file(db, project_id, model_name, current_user)
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post(
    "",
    response_model=OkResp[ProjectResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create(
    cmd: BasicConfigCommand,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a project with basic config.
    """

    # business logic
    data = await service.create(db=db, cmd=cmd, current_user=current_user)

    # response
    return OkResp[ProjectResponse](data=data)


@router.get(
    "",
    response_model=OkRespWithMeta[List[ProjectResponseWithStatics]],
    status_code=status.HTTP_200_OK,
)
async def list_by(
    page: int = 0,
    size: int = 100,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List project.
    """

    # business logic
    data, total = await service.list_by(
        db=db, current_user=current_user, page=page, size=size
    )

    # response
    meta_data = MetaData(total=total, page=page, size=len(data))
    return OkRespWithMeta[List[ProjectResponseWithStatics]](
        meta_data=meta_data, data=data
    )


@router.get(
    "/{project_id}",
    response_model=OkResp[ProjectResponseWithStatics],
    status_code=status.HTTP_200_OK,
)
async def get(
    project_id: int,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get project detail.
    """

    # business logic
    data = await service.get(db=db, project_id=project_id, current_user=current_user)

    # response
    return OkResp[ProjectResponseWithStatics](data=data)


@router.get(
    "/{project_id}/collaborators",
    response_model=OkResp[List[UserResponse]],
    status_code=status.HTTP_200_OK,
)
async def get_collaborators(
    project_id: int,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get project detail.
    """

    # business logic
    data = await service.get_collaborators(
        db=db, project_id=project_id, current_user=current_user
    )

    # response
    return OkResp[List[UserResponse]](data=data)


@router.post(
    "/{project_id}/collaborators",
    response_model=OkResp[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_collaborator(
    project_id: int,
    cmd: CollaboratorUpdateCommand,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add collaborator to project.
    """

    # business logic
    data = await service.add_collaborator(
        db=db, project_id=project_id, user_id=cmd.user_id, current_user=current_user
    )

    # response
    return OkResp[UserResponse](data=data)


@router.post(
    "/{project_id}/collaborators/batch_add",
    response_model=OkResp[List[UserResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def batch_add_collaborator_request(
    project_id: int,
    cmd: CollaboratorBatchCommand,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add collaborators to project.
    """

    # business logic
    data = await service.batch_add_collaborators(
        db=db, project_id=project_id, user_ids=cmd.user_ids, current_user=current_user
    )

    # response
    return OkResp[List[UserResponse]](data=data)


@router.post(
    "/{project_id}/collaborators/batch_remove",
    response_model=OkResp[CommonDataResp],
    status_code=status.HTTP_201_CREATED,
)
async def batch_remove_collaborator_request(
    project_id: int,
    cmd: CollaboratorBatchCommand,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add collaborators to project.
    """

    # business logic
    data = await service.batch_remove_collaborators(
        db=db, project_id=project_id, user_ids=cmd.user_ids, current_user=current_user
    )

    # response
    return OkResp[CommonDataResp](data=data)


@router.delete(
    "/{project_id}/collaborators/{user_id}",
    response_model=OkResp[CommonDataResp],
    status_code=status.HTTP_200_OK,
)
async def remove_collaborator(
    project_id: int,
    user_id: int,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Remove collaborator from project.
    """

    # business logic
    data = await service.remove_collaborator(
        db=db, project_id=project_id, user_id=user_id, current_user=current_user
    )

    # response
    return OkResp[CommonDataResp](data=data)


@router.patch(
    "/{project_id}",
    response_model=OkResp[ProjectResponse],
    status_code=status.HTTP_200_OK,
)
async def update(
    project_id: int,
    cmd: UpdateCommand,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update project info, inlucde annotation config, name, description and tips.
    """

    # business logic
    data = await service.update(
        db=db, project_id=project_id, cmd=cmd, current_user=current_user
    )

    # response
    return OkResp[ProjectResponse](data=data)


@router.delete(
    "/{project_id}",
    response_model=OkResp[CommonDataResp],
    status_code=status.HTTP_200_OK,
)
async def delete(
    project_id: int,
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete project.
    """

    # business logic
    data = await service.delete(db=db, project_id=project_id, current_user=current_user)

    # response
    return OkResp[CommonDataResp](data=data)


@router.get("/{project_id}/models", response_model=OkResp[List[str]])
async def list_models(
    project_id: int,
    algorithm: AnnotationAlgorithm = "yolo",
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
) -> OkResp[List[str]]:
    """列出项目数据集 models/ 下的权重文件。"""
    from backend.application.service import auto_label

    return OkResp[List[str]](
        data=auto_label.list_models(db, project_id, current_user, algorithm)
    )
