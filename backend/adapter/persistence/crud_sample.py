from datetime import datetime
from typing import Any, Dict, List, Union


from sqlalchemy import case, func
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder

from backend.domain.models.sample import SampleState
from backend.domain.models.sample import ProjectSample


def batch(db: Session, samples: List[ProjectSample]) -> List[ProjectSample]:
    db.bulk_save_objects(samples, return_defaults=True)
    return samples


def list_by(
    db: Session,
    project_id: Union[int, None],
    after: Union[int, None],
    before: Union[int, None],
    page: Union[int, None],
    size: int,
    sorting: Union[str, None],
    split: str | None = None,
    state: SampleState | None = None,
) -> List[ProjectSample]:

    # query filter
    query_filter = [ProjectSample.deleted_at.is_(None)]
    if before:
        query_filter.append(ProjectSample.id < before)
    if after:
        query_filter.append(ProjectSample.id > after)
    if project_id:
        query_filter.append(ProjectSample.project_id == project_id)
    if split is not None:
        query_filter.append(ProjectSample.split == split)
    if state is not None:
        query_filter.append(ProjectSample.state == state)
    query = db.query(ProjectSample).filter(*query_filter)

    # case when for state enum
    whens = {state.value: index for index, state in enumerate(SampleState)}
    sort_logic = case(whens, value=ProjectSample.state).label(ProjectSample.state.key)

    # Allowlist of sortable columns mapped to real ORM columns. Only these
    # identifiers may reach ORDER BY; anything else is rejected so request
    # input can never be interpolated into raw SQL.
    sortable_columns = {
        "inner_id": ProjectSample.inner_id,
        "updated_at": ProjectSample.updated_at,
        "annotated_count": ProjectSample.annotated_count,
    }

    if sorting:
        sort_strings = sorting.split(",")
        for item in sort_strings:
            sort_key = item.split(":")
            column = sort_key[0]
            direction = sort_key[1] if len(sort_key) > 1 else "asc"
            if direction not in ("asc", "desc"):
                continue
            if column == ProjectSample.state.key:
                order_target = sort_logic
            elif column in sortable_columns:
                order_target = sortable_columns[column]
            else:
                continue
            query = query.order_by(
                order_target.asc() if direction == "asc" else order_target.desc()
            )

    # default order by id, before need select last items
    if before:
        query = query.order_by(ProjectSample.id.desc())
    else:
        query = query.order_by(ProjectSample.id.asc())
    results = query.offset(offset=page * size if page else 0).limit(limit=size).all()
    if before:
        results.reverse()
    return results


def get(db: Session, sample_id: int) -> ProjectSample:
    return (
        db.query(ProjectSample)
        .filter(ProjectSample.id == sample_id, ProjectSample.deleted_at.is_(None))
        .first()
    )


def get_by_ids(
    db: Session, sample_ids: List[int], project_id: Union[int, None] = None
) -> List[ProjectSample]:
    query_filter = [
        ProjectSample.id.in_(sample_ids),
        ProjectSample.deleted_at.is_(None),
    ]
    if project_id is not None:
        query_filter.append(ProjectSample.project_id == project_id)
    return db.query(ProjectSample).filter(*query_filter).all()


def list_new_samples(db: Session, project_id: int) -> List[ProjectSample]:
    return (
        db.query(ProjectSample)
        .filter(
            ProjectSample.project_id == project_id,
            ProjectSample.state == SampleState.NEW.value,
            ProjectSample.deleted_at.is_(None),
        )
        .all()
    )


def update(db: Session, db_obj: ProjectSample, obj_in: Dict[str, Any]) -> ProjectSample:
    obj_data = jsonable_encoder(obj_in)
    for field in obj_data:
        if field in obj_in:
            setattr(db_obj, field, obj_in[field])
    db.add(db_obj)
    db.flush()
    db.refresh(db_obj)
    return db_obj


def delete(db: Session, sample_ids: List[int]) -> None:
    db.query(ProjectSample).filter(ProjectSample.id.in_(sample_ids)).update(
        {ProjectSample.deleted_at: datetime.now()}
    )


def count(
    db: Session,
    project_id: int,
    split: str | None = None,
    state: SampleState | None = None,
) -> int:
    query_filter = [ProjectSample.deleted_at.is_(None)]
    if project_id:
        query_filter.append(ProjectSample.project_id == project_id)
    if split is not None:
        query_filter.append(ProjectSample.split == split)
    if state is not None:
        query_filter.append(ProjectSample.state == state)
    return db.query(ProjectSample).filter(*query_filter).count()


def statics(
    db: Session,
    project_ids: List[int],
) -> dict:
    query_filter = [ProjectSample.deleted_at.is_(None)]
    if project_ids:
        query_filter.append(ProjectSample.project_id.in_(project_ids))

    statics = (
        db.query(
            ProjectSample.project_id,
            ProjectSample.state,
            ProjectSample.split,
            func.count(ProjectSample.state).label("count"),
        )
        .filter(*query_filter)
        .group_by(ProjectSample.project_id, ProjectSample.state, ProjectSample.split)
        .all()
    )
    # 同一次聚合分别累计状态和数据划分，统计范围始终为项目全部有效样本。
    d = {}
    for project_id, state, split, count in statics:
        state_key = f"{project_id}_{state}"
        split_key = f"{project_id}_split_{split}"
        d[state_key] = d.get(state_key, 0) + count
        d[split_key] = d.get(split_key, 0) + count
    return d
