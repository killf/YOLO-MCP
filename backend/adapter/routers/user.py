from typing import List
from sqlalchemy.orm import Session
from fastapi import APIRouter, status, Depends, Security
from fastapi.security import HTTPAuthorizationCredentials

from backend.common import db as db_module
from backend.domain.models.user import User
from backend.common.security import security
from backend.dependencies.user import get_current_user, get_admin_user, get_session_user
from backend.application.command.user import (
    CreateUserCommand,
    UpdateUserCommand,
    CreateTokenCommand,
)
from backend.application.response.user import (
    PersonalTokenResponse,
    CreatedTokenResponse,
)
from backend.application.service import access_token
from backend.clients.ws import sampleConnectionManager
from backend.application.response.base import UserResp, CommonDataResp
from backend.application.response.base import MetaData, OkResp, OkRespWithMeta
from backend.application.service import user as service
from backend.application.command.user import LoginCommand
from backend.application.command.user import SignupCommand
from backend.application.response.user import LoginResponse
from backend.application.response.user import LogoutResponse
from backend.application.response.user import UserResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/bootstrap")
def bootstrap_status(db: Session = Depends(db_module.get_db)):
    return {"data": {"required": db.query(User.id).first() is None}}


@router.post("", response_model=OkResp[UserResponse], status_code=201)
async def create_user(
    cmd: CreateUserCommand,
    db: Session = Depends(db_module.get_db),
    admin: User = Depends(get_admin_user),
):
    return OkResp(data=await service.create(db, cmd))


@router.patch("/{user_id}", response_model=OkResp[UserResponse])
async def update_user(
    user_id: int,
    cmd: UpdateUserCommand,
    db: Session = Depends(db_module.get_db),
    admin: User = Depends(get_admin_user),
):
    return OkResp(data=await service.update(db, user_id, cmd))


@router.get("/directory", response_model=OkResp[list[UserResp]])
def user_directory(
    db: Session = Depends(db_module.get_db), user: User = Depends(get_current_user)
):
    users = (
        db.query(User).filter(User.is_active.is_(True)).order_by(User.username).all()
    )
    return OkResp[list[UserResp]](
        data=[UserResp(id=item.id, username=item.username) for item in users]
    )


@router.post("/tokens", response_model=OkResp[CreatedTokenResponse], status_code=201)
def create_token(
    cmd: CreateTokenCommand,
    db: Session = Depends(db_module.get_db),
    user: User = Depends(get_session_user),
):
    return OkResp(data=access_token.create(db, user, cmd))


@router.get("/tokens", response_model=OkResp[list[PersonalTokenResponse]])
def list_tokens(
    user_id: int | None = None,
    db: Session = Depends(db_module.get_db),
    user: User = Depends(get_session_user),
):
    return OkResp[list[PersonalTokenResponse]](
        data=access_token.list_by(db, user, user_id)
    )


@router.delete("/tokens/{token_id}", response_model=OkResp[CommonDataResp])
async def revoke_token(
    token_id: int,
    db: Session = Depends(db_module.get_db),
    user: User = Depends(get_session_user),
):
    target_user_id = access_token.revoke(db, user, token_id)
    await sampleConnectionManager.close_user_connections(target_user_id)
    return OkResp(data=CommonDataResp(ok=True))


@router.get(
    "",
    response_model=OkRespWithMeta[List[UserResponse]],
    status_code=status.HTTP_200_OK,
)
async def list_users(
    authorization: HTTPAuthorizationCredentials = Security(security),
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(db_module.get_db),
    page: int | None = 0,
    size: int | None = 10,
    username: str | None = None,
):
    """
    List all users
    """

    # business logic
    data, total = await service.list_by(db=db, page=page, size=size, username=username)

    meta_data = MetaData(total=total, page=page, size=len(data))

    # response
    return OkRespWithMeta[List[UserResponse]](meta_data=meta_data, data=data)


@router.get("/me", response_model=OkResp[UserResponse], status_code=status.HTTP_200_OK)
async def get_me(
    authorization: HTTPAuthorizationCredentials = Security(security),
    current_user: User = Depends(get_current_user),
):
    """
    Get current user information
    """

    # response
    return OkResp[UserResponse](data=UserResponse.model_validate(current_user))


@router.post(
    "/signup",
    response_model=OkResp[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def signup(cmd: SignupCommand, db: Session = Depends(db_module.get_db)):
    """仅空库允许通过网页初始化首个管理员，之后拒绝公开注册。"""

    # business logic
    data = await service.signup(db=db, cmd=cmd)

    # response
    return OkResp[UserResponse](data=data)


@router.post(
    "/login",
    response_model=OkResp[LoginResponse],
    status_code=status.HTTP_200_OK,
)
async def login(cmd: LoginCommand, db: Session = Depends(db_module.get_db)):
    """
    User login, get an access token for future requests
    """

    # business logic
    data = await service.login(db=db, cmd=cmd)

    # response
    return OkResp[LoginResponse](data=data)


@router.post(
    "/logout",
    response_model=OkResp[LogoutResponse],
    status_code=status.HTTP_200_OK,
)
async def logout(
    authorization: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(db_module.get_db),
    current_user: User = Depends(get_current_user),
):
    """
    User logout.

    网页退出时丢弃本地会话；停用账号或重置密码会使其全部旧凭据失效。
    """

    # response
    data = LogoutResponse(msg="succeeded")
    return OkResp[LogoutResponse](data=data)
