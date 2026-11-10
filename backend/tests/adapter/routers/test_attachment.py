from io import BytesIO
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.adapter.persistence import crud_attachment
from backend.common.config import settings
from backend.common.db import begin_transaction
from backend.domain.models.user import User

from fastapi.testclient import TestClient
from PIL import Image

from backend.common.storage import get_storage


def _image() -> bytes:
    content = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(content, format="PNG")
    return content.getvalue()


def test_attachment_sample_lifecycle(client, testuser_token_headers, db):
    """拒绝重复建样本和绕过样本删除图片，删除后可重新上传同名图片。"""
    from backend.domain.models.attachment import ProjectAttachment

    headers = testuser_token_headers
    project_id = _create_project(client, headers)
    base = f"/api/v1/projects/{project_id}"

    def upload():
        response = client.post(
            f"{base}/attachments",
            headers=headers,
            files={"file": ("same.png", _image(), "image/png")},
        )
        assert response.status_code == 201
        return response.json()["data"]

    attachment = upload()
    command = {"file_id": attachment["id"]}
    duplicate = client.post(f"{base}/samples", headers=headers, json=[command, command])
    assert duplicate.status_code == 409
    assert (
        client.get(f"{base}/samples", headers=headers, params={"page": 0}).json()[
            "data"
        ]
        == []
    )

    created = client.post(f"{base}/samples", headers=headers, json=[command])
    assert created.status_code == 201
    sample_id = created.json()["data"]["ids"][0]
    assert (
        client.post(f"{base}/samples", headers=headers, json=[command]).status_code
        == 409
    )
    assert (
        client.request(
            "DELETE",
            f"{base}/attachments",
            headers=headers,
            json={"attachment_ids": [attachment["id"]]},
        ).status_code
        == 409
    )
    assert client.get(attachment["url"]).status_code == 200
    assert (
        client.request(
            "DELETE",
            f"{base}/samples",
            headers=headers,
            json={"sample_ids": [sample_id]},
        ).status_code
        == 200
    )
    assert client.get(attachment["url"]).status_code == 404
    assert db.get(ProjectAttachment, attachment["id"]).deleted_at is not None
    assert upload()["id"] != attachment["id"]


def test_upload_preview_and_delete_local_attachment(
    client: TestClient, testuser_token_headers: dict
) -> None:
    headers = testuser_token_headers
    project = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Local upload",
            "media_type": "IMAGE",
        },
    ).json()["data"]
    content = BytesIO()
    Image.new("RGB", (100, 80), "blue").save(content, format="PNG")

    response = client.post(
        f"/api/v1/projects/{project['id']}/attachments",
        headers=headers,
        files={"file": ("sample.png", content.getvalue(), "image/png")},
    )
    assert response.status_code == 201
    attachment = response.json()["data"]
    key = f"projects/{project['id']}/images/sample.png"
    storage = get_storage()
    assert storage.read_bytes(key) == content.getvalue()
    assert storage.exists(f"projects/{project['id']}/thumbnails/images/sample.png")
    assert client.get(attachment["url"]).status_code == 200
    assert client.get(attachment["thumbnail_url"]).status_code == 200

    redirect = client.get(f"/api/v1/projects/partial/{key}", follow_redirects=False)
    assert redirect.status_code == 404

    response = client.request(
        "DELETE",
        f"/api/v1/projects/{project['id']}/attachments",
        headers=headers,
        json={"attachment_ids": [attachment["id"]]},
    )
    assert response.status_code == 200
    assert not storage.exists(key)
    assert not storage.exists(f"projects/{project['id']}/thumbnails/images/sample.png")


def _create_project(client: TestClient, headers: dict) -> int:
    response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Upload boundary",
            "media_type": "IMAGE",
        },
    )
    assert response.status_code == 201
    return response.json()["data"]["id"]


def test_upload_rejects_project_without_access(
    client: TestClient,
    testuser_token_headers: dict,
    db: Session,
):
    project_id = _create_project(client, testuser_token_headers)
    from backend.domain.models.project import Project

    with begin_transaction(db):
        other = User(username="other-upload@example.com", hashed_password="test-only")
        db.add(other)
        db.flush()
        db.get(Project, project_id).created_by = other.id
    response = client.post(
        f"/api/v1/projects/{project_id}/attachments",
        headers=testuser_token_headers,
        files={"file": ("private.txt", b"private", "text/plain")},
    )
    assert response.status_code == 403
    assert not get_storage().exists(f"projects/{project_id}/images/private.txt")


def test_delete_rejects_attachment_from_another_project(
    client: TestClient,
    testuser_token_headers: dict,
):
    first = _create_project(client, testuser_token_headers)
    second = _create_project(client, testuser_token_headers)
    response = client.post(
        f"/api/v1/projects/{second}/attachments",
        headers=testuser_token_headers,
        files={"file": ("keep.png", _image(), "image/png")},
    )
    assert response.status_code == 201
    attachment_id = response.json()["data"]["id"]
    response = client.request(
        "DELETE",
        f"/api/v1/projects/{first}/attachments",
        headers=testuser_token_headers,
        json={"attachment_ids": [attachment_id]},
    )
    assert response.status_code == 403
    assert get_storage().read_bytes(f"projects/{second}/images/keep.png") == _image()


def test_upload_size_limit_does_not_leave_objects(
    client: TestClient,
    testuser_token_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = _create_project(client, testuser_token_headers)
    monkeypatch.setattr(settings, "UPLOAD_FILE_MAX_SIZE", 2)
    response = client.post(
        f"/api/v1/projects/{project_id}/attachments",
        headers=testuser_token_headers,
        files={"file": ("large.png", b"abc", "image/png")},
    )
    assert response.status_code == 413
    assert not get_storage().exists(f"projects/{project_id}/images/large.png")


def test_database_failure_removes_uploaded_objects(
    client: TestClient,
    testuser_token_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = _create_project(client, testuser_token_headers)
    monkeypatch.setattr(
        crud_attachment, "create", Mock(side_effect=RuntimeError("test insert failure"))
    )
    content = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(content, format="PNG")
    response = client.post(
        f"/api/v1/projects/{project_id}/attachments",
        headers=testuser_token_headers,
        files={"file": ("failed.png", content.getvalue(), "image/png")},
    )
    assert response.status_code == 500
    storage = get_storage()
    assert not storage.exists(f"projects/{project_id}/images/failed.png")
    assert not storage.exists(f"projects/{project_id}/thumbnails/images/failed.png")


def test_cleanup_failure_does_not_replace_upload_error(
    client: TestClient,
    testuser_token_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = _create_project(client, testuser_token_headers)
    storage = get_storage()
    monkeypatch.setattr(
        storage, "save_file", Mock(side_effect=HTTPException(413, "test limit"))
    )
    monkeypatch.setattr(
        storage, "delete", Mock(side_effect=RuntimeError("test cleanup failure"))
    )
    response = client.post(
        f"/api/v1/projects/{project_id}/attachments",
        headers=testuser_token_headers,
        files={"file": ("failed.png", _image(), "image/png")},
    )
    assert response.status_code == 413
    assert "test limit" in response.text
