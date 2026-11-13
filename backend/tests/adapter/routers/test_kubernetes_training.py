"""通过真实训练路由验证远端提交、暂停恢复、清理保护与启动重连。"""

import asyncio
import json
from unittest.mock import Mock

import pytest

from backend.application.service import training
from backend.common.db import begin_transaction
from backend.common.storage import get_storage
from backend.domain.models.training_run import TrainingRun
from backend.tests.conftest import TestingSessionLocal


@pytest.fixture
def remote(monkeypatch, tmp_path):
    kubeconfig = tmp_path / "fake-kubeconfig"
    kubeconfig.write_text("test placeholder")
    monkeypatch.setattr(training.settings, "KUBECONFIG", kubeconfig)
    monkeypatch.setattr(training.settings, "K8S_NAMESPACE", "training-test")
    monkeypatch.setattr(training.settings, "K8S_IMAGE", "example/train:gpu")
    monkeypatch.setattr(training.kubernetes.shutil, "which", lambda _: "fake-kubectl")
    # 远端路径不能要求本机安装 Ultralytics，也不能用本机框架校验远端参数。
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _: None)
    monkeypatch.setattr(
        training,
        "validate_training_options",
        Mock(side_effect=AssertionError("local validation")),
    )
    monkeypatch.setattr(training, "_schedule", lambda _: None)

    async def unexpected_command(*args, **kwargs):
        raise AssertionError("Router tests must not invoke a cluster CLI")

    monkeypatch.setattr(training.kubernetes, "_command", unexpected_command)


def test_remote_submit_pause_resume_without_local_training_runtime(
    client,
    testuser_token_headers,
    training_project,
    db,
    monkeypatch,
    remote,
):
    url = f"/api/v1/projects/{training_project}/training-runs"
    response = client.post(
        url, headers=testuser_token_headers, json={"extra_params": {"amp": False}}
    )
    assert response.status_code == 202, response.text
    run = response.json()["data"]
    run_id = run["id"]
    assert run["parameters"]["executor"] == "kubernetes"
    workspace = get_storage().path(f"projects/{training_project}/runs/{run_id}")
    state = json.loads((workspace / "kubernetes.json").read_text())
    assert state["namespace"] == "training-test"
    assert state["image"] == "example/train:gpu"
    with begin_transaction(db):
        db.get(TrainingRun, run_id).status = "RUNNING"
    monkeypatch.setattr(training.settings, "DEVICE", "0,1")
    assert (
        client.post(f"{url}/{run_id}/pause", headers=testuser_token_headers).status_code
        == 202
    )
    assert (workspace / "pause.request").is_file()
    with begin_transaction(db):
        db.get(TrainingRun, run_id).status = "PAUSED"
    (workspace / "resume.pt").write_bytes(b"checkpoint")
    state.update(stage="collected", context="original-context", deleted=True)
    training.kubernetes._save(workspace, state)
    # 后续修改默认 namespace 或关闭远端配置，不改变该记录恢复时的执行后端。
    monkeypatch.setattr(training.settings, "KUBECONFIG", None)
    monkeypatch.setattr(training.settings, "K8S_NAMESPACE", "different-default")
    resumed = client.post(f"{url}/{run_id}/resume", headers=testuser_token_headers)
    assert resumed.status_code == 202, resumed.text
    new_state = json.loads((workspace / "kubernetes.json").read_text())
    assert new_state["pod"] != state["pod"]
    assert new_state["context"] == "original-context"
    assert new_state["namespace"] == "training-test"
    assert (workspace / "resume.pt").read_bytes() == b"checkpoint"


def test_invalid_kubeconfig_does_not_allocate_run(
    client,
    testuser_token_headers,
    training_project,
    db,
    monkeypatch,
    remote,
    tmp_path,
):
    monkeypatch.setattr(training.settings, "KUBECONFIG", tmp_path / "does-not-exist")
    response = client.post(
        f"/api/v1/projects/{training_project}/training-runs",
        headers=testuser_token_headers,
        json={},
    )
    assert response.status_code == 503
    assert db.query(TrainingRun).count() == 0


