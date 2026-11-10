"""通过公开 HTTP 接口验证账户、令牌及项目权限边界。"""

import hashlib
from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from backend.common.config import settings
from backend.common.db import begin_transaction
from backend.domain.models.access_token import PersonalAccessToken
from backend.domain.models.project import Project
from backend.tests.conftest import TestingSessionLocal

API = settings.API_V1_STR


def account(client, admin, is_admin=False):
    credentials = {
        "username": f"u{uuid4().hex}@example.com",
        "password": "Test-user-123",
    }
    response = client.post(
        f"{API}/users", headers=admin, json={**credentials, "is_admin": is_admin}
    )
    assert response.status_code == 201, response.text
    login = client.post(f"{API}/users/login", json=credentials)
    assert login.status_code == 200
    return response.json()["data"], {"Authorization": login.json()["data"]["token"]}


def project(client, headers):
    result = client.post(
        f"{API}/projects",
        headers=headers,
        json={"name": "permission test", "media_type": "IMAGE"},
    )
    assert result.status_code == 201, result.text
    return result.json()["data"]["id"]


def image(client, headers, project_id, name="test.png"):
    buffer = BytesIO()
    Image.new("RGB", (24, 24), "red").save(buffer, format="PNG")
    response = client.post(
        f"{API}/projects/{project_id}/attachments",
        headers=headers,
        files={"file": (name, buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def personal_token(client, headers):
    response = client.post(
        f"{API}/users/tokens",
        headers=headers,
        json={"name": "test client", "expires_days": 1},
    )
    assert response.status_code == 201, response.text
    token = response.json()["data"]
    return token, {"Authorization": f"Bearer {token['token']}"}


def test_public_registration_closed_and_admin_routes_protected(
    client, testuser_token_headers
):
    assert client.get(f"{API}/users/bootstrap").json() == {"data": {"required": False}}
    assert (
        client.post(
            f"{API}/users/signup",
            json={"username": "blocked@example.com", "password": "test123"},
        ).status_code
        == 403
    )
    assert client.get(f"{API}/users", headers=testuser_token_headers).status_code == 403
    assert (
        client.post(
            f"{API}/users",
            headers=testuser_token_headers,
            json={
                "username": "blocked@example.com",
                "password": "test123",
                "is_admin": True,
            },
        ).status_code
        == 403
    )


def test_invalid_credentials_are_not_echoed_or_logged(
    client, admin_token_headers, capsys
):
    secret = "synthetic-password-exceeds-limit"
    response = client.post(
        f"{API}/users",
        headers=admin_token_headers,
        json={"username": "invalid@example.com", "password": secret},
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert secret not in capsys.readouterr().out


def test_sample_deletion_checks_the_url_project(client, admin_token_headers):
    _, owner = account(client, admin_token_headers)
    first = project(client, owner)
    second = project(client, owner)
    file = image(client, owner, second)
    sid = client.post(
        f"{API}/projects/{second}/samples",
        headers=owner,
        json=[{"file_id": file["id"]}],
    ).json()["data"]["ids"][0]
    response = client.request(
        "DELETE",
        f"{API}/projects/{first}/samples",
        headers=owner,
        json={"sample_ids": [sid]},
    )
    assert response.status_code == 403
    assert (
        client.get(f"{API}/projects/{second}/samples/{sid}", headers=owner).status_code
        == 200
    )
    assert client.get(file["url"]).status_code == 200


def test_personal_token_disclosure_hash_expiry_and_revocation(
    client, admin_token_headers
):
    user, headers = account(client, admin_token_headers)
    token, bearer = personal_token(client, headers)
    assert token["token"].startswith("ymcp_")
    assert "token_hash" not in token
    with TestingSessionLocal() as db:
        stored = db.get(PersonalAccessToken, token["id"])
        assert stored.token_hash == hashlib.sha256(token["token"].encode()).hexdigest()
    listing = client.get(f"{API}/users/tokens", headers=headers).json()["data"]
    assert "token" not in listing[0] and "token_hash" not in listing[0]
    assert (
        client.get(f"{API}/users/me", headers=bearer).json()["data"]["id"] == user["id"]
    )
    assert client.get(f"{API}/users/tokens", headers=bearer).status_code == 403
    assert (
        client.post(
            f"{API}/users/tokens", headers=bearer, json={"name": "recursive"}
        ).status_code
        == 403
    )
    with TestingSessionLocal() as db:
        with begin_transaction(db):
            db.get(PersonalAccessToken, token["id"]).expires_at = (
                datetime.now() - timedelta(seconds=1)
            )
    assert client.get(f"{API}/users/me", headers=bearer).status_code == 401
    token, bearer = personal_token(client, headers)
    assert (
        client.delete(f"{API}/users/tokens/{token['id']}", headers=headers).status_code
        == 200
    )
    assert client.get(f"{API}/users/me", headers=bearer).status_code == 401


def test_tokens_are_private_but_admin_can_revoke(client, admin_token_headers):
    first, headers = account(client, admin_token_headers)
    _, stranger = account(client, admin_token_headers)
    token, bearer = personal_token(client, headers)
    assert (
        client.get(
            f"{API}/users/tokens", headers=stranger, params={"user_id": first["id"]}
        ).status_code
        == 403
    )
    assert (
        client.delete(f"{API}/users/tokens/{token['id']}", headers=stranger).status_code
        == 403
    )
    assert (
        client.get(
            f"{API}/users/tokens",
            headers=admin_token_headers,
            params={"user_id": first["id"]},
        ).json()["data"][0]["id"]
        == token["id"]
    )
    assert (
        client.delete(
            f"{API}/users/tokens/{token['id']}", headers=admin_token_headers
        ).status_code
        == 200
    )
    assert client.get(f"{API}/users/me", headers=bearer).status_code == 401


@pytest.mark.parametrize(
    "change", [{"is_active": False}, {"password": "Changed-pass-123"}]
)
def test_account_change_invalidates_session_token_and_signed_image(
    client, admin_token_headers, change
):
    user, headers = account(client, admin_token_headers)
    pid = project(client, headers)
    file = image(client, headers, pid)
    _, bearer = personal_token(client, headers)
    assert client.get(file["url"]).status_code == 200
    response = client.patch(
        f"{API}/users/{user['id']}", headers=admin_token_headers, json=change
    )
    assert response.status_code == 200, response.text
    assert client.get(f"{API}/users/me", headers=headers).status_code == 401
    assert client.get(f"{API}/users/me", headers=bearer).status_code == 401
    assert client.get(file["url"]).status_code == 403
    if "is_active" in change:
        assert (
            client.patch(
                f"{API}/users/{user['id']}",
                headers=admin_token_headers,
                json={"is_active": True},
            ).status_code
            == 200
        )
        assert client.get(f"{API}/users/me", headers=headers).status_code == 401
        assert client.get(f"{API}/users/me", headers=bearer).status_code == 401


def test_last_enabled_administrator_cannot_be_removed(client, admin_token_headers):
    me = client.get(f"{API}/users/me", headers=admin_token_headers).json()["data"]
    assert (
        client.patch(
            f"{API}/users/{me['id']}",
            headers=admin_token_headers,
            json={"is_admin": False},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{API}/users/{me['id']}",
            headers=admin_token_headers,
            json={"is_active": False},
        ).status_code
        == 409
    )


def test_project_roles_membership_revocation_and_foreign_attachment(
    client, admin_token_headers
):
    owner, headers = account(client, admin_token_headers)
    collaborator, collab_headers = account(client, admin_token_headers)
    _, stranger = account(client, admin_token_headers)
    pid = project(client, headers)
    other = project(client, stranger)
    foreign = image(client, stranger, other)
    base = f"{API}/projects/{pid}"
    assert client.get(base, headers=stranger).status_code == 403
    assert client.get(f"{base}/collaborators", headers=stranger).status_code == 403
    assert (
        client.post(
            f"{base}/collaborators",
            headers=headers,
            json={"user_id": collaborator["id"]},
        ).status_code
        == 201
    )
    assert client.get(base, headers=collab_headers).status_code == 200
    assert client.get(base, headers=admin_token_headers).status_code == 200
    assert (
        client.patch(
            base, headers=collab_headers, json={"name": "forbidden"}
        ).status_code
        == 403
    )
    assert client.delete(base, headers=collab_headers).status_code == 403
    assert (
        client.post(
            f"{base}/collaborators",
            headers=collab_headers,
            json={"user_id": owner["id"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{base}/samples", headers=collab_headers, json=[{"file_id": foreign["id"]}]
        ).status_code
        == 403
    )
    own = image(client, collab_headers, pid)
    created = client.post(
        f"{base}/samples", headers=collab_headers, json=[{"file_id": own["id"]}]
    )
    assert created.status_code == 201, created.text
    sid = created.json()["data"]["ids"][0]
    assert (
        client.patch(
            f"{base}/samples/{sid}", headers=collab_headers, json={"split": "test"}
        ).status_code
        == 200
    )
    sample = client.get(f"{base}/samples/{sid}", headers=collab_headers).json()["data"]
    preview = sample["file"]["url"]
    assert client.get(preview).status_code == 200
    assert (
        client.request(
            "DELETE",
            f"{base}/attachments",
            headers=collab_headers,
            json={"attachment_ids": [own["id"]]},
        ).status_code
        == 403
    )
    pending = image(client, collab_headers, pid, "unsubmitted.png")
    assert (
        client.request(
            "DELETE",
            f"{base}/attachments",
            headers=collab_headers,
            json={"attachment_ids": [pending["id"]]},
        ).status_code
        == 200
    )
    with TestingSessionLocal() as db:
        with begin_transaction(db):
            model_path = (
                settings.DATA_DIR
                / db.get(Project, pid).dataset_prefix
                / "models"
                / "test.pt"
            )
            model_path.write_bytes(b"test model")
    assert (
        client.get(f"{base}/models/test.pt", headers=collab_headers).status_code == 200
    )
    assert client.get(f"{base}/models/test.pt", headers=stranger).status_code == 403
    assert (
        client.delete(
            f"{base}/collaborators/{collaborator['id']}", headers=headers
        ).status_code
        == 200
    )
    assert client.get(base, headers=collab_headers).status_code == 403
    assert client.get(preview).status_code == 403
    assert (
        client.get(f"{base}/models/test.pt", headers=collab_headers).status_code == 403
    )
    listed = client.get(
        f"{API}/projects", headers=admin_token_headers, params={"page": 0, "size": 10}
    ).json()["data"]
    assert {pid, other}.issubset({item["id"] for item in listed})


def test_websocket_rejects_cross_project_and_closes_on_revocation(
    client, admin_token_headers
):
    _, owner = account(client, admin_token_headers)
    member, collaborator = account(client, admin_token_headers)
    pid = project(client, owner)
    file = image(client, owner, pid)
    sid = client.post(
        f"{API}/projects/{pid}/samples", headers=owner, json=[{"file_id": file["id"]}]
    ).json()["data"]["ids"][0]
    token = collaborator["Authorization"].removeprefix("Bearer ")
    url = f"/ws/project/{pid}/{sid}?token={token}"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url):
            pass
    assert (
        client.post(
            f"{API}/projects/{pid}/collaborators",
            headers=owner,
            json={"user_id": member["id"]},
        ).status_code
        == 201
    )
    with client.websocket_connect(url) as ws:
        assert ws.receive_json()["type"] == "peers"
        assert (
            client.delete(
                f"{API}/projects/{pid}/collaborators/{member['id']}", headers=owner
            ).status_code
            == 200
        )
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_deleted_project_samples_are_not_public(client, admin_token_headers):
    _, owner = account(client, admin_token_headers)
    _, stranger = account(client, admin_token_headers)
    pid = project(client, owner)
    file = image(client, owner, pid)
    sid = client.post(
        f"{API}/projects/{pid}/samples", headers=owner, json=[{"file_id": file["id"]}]
    ).json()["data"]["ids"][0]
    assert client.delete(f"{API}/projects/{pid}", headers=owner).status_code == 200
    assert (
        client.get(
            f"{API}/projects/{pid}/samples", headers=stranger, params={"page": 0}
        ).status_code
        == 404
    )
    assert (
        client.get(f"{API}/projects/{pid}/samples/{sid}", headers=stranger).status_code
        == 404
    )
    assert (
        client.request(
            "DELETE",
            f"{API}/projects/{pid}/samples",
            headers=stranger,
            json={"sample_ids": [sid]},
        ).status_code
        == 404
    )


def test_revoked_administrator_privileges_apply_to_existing_token(
    client, admin_token_headers
):
    user, session = account(client, admin_token_headers)
    _, bearer = personal_token(client, session)
    private = project(client, admin_token_headers)
    assert client.get(f"{API}/projects/{private}", headers=bearer).status_code == 403
    assert (
        client.patch(
            f"{API}/users/{user['id']}",
            headers=admin_token_headers,
            json={"is_admin": True},
        ).status_code
        == 200
    )
    assert client.get(f"{API}/projects/{private}", headers=bearer).status_code == 200
    assert (
        client.patch(
            f"{API}/users/{user['id']}",
            headers=admin_token_headers,
            json={"is_admin": False},
        ).status_code
        == 200
    )
    assert client.get(f"{API}/projects/{private}", headers=bearer).status_code == 403


def test_mcp_real_protocol_authentication_tools_and_permissions(
    client, admin_token_headers, monkeypatch
):
    from backend import mcp_server

    monkeypatch.setattr(mcp_server, "SessionLocal", TestingSessionLocal)
    _, session = account(client, admin_token_headers)
    token, bearer = personal_token(client, session)
    base_headers = {
        "Host": "localhost",
        "Accept": "application/json, text/event-stream",
    }
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    assert client.post("/mcp", headers=base_headers, json=init).status_code == 401
    assert (
        client.post("/mcp", headers={**base_headers, **session}, json=init).status_code
        == 401
    )
    headers = {**base_headers, **bearer}
    assert (
        client.post(
            "/mcp", headers={**headers, "Host": "evil.example"}, json=init
        ).status_code
        == 421
    )
    assert (
        client.post(
            "/mcp", headers={**headers, "Origin": "https://evil.example"}, json=init
        ).status_code
        == 403
    )
    result = client.post("/mcp", headers=headers, json=init)
    assert result.status_code == 200, result.text
    assert result.json()["result"]["serverInfo"]["name"] == "YOLO MCP"
    tools = client.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ).json()["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert {
        "create_project",
        "upload_image",
        "save_annotation",
        "start_training",
        "get_model_download",
    }.issubset(names)

    def call(name, arguments):
        response = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["result"]

    import json

    result = call("create_project", {"name": "MCP created"})
    assert not result.get("isError"), result
    pid = json.loads(result["content"][0]["text"])["id"]
    assert client.get(f"{API}/projects/{pid}", headers=session).status_code == 200
    other = project(client, admin_token_headers)
    assert call("get_project", {"project_id": other})["isError"]
    assert call("delete_project", {"project_id": other})["isError"]
    assert not call("list_projects", {}).get("isError")
    assert call(
        "upload_image",
        {"project_id": pid, "filename": "x.png", "image_base64": "invalid!"},
    )["isError"]
    assert (
        client.delete(f"{API}/users/tokens/{token['id']}", headers=session).status_code
        == 200
    )
    assert client.post("/mcp", headers=headers, json=init).status_code == 401
