from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.common.storage import get_storage


def test_local_file_round_trip(tmp_path: Path):
    storage = get_storage()
    file = tmp_path / "sample.txt"
    file.write_text("标注数据", encoding="utf-8")
    storage.save_file(file, "projects/1/uploads/sample.txt")
    assert storage.read_text("projects/1/uploads/sample.txt") == "标注数据"
    assert storage.exists("projects/1/uploads/sample.txt")
    storage.delete("projects/1/uploads/sample.txt")
    assert not storage.exists("projects/1/uploads/sample.txt")


def test_legacy_thumbnail_moves_without_touching_original():
    storage = get_storage()
    original = "projects/5/images/nested/sample.png"
    legacy = "projects/5/images/nested/sample-thumbnail.png"
    storage.save_bytes(b"original", original)
    storage.save_bytes(b"thumbnail", legacy)
    target = storage.thumbnail_key(original)
    assert target == "projects/5/thumbnails/images/nested/sample.png"
    assert storage.read_bytes(target) == b"thumbnail"
    assert storage.read_bytes(original) == b"original"
    assert not storage.exists(legacy)
    assert storage.thumbnail_key(original) == target
    storage.save_bytes(b"another original", legacy)
    storage.thumbnail_key(original)
    assert storage.read_bytes(legacy) == b"another original"


@pytest.mark.parametrize(
    "key",
    ["../outside.txt", "/outside.txt", "projects/../../outside.txt", "C:\\outside.txt"],
)
def test_storage_rejects_paths_outside_root(key):
    with pytest.raises(ValueError):
        get_storage().path(key)


@pytest.mark.parametrize("directory", ["images", "uploads", "thumbnails"])
def test_preview_signature_is_bound_to_path_and_expiration(directory):
    storage = get_storage()
    key = f"projects/1/{directory}/image.png"
    url = storage.get_read_url(key, 1, 0)
    query = parse_qs(urlsplit(url).query)
    expires = int(query["expires"][0])
    signature = query["signature"][0]
    assert storage.verify_read_url(key, expires, signature, 1, 0)
    assert not storage.verify_read_url(key, expires, signature, 2, 0)
    assert not storage.verify_read_url(key, expires, signature, 1, 1)
    assert not storage.verify_read_url(
        "projects/2/uploads/image.png", expires, signature, 1, 0
    )
    assert not storage.verify_read_url(key, expires - 86400, signature, 1, 0)
    assert not storage.verify_read_url(key, expires, "modified", 1, 0)
    with pytest.raises(ValueError):
        storage.get_read_url("projects/1/models/model.pt", 1, 0)


def test_default_database_follows_data_directory(tmp_path):
    from backend.common.config import Settings

    configured = Settings(DATA_DIR=str(tmp_path), DATABASE_URL="")
    assert configured.DATABASE_URL == f"sqlite:///{tmp_path.as_posix()}/labels.sqlite"
    explicit = Settings(DATA_DIR=str(tmp_path), DATABASE_URL="sqlite:///:memory:")
    assert explicit.DATABASE_URL == "sqlite:///:memory:"


def test_default_data_directory_is_under_user_home(tmp_path, monkeypatch):
    from backend.common.config import Settings

    monkeypatch.delenv("YOLO_MCP_DATA_DIR", raising=False)
    monkeypatch.delenv("YOLO_MCP_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "unrelated"))
    monkeypatch.setenv("DATABASE_URL", "not-a-project-database")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    configured = Settings()
    assert configured.DATA_DIR == tmp_path / ".yolo-mcp"
    assert (
        configured.DATABASE_URL
        == f"sqlite:///{tmp_path.as_posix()}/.yolo-mcp/labels.sqlite"
    )
    assert not configured.DATA_DIR.exists()


def test_new_environment_names_control_storage_and_inference(tmp_path, monkeypatch):
    from backend.common.config import Settings

    monkeypatch.setenv("YOLO_MCP_DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("YOLO_MCP_DATABASE_URL", "")
    monkeypatch.setenv("YOLO_MCP_USE_AUTO_LABEL", "false")
    monkeypatch.setenv("YOLO_MCP_DEVICE", "cpu")
    monkeypatch.setenv("USE_AUTO_LABEL", "true")
    monkeypatch.setenv("DEVICE", "unrelated-device")
    configured = Settings()
    assert configured.DATA_DIR == tmp_path / "custom"
    assert configured.USE_AUTO_LABEL is False
    assert configured.DEVICE == "cpu"
    assert not configured.DATA_DIR.exists()
