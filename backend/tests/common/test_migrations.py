import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.common.db import Base


def test_sqlite_enforces_foreign_keys_and_unique_attachment(tmp_path: Path):
    """验证约束在实际连接生效，主键及唯一列无需额外冗余索引。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'constraints.sqlite'}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            connection.execute(text("INSERT INTO project (id) VALUES (1)"))
            connection.execute(text("INSERT INTO project_attachment (id) VALUES (1)"))
            connection.execute(
                text("INSERT INTO project_sample (project_id, file_id) VALUES (1, 1)")
            )
        for values in [(999, None), (1, 999), (1, 1)]:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO project_sample (project_id, file_id) "
                        "VALUES (:project_id, :file_id)"
                    ),
                    dict(zip(["project_id", "file_id"], values)),
                )
        for table in Base.metadata.sorted_tables:
            if len(table.primary_key.columns) == 1:
                primary_key = next(iter(table.primary_key.columns)).name
                assert all(
                    index["column_names"] != [primary_key]
                    for index in inspect(engine).get_indexes(table.name)
                )
    finally:
        engine.dispose()


def test_initial_schema_round_trip_preserves_data_on_repeated_upgrade(tmp_path: Path):
    """用隔离 SQLite 验证完整结构、重复升级保留数据及完整回退。"""
    config = Config()
    directory = Path(__file__).resolve().parents[2] / "migrations"
    config.set_main_option("script_location", str(directory))
    database_url = f"sqlite:///{(tmp_path / 'initial.sqlite').as_posix()}"
    config.set_main_option("sqlalchemy.url", database_url)
    engine = create_engine(database_url)

    try:
        # 1. 直接从空库建立所有表、索引与外键，不预先调用 ORM 建表。
        command.upgrade(config, "head")
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
            connection.execute(text("INSERT INTO project (id) VALUES (1)"))
            connection.execute(
                text("INSERT INTO auto_label_job (id, project_id) VALUES (1, 1)")
            )
            connection.execute(
                text("INSERT INTO project_sample (id, project_id) VALUES (1, 1)")
            )
            assert (
                connection.execute(
                    text("SELECT ai_algorithm FROM project")
                ).scalar_one()
                == "yolo"
            )
            assert (
                connection.execute(
                    text("SELECT model_name FROM auto_label_job")
                ).scalar_one()
                == ""
            )
            assert (
                connection.execute(
                    text("SELECT split FROM project_sample")
                ).scalar_one()
                == "train"
            )
            connection.execute(
                text(
                    "INSERT INTO user (id, username) VALUES (1, 'initial@example.com')"
                )
            )

        # 2. 再次运行初始化入口时，已有业务数据保持不变。
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT username FROM user")
            ).scalar_one() == ("initial@example.com")

        # 3. 回退删除全部业务结构，并允许重新初始化。
        command.downgrade(config, "base")
        assert set(inspect(engine).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


def _run_isolated_app(tmp_path: Path, script: str) -> None:
    """用独立进程与合成配置检查启动，避免复用测试进程的数据库全局状态。"""
    database = tmp_path / "data" / "application.sqlite"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
        "TEMP": str(tmp_path),
        "TMP": str(tmp_path),
        "YOLO_MCP_DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "YOLO_MCP_DATA_DIR": str(database.parent),
    }
    result = subprocess.run(
        [sys.executable, "-c", script, str(database)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_import_and_cli_help_do_not_create_database(tmp_path: Path):
    _run_isolated_app(
        tmp_path,
        """
import sys
from pathlib import Path
from click.testing import CliRunner
from backend.main import cli

database = Path(sys.argv[1])
result = CliRunner().invoke(cli, ["--help"])
assert result.exit_code == 0, result.output
assert "migrate_to_mysql" not in result.output
assert not database.parent.exists()
""",
    )


@pytest.mark.parametrize(
    "host, browser_host",
    [
        ("localhost", "localhost"),
        ("0.0.0.0", "127.0.0.1"),
        ("::", "[::1]"),
        ("2001:db8::1", "[2001:db8::1]"),
    ],
)
def test_cli_displays_browser_url_without_changing_bind_address(
    monkeypatch, host, browser_host
):
    """控制台提供可复制的地址，通配监听与 IPv6 地址均正确显示。"""
    from backend import main

    run = Mock()
    monkeypatch.setattr(main.uvicorn, "run", run)
    monkeypatch.setattr(main.settings, "HOST", main.settings.HOST)
    monkeypatch.setattr(main.settings, "PORT", main.settings.PORT)
    response = CliRunner().invoke(main.cli, ["--host", host, "--port", "9234"])
    assert response.exit_code == 0, response.output
    assert f"YOLO MCP 服务地址: http://{browser_host}:9234" in response.output
    run.assert_called_once_with(app=main.app, host=host, port=9234, ws="websockets")


def test_startup_initializes_database_and_marks_interrupted_jobs(tmp_path: Path):
    _run_isolated_app(
        tmp_path,
        """
