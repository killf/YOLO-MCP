from datetime import datetime, timedelta
from typing import List, Tuple

from loguru import logger
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_, select, update as sql_update
from sqlalchemy.orm import Session

from backend.domain.models.user import User
from backend.adapter.persistence import crud_user
from backend.common.db import begin_transaction
from backend.common.config import settings
from backend.common.error_code import ErrorCode
from backend.common.error_code import YoloMcpException
from backend.common.security import AccessToken
from backend.common.security import verify_password
from backend.common.security import get_password_hash
from backend.common.security import create_access_token
from backend.application.command.user import LoginCommand
from backend.application.command.user import SignupCommand
from backend.application.command.user import CreateUserCommand, UpdateUserCommand
from backend.domain.models.access_token import PersonalAccessToken
from backend.clients.ws import sampleConnectionManager
from backend.application.response.user import UserResponse
from backend.application.response.user import LoginResponse


async def signup(db: Session, cmd: SignupCommand) -> UserResponse:
    """仅空库允许初始化首个管理员；固定首行 ID 防止并发初始化多个管理员。"""
    if db.query(User.id).first() is not None:
        raise HTTPException(403, "管理员已初始化，请由管理员添加用户")
    try:
        with begin_transaction(db):
            user = User(
                id=1,
                username=cmd.username,
                hashed_password=get_password_hash(cmd.password),
                is_admin=True,
            )
            db.add(user)
            db.flush()
    except IntegrityError:
        raise HTTPException(409, "管理员已初始化") from None
    return UserResponse.model_validate(user)


async def create(db: Session, cmd: CreateUserCommand) -> UserResponse:
    """由管理员创建账户，普通用户不经过公开注册。"""
    user = crud_user.get_user_by_username(db, username=cmd.username)
    if user:
        logger.error("user already exist:{}", cmd.username)
        raise YoloMcpException(
            code=ErrorCode.CODE_40001_USERNAME_ALREADY_EXISTS,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # new a user
    with begin_transaction(db):
        user = crud_user.create(
            db,
            User(
                username=cmd.username,
                hashed_password=get_password_hash(cmd.password),
                is_admin=cmd.is_admin,
            ),
        )

    # response
    return UserResponse.model_validate(user)


async def update(db: Session, user_id: int, cmd: UpdateUserCommand) -> UserResponse:
    """更新角色、启停或密码；凭据变化时撤销旧会话与个人令牌。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "用户不存在")
    changes = cmd.model_dump(exclude_none=True, exclude={"password"})
    if cmd.password is not None:
        changes["hashed_password"] = get_password_hash(cmd.password)
    revoke_credentials = cmd.password is not None or cmd.is_active is False
    if revoke_credentials:
        changes["auth_version"] = User.auth_version + 1
    statement = sql_update(User).where(User.id == user_id)
    if cmd.is_admin is False or cmd.is_active is False:
        others = (
            select(func.count())
            .select_from(User)
            .where(
                User.id != user_id, User.is_admin.is_(True), User.is_active.is_(True)
            )
            .scalar_subquery()
        )
        # 将最后管理员检查放在同一条写语句中，避免并发降权后无人管理。
        statement = statement.where(
            or_(User.is_admin.is_(False), User.is_active.is_(False), others > 0)
        )
    with begin_transaction(db):
        if changes:
            result = db.execute(
                statement.values(**changes).execution_options(synchronize_session=False)
            )
            if result.rowcount == 0:
                raise HTTPException(409, "至少保留一个启用的管理员")
        if revoke_credentials:
            db.query(PersonalAccessToken).filter(
                PersonalAccessToken.user_id == user.id,
                PersonalAccessToken.revoked_at.is_(None),
            ).update({PersonalAccessToken.revoked_at: datetime.now()})
    db.refresh(user)
    if cmd.password is not None or cmd.is_active is False or cmd.is_admin is not None:
        await sampleConnectionManager.close_user_connections(user.id)
    return UserResponse.model_validate(user)


async def list_by(
    db: Session, page: int, size: int, username: str = None
) -> Tuple[List[UserResponse], int]:
    # get all users
    users, total = crud_user.list_by(db, page, size, username)

    # response
    return [UserResponse.model_validate(user) for user in users], total


async def login(db: Session, cmd: LoginCommand) -> LoginResponse:

    # check user exsit and verify password
    user = crud_user.get_user_by_username(db, cmd.username)
    if (
        not user
        or not user.is_active
        or not verify_password(cmd.password, user.hashed_password)
    ):
        raise YoloMcpException(
            code=ErrorCode.CODE_40000_USERNAME_OR_PASSWORD_INCORRECT,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    # create access token
    access_token_expires = timedelta(minutes=settings.TOKEN_ACCESS_EXPIRE_MINUTES)
    access_token = create_access_token(
        token=AccessToken(
            id=user.id, username=user.username, auth_version=user.auth_version
        ),
        expires_delta=access_token_expires,
    )

    # response
    return LoginResponse(token=f"{settings.TOKEN_TYPE} {access_token}")
