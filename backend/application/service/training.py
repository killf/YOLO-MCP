"""在本机或 Kubernetes 中训练，统一保存状态、日志和模型产出。"""

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from fastapi import HTTPException
from loguru import logger
from sqlalchemy.orm import Session
from pydantic import ValidationError

from backend.adapter.persistence import crud_project
from backend.application.command.training import StartTrainingCommand
from backend.application.response.training import TrainingRunResponse
from backend.application.service.access import assert_project_access
from backend.application.service.dataset import create_run_dataset
from backend.common.config import settings
from backend.common.db import SessionLocal, begin_transaction
from backend.common.storage import get_storage
from backend.domain.models.sample import SampleState, ProjectSample
from backend.domain.models.project import Project
from backend.domain.models.training_run import TrainingRun, TrainingStatus
from backend.domain.models.auto_label_job import AutoLabelJob
from backend.domain.models.user import User
from backend.training.train import (
    OFFICIAL_MODELS,
    PAUSED_EXIT_CODE,
    training_parameter_catalog,
    validate_training_options,
)
from backend.training import kubernetes

_workers: set[asyncio.Task] = set()
ACTIVE_STATUSES = (
    TrainingStatus.PENDING.value,
    TrainingStatus.RUNNING.value,
    TrainingStatus.PAUSING.value,
)


def _project(db: Session, project_id: int, user: User) -> Project:
    project = crud_project.get(db, project_id)
    if project is None:
        raise HTTPException(404, "标注项目不存在")
    assert_project_access(project, user)
    return project


