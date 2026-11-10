import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from backend.application.service import training
from backend.application.service import dataset
from backend.common.db import begin_transaction
from backend.common.storage import get_storage
from backend.domain.models.project import Project
from backend.domain.models.training_run import TrainingRun
from backend.tests.conftest import TestingSessionLocal


def test_project_initializes_fixed_directories(client, testuser_token_headers):
    response = client.post(
        "/api/v1/projects",
        headers=testuser_token_headers,
        json={"name": "Automatic directory", "media_type": "IMAGE"},
    )
    assert response.status_code == 201
    project = response.json()["data"]
    assert project["dataset_prefix"] == f"projects/{project['id']}"
    assert "dataset_data_source_id" not in project
    storage = get_storage()
    for directory in ["", "images/", "thumbnails/", "models/", "runs/"]:
        assert storage.path(f"projects/{project['id']}/{directory}").is_dir()
    assert not storage.path(f"projects/{project['id']}/uploads").exists()
    assert not storage.path(f"projects/{project['id']}/labels").exists()
    client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=testuser_token_headers,
        json={"name": "Renamed"},
    )
    assert (
        client.get(
            f"/api/v1/projects/{project['id']}", headers=testuser_token_headers
        ).json()["data"]["dataset_prefix"]
        == project["dataset_prefix"]
    )


def test_failed_directory_creation_rolls_back_project(
    client, testuser_token_headers, db, monkeypatch
):
    storage = get_storage()
    original_mkdir = Path.mkdir

    def fail_images(path, *args, **kwargs):
        if path.name == "images":
            raise OSError("test disk failure")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_images)
    response = client.post(
        "/api/v1/projects",
        headers=testuser_token_headers,
        json={"name": "Must not remain", "media_type": "IMAGE"},
    )
    assert response.status_code == 500
    db.expire_all()
    assert db.query(Project).filter(Project.name == "Must not remain").count() == 0
    assert not storage.path("projects/1/").exists()


