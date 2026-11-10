from datetime import datetime
from typing import List, Tuple

from sqlalchemy.orm import Session

from backend.domain.models.pre_annotation import ProjectPreAnnotation


def batch(
    db: Session, pre_annotations: List[ProjectPreAnnotation]
) -> List[ProjectPreAnnotation]:
    db.bulk_save_objects(pre_annotations, return_defaults=True)
    return pre_annotations


def list_by(
    db: Session,
    project_id: int | None = None,
    sample_name: str | None = None,
    after: int | None = None,
    before: int | None = None,
    page: int | None = None,
    sorting: str | None = None,
    size: int | None = 10,
) -> Tuple[List[ProjectPreAnnotation], int]:

    # query filter
    query_filter = [ProjectPreAnnotation.deleted_at.is_(None)]
    if before:
        query_filter.append(ProjectPreAnnotation.id < before)
    if after:
        query_filter.append(ProjectPreAnnotation.id > after)
    if project_id:
        query_filter.append(ProjectPreAnnotation.project_id == project_id)

    if sample_name:
        query_filter.append(ProjectPreAnnotation.sample_name == sample_name)

    query = db.query(ProjectPreAnnotation).filter(*query_filter)

    # default order by id, before need select last items
    if before:
        query = query.order_by(ProjectPreAnnotation.id.desc())
    else:
        query = query.order_by(ProjectPreAnnotation.id.asc())

    count = query.count()

    results = query.offset(offset=page * size if page else 0).limit(limit=size).all()

    if sorting:
        field, order = sorting.split(":")
        if order == "desc":
            results = sorted(results, key=lambda x: getattr(x, field), reverse=True)
        else:
            results = sorted(results, key=lambda x: getattr(x, field))

    if before:
        results.reverse()

    return results, count


def delete(db: Session, pre_annotation_ids: List[int]) -> None:
    db.query(ProjectPreAnnotation).filter(
        ProjectPreAnnotation.id.in_(pre_annotation_ids)
    ).update({ProjectPreAnnotation.deleted_at: datetime.now()})
