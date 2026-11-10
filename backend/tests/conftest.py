import os
import json
from io import BytesIO
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Generator

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# 1. 数据库与文件存储均使用隔离临时目录，不读取开发者的配置或凭据。
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="yolo-mcp-test-"))
os.environ["YOLO_MCP_DATABASE_URL"] = (
    f"sqlite:///{(_TEST_DATA_DIR / 'application.sqlite').as_posix()}"
)
os.environ["YOLO_MCP_DATA_DIR"] = str(_TEST_DATA_DIR)
from backend.common.config import settings

settings.initialize_secret_key()
from backend.common.storage import get_storage

from backend.main import app
from backend.common.db import Base
from backend.common.db import begin_transaction
from backend.common.db import get_db
from backend.common.security import get_password_hash
from backend.domain.models.user import User
from backend.adapter.persistence import crud_user

TEST_USERNAME = "test@example.com"
TEST_USER_PASSWORD = "test@123"


SQLALCHEMY_DATABASE_URL = f"sqlite:///{_TEST_DATA_DIR / 'test.db'}"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)
TestingSessionLocal = sessionmaker(autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True, scope="session")
def _hermetic_storage() -> Generator:
    """Guarantee the isolated media root is active and clean it up afterwards.

    The redirect itself happens at import time (above); this fixture re-clears
    the local-storage cache in case anything memoized it during collection and
    removes the throwaway directory (test DB + media) once the session ends.
    """
    get_storage.cache_clear()
    try:
        yield
    finally:
        engine.dispose()
        get_storage.cache_clear()
        shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


def override_get_db():
    db = None
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        if db is not None:
            db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True, scope="session")
def db() -> Generator:
    db = None
    try:
        db = TestingSessionLocal()
        # Seed the test user at session scope so it exists before the
        # module-scoped ``testuser_token_headers`` fixture logs in. The
        # per-test ``run_around_tests`` cleanup preserves the ``user`` table, so
        # this single seed lasts the whole session. (Previously the user
        # survived only because ``test.db`` persisted in the cwd across runs.)
        init_db()
        yield db
    finally:
        if db is not None:
            db.close()


@pytest.fixture(scope="session", autouse=True)
def ensure_test_user() -> Generator:
    # Initialize test user once per test session
    init_db()
    yield


@pytest.fixture(autouse=True)
def run_around_tests(db: Session):
    init_db()
    yield
    # Release any autobegin transaction on the session-scoped fixture so SQLite
    # teardown and TestClient requests do not deadlock.
    db.rollback()
    cleanup = None
    try:
        cleanup = TestingSessionLocal()
        meta = Base.metadata
        with begin_transaction(cleanup):
            for table in reversed(meta.sorted_tables):
                if table.key != "user":
                    cleanup.execute(table.delete())
        project_files = (_TEST_DATA_DIR / "projects").resolve()
        assert project_files.is_relative_to(_TEST_DATA_DIR.resolve())
        shutil.rmtree(project_files, ignore_errors=True)
    finally:
        if cleanup is not None:
            cleanup.close()


@pytest.fixture(scope="module")
def client() -> Generator:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def testuser_token_headers(client: TestClient) -> Dict[str, str]:
    return get_testuser_token_headers(client)


@pytest.fixture
def other_user_id(db: Session) -> int:
    """提供真实的非成员账户，用于项目权限测试。"""
    username = "other-owner@example.com"
    user = crud_user.get_user_by_username(db, username)
    if user is None:
        with begin_transaction(db):
            user = crud_user.create(
                db,
                User(
                    username=username,
                    hashed_password=get_password_hash(TEST_USER_PASSWORD),
                ),
            )
    return user.id


@pytest.fixture(scope="module")
def admin_token_headers(client: TestClient) -> Dict[str, str]:
    with TestingSessionLocal() as session:
        admin = crud_user.get_user_by_username(session, "admin@example.com")
        if admin is None:
            with begin_transaction(session):
                session.add(
                    User(
                        username="admin@example.com",
                        hashed_password=get_password_hash(TEST_USER_PASSWORD),
                        is_admin=True,
                    )
                )
    response = client.post(
        f"{settings.API_V1_STR}/users/login",
        json={"username": "admin@example.com", "password": TEST_USER_PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": response.json()["data"]["token"]}


def get_testuser_token_headers(client: TestClient) -> Dict[str, str]:
    data = {
        "username": TEST_USERNAME,
        "password": TEST_USER_PASSWORD,
    }
    r = client.post(f"{settings.API_V1_STR}/users/login", json=data)
    response_json = r.json()

    # Add debugging info for CI failures
    if "data" not in response_json:
        print(f"Login failed. Response: {response_json}")
        print(f"Status code: {r.status_code}")
        print(f"Password length (bytes): {len(TEST_USER_PASSWORD.encode('utf-8'))}")
        raise ValueError(f"Login failed with response: {response_json}")

    token = response_json["data"]["token"]
    headers = {"Authorization": f"{token}"}
    return headers


def init_db() -> None:
    db = None
    try:
        db = TestingSessionLocal()
        with begin_transaction(db):
            user = crud_user.get_user_by_username(db, username=TEST_USERNAME)
            if not user:
                user_in = User(
                    username=TEST_USERNAME,
                    hashed_password=get_password_hash(TEST_USER_PASSWORD),
                )
                user = crud_user.create(db=db, user=user_in)
    finally:
        if db is not None:
            db.close()


@pytest.fixture
def training_project(client, testuser_token_headers):
    """通过公共接口准备分别含一张人工完成图片的训练集和测试集。"""
    headers = testuser_token_headers
    project = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "Page training",
            "media_type": "IMAGE",
        },
    ).json()["data"]
    project_id = project["id"]
    config = {
        "tools": [
            {
                "tool": "rectTool",
                "config": {"attributes": [{"key": "person", "value": "person"}]},
            }
        ]
    }
    response = client.patch(
        f"/api/v1/projects/{project_id}",
        headers=headers,
        json={"config": json.dumps(config)},
    )
    assert response.status_code == 200
    content = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(content, format="PNG")
    result = {
        "width": 10,
        "height": 10,
        "rectTool": {
            "result": [{"x": 1, "y": 1, "width": 3, "height": 4, "label": "person"}]
        },
    }
    for split in ["train", "test"]:
        attachment = client.post(
            f"/api/v1/projects/{project_id}/attachments",
            headers=headers,
            files={"file": (f"{split}.png", content.getvalue(), "image/png")},
        ).json()["data"]
        sample_id = client.post(
            f"/api/v1/projects/{project_id}/samples",
            headers=headers,
            json=[{"file_id": attachment["id"], "split": split}],
        ).json()["data"]["ids"][0]
        response = client.patch(
            f"/api/v1/projects/{project_id}/samples/{sample_id}",
            headers=headers,
            json={
                "state": "DONE",
                "data": {"result": json.dumps(result)},
                "annotated_count": 1,
            },
        )
        assert response.status_code == 200
    return project_id
