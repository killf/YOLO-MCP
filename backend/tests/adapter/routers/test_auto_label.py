import json
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from backend.adapter.persistence import crud_auto_label_job
from backend.application.service import auto_label
from backend.common.db import begin_transaction
from backend.common.storage import get_storage
from backend.domain.models.auto_label_job import AutoLabelJob
from backend.domain.models.sample import ProjectSample
from backend.tests.conftest import TestingSessionLocal


class Vector(list):
    def tolist(self) -> list:
        return list(self)


@pytest.fixture
def ai_project(client: TestClient, testuser_token_headers: dict) -> tuple[int, int]:
    headers = testuser_token_headers
    project = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "AI detection",
            "media_type": "IMAGE",
        },
    ).json()["data"]
    config = {
        "tools": [
            {
                "tool": "rectTool",
                "config": {"attributes": [{"key": "Object", "value": "object"}]},
            }
        ]
    }
    client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={"config": json.dumps(config), "ai_model_name": "20261107-1.pt"},
    )
    content = BytesIO()
    Image.new("RGB", (100, 80), "blue").save(content, format="PNG")
    attachment = client.post(
        f"/api/v1/projects/{project['id']}/attachments",
        headers=headers,
        files={"file": ("sample.png", content.getvalue(), "image/png")},
    ).json()["data"]
    sample_id = client.post(
        f"/api/v1/projects/{project['id']}/samples",
        headers=headers,
        json=[{"file_id": attachment["id"], "data": {}}],
    ).json()["data"]["ids"][0]
    return project["id"], sample_id


