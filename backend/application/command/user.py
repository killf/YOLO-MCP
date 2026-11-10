from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupCommand(BaseModel):
    username: EmailStr
    password: str = Field(min_length=6, max_length=18)


class LoginCommand(BaseModel):
    username: EmailStr
    password: str = Field(min_length=6, max_length=18)


class CreateUserCommand(SignupCommand):
    model_config = ConfigDict(extra="forbid")

    is_admin: bool = False


class UpdateUserCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_admin: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=6, max_length=18)


class CreateTokenCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    expires_days: int | None = Field(default=90, ge=1, le=3650)
