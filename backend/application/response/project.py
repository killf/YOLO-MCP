from datetime import datetime

from typing import Union
from pydantic import BaseModel, EmailStr, Field

from backend.application.response.base import UserResp
from backend.application.command.training import StartTrainingCommand


class ProjectResponse(BaseModel):
    ai_algorithm: str = "yolo"
    dataset_prefix: str = ""
    ai_model_name: str | None = None
    training_config: StartTrainingCommand | None = None
    id: Union[int, None] = Field(default=None, description="description: project id")
    name: Union[str, None] = Field(
        default=None, description="description: project name"
    )
    description: Union[str, None] = Field(
        default=None, description="description: project description"
    )
    tips: Union[str, None] = Field(
        default=None, description="description: project tips"
    )
    config: Union[str, None] = Field(
        default=None, description="description: project config content"
    )
    media_type: Union[str, None] = Field(
        default=None, description="description: project media type: IMAGE, VIDEO, AUDIO"
    )
    status: Union[str, None] = Field(
        default=None,
        description=(
            "Project status: DRAFT, IMPORTED, CONFIGURED, INPROGRESS, FINISHED"
        ),
    )
    created_at: Union[datetime, None] = Field(
        default=None, description="description: project created at time"
    )
    created_by: Union[UserResp, None] = Field(
        default=None, description="description: project created by"
    )


class ProjectStatics(BaseModel):
    train: int = Field(default=0, description="项目内训练集样本数")
    test: int = Field(default=0, description="项目内测试集样本数")
    new: Union[int, None] = Field(
        default=0,
        description="description: count for project data have not labeled yet",
    )
    done: Union[int, None] = Field(
        default=0, description="description: count for project data already labeled"
    )
    skipped: Union[int, None] = Field(
        default=0, description="description: count for project data skipped"
    )


class ProjectResponseWithStatics(ProjectResponse):
    stats: Union[ProjectStatics, None] = None


class User(BaseModel):
    id: Union[int, None] = None
    username: Union[EmailStr, None] = None