def test_yolo_prediction_is_editable_and_does_not_complete_sample(
    client: TestClient,
    testuser_token_headers: dict,
    ai_project: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prediction = SimpleNamespace(
        names={0: "Object", 1: "unconfigured"},
        boxes=SimpleNamespace(
            xyxy=Vector([[10, 20, 50, 40], [0, 0, 10, 10]]),
            cls=Vector([0, 1]),
            conf=Vector([0.9, 0.8]),
        ),
    )
    model = SimpleNamespace(predict=lambda *args, **kwargs: [prediction])

    @contextmanager
    def load_model(*args):
        yield model

    monkeypatch.setattr(auto_label, "_load_model", load_model)
    project_id, sample_id = ai_project
    for _ in range(2):
        response = client.post(
            f"/api/v1/projects/{project_id}/samples/{sample_id}/auto_label",
            headers=testuser_token_headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["warning_message"]

    annotations = client.get(
        f"/api/v1/projects/{project_id}/pre_annotations",
        params={"sample_name": "sample.png", "page": 0},
        headers=testuser_token_headers,
    ).json()["data"]
    assert len(annotations) == 1
    payload = json.loads(annotations[0]["data"])
    boxes = payload["annotations"]["rectTool"]["result"]
    assert len(boxes) == 1 and boxes[0]["label"] == "object"
    assert (boxes[0]["x"], boxes[0]["width"]) == (10, 40)
    sample = client.get(
        f"/api/v1/projects/{project_id}/samples/{sample_id}",
        headers=testuser_token_headers,
    ).json()["data"]
    assert sample["state"] == "NEW" and sample["data"] == {}


def test_batch_reuses_model_and_reports_partial_failure(
    db: Session,
    ai_project: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, sample_id = ai_project
    first = db.get(ProjectSample, sample_id)
    with begin_transaction(db):
        second = ProjectSample(
            project_id=project_id,
            inner_id=2,
            created_by=first.created_by,
            updated_by=first.created_by,
            data="{}",
        )
        db.add(second)
        db.flush()
        second_id = second.id
        job = crud_auto_label_job.create(
            db, project_id, first.created_by, 2, "20261107-1.pt"
        )
        job_id = job.id
    loads = []

    @contextmanager
    def load_model(*args):
        loads.append(1)
        yield object()

    def predict(model, sample, project, model_name, algorithm=None):
        if sample.id == second_id:
            raise RuntimeError("synthetic inference failure")
        return {
            "sample_name": "sample.png",
            "annotations": {},
            "meta": {"source_type": "ai_generated", "sample_id": sample.id},
        }

    monkeypatch.setattr(auto_label, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(auto_label, "_load_model", load_model)
    monkeypatch.setattr(auto_label, "_predict", predict)
    auto_label._run_batch(job_id, [sample_id, second_id])
    db.expire_all()
    completed = db.get(AutoLabelJob, job_id)
    assert loads == [1]
    assert (
        completed.status,
        completed.processed_count,
        completed.success_count,
        completed.failed_count,
    ) == ("FAILED", 2, 1, 1)
    assert completed.error_message


def test_restart_marks_unfinished_ai_job_as_interrupted(
    db: Session,
    ai_project: tuple[int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id, sample_id = ai_project
    sample = db.get(ProjectSample, sample_id)
    with begin_transaction(db):
        job = crud_auto_label_job.create(
            db, project_id, sample.created_by, 1, "20261107-1.pt"
        )
        job_id = job.id
    monkeypatch.setattr(auto_label, "SessionLocal", TestingSessionLocal)
    auto_label.fail_interrupted_jobs()
    db.expire_all()
    assert db.get(AutoLabelJob, job_id).status == "FAILED"


def test_list_dataset_model_weights(
    client: TestClient, testuser_token_headers: dict, ai_project: tuple[int, int]
) -> None:
    project_id, _ = ai_project
    get_storage().save_bytes(
        b"synthetic weight", f"projects/{ai_project[0]}/models/20261107-1.pt"
    )
    response = client.get(
        f"/api/v1/projects/{project_id}/models", headers=testuser_token_headers
    )
    assert response.status_code == 200
    assert response.json()["data"] == ["20261107-1.pt"]


def test_missing_batch_job_does_not_load_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auto_label, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(
        auto_label,
        "_load_model",
        lambda *args: pytest.fail("missing job loaded a model"),
    )
    auto_label._run_batch(999999, [])


@pytest.mark.parametrize("name", ["../escape.pt", "..\\escape.pt", "C:\\escape.pt"])
def test_model_names_reject_paths_before_loading(name: str):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        with auto_label._load_model(None, None, name):
            pytest.fail("invalid model path reached inference")
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "algorithm,weights",
    [
        ("florence2", "microsoft/Florence-2-base"),
        ("grounding_dino_sam", "grounding-dino-tiny+sam-vit-base"),
        ("sam3", "facebook/sam3"),
    ],
)
def test_open_vocabulary_algorithms_share_editable_annotation_contract(
    client, testuser_token_headers, ai_project, monkeypatch, algorithm, weights
):
    from backend.inference import Detection

    project_id, sample_id = ai_project
    base = f"/api/v1/projects/{project_id}"
    models = client.get(
        base + "/models",
        headers=testuser_token_headers,
        params={"algorithm": algorithm},
    )
    assert models.status_code == 200 and weights in models.json()["data"]
    saved = client.patch(
        base,
        headers=testuser_token_headers,
        json={"ai_algorithm": algorithm, "ai_model_name": weights},
    )
    assert saved.status_code == 200, saved.text
    detector = SimpleNamespace(
        predict=lambda image, labels: [Detection([1, 2, 7, 8], labels[0], 0.9)]
    )
    monkeypatch.setattr(auto_label, "load_detector", lambda *args: detector)
    response = client.post(
        base + f"/samples/{sample_id}/auto_label", headers=testuser_token_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["provider"] == algorithm
    annotations = client.get(
        base + "/pre_annotations",
        headers=testuser_token_headers,
        params={"sample_name": "sample.png", "page": 0},
    ).json()["data"]
    payload = json.loads(annotations[0]["data"])
    assert payload["meta"]["provider"] == algorithm
    assert payload["annotations"]["rectTool"]["result"][0]["label"] == "object"
    assert (
        client.get(
            base + f"/samples/{sample_id}", headers=testuser_token_headers
        ).json()["data"]["state"]
        == "NEW"
    )


def test_missing_optional_model_cache_returns_actionable_error(monkeypatch):
    from fastapi import HTTPException

    def unavailable(*_args):
        raise OSError("synthetic missing cache")

    monkeypatch.setattr(auto_label, "load_detector", unavailable)
    with pytest.raises(HTTPException) as error:
        with auto_label._load_model(
            None, SimpleNamespace(ai_algorithm="sam3"), "facebook/sam3"
        ):
            pytest.fail("missing model reached inference")
    assert error.value.status_code == 503
    assert "facebook/sam3" in error.value.detail
    assert "权重下载或读取失败" in error.value.detail


@pytest.mark.parametrize(
    "algorithm,weights",
    [
        ("yolo", "microsoft/Florence-2-base"),
        ("yolo", "../outside.pt"),
        ("florence2", "facebook/sam3"),
    ],
)
def test_configuration_rejects_mismatched_annotation_weights(
    client, testuser_token_headers, ai_project, algorithm, weights
):
    response = client.patch(
        f"/api/v1/projects/{ai_project[0]}",
        headers=testuser_token_headers,
        json={"ai_algorithm": algorithm, "ai_model_name": weights},
    )
    assert response.status_code == 422


def test_batch_uses_algorithm_snapshot_after_project_selection_changes(
    db, ai_project, monkeypatch
):
    from backend.domain.models.project import Project
    from backend.domain.models.pre_annotation import ProjectPreAnnotation
    from backend.inference import Detection

    project_id, sample_id = ai_project
    sample = db.get(ProjectSample, sample_id)
    with begin_transaction(db):
        job = crud_auto_label_job.create(
            db,
            project_id,
            sample.created_by,
            1,
            "microsoft/Florence-2-base",
            "florence2",
        )
        job_id = job.id
    assert db.get(Project, project_id).ai_algorithm == "yolo"
    detector = SimpleNamespace(
        predict=lambda image, labels: [Detection([1, 2, 7, 8], labels[0])]
    )
    monkeypatch.setattr(auto_label, "load_detector", lambda *args: detector)
    monkeypatch.setattr(auto_label, "SessionLocal", TestingSessionLocal)
    auto_label._run_batch(job_id, [sample_id])
    db.expire_all()
    assert db.get(AutoLabelJob, job_id).status == "COMPLETED"
    record = db.query(ProjectPreAnnotation).one()
    assert json.loads(record.data)["meta"]["provider"] == "florence2"
