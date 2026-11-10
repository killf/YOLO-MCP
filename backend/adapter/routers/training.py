from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from backend.application.command.training import StartTrainingCommand
from backend.application.response.base import (
    CommonDataResp,
    MetaData,
    OkResp,
    OkRespWithMeta,
)
from backend.application.response.training import (
    TrainingParameterResponse,
    TrainingRunResponse,
)
from backend.application.service import training as service
from backend.common.db import get_db
from backend.dependencies.user import get_current_user
from backend.domain.models.user import User

router = APIRouter(prefix="/projects/{project_id}/training-runs", tags=["training"])


@router.get("/parameters", response_model=OkResp[list[TrainingParameterResponse]])
async def parameter_catalog(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OkResp[list[TrainingParameterResponse]](
        data=await service.parameter_catalog(db, project_id, user)
    )


@router.post("", response_model=OkResp[TrainingRunResponse], status_code=202)
async def start(
    project_id: int,
    cmd: StartTrainingCommand,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OkResp[TrainingRunResponse](
        data=await service.start(db, project_id, cmd, user)
    )


@router.get("", response_model=OkRespWithMeta[list[TrainingRunResponse]])
async def list_runs(
    project_id: int,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runs, total = service.list_runs(db, project_id, user, page, size)
    return OkRespWithMeta[list[TrainingRunResponse]](
        data=runs, meta_data=MetaData(total=total, page=page, size=len(runs))
    )


@router.get("/{run_id}", response_model=OkResp[TrainingRunResponse])
async def get_run(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OkResp[TrainingRunResponse](
        data=service.get_run(db, project_id, run_id, user)
    )


@router.get("/{run_id}/log", response_class=PlainTextResponse)
async def get_log(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return PlainTextResponse(service.get_log(db, project_id, run_id, user))


@router.post(
    "/{run_id}/pause", response_model=OkResp[TrainingRunResponse], status_code=202
)
async def pause(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OkResp[TrainingRunResponse](data=service.pause(db, project_id, run_id, user))


@router.post(
    "/{run_id}/resume", response_model=OkResp[TrainingRunResponse], status_code=202
)
async def resume(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return OkResp[TrainingRunResponse](
        data=await service.resume(db, project_id, run_id, user)
    )


@router.delete("/{run_id}/log", response_model=OkResp[CommonDataResp])
async def clear_logs(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service.clear_logs(db, project_id, run_id, user)
    return OkResp[CommonDataResp](data=CommonDataResp(ok=True))


@router.delete("/{run_id}", response_model=OkResp[CommonDataResp])
async def delete_run(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service.delete_run(db, project_id, run_id, user)
    return OkResp[CommonDataResp](data=CommonDataResp(ok=True))
