"""在后端按所选算法加载本地权重，生成可人工修改的矩形预标注。"""

import asyncio
import json
import os
import time
import uuid
from contextlib import contextmanager
from io import BytesIO
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Iterator

from fastapi import HTTPException
from loguru import logger
from PIL import Image
from sqlalchemy.orm import Session

from backend.adapter.persistence import (
    crud_auto_label_job,
    crud_pre_annotation,
    crud_sample,
    crud_project,
)
from backend.application.response.auto_label import (
    AutoLabelResponse,
    AutoLabelJobResponse,
)
from backend.application.service.access import assert_project_access
from backend.application.service.dataset import dataset_classes
from backend.common.config import settings
from backend.common.db import SessionLocal, begin_transaction
from backend.common.storage import get_storage
from backend.domain.models.auto_label_job import AutoLabelJob, AutoLabelStatus
from backend.domain.models.pre_annotation import ProjectPreAnnotation
from backend.domain.models.sample import SampleState, ProjectSample
from backend.domain.models.project import Project
from backend.domain.models.user import User
from backend.inference import (
    ANNOTATION_WEIGHTS,
    Detection,
    load_detector,
    model_load_error,
)


def _project(db: Session, project_id: int, user: User) -> Project:
    """读取项目并验证用户访问权，不存在时返回 404。"""
    project = crud_project.get(db=db, project_id=project_id)
    if project is None:
        raise HTTPException(404, "标注项目不存在")
    assert_project_access(project, user)
    return project


def list_models(
    db: Session, project_id: int, user: User, algorithm: str = "yolo"
) -> list[str]:
    """验证项目访问权，返回算法对应的项目权重或官方模型 ID。"""
    project = _project(db, project_id, user)
    if algorithm != "yolo":
        return list(ANNOTATION_WEIGHTS.get(algorithm, ()))
    return get_storage().list_models(f"{project.dataset_prefix}/models/")


@contextmanager
def _load_model(
    db: Session, project: Project, model_name: str, algorithm: str | None = None
) -> Iterator[Any]:
    """按项目选择在后端加载本地权重，在本批次内复用模型。"""
    if not settings.USE_AUTO_LABEL:
        raise HTTPException(400, "AI 标注未启用")
    if not model_name:
        raise HTTPException(400, "请在项目配置中选择 AI 模型")
    algorithm = algorithm or getattr(project, "ai_algorithm", "yolo")
    if algorithm != "yolo":
        if model_name not in ANNOTATION_WEIGHTS.get(algorithm, ()):
            raise HTTPException(422, "所选权重不属于当前自动标注算法")
        try:
            model = load_detector(algorithm, model_name, settings.DEVICE)
        except Exception as error:
            logger.warning(
                "AI model load failed: model={}, error={}",
                model_name,
                type(error).__name__,
            )
            raise HTTPException(503, model_load_error(error, model_name)) from None
        yield model
        return
    if (
        PurePosixPath(model_name).name != model_name
        or PureWindowsPath(model_name).name != model_name
        or not model_name.endswith(".pt")
    ):
        raise HTTPException(422, "请选择 models/ 目录下的权重文件")

    # 1. 使用现有训练环境中的 Ultralytics，不在请求中安装依赖或下载官方权重。
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    try:
        from ultralytics import YOLO
    except ImportError:
        raise HTTPException(
            503, "AI 标注需要 Ultralytics，请使用已安装训练依赖的 Python 环境"
        ) from None

    # 2. 仅加载当前项目目录内已存在的本地权重。
    storage = get_storage()
    weights = storage.path(f"{project.dataset_prefix}/models/{model_name}")
    if not weights.is_file():
        raise HTTPException(404, "所选模型文件不存在")
    try:
        model = YOLO(str(weights))
    except Exception as error:
        raise HTTPException(503, model_load_error(error, model_name)) from None
    yield model


def _image_content(sample: ProjectSample) -> bytes:
    """从本地目录读取本项目上传的原图。"""
    return get_storage().read_bytes(sample.file.path)


