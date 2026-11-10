import json
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from backend.application.service import dataset
from backend.common.storage import get_storage
from backend.domain.models.project import Project


@pytest.fixture
def annotated_sample(
    client: TestClient, testuser_token_headers: dict
) -> tuple[int, int]:
    headers = testuser_token_headers
    project = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "YOLO dataset",
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
    response = client.patch(
        f"/api/v1/projects/{project['id']}",
        headers=headers,
        json={"config": json.dumps(config)},
    )
    assert response.status_code == 200

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
    result = {
        "width": 100,
        "height": 80,
        "rotate": 0,
        "rectTool": {
            "result": [{"x": 10, "y": 20, "width": 40, "height": 20, "label": "object"}]
        },
    }
    response = client.patch(
        f"/api/v1/projects/{project['id']}/samples/{sample_id}",
        headers=headers,
        json={
            "state": "DONE",
            "data": {"result": json.dumps(result)},
            "annotated_count": 1,
        },
    )
    assert response.status_code == 200
    test_attachment = client.post(
        f"/api/v1/projects/{project['id']}/attachments",
        headers=headers,
        files={"file": ("test.png", content.getvalue(), "image/png")},
    ).json()["data"]
    test_id = client.post(
        f"/api/v1/projects/{project['id']}/samples",
        headers=headers,
        json=[{"file_id": test_attachment["id"], "split": "test"}],
    ).json()["data"]["ids"][0]
    assert (
        client.patch(
            f"/api/v1/projects/{project['id']}/samples/{test_id}",
            headers=headers,
            json={"data": {"result": json.dumps(result)}, "annotated_count": 1},
        ).status_code
        == 200
    )
    return project["id"], sample_id


def _snapshot(db, project_id: int, name: str) -> Path:
    directory = get_storage().path(f"projects/{project_id}/runs/{name}/dataset")
    directory.parent.mkdir()
    dataset.create_run_dataset(db, db.get(Project, project_id), directory)
    return directory


def test_annotation_and_split_only_update_database(
    client, testuser_token_headers, annotated_sample, db
):
    project_id, sample_id = annotated_sample
    root = get_storage().path(f"projects/{project_id}")
    assert {p.name for p in root.iterdir()} == {"images", "models", "runs"}
    image = root / "images/sample.png"
    original_bytes = image.read_bytes()
    path = f"/api/v1/projects/{project_id}/samples/{sample_id}"
    original = client.get(path, headers=testuser_token_headers).json()["data"]
    assert "/files/images/" in original["file"]["url"]
    assert client.get(original["file"]["url"]).status_code == 200
    for split in ("test", "train"):
        response = client.patch(
            path, headers=testuser_token_headers, json={"split": split}
        )
        assert response.status_code == 200
        assert response.json()["data"]["data"] == original["data"]
    assert image.read_bytes() == original_bytes
    assert not list((root / "runs").iterdir())
    assert not (root / "labels").exists()
    assert not any(
        (root / name).exists() for name in ("train.txt", "test.txt", "data.yaml")
    )

    snapshot = _snapshot(db, project_id, "first")
    assert (snapshot / f"labels/{sample_id}.txt").read_text() == (
        "0 0.30000000 0.37500000 0.40000000 0.25000000\n"
    )
    config = yaml.safe_load((snapshot / "data.yaml").read_text())
    assert config["names"] == ["Object"]
    assert config["val"] == config["test"] == "test.txt"
    assert (snapshot / "train.txt").read_text() == f"./images/{sample_id}.png\n"


def test_skipped_sample_keeps_original_and_cannot_start_empty_training(
    client, testuser_token_headers, annotated_sample, db
):
    project_id, sample_id = annotated_sample
    response = client.patch(
        f"/api/v1/projects/{project_id}/samples/{sample_id}",
        headers=testuser_token_headers,
        json={"state": "SKIPPED"},
    )
    assert response.status_code == 200
    assert get_storage().exists(f"projects/{project_id}/images/sample.png")
    with pytest.raises(HTTPException) as error:
        _snapshot(db, project_id, "empty")
    assert error.value.status_code == 422


