from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: EmailStr
    is_admin: bool = False
    is_active: bool = True


class LoginResponse(BaseModel):
    token: str = Field(..., description="description: user credential")


class LogoutResponse(BaseModel):
    msg: str


class PersonalTokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    revoked_at: datetime | None


class CreatedTokenResponse(PersonalTokenResponse):
    token: str