def _predict(
    model: Any,
    sample: ProjectSample,
    project: Project,
    model_name: str,
    algorithm: str | None = None,
) -> dict:
    """使用所选模型推理图片，将匹配类别的框转换为可编辑预标注。"""
    # 1. 类别显示名和内部值均可匹配，覆盖训练 data.yaml 与标注工具的命名差异。
    attributes = dataset_classes(json.loads(project.config))
    labels = {
        name.casefold(): attribute["value"]
        for attribute in attributes
        for name in (attribute["key"], attribute["value"])
    }
    started = time.perf_counter()
    algorithm = algorithm or project.ai_algorithm
    with Image.open(BytesIO(_image_content(sample))) as image:
        if algorithm == "yolo":
            prediction = model.predict(
                image.convert("RGB"),
                imgsz=1024,
                conf=0.25,
                device=settings.DEVICE or None,
                verbose=False,
            )[0]
            detections = [
                Detection(coordinates, prediction.names[int(class_id)], confidence)
                for coordinates, class_id, confidence in zip(
                    prediction.boxes.xyxy.tolist(),
                    prediction.boxes.cls.tolist(),
                    prediction.boxes.conf.tolist(),
                )
            ]
        else:
            detections = model.predict(
                image.convert("RGB"), [item["key"] for item in attributes]
            )

    # 2. 只生成项目已配置类别的矩形框；预标注不改变样本的人工完成状态。
    boxes = []
    unmatched = 0
    for detection in detections:
        name = detection.label.casefold()
        if name not in labels:
            unmatched += 1
            continue
        x1, y1, x2, y2 = detection.xyxy
        boxes.append(
            {
                "id": str(uuid.uuid4()),
                "order": len(boxes) + 1,
                "label": labels[name],
                "valid": True,
                "isVisible": True,
                "x": x1,
                "y": y1,
                "width": x2 - x1,
                "height": y2 - y1,
                "attributes": (
                    {"score": str(detection.score)}
                    if detection.score is not None
                    else {}
                ),
            }
        )

    warning = f"已忽略 {unmatched} 个未匹配项目类别的预测框" if unmatched else None
    return {
        "sample_name": sample.file.filename,
        "annotations": {"rectTool": {"toolName": "rectTool", "result": boxes}},
        "config": {"rectTool": attributes},
        "meta": {
            "source_type": "ai_generated",
            "provider": algorithm,
            "model": model_name,
            "sample_id": sample.id,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "warning_message": warning,
        },
    }


def _save_prediction(
    db: Session, project: Project, sample: ProjectSample, payload: dict, user_id: int
) -> int:
    """替换当前样本的 AI 预标注并提交。"""
    existing, _ = crud_pre_annotation.list_by(
        db=db,
        project_id=project.id,
        sample_name=sample.file.filename,
        page=0,
        size=None,
    )
    # 仅替换当前样本的 AI 结果，保留同名其他样本的预标注。
    previous_ai = []
    for item in existing:
        meta = json.loads(item.data).get("meta", {})
        if (
            meta.get("source_type") == "ai_generated"
            and meta.get("sample_id") == sample.id
        ):
            previous_ai.append(item.id)
    with begin_transaction(db):
        if previous_ai:
            crud_pre_annotation.delete(db=db, pre_annotation_ids=previous_ai)
        created = crud_pre_annotation.batch(
            db=db,
            pre_annotations=[
                ProjectPreAnnotation(
                    project_id=project.id,
                    sample_name=sample.file.filename,
                    data=json.dumps(payload, ensure_ascii=False),
                    created_by=user_id,
                    updated_by=user_id,
                )
            ],
        )
    return created[0].id


def _single(
    db: Session, project_id: int, sample_id: int, user: User
) -> AutoLabelResponse:
    """验证项目和样本，运行一次预测并返回保存后的预标注信息。"""
    project = _project(db, project_id, user)
    sample = crud_sample.get(db=db, sample_id=sample_id)
    if sample is None or sample.project_id != project_id or not sample.file:
        raise HTTPException(404, "标注样本不存在")

    try:
        with _load_model(db, project, project.ai_model_name) as model:
            payload = _predict(model, sample, project, project.ai_model_name)
    except HTTPException:
        raise
    except Exception as error:
        logger.error(
            "AI prediction failed: project_id={}, sample_id={}, error={}",
            project_id,
            sample_id,
            type(error).__name__,
        )
        raise HTTPException(502, "AI 预标注失败，请检查权重与运行环境") from None
    annotation_id = _save_prediction(db, project, sample, payload, user.id)
    return AutoLabelResponse(
        status="COMPLETED",
        project_id=project.id,
        sample_id=sample.id,
        media_type=project.media_type,
        provider=project.ai_algorithm,
        model=project.ai_model_name,
        pre_annotation_id=annotation_id,
        latency_ms=payload["meta"]["latency_ms"],
        warning_message=payload["meta"]["warning_message"],
    )


async def create(
    db: Session, project_id: int, sample_id: int, current_user: User
) -> AutoLabelResponse:
    # 推理在线程中执行，保持页面 API 和批量进度查询可响应。
    """在线程中执行单张预标注，返回结果且不改变样本完成状态。"""
    return await asyncio.to_thread(_single, db, project_id, sample_id, current_user)


