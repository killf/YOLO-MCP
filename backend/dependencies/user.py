"""统一浏览器会话、个人令牌和 WebSocket 的用户认证。"""

from datetime import timedelta

from jose import jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, Request, Response, WebSocket

from backend.common import db as db_module
from backend.common.config import settings
from backend.common.security import (
    AccessToken,
    create_access_token,
    should_refresh_token,
)
from backend.common.error_code import ErrorCode, YoloMcpException
from backend.domain.models.user import User
from backend.application.service import access_token


class SpecialOAuth2PasswordBearer:
    def __call__(self, request: Request) -> str:
        scheme, _, value = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not value:
            raise YoloMcpException(
                code=ErrorCode.CODE_40003_CREDENTIAL_ERROR, status_code=401
            )
        return value


reusable_oauth2 = SpecialOAuth2PasswordBearer()


def authenticate_credential(db: Session, token: str) -> tuple[User, dict | None]:
    """每次请求读取当前账号状态，JWT 还需匹配凭据版本，PAT 需检查撤销和过期。"""
    if token.startswith("ymcp_"):
        return access_token.authenticate(db, token), None
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.TOKEN_GENERATE_ALGORITHM],
            options={"verify_exp": True},
        )
        claims = AccessToken(**payload)
    except (jwt.JWTError, ValidationError):
        raise YoloMcpException(
            code=ErrorCode.CODE_40003_CREDENTIAL_ERROR, status_code=401
        ) from None
    user = db.get(User, claims.id)
    if user is None:
        raise YoloMcpException(
            code=ErrorCode.CODE_40002_USER_NOT_FOUND, status_code=401
        )
    if not user.is_active or claims.auth_version != user.auth_version:
        raise YoloMcpException(
            code=ErrorCode.CODE_40003_CREDENTIAL_ERROR, status_code=401
        )
    return user, payload


def get_current_user(
    response: Response,
    db: Session = Depends(db_module.get_db),
    token: str = Depends(reusable_oauth2),
) -> User:
    user, payload = authenticate_credential(db, token)
    if payload is not None and should_refresh_token(payload.get("exp")):
        value = create_access_token(
            token=AccessToken(
                id=user.id, username=user.username, auth_version=user.auth_version
            ),
            expires_delta=timedelta(minutes=settings.TOKEN_ACCESS_EXPIRE_MINUTES),
        )
        response.headers["X-New-Token"] = f"{settings.TOKEN_TYPE} {value}"
    return user


def get_session_user(
    user: User = Depends(get_current_user), token: str = Depends(reusable_oauth2)
) -> User:
    """账户和令牌管理仅接受浏览器会话，个人令牌不能继续签发其他凭据。"""
    if token.startswith("ymcp_"):
        raise HTTPException(403, "请登录页面管理账户和访问令牌")
    return user


def get_admin_user(user: User = Depends(get_session_user)) -> User:
    if not user.is_admin:
        raise HTTPException(403, "仅管理员可以管理用户")
    return user


async def verify_ws_token(
    websocket: WebSocket, db: Session = Depends(db_module.get_db)
):
    """握手前验证用户、项目和样本归属，不接收跨项目连接。"""
    from backend.adapter.persistence import crud_project
    from backend.application.service.access import assert_project_access
    from backend.domain.models.sample import ProjectSample

    try:
        user, _ = authenticate_credential(db, websocket.query_params.get("token", ""))
        project_id = int(websocket.path_params["project_id"])
        project = crud_project.get(db, project_id)
        if project is None:
            raise HTTPException(404, "项目不存在")
        assert_project_access(project, user)
        sample = db.get(ProjectSample, int(websocket.path_params["sample_id"]))
        if sample is None or sample.project_id != project_id or sample.deleted_at:
            raise HTTPException(403, "样本不属于当前项目")
        return user
    except (HTTPException, ValueError):
        await websocket.close(code=4003, reason="Unauthorized")
        return None