def _response(run: TrainingRun) -> TrainingRunResponse:
    return TrainingRunResponse(
        id=run.id,
        project_id=run.project_id,
        created_by=run.created_by,
        initial_model=run.initial_model,
        parameters=json.loads(run.parameters),
        status=run.status,
        run_id=run.run_id,
        model_name=run.model_name,
        model_available=bool(
            run.model_name
            and get_storage()
            .path(f"projects/{run.project_id}/models/{run.model_name}")
            .is_file()
        ),
        log_available=(_workspace(run.project_id, run.id) / "train.log").is_file(),
        pause_available=run.status == TrainingStatus.RUNNING.value
        and (
            json.loads(run.parameters).get("executor") == "kubernetes"
            or "," not in settings.DEVICE
        ),
        resume_available=(
            run.status == TrainingStatus.PAUSED.value
            and (_workspace(run.project_id, run.id) / "resume.pt").is_file()
            and (_workspace(run.project_id, run.id) / "dataset/data.yaml").is_file()
        ),
        metrics=json.loads(run.metrics or "{}"),
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


async def parameter_catalog(db: Session, project_id: int, user: User) -> list[dict]:
    """验证项目访问权，返回当前运行环境允许追加的参数和框架说明。"""
    _project(db, project_id, user)
    try:
        return await asyncio.to_thread(training_parameter_catalog)
    except (ImportError, OSError):
        if settings.KUBECONFIG:
            return []
        raise HTTPException(503, "当前训练环境无法提供参数说明") from None


def list_runs(
    db: Session, project_id: int, user: User, page: int, size: int
) -> tuple[list[TrainingRunResponse], int]:
    """验证项目访问权，按发起时间倒序返回训练记录与总数。"""
    _project(db, project_id, user)
    query = db.query(TrainingRun).filter(TrainingRun.project_id == project_id)
    return [
        _response(run)
        for run in query.order_by(TrainingRun.id.desc()).offset(page * size).limit(size)
    ], query.count()


def get_run(
    db: Session, project_id: int, run_id: int, user: User
) -> TrainingRunResponse:
    _project(db, project_id, user)
    run = db.get(TrainingRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(404, "训练记录不存在")
    return _response(run)


def model_file(db: Session, project_id: int, name: str, user: User) -> Path:
    """验证项目访问权，只允许下载该项目目录直属的模型文件。"""
    project = _project(db, project_id, user)
    if (
        PurePosixPath(name).name != name
        or PureWindowsPath(name).name != name
        or not name.endswith(".pt")
    ):
        raise HTTPException(422, "无效的模型文件名")
    directory = get_storage().path(f"{project.dataset_prefix}/models")
    file = get_storage().path(f"{project.dataset_prefix}/models/{name}")
    if not file.is_relative_to(directory) or not file.is_file():
        raise HTTPException(404, "模型文件不存在")
    return file


def _cleanup_run(
    db: Session, project_id: int, run_id: int, user: User
) -> tuple[Project, TrainingRun]:
    project = _project(db, project_id, user)
    if project.created_by != user.id and not user.is_admin:
        raise HTTPException(403, "只有项目创建者可以清理执行记录")
    run = db.get(TrainingRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(404, "训练记录不存在")
    if run.status in ACTIVE_STATUSES:
        raise HTTPException(409, "训练尚未结束，不能清理")
    return project, run


def _remove_logs(project_id: int, run_id: int) -> None:
    """只清理当前项目 runs/ 下的指定执行目录，不删除记录或模型目录。"""
    directory = _workspace(project_id, run_id)
    parent = get_storage().path(f"projects/{project_id}/runs")
    if not directory.is_relative_to(parent) or directory == parent:
        raise HTTPException(403, "无效的日志目录")
    if directory.exists():
        shutil.rmtree(directory)


async def clear_logs(db: Session, project_id: int, run_id: int, user: User) -> None:
    """清理日志和中间文件，保留数据库记录、指标与产出模型。"""
    _, run = _cleanup_run(db, project_id, run_id, user)
    if run.status == TrainingStatus.PAUSED.value:
        raise HTTPException(409, "暂停中的训练需要保留检查点；如需放弃训练，请删除记录")
    try:
        await kubernetes.cleanup(_workspace(project_id, run_id))
        _remove_logs(project_id, run_id)
    except (kubernetes.KubernetesError, TimeoutError):
        raise HTTPException(503, "远端 Pod 清理失败，本地记录和日志已保留") from None
    except OSError:
        raise HTTPException(500, "日志清理失败，请检查文件权限后重试") from None


async def delete_run(db: Session, project_id: int, run_id: int, user: User) -> None:
    """删除执行记录、产出模型和日志；被 AI 或其他训练引用的模型不能清理。"""
    project, run = _cleanup_run(db, project_id, run_id, user)
    model = None
    if run.model_name:
        referenced = project.ai_model_name == run.model_name
        referenced |= (
            db.query(TrainingRun)
            .filter(
                TrainingRun.project_id == project_id,
                TrainingRun.initial_model == run.model_name,
                TrainingRun.status.in_([*ACTIVE_STATUSES, TrainingStatus.PAUSED.value]),
            )
            .first()
            is not None
        )
        referenced |= (
            db.query(AutoLabelJob)
            .filter(
                AutoLabelJob.project_id == project_id,
                AutoLabelJob.model_name == run.model_name,
                AutoLabelJob.status.in_(["PENDING", "PROCESSING"]),
            )
            .first()
            is not None
        )
        if referenced:
            raise HTTPException(409, "模型正在使用，请先切换 AI 模型并等待相关项目结束")
        directory = get_storage().path(f"projects/{project_id}/models")
        model = get_storage().path(f"projects/{project_id}/models/{run.model_name}")
        if not model.is_relative_to(directory) or model == directory:
            raise HTTPException(403, "无效的模型路径")

    # 文件删除失败时回滚数据库记录，允许用户重试清理。
    try:
        await kubernetes.cleanup(_workspace(project_id, run_id))
        with begin_transaction(db):
            _remove_logs(project_id, run_id)
            if model is not None:
                model.unlink(missing_ok=True)
            db.delete(run)
    except (kubernetes.KubernetesError, TimeoutError):
        raise HTTPException(503, "远端 Pod 清理失败，本地记录和文件已保留") from None
    except OSError:
        raise HTTPException(500, "执行记录清理失败，请检查文件权限后重试") from None


def _workspace(project_id: int, run_id: int) -> Path:
    return get_storage().path(f"projects/{project_id}/runs/{run_id}")


def get_log(db: Session, project_id: int, run_id: int, user: User) -> str:
    """仅返回本项目训练日志的末尾 64 KiB，避免轮询读取无限增长的文件。"""
    get_run(db, project_id, run_id, user)
    path = _workspace(project_id, run_id) / "train.log"
    if not path.exists():
        return ""
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        content = stream.read().decode("utf-8", errors="replace")
    # 终端颜色与进度条控制符不适用于网页文本，原始文件仍保持不变。
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", content).replace("\r", "\n")


async def start(
    db: Session, project_id: int, cmd: StartTrainingCommand, user: User
) -> TrainingRunResponse:
    """检查完成样本和初始模型，冻结执行后端与数据后异步启动训练。"""
    # 1. 同一项目已有训练时明确返回状态；不创建GPU 预留记录。
    project = _project(db, project_id, user)
    try:
        cmd = StartTrainingCommand.model_validate(
            {**(project.training_config or {}), **cmd.model_dump(exclude_unset=True)}
        )
    except ValidationError as error:
        raise HTTPException(422, str(error)) from None
    active = (
        db.query(TrainingRun)
        .filter(
            TrainingRun.project_id == project_id,
            TrainingRun.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )
    if active is not None:
        raise HTTPException(409, "该项目已有训练正在进行，请查看训练记录")
    remote = settings.KUBECONFIG is not None
    if remote:
        try:
            kubernetes.validate_environment(settings.KUBECONFIG)
        except kubernetes.KubernetesError as error:
            raise HTTPException(503, str(error)) from None
    else:
        if importlib.util.find_spec("ultralytics") is None:
            raise HTTPException(503, "当前后端 Python 环境尚未安装训练依赖")
        try:
            await asyncio.to_thread(validate_training_options, cmd.extra_params)
        except ImportError:
            raise HTTPException(503, "当前后端 Python 环境无法加载训练依赖") from None
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from None
    if not project.config:
        raise HTTPException(422, "请先完成标注配置")
    splits = {
        split
        for (split,) in db.query(ProjectSample.split)
        .filter(
            ProjectSample.project_id == project_id,
            ProjectSample.deleted_at.is_(None),
            ProjectSample.state == SampleState.DONE.value,
        )
        .distinct()
    }
    if not {"train", "test"}.issubset(splits):
        raise HTTPException(422, "训练集和测试集都需要至少一张已完成标注的图片")
    storage = get_storage()
    if (
        cmd.initial_model not in OFFICIAL_MODELS
        and cmd.initial_model
        not in storage.list_models(f"{project.dataset_prefix}/models/")
    ):
        raise HTTPException(422, "请选择官方 YOLO26 权重或当前项目已有模型")

    # 2. 分配记录 ID 后冻结输入；失败时回滚记录，仅清理本次新建的目录。
    workspace_created = False
    try:
        with begin_transaction(db):
            run = TrainingRun(
                project_id=project_id,
                created_by=user.id,
                initial_model=cmd.initial_model,
                parameters=json.dumps(
                    {
                        **cmd.model_dump(),
                        **({"executor": "kubernetes"} if remote else {}),
                    }
                ),
                status=TrainingStatus.PENDING.value,
            )
            db.add(run)
            db.flush()
            run_id = run.id
            _workspace(project_id, run_id).mkdir(parents=True, exist_ok=False)
            workspace_created = True
            create_run_dataset(db, project, _workspace(project_id, run_id) / "dataset")
            if remote:
                kubernetes.prepare(
                    _workspace(project_id, run_id),
                    settings.KUBECONFIG,
                    settings.K8S_NAMESPACE,
                    settings.K8S_IMAGE,
                    vci_instance_family=settings.K8S_VCI_INSTANCE_FAMILY,
                    vci_gpu_driver_version=settings.K8S_VCI_GPU_DRIVER_VERSION,
                    vci_zone=settings.K8S_VCI_ZONE,
                )
    except Exception as error:
        if workspace_created:
            try:
                _remove_logs(project_id, run_id)
            except OSError:
                logger.error("Run dataset cleanup failed: run_id={}", run_id)
        if isinstance(error, OSError):
            raise HTTPException(500, "训练目录创建失败，请检查本地文件后重试") from None
        raise
    response = _response(run)
    _schedule(run_id)
    return response


def _schedule(run_id: int) -> None:
    worker = asyncio.create_task(_run(run_id))
    _workers.add(worker)
    worker.add_done_callback(_workers.discard)


def pause(db: Session, project_id: int, run_id: int, user: User) -> TrainingRunResponse:
    """请求训练在下一个 epoch 检查点写入后退出，当前 epoch 继续运行。"""
    response = get_run(db, project_id, run_id, user)
    if not response.pause_available:
        raise HTTPException(409, "只有单设备上运行中的训练可以暂停")
    request = _workspace(project_id, run_id) / "pause.request"
    try:
        with begin_transaction(db):
            changed = (
                db.query(TrainingRun)
                .filter(
                    TrainingRun.id == run_id,
                    TrainingRun.status == TrainingStatus.RUNNING.value,
                )
                .update({TrainingRun.status: TrainingStatus.PAUSING.value})
            )
            if not changed:
                raise HTTPException(409, "只有运行中的训练可以暂停")
            request.touch()
    except OSError:
        raise HTTPException(500, "无法写入暂停请求，请检查运行目录后重试") from None
    db.expire_all()
    return _response(db.get(TrainingRun, run_id))


async def resume(
    db: Session, project_id: int, run_id: int, user: User
) -> TrainingRunResponse:
    """复用原记录、参数和数据快照，从暂停检查点恢复。"""
    response = get_run(db, project_id, run_id, user)
    if not response.resume_available:
        raise HTTPException(409, "训练未暂停或检查点已丢失，无法继续")
    remote = response.parameters.get("executor") == "kubernetes"
    if not remote and importlib.util.find_spec("ultralytics") is None:
        raise HTTPException(503, "当前后端 Python 环境尚未安装训练依赖")
    active = (
        db.query(TrainingRun)
        .filter(
            TrainingRun.project_id == project_id,
            TrainingRun.status.in_(ACTIVE_STATUSES),
        )
        .first()
    )
    if active is not None:
        raise HTTPException(409, "该项目已有训练正在进行，请先暂停或等待完成")
    workspace = _workspace(project_id, run_id)
    try:
        if remote:
            await kubernetes.cleanup(workspace)
        with begin_transaction(db):
            changed = (
                db.query(TrainingRun)
                .filter(
                    TrainingRun.id == run_id,
                    TrainingRun.status == TrainingStatus.PAUSED.value,
                )
                .update(
                    {
                        TrainingRun.status: TrainingStatus.PENDING.value,
                        TrainingRun.error_message: None,
                        TrainingRun.finished_at: None,
                    }
                )
            )
            if not changed:
                raise HTTPException(409, "训练状态已变化，请刷新记录")
            if remote:
                kubernetes.prepare_resume(workspace)
            (workspace / "pause.request").unlink(missing_ok=True)
            (workspace / "result.json").unlink(missing_ok=True)
    except kubernetes.KubernetesError as error:
        raise HTTPException(503, str(error)) from None
    except TimeoutError:
        raise HTTPException(503, "远端 Pod 清理超时，检查点已保留") from None
    except OSError:
        raise HTTPException(500, "无法准备恢复训练，请检查运行目录后重试") from None
    db.expire_all()
    response = _response(db.get(TrainingRun, run_id))
    _schedule(run_id)
    return response


async def _run(run_id: int) -> None:
    """准备工作目录并执行本机或远端训练，保存退出状态和结构化模型产物。"""
    process = None
    remote = False
    with SessionLocal() as db:
        run = db.get(TrainingRun, run_id)
        if run is None:
            return
        try:
            # 1. 项目模型使用本地文件，官方权重由训练进程下载到公共缓存。
            project = crud_project.get(db, run.project_id)
            if project is None:
                raise RuntimeError("标注项目已不存在")
            workspace = _workspace(run.project_id, run_id)
            workspace.mkdir(parents=True, exist_ok=True)
            model = run.initial_model
            if run.initial_model not in OFFICIAL_MODELS:
                model = get_storage().path(
                    f"{project.dataset_prefix}/models/{run.initial_model}"
                )
            parameters = json.loads(run.parameters)
            remote = parameters.get("executor") == "kubernetes"
            checkpoint = workspace / "resume.pt"
            resuming = checkpoint.is_file()
            prefix = project.dataset_prefix
            with begin_transaction(db):
                if run.status != TrainingStatus.PAUSING.value:
                    run.status = TrainingStatus.RUNNING.value
                if run.started_at is None:
                    run.started_at = datetime.now()

            # 2. 参数通过数组传入独立进程，不经过 shell，不接收任意用户命令。
            training_workspace = (
                PurePosixPath("/workspace/run") if remote else workspace
            )
            models_directory = (
                PurePosixPath("/workspace/models")
                if remote
                else get_storage().path(f"{prefix}/models")
            )
            args = [
                "python" if remote else sys.executable,
                "-m",
                "backend.training.train",
                "--data",
                str(training_workspace / "dataset"),
                "--models-dir",
                str(models_directory),
                "--work-dir",
                str(training_workspace),
                "--result-file",
                str(training_workspace / "result.json"),
                "--model",
                "/workspace/initial.pt" if remote else str(model),
                "--epochs",
                str(parameters["epochs"]),
                "--imgsz",
                str(parameters["imgsz"]),
                "--batch",
                str(parameters["batch"]),
                "--workers",
                "0",
            ]
            if remote:
                args.extend(["--device", "0"])
            elif settings.DEVICE:
                args.extend(["--device", settings.DEVICE])
            args.extend(
                [
                    (
                        "--augmentation"
                        if parameters.get("augmentation", True)
                        else "--no-augmentation"
                    ),
                    "--training-scope",
                    parameters.get("training_scope", "full"),
                    "--unfreeze-steps",
                    str(parameters.get("unfreeze_steps", 100)),
                ]
            )
            if resuming:
                args.extend(
                    ["--resume-checkpoint", str(training_workspace / "resume.pt")]
                )
            if parameters.get("lr0") is not None:
                args.extend(["--lr0", str(parameters["lr0"])])
            if parameters.get("extra_params"):
                args.extend(
                    [
                        "--extra-params",
                        json.dumps(parameters["extra_params"], allow_nan=False),
                    ]
                )
            args.append("--log-to-stdout")
            if remote:
                code = await kubernetes.execute(
                    workspace,
                    get_storage().path(f"{prefix}/models"),
                    str(model),
                    get_storage().path("models/ultralytics"),
                    args,
                )
            else:
                environment = os.environ.copy()
                environment.update(
                    {
                        "YOLO_AUTOINSTALL": "false",
                        "PYTHONUNBUFFERED": "1",
                        "PYTHONIOENCODING": "utf-8",
                        "YOLO_CONFIG_DIR": str(get_storage().path(".ultralytics")),
                    }
                )
                with (workspace / "train.log").open(
                    "ab" if resuming else "wb"
                ) as output:
                    process = await asyncio.create_subprocess_exec(
                        *args,
                        cwd=str(Path(__file__).resolve().parents[3]),
                        env=environment,
                        stdout=output,
                        stderr=asyncio.subprocess.STDOUT,
                    )
                    code = await process.wait()

            # 3. 只有训练退出成功且结果文件可读时，记录模型与指标。
            with begin_transaction(db):
                if code == 0:
                    result = json.loads(
                        (workspace / "result.json").read_text(encoding="utf-8")
                    )
                    run.status = TrainingStatus.SUCCEEDED.value
                    run.run_id = result["run_id"]
                    run.model_name = result["model_name"]
                    run.metrics = json.dumps(result["metrics"])
                elif code == PAUSED_EXIT_CODE and checkpoint.is_file():
                    run.status = TrainingStatus.PAUSED.value
                    run.error_message = None
                else:
                    run.status = TrainingStatus.FAILED.value
                    run.error_message = f"训练进程退出码为 {code}，请查看训练日志"
                    result_file = workspace / "result.json"
                    if result_file.is_file():
                        result = json.loads(result_file.read_text(encoding="utf-8"))
                        run.error_message = (
                            result.get("error_message") or run.error_message
                        )
                run.finished_at = (
                    None
                    if run.status == TrainingStatus.PAUSED.value
                    else datetime.now()
                )
        except asyncio.CancelledError:
            if remote:
                # 远端训练独立运行；保留活动状态，服务启动后只恢复监控和回收。
                raise
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()
            with begin_transaction(db):
                run.status = TrainingStatus.INTERRUPTED.value
                run.error_message = "服务关闭，训练已中断"
                run.finished_at = datetime.now()
            raise
        except Exception as error:
            logger.error(
                "Training failed: run_id={}, error={}", run_id, type(error).__name__
            )
            if isinstance(error, kubernetes.KubernetesError):
                message = str(error)
            elif remote:
                message = "远端执行或传输失败，请检查连接、Pod 状态与训练日志"
            else:
                message = "训练执行失败，请查看训练日志与运行环境"
            with begin_transaction(db):
                run.status = TrainingStatus.FAILED.value
                run.error_message = message
                run.finished_at = datetime.now()


def fail_interrupted_runs() -> None:
    """启动时标记本地中断任务，远端活动任务保留状态等待重新连接。"""
    with SessionLocal() as db, db.begin():
        runs = (
            db.query(TrainingRun)
            .filter(
                TrainingRun.status.in_(
                    [
                        TrainingStatus.PENDING.value,
                        TrainingStatus.RUNNING.value,
                        TrainingStatus.PAUSING.value,
                    ]
                )
            )
            .all()
        )
        for run in runs:
            if json.loads(run.parameters).get("executor") == "kubernetes":
                continue
            run.status = TrainingStatus.INTERRUPTED.value
            run.error_message = "服务重启，训练状态已中断，请确认后重新发起"
            run.finished_at = datetime.now()


def reconnect_remote_runs() -> None:
    """仅调度已有活动远端记录的监控，不创建新的训练记录或自动重跑失败任务。"""
    with SessionLocal() as db:
        for run in db.query(TrainingRun).filter(
            TrainingRun.status.in_(ACTIVE_STATUSES)
        ):
            if json.loads(run.parameters).get("executor") == "kubernetes":
                _schedule(run.id)


async def stop_workers() -> None:
    """服务关闭时终止本地训练及远端监控，保留 Pod，等待本地状态写入完成。"""
    workers = list(_workers)
    for worker in workers:
        worker.cancel()
    if workers:
        await asyncio.gather(*workers, return_exceptions=True)
