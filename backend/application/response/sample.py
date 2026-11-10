from datetime import datetime

from typing import List, Union
from pydantic import BaseModel, Field

from backend.application.response.base import UserResp
from backend.domain.models.sample import DatasetSplit


class CreateSampleResponse(BaseModel):
    ids: Union[List[int], None] = Field(
        default=None, description="description: attachment ids"
    )


class SampleResponse(BaseModel):
    split: DatasetSplit = DatasetSplit.TRAIN
    id: Union[int, None] = Field(default=None, description="description: annotation id")
    inner_id: Union[int, None] = Field(
        default=None, description="description: inner id of a sample in project"
    )
    state: Union[str, None] = Field(
        default=None,
        description="Sample state: NEW (未开始), DONE (完成), SKIPPED (跳过)",
    )
    data: Union[object, None] = Field(
        default=None,
        description="description: sample data, include filename, file url, or result",
    )
    file: Union[object, None] = Field(
        default=None, description="description: media attachment file"
    )
    is_pre_annotated: Union[bool, None] = Field(
        default=False, description="description: is pre annotated"
    )
    annotated_count: Union[int, None] = Field(
        default=0, description="description: annotate result count"
    )
    created_at: Union[datetime, None] = Field(
        default=None, description="description: project created at time"
    )
    created_by: Union[UserResp, None] = Field(
        default=None, description="description: project created by"
    )
    updated_at: Union[datetime, None] = Field(
        default=None, description="description: project updated at time"
    )
    updaters: List[UserResp] | None = Field(
        default=[], description="description: sample updaters"
    )
