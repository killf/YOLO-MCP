from datetime import datetime
from sqlalchemy import or_, exists
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

from backend.domain.models.project import Project
from backend.domain.models.project_collaborator import ProjectCollaborator


def create(db: Session, project: Project) -> Project:
    db.add(project)
    db.flush()
    db.refresh(project)
    return project


def list_by(
    db: Session, owner_id: int | None, page: int = 0, size: int = 100
) -> Tuple[List[Project], int]:
    collaborator_exists = exists().where(
        ProjectCollaborator.project_id == Project.id,
        ProjectCollaborator.user_id == owner_id,
    )
    query = db.query(Project).filter(Project.deleted_at.is_(None))
    if owner_id is not None:
        query = query.filter(or_(Project.created_by == owner_id, collaborator_exists))
    total = query.count()

    return (
        query.order_by(Project.id.desc())
        .offset(offset=page * size)
        .limit(limit=size)
        .all()
    ), total


def get(db: Session, project_id: int, lock: bool = False) -> Project:
    """return a Project item according to project id

    Args:
        db (Session): a session connect to table
        project_id (int): a given project id
        lock (bool, optional): 是否锁定返回行，默认 False。
    """
    if not lock:
        return (
            db.query(Project)
            .filter(Project.id == project_id, Project.deleted_at.is_(None))
            .first()
        )
    else:
        return (
            db.query(Project)
            .filter(Project.id == project_id, Project.deleted_at.is_(None))
            .with_for_update()
            .first()
        )


def update(db: Session, db_obj: Project, obj_in: Dict[str, Any]) -> Project:
    obj_data = jsonable_encoder(obj_in)
    for field in obj_data:
        if field in obj_in:
            setattr(db_obj, field, obj_in[field])
    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    return db_obj


def delete(db: Session, db_obj: Project) -> Project:
    db_obj.deleted_at = datetime.now()
    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    return db_obj


def count(db: Session, owner_id: int) -> int:
    return (
        db.query(Project)
        .filter(Project.created_by == owner_id, Project.deleted_at.is_(None))
        .count()
    )