def test_removed_import_routes_and_val_split(
    client, testuser_token_headers, training_project
):
    paths = client.get("/openapi.json").json()["paths"]
    assert not any(
        "datasources" in path or "import_s3" in path or "pre_annotations/files" in path
        for path in paths
    )
    assert "post" not in paths["/api/v1/projects/{project_id}/pre_annotations"]
    response = client.patch(
        f"/api/v1/projects/{training_project}/samples/1",
        headers=testuser_token_headers,
        json={"split": "val"},
    )
    assert response.status_code == 422
    response = client.post(
        f"/api/v1/projects/{training_project}/attachments",
        headers=testuser_token_headers,
        files={"file": ("annotations.json", b"{}", "application/json")},
    )
    assert response.status_code == 422
    response = client.post(
        f"/api/v1/projects/{training_project}/attachments",
        headers=testuser_token_headers,
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    assert response.status_code == 422


def test_training_queue_and_duplicate_start(
    client, testuser_token_headers, training_project, monkeypatch
):
    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    url = f"/api/v1/projects/{training_project}/training-runs"
    response = client.post(
        url,
        headers=testuser_token_headers,
        json={"initial_model": "yolo26n.pt", "epochs": 2, "imgsz": 640, "batch": 2},
    )
    assert response.status_code == 202
    run = response.json()["data"]
    assert run["status"] == "PENDING" and run["parameters"]["epochs"] == 2
    assert client.post(url, headers=testuser_token_headers, json={}).status_code == 409
    listing = client.get(url, headers=testuser_token_headers).json()
    assert listing["meta_data"]["total"] == 1
    assert (
        client.get(f"{url}/{run['id']}/log", headers=testuser_token_headers).text == ""
    )


def test_collaborator_can_train_but_cannot_clean_records(
    client, testuser_token_headers, admin_token_headers, training_project, monkeypatch
):
    """协作者允许启动和读取训练，日志与模型删除仍限拥有者或管理员。"""
    from uuid import uuid4

    credentials = {
        "username": f"train-{uuid4().hex}@example.com",
        "password": "Train-test-123",
    }
    user = client.post(
        "/api/v1/users", headers=admin_token_headers, json=credentials
    ).json()["data"]
    token = client.post("/api/v1/users/login", json=credentials).json()["data"]["token"]
    headers = {"Authorization": token}
    base = f"/api/v1/projects/{training_project}"
    assert (
        client.post(
            f"{base}/collaborators",
            headers=testuser_token_headers,
            json={"user_id": user["id"]},
        ).status_code
        == 201
    )

    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(training, "validate_training_options", Mock())
    response = client.post(f"{base}/training-runs", headers=headers, json={})
    assert response.status_code == 202, response.text
    run_id = response.json()["data"]["id"]
    assert (
        client.get(f"{base}/training-runs/{run_id}", headers=headers).status_code == 200
    )
    assert (
        client.delete(f"{base}/training-runs/{run_id}/log", headers=headers).status_code
        == 403
    )
    assert (
        client.delete(f"{base}/training-runs/{run_id}", headers=headers).status_code
        == 403
    )


def test_each_run_freezes_current_annotation_classes_and_split(
    client, testuser_token_headers, training_project, monkeypatch, db
):
    """两次训练读取各自输入；修改或删除原始样本不会改变先前快照。"""

    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(training, "validate_training_options", Mock())
    headers = testuser_token_headers
    base = f"/api/v1/projects/{training_project}"
    first = client.post(f"{base}/training-runs", headers=headers, json={})
    assert first.status_code == 202
    first_id = first.json()["data"]["id"]
    root = get_storage().path(f"projects/{training_project}")
    first_dir = root / f"runs/{first_id}/dataset"
    frozen = {
        p.relative_to(first_dir): p.read_bytes()
        for p in first_dir.rglob("*")
        if p.is_file()
    }
    assert (first_dir / "train.txt").read_text() == "./images/1.png\n"
    assert (first_dir / "test.txt").read_text() == "./images/2.png\n"

    with begin_transaction(db):
        db.get(TrainingRun, first_id).status = "SUCCEEDED"
    config = {
        "tools": [
            {
                "tool": "rectTool",
                "config": {
                    "attributes": [
                        {"key": "Unused", "value": "unused"},
                        {"key": "Person", "value": "person"},
                    ]
                },
            }
        ]
    }
    assert (
        client.patch(
            base, headers=headers, json={"config": json.dumps(config)}
        ).status_code
        == 200
    )
    for sample_id, split in ((1, "test"), (2, "train")):
        assert (
            client.patch(
                f"{base}/samples/{sample_id}", headers=headers, json={"split": split}
            ).status_code
            == 200
        )
    assert (
        client.patch(
            f"{base}/samples/1",
            headers=headers,
            json={
                "data": {
                    "result": json.dumps(
                        {
                            "rectTool": {
                                "result": [
                                    {
                                        "x": 2,
                                        "y": 2,
                                        "width": 4,
                                        "height": 4,
                                        "label": "person",
                                    }
                                ]
                            }
                        }
                    )
                },
                "annotated_count": 1,
            },
        ).status_code
        == 200
    )
    second = client.post(f"{base}/training-runs", headers=headers, json={})
    assert second.status_code == 202
    second_dir = root / f"runs/{second.json()['data']['id']}/dataset"
    assert (second_dir / "train.txt").read_text() == "./images/2.png\n"
    assert (second_dir / "test.txt").read_text() == "./images/1.png\n"
    assert yaml.safe_load((second_dir / "data.yaml").read_text())["names"] == [
        "Unused",
        "Person",
    ]
    assert (second_dir / "labels/1.txt").read_text().startswith("1 0.40000000")
    assert (first_dir / "labels/1.txt").read_text().startswith("0 0.25000000")
    assert (
        client.request(
            "DELETE", f"{base}/samples", headers=headers, json={"sample_ids": [1]}
        ).status_code
        == 200
    )
    assert not (root / "images/train.png").exists()
    assert (second_dir / "images/1.png").is_file()
    assert frozen == {
        p.relative_to(first_dir): p.read_bytes()
        for p in first_dir.rglob("*")
        if p.is_file()
    }
    assert not any(
        (root / name).exists()
        for name in ("train.txt", "test.txt", "data.yaml", "labels", "uploads")
    )


def test_snapshot_failure_rolls_back_run_and_allows_retry(
    client, testuser_token_headers, training_project, monkeypatch, db
):
    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(training, "validate_training_options", Mock())
    render = dataset.render_sample
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("test disk failure")
        return render(*args, **kwargs)

    url = f"/api/v1/projects/{training_project}/training-runs"
    with monkeypatch.context() as patch:
        patch.setattr(dataset, "render_sample", fail_second)
        assert (
            client.post(url, headers=testuser_token_headers, json={}).status_code == 500
        )
    db.expire_all()
    assert db.query(TrainingRun).count() == 0
    root = get_storage().path(f"projects/{training_project}")
    assert not list((root / "runs").iterdir())
    assert (root / "images/train.png").is_file()
    retry = client.post(url, headers=testuser_token_headers, json={})
    assert retry.status_code == 202
    assert (root / f"runs/{retry.json()['data']['id']}/dataset/data.yaml").is_file()


@pytest.mark.parametrize(
    "body",
    [
        {"initial_model": "../outside.pt"},
        {"initial_model": "https://example.com/model.pt"},
        {"batch": 0},
        {"epochs": 0},
        {"imgsz": 641},
        {"command": "not allowed"},
        {"algorithm": "yolo11_detect"},
        {"extra_params": []},
        {"extra_params": None},
        {"extra_params": {"epochs": 2}},
        {"extra_params": {"data": "outside"}},
        {"extra_params": {"models_dir": "outside"}},
        {"extra_params": {"save": False}},
    ],
)
def test_training_rejects_invalid_parameters(
    client, testuser_token_headers, training_project, body
):
    response = client.post(
        f"/api/v1/projects/{training_project}/training-runs",
        headers=testuser_token_headers,
        json=body,
    )
    assert response.status_code == 422


def test_training_records_require_project_access(
    client, testuser_token_headers, training_project, db
):
    from backend.domain.models.user import User

    with begin_transaction(db):
        user = User(username="other-training@example.com", hashed_password="test-only")
        db.add(user)
        db.flush()
        db.get(Project, training_project).created_by = user.id
    for tail in ["", "/1", "/1/log"]:
        assert (
            client.get(
                f"/api/v1/projects/{training_project}/training-runs{tail}",
                headers=testuser_token_headers,
            ).status_code
            == 403
        )
    for action in ["pause", "resume"]:
        assert (
            client.post(
                f"/api/v1/projects/{training_project}/training-runs/1/{action}",
                headers=testuser_token_headers,
            ).status_code
            == 403
        )


@pytest.mark.parametrize("exit_code,expected", [(0, "SUCCEEDED"), (1, "FAILED")])
@pytest.mark.parametrize("extra_params", [{}, {"lr0": 0.001, "amp": False}])
@pytest.mark.parametrize("lr0", [None, 0.003])
def test_worker_records_process_result(
    training_project, db, monkeypatch, tmp_path, exit_code, expected, extra_params, lr0
):
    with begin_transaction(db):
        project = db.get(Project, training_project)
        run = TrainingRun(
            project_id=training_project,
            created_by=project.created_by,
            initial_model="yolo26n.pt",
            parameters=json.dumps(
                {
                    "epochs": 2,
                    "imgsz": 640,
                    "batch": 2,
                    **({"lr0": lr0} if lr0 is not None else {}),
                    **({"extra_params": extra_params} if extra_params else {}),
                }
            ),
            status="PENDING",
        )
        db.add(run)
        db.flush()
        run_id = run.id
    captured = {}

    class Process:
        returncode = exit_code

        async def wait(self):
            return exit_code

    async def spawn(*args, **kwargs):
        captured["args"] = args
        assert "shell" not in kwargs
        assert Path(kwargs["env"]["YOLO_CONFIG_DIR"]) == get_storage().path(
            ".ultralytics"
        )
        assert Path(args[args.index("--data") + 1]) == tmp_path / "dataset"
        assert Path(args[args.index("--models-dir") + 1]) == get_storage().path(
            f"projects/{training_project}/models"
        )
        assert args[args.index("--model") + 1] == "yolo26n.pt"
        result = Path(args[args.index("--result-file") + 1])
        if exit_code == 0:
            result.write_text(
                json.dumps(
                    {
                        "run_id": "20261107-1",
                        "model_name": "20261107-1.pt",
                        "metrics": {"metrics/mAP50(B)": 0.5},
                    }
                )
            )
        else:
            result.write_text(
                json.dumps(
                    {"error_message": "模型 yolo26n.pt 权重下载失败，请检查网络"}
                ),
                encoding="utf-8",
            )
        return Process()

    monkeypatch.setattr(training, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(training, "_workspace", lambda *_: tmp_path)
    monkeypatch.setattr(training.asyncio, "create_subprocess_exec", spawn)
    asyncio.run(training._run(run_id))
    db.expire_all()
    saved = db.get(TrainingRun, run_id)
    assert saved.status == expected and saved.finished_at is not None
    assert "--workers" in captured["args"]
    if lr0 is not None:
        assert float(captured["args"][captured["args"].index("--lr0") + 1]) == lr0
    if extra_params:
        arguments = captured["args"]
        assert (
            json.loads(arguments[arguments.index("--extra-params") + 1]) == extra_params
        )
    else:
        assert "--extra-params" not in captured["args"]
    if exit_code == 0:
        assert saved.model_name == "20261107-1.pt"
        assert json.loads(saved.metrics)["metrics/mAP50(B)"] == 0.5
    else:
        assert saved.model_name is None
        assert saved.error_message == "模型 yolo26n.pt 权重下载失败，请检查网络"


def test_custom_training_parameters_are_saved_and_returned(
    client, testuser_token_headers, training_project, monkeypatch
):
    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    validate = Mock()
    monkeypatch.setattr(training, "validate_training_options", validate)
    parameters = {"lr0": 0.001, "amp": False, "seed": 7}
    url = f"/api/v1/projects/{training_project}/training-runs"
    response = client.post(
        url, headers=testuser_token_headers, json={"extra_params": parameters}
    )
    assert response.status_code == 202
    record = response.json()["data"]
    assert record["parameters"]["extra_params"] == parameters
    validate.assert_called_once_with(parameters)
    detail = client.get(f"{url}/{record['id']}", headers=testuser_token_headers)
    assert detail.json()["data"]["parameters"]["extra_params"] == parameters


def test_invalid_framework_options_do_not_create_a_run(
    client, testuser_token_headers, training_project, monkeypatch, db
):
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(
        training,
        "validate_training_options",
        Mock(side_effect=ValueError("未知训练参数：typo")),
    )
    response = client.post(
        f"/api/v1/projects/{training_project}/training-runs",
        headers=testuser_token_headers,
        json={"extra_params": {"typo": 1}},
    )
    assert response.status_code == 422
    db.expire_all()
    assert db.query(TrainingRun).count() == 0


def test_parameter_catalog_requires_project_access(
    client, testuser_token_headers, training_project, monkeypatch, db
):
    from backend.domain.models.user import User

    catalog = Mock(
        return_value=[{"name": "lr0", "default": 0.01, "description": "初始学习率"}]
    )
    monkeypatch.setattr(training, "training_parameter_catalog", catalog)
    url = f"/api/v1/projects/{training_project}/training-runs/parameters"
    response = client.get(url, headers=testuser_token_headers)
    assert response.status_code == 200
    assert response.json()["data"][0]["name"] == "lr0"
    catalog.assert_called_once_with()
    assert client.get(url).status_code == 401
    with begin_transaction(db):
        user = User(username="catalog-other@example.com", hashed_password="test-only")
        db.add(user)
        db.flush()
        db.get(Project, training_project).created_by = user.id
    assert client.get(url, headers=testuser_token_headers).status_code == 403
    assert catalog.call_count == 1


def test_parameter_catalog_handles_unavailable_runtime(
    client, testuser_token_headers, training_project, monkeypatch
):
    monkeypatch.setattr(
        training, "training_parameter_catalog", Mock(side_effect=ImportError)
    )
    response = client.get(
        f"/api/v1/projects/{training_project}/training-runs/parameters",
        headers=testuser_token_headers,
    )
    assert response.status_code == 503


def test_project_training_defaults_are_returned_and_applied_with_request_override(
    client, testuser_token_headers, training_project, monkeypatch
):
    async def pending(_run_id):
        return

    monkeypatch.setattr(training, "_run", pending)
    monkeypatch.setattr(training.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(training, "validate_training_options", Mock())
    url = f"/api/v1/projects/{training_project}"
    defaults = {
        "initial_model": "yolo26n.pt",
        "epochs": 23,
        "lr0": 0.003,
        "augmentation": False,
        "training_scope": "head_then_full",
        "unfreeze_steps": 8,
        "extra_params": {"optimizer": "AdamW", "amp": False},
    }
    saved = client.patch(
        url, headers=testuser_token_headers, json={"training_config": defaults}
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["data"]["training_config"]["lr0"] == 0.003
    loaded = client.get(url, headers=testuser_token_headers).json()["data"]
    assert loaded["training_config"]["epochs"] == 23
    result = client.post(
        url + "/training-runs", headers=testuser_token_headers, json={"epochs": 2}
    )
    assert result.status_code == 202, result.text
    parameters = result.json()["data"]["parameters"]
    assert parameters["initial_model"] == "yolo26n.pt"
    assert parameters["epochs"] == 2 and parameters["lr0"] == 0.003
    assert parameters["extra_params"] == defaults["extra_params"]
    assert parameters["augmentation"] is False
    assert parameters["training_scope"] == "head_then_full"
    assert parameters["unfreeze_steps"] == 8
    assert (
        client.get(url, headers=testuser_token_headers).json()["data"][
            "training_config"
        ]["epochs"]
        == 23
    )