import sqlite3
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

database = Path(sys.argv[1])
assert not database.exists()
with TestClient(app) as client:
    assert client.get("/openapi.json").json()["info"]["version"] == "2.0.3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO auto_label_job (id, status, model_name) "
            "VALUES (1, 'PENDING', 'fake.pt')"
        )
with TestClient(app):
    with sqlite3.connect(database) as connection:
        status = connection.execute(
            "SELECT status FROM auto_label_job WHERE id = 1"
        ).fetchone()
        assert status == ("FAILED",)
""",
    )


def test_first_registration_initializes_only_one_administrator(tmp_path: Path):
    _run_isolated_app(
        tmp_path,
        """
from fastapi.testclient import TestClient
from backend.main import app

with TestClient(app) as client:
    assert client.get("/api/v1/users/bootstrap").json()["data"]["required"]
    account = {
        "username": "initial-admin@example.com",
        "password": "Bootstrap-123",
    }
    response = client.post("/api/v1/users/signup", json=account)
    assert response.status_code == 201, response.text
    assert response.json()["data"]["is_admin"] is True
    assert (
        client.get("/api/v1/users/bootstrap").json()["data"]["required"]
        is False
    )
    assert client.post("/api/v1/users/signup", json=account).status_code == 403
    token = client.post("/api/v1/users/login", json=account).json()["data"][
        "token"
    ]
    assert (
        client.get(
            "/api/v1/users", headers={"Authorization": token}
        ).status_code
        == 200
    )
""",
    )


def test_memory_database_url_needs_no_data_directory(tmp_path: Path):
    _run_isolated_app(
        tmp_path,
        """
import os
import sys
from pathlib import Path

os.environ["YOLO_MCP_DATABASE_URL"] = "sqlite://"
from backend.migrations.run_migrate import run_db_migrations

run_db_migrations()
assert not Path(sys.argv[1]).parent.exists()
""",
    )


def test_concurrent_demotion_keeps_one_active_administrator(tmp_path: Path):
    _run_isolated_app(
        tmp_path,
        """
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from backend.main import app

with TestClient(app) as client:
    account = {"username": "first@example.com", "password": "Admin-test-123"}
    first = client.post("/api/v1/users/signup", json=account).json()["data"]
    token = client.post("/api/v1/users/login", json=account).json()["data"][
        "token"
    ]
    second = client.post(
        "/api/v1/users",
        headers={"Authorization": token},
        json={
            "username": "second@example.com",
            "password": "Admin-test-123",
            "is_admin": True,
        },
    ).json()["data"]

    def demote(user):
        return client.patch(
            "/api/v1/users/" + str(user["id"]),
            headers={"Authorization": token},
            json={"is_admin": False},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(demote, [first, second]))
    assert outcomes.count(200) == 1 and all(
        code in (200, 403, 409) for code in outcomes
    ), outcomes
""",
    )


def test_login_and_image_signatures_survive_process_restart(tmp_path: Path):
    _run_isolated_app(
        tmp_path,
        """
import json
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app
from backend.common.storage import get_storage

directory = Path(sys.argv[1]).parent
with TestClient(app) as client:
    account = {
        "username": "restart@example.com",
        "password": "Restart-test-123",
    }
    assert client.post("/api/v1/users/signup", json=account).status_code == 201
    token = client.post("/api/v1/users/login", json=account).json()["data"][
        "token"
    ]
    assert (
        client.post(
            "/api/v1/projects",
            headers={"Authorization": token},
            json={"name": "restart", "media_type": "IMAGE"},
        ).status_code
        == 201
    )
    storage = get_storage()
    key = "projects/1/images/restart.png"
    storage.save_bytes(b"test-only-preview-content", key)
    (directory / "restart-proof.json").write_text(
        json.dumps(
            {
                "token": token,
                "preview": storage.get_read_url(key, 1, 0),
            }
        )
    )
    assert (directory / "secret.key").is_file()
""",
    )
    _run_isolated_app(
        tmp_path,
        """
import json
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

directory = Path(sys.argv[1]).parent
proof = json.loads((directory / "restart-proof.json").read_text())
with TestClient(app) as client:
    me = client.get(
        "/api/v1/users/me", headers={"Authorization": proof["token"]}
    )
    assert me.status_code == 200
    preview = client.get(proof["preview"])
    assert preview.status_code == 200
    assert preview.content == b"test-only-preview-content"
""",
    )