def test_remote_worker_uses_pod_paths_and_updates_same_record(
    client,
    testuser_token_headers,
    training_project,
    db,
    monkeypatch,
    remote,
):
    url = f"/api/v1/projects/{training_project}/training-runs"
    response = client.post(url, headers=testuser_token_headers, json={"lr0": 0.001})
    run_id = response.json()["data"]["id"]

    async def execute(workspace, models, model, cache, args):
        assert model == "yolo26s.pt"
        assert args[args.index("--model") + 1] == "/workspace/initial.pt"
        assert args[args.index("--data") + 1] == "/workspace/run/dataset"
        assert args[args.index("--device") + 1] == "0"
        assert args[args.index("--lr0") + 1] == "0.001"
        models.mkdir(parents=True, exist_ok=True)
        (models / "result.pt").write_bytes(b"model")
        (workspace / "result.json").write_text(
            '{"run_id":"result","model_name":"result.pt","metrics":{"map":0.8}}'
        )
        return 0

    monkeypatch.setattr(training, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(training.kubernetes, "execute", execute)
    asyncio.run(training._run(run_id))
    db.expire_all()
    saved = db.get(TrainingRun, run_id)
    assert saved.status == "SUCCEEDED"
    result = client.get(f"{url}/{run_id}", headers=testuser_token_headers).json()[
        "data"
    ]
    assert result["model_available"] is True
    assert result["metrics"] == {"map": 0.8}


def test_restart_reconnects_only_active_remote_records(
    training_project, db, monkeypatch
):
    with begin_transaction(db):
        for executor, status in [
            ("local", "RUNNING"),
            ("kubernetes", "PAUSING"),
            ("kubernetes", "PAUSED"),
            ("kubernetes", "FAILED"),
        ]:
            db.add(
                TrainingRun(
                    project_id=training_project,
                    created_by=1,
                    initial_model="yolo26n.pt",
                    parameters=json.dumps({"executor": executor}),
                    status=status,
                )
            )
    monkeypatch.setattr(training, "SessionLocal", TestingSessionLocal)
    schedule = Mock()
    monkeypatch.setattr(training, "_schedule", schedule)
    training.fail_interrupted_runs()
    training.reconnect_remote_runs()
    db.expire_all()
    runs = db.query(TrainingRun).order_by(TrainingRun.id).all()
    assert [run.status for run in runs] == [
        "INTERRUPTED",
        "PAUSING",
        "PAUSED",
        "FAILED",
    ]
    schedule.assert_called_once_with(runs[1].id)


def test_remote_cleanup_failure_preserves_record_and_checkpoint(
    client,
    testuser_token_headers,
    training_project,
    db,
    monkeypatch,
    remote,
):
    url = f"/api/v1/projects/{training_project}/training-runs"
    run_id = client.post(url, headers=testuser_token_headers, json={}).json()["data"][
        "id"
    ]
    with begin_transaction(db):
        db.get(TrainingRun, run_id).status = "FAILED"
    workspace = get_storage().path(f"projects/{training_project}/runs/{run_id}")

    async def cleanup(_):
        raise training.kubernetes.KubernetesError("synthetic connection failure")

    monkeypatch.setattr(training.kubernetes, "cleanup", cleanup)
    assert (
        client.delete(f"{url}/{run_id}", headers=testuser_token_headers).status_code
        == 503
    )
    assert (
        client.delete(f"{url}/{run_id}/log", headers=testuser_token_headers).status_code
        == 503
    )
    assert (workspace / "dataset/data.yaml").is_file()
    assert db.get(TrainingRun, run_id) is not None


def test_shutdown_keeps_remote_job_active_for_reconnection(
    client,
    testuser_token_headers,
    training_project,
    db,
    monkeypatch,
    remote,
):
    url = f"/api/v1/projects/{training_project}/training-runs"
    run_id = client.post(url, headers=testuser_token_headers, json={}).json()["data"][
        "id"
    ]

    async def execute(*args):
        raise asyncio.CancelledError

    monkeypatch.setattr(training, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(training.kubernetes, "execute", execute)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(training._run(run_id))
    db.expire_all()
    assert db.get(TrainingRun, run_id).status == "RUNNING"
