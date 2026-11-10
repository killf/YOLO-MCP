from typing import List, Union

from fastapi import APIRouter, Depends, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from backend.common import db as db_module
from backend.common.security import security
from backend.dependencies.user import get_current_user
from backend.domain.models.user import User
from backend.application.service import pre_annotation as service
from backend.application.response.base import MetaData, OkRespWithMeta
from backend.application.response.pre_annotation import PreAnnotationResponse
from backend.common.error_code import ErrorCode, YoloMcpException

router = APIRouter(prefix="/projects", tags=["pre_annotations"])


@router.get(
    "/{project_id}/pre_annotations",
    response_model=OkRespWithMeta[List[PreAnnotationResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_by(
    project_id: int,
    sample_name: str = Query(default=None, min_length=1, max_length=255),
    after: Union[int, None] = Query(default=None, gt=0),
    before: Union[int, None] = Query(default=None, gt=0),
    page: Union[int, None] = Query(default=None, ge=0),
    size: Union[int, None] = 100,
    sort: Union[str, None] = Query(
        default=None, pattern="(annotated_count|state):(desc|asc)"
    ),
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a annotation result.
    """

    if len([i for i in (after, before, page) if i is not None]) != 1:
        raise YoloMcpException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=ErrorCode.CODE_55000_SAMPLE_LIST_PARAMETERS_ERROR,
        )

    # business logic
    data, total = await service.list_by(
        db=db,
        project_id=project_id,
        sample_name=sample_name,
        after=after,
        before=before,
        page=page,
        size=size,
        sorting=sort,
        current_user=current_user,
    )

    # response
    meta_data = MetaData(total=total, page=page, size=len(data))
    return OkRespWithMeta[List[PreAnnotationResponse]](meta_data=meta_data, data=data)
