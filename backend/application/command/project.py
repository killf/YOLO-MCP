from typing import List, Union
from pydantic import BaseModel, Field

from backend.domain.models.project import MediaType
from backend.application.command.training import StartTrainingCommand
from backend.inference import AnnotationAlgorithm


class BasicConfigCommand(BaseModel):
    name: str = Field(description="description: project name", max_length=50)
    media_type: Union[MediaType, None] = Field(
        default=None, description="description: media type of project files"
    )
    description: str = Field(
        default=None, description="description: project description", max_length=500
    )
    tips: Union[str, None] = Field(
        default=None, description="description: project tips", max_length=1000
    )


class CollaboratorUpdateCommand(BaseModel):
    user_id: int = Field(description="description: user id")


class CollaboratorBatchCommand(BaseModel):
    user_ids: List[int] = Field(description="description: user ids")


class UpdateCommand(BaseModel):
    ai_algorithm: AnnotationAlgorithm = "yolo"
    ai_model_name: str | None = None
    training_config: StartTrainingCommand | None = None
    name: Union[str, None] = Field(
        default=None, description="description: project name", max_length=50
    )
    description: Union[str, None] = Field(
        default=None, description="description: project description", max_length=500
    )
    tips: Union[str, None] = Field(
        default=None, description="description: project tips", max_length=1000
    )
    media_type: Union[MediaType, None] = Field(
        default=None, description="description: media type of project files"
    )
    config: Union[str, None] = Field(
        default=None, description="description: project config content"
    )
