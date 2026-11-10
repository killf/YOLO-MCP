from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.domain.models.attachment import ProjectAttachment


def list_by(
    db: Session,
    size: int,
    ids: List[int] | None = [],
    project_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    after: Optional[int] = None,
    before: Optional[int] = None,
    page: Optional[int] = None,
    sorting: Optional[str] = None,
) -> Tuple[List[ProjectAttachment], int]:
    # query filter
    query_filter = [
        ProjectAttachment.deleted_at.is_(None),
        ProjectAttachment.id.in_(ids),
    ]
    if owner_id:
        query_filter.append(ProjectAttachment.created_by == owner_id)

    if before:
        query_filter.append(ProjectAttachment.id < before)
    if after:
        query_filter.append(ProjectAttachment.id > after)
    if project_id:
        query_filter.append(ProjectAttachment.project_id == project_id)

    query = db.query(ProjectAttachment).filter(*query_filter)

    # default order by id, before need select last items
    if before:
        query = query.order_by(ProjectAttachment.id.desc())
    else:
        query = query.order_by(ProjectAttachment.id.asc())

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


def create(db: Session, attachment: ProjectAttachment) -> ProjectAttachment:
    db.add(attachment)
    db.flush()
    db.refresh(attachment)
    return attachment


def get(db: Session, attachment_id: int) -> ProjectAttachment:
    return (
        db.query(ProjectAttachment)
        .filter(
            ProjectAttachment.id == attachment_id,
            ProjectAttachment.deleted_at.is_(None),
        )
        .first()
    )


def get_by_ids(db: Session, attachment_ids: List[int]) -> List[ProjectAttachment]:
    return (
        db.query(ProjectAttachment)
        .filter(
            ProjectAttachment.id.in_(attachment_ids),
            ProjectAttachment.deleted_at.is_(None),
        )
        .all()
    )


def delete(db: Session, attachment_ids: List[int]) -> None:
    db.query(ProjectAttachment).filter(ProjectAttachment.id.in_(attachment_ids)).update(
        {ProjectAttachment.deleted_at: datetime.now()}
    )
