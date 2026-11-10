"""管理和验证个人令牌，明文只在创建响应中返回一次。"""

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.application.command.user import CreateTokenCommand
from backend.application.response.user import (
    CreatedTokenResponse,
    PersonalTokenResponse,
)
from backend.common.db import begin_transaction
from backend.domain.models.access_token import PersonalAccessToken
from backend.domain.models.user import User


def create(
    db: Session, user: User, command: CreateTokenCommand
) -> CreatedTokenResponse:
    """为当前用户生成高熵令牌，持久化摘要并仅在本次响应返回明文。"""
    value = "ymcp_" + secrets.token_urlsafe(32)
    with begin_transaction(db):
        token = PersonalAccessToken(
            user_id=user.id,
            name=command.name,
            token_hash=hashlib.sha256(value.encode()).hexdigest(),
            expires_at=(
                (datetime.now() + timedelta(days=command.expires_days))
                if command.expires_days
                else None
            ),
        )
        db.add(token)
        db.flush()
    return CreatedTokenResponse(
        **PersonalTokenResponse.model_validate(token).model_dump(), token=value
    )


def list_by(
    db: Session, user: User, user_id: int | None = None
) -> list[PersonalTokenResponse]:
    """列出本人或管理员指定用户的令牌元数据，不返回明文或摘要。"""
    owner = user_id if user_id is not None else user.id
    if owner != user.id and not user.is_admin:
        raise HTTPException(403, "只能查看自己的访问令牌")
    return [
        PersonalTokenResponse.model_validate(token)
        for token in db.query(PersonalAccessToken)
        .filter(PersonalAccessToken.user_id == owner)
        .order_by(PersonalAccessToken.id.desc())
    ]


def revoke(db: Session, user: User, token_id: int) -> int:
    """校验所属用户后标记撤销，返回用户 ID 供调用方关闭相关连接。"""
    token = db.get(PersonalAccessToken, token_id)
    if token is None:
        raise HTTPException(404, "访问令牌不存在")
    if token.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "只能撤销自己的访问令牌")
    with begin_transaction(db):
        token.revoked_at = datetime.now()
    return token.user_id


def authenticate(db: Session, value: str, *, record_usage: bool = True) -> User:
    """每次请求校验摘要、有效期、撤销状态和账号状态，返回当前用户。"""
    token = (
        db.query(PersonalAccessToken)
        .filter(
            PersonalAccessToken.token_hash == hashlib.sha256(value.encode()).hexdigest()
        )
        .first()
    )
    now = datetime.now()
    if (
        token is None
        or token.revoked_at
        or (token.expires_at and token.expires_at <= now)
    ):
        raise HTTPException(
            401, "访问令牌无效或已过期", headers={"WWW-Authenticate": "Bearer"}
        )
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "账号已停用")
    if record_usage:
        with begin_transaction(db):
            token.last_used_at = now
    return user
