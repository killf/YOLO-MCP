"""通过真实路由验证暂停、恢复、清理保护及原训练快照复用。"""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.application.service import training
from backend.common.db import begin_transaction
from backend.common.storage import get_storage
from backend.domain.models.training_run import TrainingRun
from backend.tests.conftest import TestingSessionLocal


def test_pause_resume_keeps_record_and_dataset(
    client, testuser_token_headers, training_project, db, monkeypatch
):
    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(training, "validate_training_options", Mock())
    headers = testuser_token_headers
    base = f"/api/v1/projects/{training_project}/training-runs"
    first = client.post(
        base,
        headers=headers,
        json={"training_scope": "head_then_full", "unfreeze_steps": 8},
    ).json()["data"]
    run_id = first["id"]
    url = f"{base}/{run_id}"
    workspace = get_storage().path(f"projects/{training_project}/runs/{run_id}")
    snapshot = {
        str(p.relative_to(workspace)): p.read_bytes()
        for p in (workspace / "dataset").rglob("*")
        if p.is_file()
    }
    assert client.post(url + "/pause", headers=headers).status_code == 409
    with begin_transaction(db):
        db.get(TrainingRun, run_id).status = "RUNNING"
    paused = client.post(url + "/pause", headers=headers)
    assert paused.status_code == 202
    assert paused.json()["data"]["status"] == "PAUSING"
    assert paused.json()["data"]["pause_available"] is False
    assert (workspace / "pause.request").is_file()
    assert client.post(url + "/pause", headers=headers).status_code == 409
    assert client.delete(url, headers=headers).status_code == 409
    assert client.post(base, headers=headers, json={}).status_code == 409

    with begin_transaction(db):
        db.get(TrainingRun, run_id).status = "PAUSED"
    assert client.post(url + "/resume", headers=headers).status_code == 409
    (workspace / "resume.pt").write_bytes(b"synthetic checkpoint")
    (workspace / "result.json").write_text('{"status":"PAUSED"}')
    assert client.delete(url + "/log", headers=headers).status_code == 409
    resumed = client.post(url + "/resume", headers=headers)
    assert resumed.status_code == 202, resumed.text
    assert resumed.json()["data"]["id"] == run_id
    assert resumed.json()["data"]["parameters"] == first["parameters"]
    assert not (workspace / "pause.request").exists()
    assert not (workspace / "result.json").exists()
    assert client.post(url + "/resume", headers=headers).status_code == 409
    assert client.get(base, headers=headers).json()["meta_data"]["total"] == 1
    assert all(
        (workspace / key).read_bytes() == value for key, value in snapshot.items()
    )


def test_restart_preserves_paused_runs(training_project, db, monkeypatch):
    statuses = ["PENDING", "RUNNING", "PAUSING", "PAUSED"]
    with begin_transaction(db):
        for status in statuses:
            db.add(
                TrainingRun(
                    project_id=training_project,
                    created_by=1,
                    initial_model="yolo26n.pt",
                    parameters="{}",
                    status=status,
                )
            )
    monkeypatch.setattr(training, "SessionLocal", TestingSessionLocal)
    training.fail_interrupted_runs()
    db.expire_all()
    assert [run.status for run in db.query(TrainingRun).order_by(TrainingRun.id)] == [
        "INTERRUPTED"
    ] * 3 + ["PAUSED"]


def test_multi_device_run_does_not_offer_pause(
    client, testuser_token_headers, training_project, db, monkeypatch
):
    with begin_transaction(db):
        run = TrainingRun(
            project_id=training_project,
            created_by=1,
            initial_model="yolo26n.pt",
            parameters="{}",
            status="RUNNING",
        )
        db.add(run)
        db.flush()
        run_id = run.id
    monkeypatch.setattr(training.settings, "DEVICE", "0,1")
    url = f"/api/v1/projects/{training_project}/training-runs/{run_id}"
    assert (
        client.get(url, headers=testuser_token_headers).json()["data"][
            "pause_available"
        ]
        is False
    )
    assert (
        client.post(url + "/pause", headers=testuser_token_headers).status_code == 409
    )


def test_worker_pauses_and_resumes_same_checkpoint(training_project, db, monkeypatch):
    with begin_transaction(db):
        run = TrainingRun(
            project_id=training_project,
            created_by=1,
            initial_model="yolo26n.pt",
            parameters=json.dumps({"epochs": 3, "imgsz": 64, "batch": 2}),
            status="PENDING",
        )
        db.add(run)
        db.flush()
        run_id = run.id
    workspace = get_storage().path(f"projects/{training_project}/runs/{run_id}")
    workspace.mkdir(parents=True)
    launches = []

    async def spawn(*args, **kwargs):
        launches.append(args)
        kwargs["stdout"].write(b"epoch log\n")
        result = Path(args[args.index("--result-file") + 1])
        if len(launches) == 1:
            (workspace / "resume.pt").write_bytes(b"checkpoint")
            result.write_text('{"status":"PAUSED"}')
            code = training.PAUSED_EXIT_CODE
        else:
            assert (
                Path(args[args.index("--resume-checkpoint") + 1])
                == workspace / "resume.pt"
            )
            result.write_text(
                '{"run_id":"resumed", "model_name":"resumed.pt", "metrics":{}}'
            )
            code = 0

        class Process:
            returncode = code

            async def wait(self):
                return code

        return Process()

    monkeypatch.setattr(training, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(training.asyncio, "create_subprocess_exec", spawn)
    asyncio.run(training._run(run_id))
    db.expire_all()
    assert db.get(TrainingRun, run_id).status == "PAUSED"
    assert db.get(TrainingRun, run_id).finished_at is None
    started_at = db.get(TrainingRun, run_id).started_at
    asyncio.run(training._run(run_id))
    db.expire_all()
    assert db.get(TrainingRun, run_id).status == "SUCCEEDED"
    assert db.get(TrainingRun, run_id).started_at == started_at
    assert (workspace / "console.log").read_bytes() == b"epoch log\nepoch log\n"


@pytest.mark.parametrize(
    "body",
    [
        {"training_scope": "head", "extra_params": {"freeze": 2}},
        {"training_scope": "head_then_full", "extra_params": {"compile": True}},
        {"unfreeze_steps": 0},
        {"training_scope": "unknown"},
    ],
)
def test_invalid_training_strategy_rejected(
    client, testuser_token_headers, training_project, body
):
    response = client.post(
        f"/api/v1/projects/{training_project}/training-runs",
        headers=testuser_token_headers,
        json=body,
    )
    assert response.status_code == 422
