from typing import Optional
from sqlalchemy.orm import Session
from backend.domain.models.auto_label_job import AutoLabelJob


def create(
    db: Session,
    project_id: int,
    user_id: int,
    sample_count: int,
    model_name: str,
    algorithm: str = "yolo",
) -> AutoLabelJob:
    job = AutoLabelJob(
        project_id=project_id,
        created_by=user_id,
        sample_count=sample_count,
        model_name=model_name,
        algorithm=algorithm,
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return job


def get(db: Session, job_id: int) -> Optional[AutoLabelJob]:
    return db.query(AutoLabelJob).filter(AutoLabelJob.id == job_id).first()


def update_status(
    db: Session, job: AutoLabelJob, status: str, **kwargs
) -> AutoLabelJob:
    job.status = status
    for k, v in kwargs.items():
        setattr(job, k, v)
    db.flush()
    db.refresh(job)
    return job


def increment_progress(db: Session, job: AutoLabelJob, success: bool) -> AutoLabelJob:
    job.processed_count = (job.processed_count or 0) + 1
    if success:
        job.success_count = (job.success_count or 0) + 1
    else:
        job.failed_count = (job.failed_count or 0) + 1
    db.flush()
    db.refresh(job)
    return job