async def create_batch_job(
    db: Session, project_id: int, current_user: User
) -> AutoLabelJobResponse:
    """保存待标注样本的批次记录并启动后台处理，返回初始进度。"""
    project = _project(db, project_id, current_user)
    if not settings.USE_AUTO_LABEL or not project.ai_model_name:
        raise HTTPException(400, "请启用 AI 标注并在项目配置中选择模型")
    dataset_classes(json.loads(project.config))
    sample_ids = [
        sample.id
        for sample in crud_sample.list_new_samples(db=db, project_id=project_id)
    ]
    if not sample_ids:
        raise HTTPException(400, "没有待标注样本")

    with begin_transaction(db):
        job = crud_auto_label_job.create(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            sample_count=len(sample_ids),
            model_name=project.ai_model_name,
            algorithm=project.ai_algorithm,
        )
        job_id = job.id

    asyncio.get_running_loop().run_in_executor(None, _run_batch, job_id, sample_ids)
    return get_batch_job(db, project_id, job_id, current_user)


def get_batch_job(
    db: Session, project_id: int, job_id: int, user: User
) -> AutoLabelJobResponse:
    """验证项目及批次归属，返回当前批次进度。"""
    _project(db, project_id, user)
    job = crud_auto_label_job.get(db=db, job_id=job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(404, "AI 标注项目不存在")
    return AutoLabelJobResponse.model_validate(job, from_attributes=True)


def _run_batch(job_id: int, sample_ids: list[int]) -> None:
    """按批次快照加载一次模型，逐张保存结果并记录最终成功或失败状态。"""
    with SessionLocal() as db:
        job = crud_auto_label_job.get(db=db, job_id=job_id)
        if job is None:
            logger.warning("AI batch no longer exists: job_id={}", job_id)
            return

        try:
            # 1. 每批只加载一次权重，逐张推理并保存预标注。
            with begin_transaction(db):
                crud_auto_label_job.update_status(
                    db, job, AutoLabelStatus.PROCESSING.value
                )
            project = crud_project.get(db=db, project_id=job.project_id)
            if project is None:
                raise HTTPException(404, "标注项目已不存在")
            with _load_model(db, project, job.model_name, job.algorithm) as model:
                for sample_id in sample_ids:
                    sample = crud_sample.get(db=db, sample_id=sample_id)
                    if (
                        sample is None
                        or sample.project_id != project.id
                        or sample.state != SampleState.NEW.value
                        or sample.file is None
                    ):
                        with begin_transaction(db):
                            crud_auto_label_job.increment_progress(
                                db, job, success=False
                            )
                        continue
                    try:
                        payload = _predict(
                            model, sample, project, job.model_name, job.algorithm
                        )
                        _save_prediction(db, project, sample, payload, job.created_by)
                        success = True
                    except Exception as error:
                        db.rollback()
                        logger.error(
                            "AI prediction failed: job_id={}, sample_id={}, error={}",
                            job_id,
                            sample_id,
                            type(error).__name__,
                        )
                        success = False
                    with begin_transaction(db):
                        crud_auto_label_job.increment_progress(db, job, success=success)

            # 2. 部分失败也明确显示失败数量，已成功的预标注仍可人工检查。
            with begin_transaction(db):
                state = (
                    AutoLabelStatus.FAILED
                    if job.failed_count
                    else AutoLabelStatus.COMPLETED
                )
                message = (
                    f"{job.failed_count} 个样本预标注失败" if job.failed_count else None
                )
                crud_auto_label_job.update_status(
                    db, job, state.value, error_message=message
                )
        except Exception as error:
            db.rollback()
            logger.error(
                "AI batch failed: job_id={}, error={}", job_id, type(error).__name__
            )
            message = (
                error.detail
                if isinstance(error, HTTPException)
                else "AI 批量标注失败，请检查权重与运行环境"
            )
            with begin_transaction(db):
                crud_auto_label_job.update_status(
                    db, job, AutoLabelStatus.FAILED.value, error_message=message
                )


def fail_interrupted_jobs() -> None:
    """服务重启后把未完成的后台批次标为中断，不自动重跑模型。"""
    with SessionLocal() as db, db.begin():
        db.query(AutoLabelJob).filter(
            AutoLabelJob.status.in_(
                [AutoLabelStatus.PENDING.value, AutoLabelStatus.PROCESSING.value]
            )
        ).update(
            {
                AutoLabelJob.status: AutoLabelStatus.FAILED.value,
                AutoLabelJob.error_message: "服务重启，批量标注已中断，请重新发起",
            },
            synchronize_session=False,
        )
