from datetime import datetime, timedelta

from jose import jwt
import pytest

from backend.common.config import settings
from backend.common.security import AccessToken
from backend.common.security import create_access_token


def test_first_start_generates_key_and_restart_reuses_it(tmp_path, monkeypatch):
    from backend.common.config import Settings

    monkeypatch.setenv("PASSWORD_SECRET_KEY", "ignored-test-environment-key")
    first = Settings(DATA_DIR=tmp_path, DATABASE_URL="sqlite:///:memory:")
    assert not (tmp_path / "secret.key").exists()
    with pytest.raises(RuntimeError, match="尚未初始化"):
        _ = first.secret_key
    first.initialize_secret_key()
    assert len(first.secret_key) == 64
    assert first.secret_key != "ignored-test-environment-key"
    saved = (tmp_path / "secret.key").read_bytes()
    token = jwt.encode({"sub": "restart-proof"}, first.secret_key, algorithm="HS256")

    second = Settings(DATA_DIR=tmp_path, DATABASE_URL="sqlite:///:memory:")
    second.initialize_secret_key()
    assert (tmp_path / "secret.key").read_bytes() == saved
    assert (
        jwt.decode(token, second.secret_key, algorithms=["HS256"])["sub"]
        == "restart-proof"
    )
    assert "secret_key" not in second.model_dump()
    assert "PASSWORD_SECRET_KEY" not in Settings.model_fields


def test_invalid_existing_key_is_not_overwritten(tmp_path):
    from backend.common.config import Settings

    path = tmp_path / "secret.key"
    path.write_text("invalid-test-file", encoding="utf-8")
    configured = Settings(DATA_DIR=tmp_path, DATABASE_URL="sqlite:///:memory:")
    with pytest.raises(ValueError, match="secret.key 无效"):
        configured.initialize_secret_key()
    assert path.read_text(encoding="utf-8") == "invalid-test-file"


def test_create_access_token_successful():
    # prepare data
    user_id = 1
    username = "labels@example.com"
    token = AccessToken(id=user_id, username=username)

    # run
    access_token = create_access_token(token=token)

    # check
    payload = jwt.decode(
        access_token,
        settings.secret_key,
        algorithms=[settings.TOKEN_GENERATE_ALGORITHM],
    )
    assert (
        (datetime.now() + timedelta(minutes=14, seconds=59)).timestamp()
        < payload["exp"]
        <= (datetime.now() + timedelta(minutes=15, seconds=1)).timestamp()
    )


def test_access_token_no_exp_time():
    # prepare data - create a token with no expiration set initially
    token = AccessToken(id=1, username="user@example.com")
    encoded = jwt.encode(
        token.model_dump(),
        settings.secret_key,
        algorithm=settings.TOKEN_GENERATE_ALGORITHM,
    )

    # check
    payload = jwt.decode(
        encoded,
        settings.secret_key,
        algorithms=[settings.TOKEN_GENERATE_ALGORITHM],
        options={"verify_exp": False},
    )
    assert payload
    assert payload["id"] == 1
    assert payload["username"] == "user@example.com"
