from datetime import timedelta

from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from backend.domain.models.user import User
from backend.adapter.persistence import crud_user
from backend.common.config import settings
from backend.common.security import AccessToken
from backend.common.security import get_password_hash
from backend.common.security import create_access_token
from backend.common.db import begin_transaction

from backend.tests.conftest import TEST_USERNAME
from backend.tests.utils.utils import random_username
from backend.tests.utils.utils import random_lower_string


class TestClassUserRouter:
    def test_admin_creates_user_successful(
        self, client: TestClient, db: Session, admin_token_headers
    ):

        # prepare data
        username = random_username()
        password = random_lower_string()
        data = {"username": username, "password": password}

        # run
        r = client.post(
            f"{settings.API_V1_STR}/users", json=data, headers=admin_token_headers
        )

        # check
        assert r.status_code == 201
        created_user = r.json()
        user = crud_user.get_user_by_username(db, username=username)
        assert user
        assert user.username == created_user["data"]["username"]

    def test_create_user_existing_username(
        self, client: TestClient, db: Session, admin_token_headers
    ):
        # prepare data
        username = random_username()
        password = random_lower_string()
        data = {"username": username, "password": password}
        with begin_transaction(db):
            crud_user.create(
                db=db,
                user=User(
                    username=username, hashed_password=get_password_hash(password)
                ),
            )

        # run
        r = client.post(
            f"{settings.API_V1_STR}/users", json=data, headers=admin_token_headers
        )

        # check
        created_user = r.json()
        assert r.status_code == 400
        assert created_user["err_code"] == 40001

    def test_user_login_sucessful(self, client: TestClient, db: Session):
        # prepare data
        username = random_username()
        password = random_lower_string()
        data = {"username": username, "password": password}
        with begin_transaction(db):
            crud_user.create(
                db=db,
                user=User(
                    username=username, hashed_password=get_password_hash(password)
                ),
            )

        # run
        r = client.post(f"{settings.API_V1_STR}/users/login", json=data)

        # check
        assert r.status_code == 200
        assert r.json()["data"]["token"].startswith(settings.TOKEN_TYPE)

    def test_user_login_cannot_find_user(self, client: TestClient, db: Session):
        # prepare data
        username = random_username()
        password = random_lower_string()
        data = {"username": username, "password": password}

        # run
        r = client.post(f"{settings.API_V1_STR}/users/login", json=data)

        # check
        user = r.json()
        assert r.status_code == 401
        assert user["err_code"] == 40000

    def test_user_logout(
        self, client: TestClient, testuser_token_headers: dict, db: Session
    ):

        # run
        r = client.post(
            f"{settings.API_V1_STR}/users/logout", headers=testuser_token_headers
        )

        # check
        assert r.status_code == 200

    def test_user_token_error(self, client: TestClient, db: Session) -> None:

        # prepare data
        headers = {"Authorization": "Bearer token"}
        # run
        r = client.post(f"{settings.API_V1_STR}/users/logout", headers=headers)

        # check
        assert r.status_code == 401
        assert r.json()["err_code"] == 40003

    def test_cannot_not_found_token(self, client: TestClient, db: Session) -> None:

        # run
        r = client.post(f"{settings.API_V1_STR}/users/logout")

        # check
        assert r.status_code == 401
        assert r.json()["err_code"] == 30003

    def test_user_not_found(self, client: TestClient, db: Session) -> None:

        # prepare data
        username = random_username()
        access_token_expires = timedelta(minutes=settings.TOKEN_ACCESS_EXPIRE_MINUTES)
        access_token = create_access_token(
            token=AccessToken(id=-1, username=username),
            expires_delta=access_token_expires,
        )
        headers = {"Authorization": f"Bearer {access_token}"}
        # run
        r = client.post(f"{settings.API_V1_STR}/users/logout", headers=headers)

        # check
        assert r.status_code == 401
        assert r.json()["err_code"] == 40002

    def test_token_sliding_refresh_when_near_expiry(
        self, client: TestClient, db: Session
    ) -> None:
        # prepare: a still-valid token whose remaining lifetime is below the
        # refresh threshold, so the request should trigger a sliding refresh.
        user = crud_user.get_user_by_username(db, username=TEST_USERNAME)
        remaining = settings.TOKEN_REFRESH_THRESHOLD_MINUTES - 1
        access_token = create_access_token(
            token=AccessToken(id=user.id, username=user.username),
            expires_delta=timedelta(minutes=remaining),
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        # run
        r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)

        # check: a brand-new token is handed back via the response header
        assert r.status_code == 200
        assert "X-New-Token" in r.headers
        assert r.headers["X-New-Token"].startswith(settings.TOKEN_TYPE)
        assert r.headers["X-New-Token"] != f"Bearer {access_token}"

    def test_token_not_refreshed_when_fresh(
        self, client: TestClient, db: Session
    ) -> None:
        # prepare: a token whose remaining lifetime is above the threshold
        user = crud_user.get_user_by_username(db, username=TEST_USERNAME)
        remaining = settings.TOKEN_REFRESH_THRESHOLD_MINUTES + 5
        access_token = create_access_token(
            token=AccessToken(id=user.id, username=user.username),
            expires_delta=timedelta(minutes=remaining),
        )
        headers = {"Authorization": f"Bearer {access_token}"}

        # run
        r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)

        # check: no refresh header on a fresh token
        assert r.status_code == 200
        assert "X-New-Token" not in r.headers