@pytest.mark.parametrize("state", ["NEW", "SKIPPED"])
def test_unconfirmed_samples_are_excluded(
    client, testuser_token_headers, annotated_sample, db, state
):
    project_id, sample_id = annotated_sample
    image = BytesIO()
    Image.new("RGB", (20, 20), "blue").save(image, format="PNG")
    upload = client.post(
        f"/api/v1/projects/{project_id}/attachments",
        headers=testuser_token_headers,
        files={"file": ("unconfirmed.png", image.getvalue(), "image/png")},
    )
    assert upload.status_code == 201
    extra = client.post(
        f"/api/v1/projects/{project_id}/samples",
        headers=testuser_token_headers,
        json=[{"file_id": upload.json()["data"]["id"]}],
    ).json()["data"]["ids"][0]
    assert (
        client.patch(
            f"/api/v1/projects/{project_id}/samples/{extra}",
            headers=testuser_token_headers,
            json={"state": state},
        ).status_code
        == 200
    )
    snapshot = _snapshot(db, project_id, "confirmed")
    assert not (snapshot / f"images/{extra}.png").exists()
    assert not (snapshot / f"labels/{extra}.txt").exists()


@pytest.mark.parametrize(
    "box",
    [
        {"x": 10, "y": 20, "width": 40, "height": 20, "label": "unknown"},
        {"x": 200, "y": 20, "width": 40, "height": 20, "label": "object"},
    ],
)
def test_invalid_annotation_preserves_saved_data(
    client, testuser_token_headers, annotated_sample, box
):
    project_id, sample_id = annotated_sample
    url = f"/api/v1/projects/{project_id}/samples/{sample_id}"
    original = client.get(url, headers=testuser_token_headers).json()["data"]["data"]
    response = client.patch(
        url,
        headers=testuser_token_headers,
        json={
            "state": "DONE",
            "data": {"result": json.dumps({"rectTool": {"result": [box]}})},
        },
    )
    assert response.status_code == 422
    assert (
        client.get(url, headers=testuser_token_headers).json()["data"]["data"]
        == original
    )


def test_background_sample_has_empty_run_label(
    client, testuser_token_headers, annotated_sample, db
):
    project_id, sample_id = annotated_sample
    response = client.patch(
        f"/api/v1/projects/{project_id}/samples/{sample_id}",
        headers=testuser_token_headers,
        json={
            "state": "DONE",
            "data": {"result": json.dumps({"rectTool": {"result": []}})},
            "annotated_count": 0,
        },
    )
    assert response.status_code == 200
    snapshot = _snapshot(db, project_id, "background")
    assert (snapshot / f"labels/{sample_id}.txt").read_text() == ""


def test_rotation_only_affects_run_image(
    client, testuser_token_headers, annotated_sample, db
):
    project_id, sample_id = annotated_sample
    source = get_storage().path(f"projects/{project_id}/images/sample.png")
    original = source.read_bytes()
    response = client.patch(
        f"/api/v1/projects/{project_id}/samples/{sample_id}",
        headers=testuser_token_headers,
        json={
            "data": {
                "result": json.dumps(
                    {
                        "rotate": 90,
                        "rectTool": {
                            "result": [
                                {
                                    "x": 10,
                                    "y": 20,
                                    "width": 40,
                                    "height": 20,
                                    "label": "object",
                                }
                            ]
                        },
                    }
                )
            },
            "annotated_count": 1,
        },
    )
    assert response.status_code == 200
    snapshot = _snapshot(db, project_id, "rotated")
    with Image.open(snapshot / f"images/{sample_id}.png") as image:
        assert image.size == (80, 100)
    assert source.read_bytes() == original
    assert (snapshot / f"labels/{sample_id}.txt").read_text() == (
        "0 0.37500000 0.30000000 0.50000000 0.20000000\n"
    )


def test_removed_export_routes_and_single_migration_head(client: TestClient) -> None:
    response = client.get("/openapi.json")
    schema = response.json()
    assert schema["info"]["title"] == "YOLO MCP"
    assert response.headers["YOLO-MCP-Version"] == schema["info"]["version"]

    paths = schema["paths"]
    assert not any("/export" in path for path in paths)

    directory = Path(__file__).resolve().parents[3] / "migrations"
    config = Config()
    config.set_main_option("script_location", str(directory))
    heads = ScriptDirectory.from_config(config).get_heads()
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())
    assert len(revisions) == 1
    assert heads == [revisions[0].revision]
    assert revisions[0].down_revision is None
