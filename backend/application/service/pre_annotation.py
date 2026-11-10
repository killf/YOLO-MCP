"""读取本项目由 AI 生成的预标注，不提供文件导入入口。"""

from typing import List, Optional, Tuple
from fastapi import HTTPException
from sqlalchemy.orm import Session
from backend.adapter.persistence import crud_pre_annotation, crud_project
from backend.application.service.access import assert_project_access
from backend.application.service.attachment import build_attachment_response
from backend.application.response.base import UserResp
from backend.application.response.pre_annotation import PreAnnotationResponse
from backend.domain.models.user import User


async def list_by(
    db: Session,
    project_id: Optional[int],
    sample_name: Optional[str],
    after: Optional[int],
    before: Optional[int],
    page: Optional[int],
    size: int,
    sorting: Optional[str],
    current_user: User,
) -> Tuple[List[PreAnnotationResponse], int]:

    project = crud_project.get(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(404, "标注项目不存在")
    assert_project_access(project, current_user)

    pre_annotations, total = crud_pre_annotation.list_by(
        db=db,
        project_id=project_id,
        after=after,
        before=before,
        page=page,
        sample_name=sample_name,
        size=None if sample_name else size,
        sorting=sorting,
    )

    return [
        PreAnnotationResponse(
            id=pre_annotation.id,
            data=pre_annotation.data,
            file=build_attachment_response(pre_annotation.file, current_user),
            created_at=pre_annotation.created_at,
            created_by=UserResp(
                id=pre_annotation.owner.id,
                username=pre_annotation.owner.username,
            ),
            updated_at=pre_annotation.updated_at,
            updated_by=UserResp(
                id=pre_annotation.updater.id,
                username=pre_annotation.updater.username,
            ),
        )
        for pre_annotation in pre_annotations
    ], total
