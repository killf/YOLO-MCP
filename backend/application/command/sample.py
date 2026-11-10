from typing import List, Union
from pydantic import BaseModel, Field

from backend.domain.models.sample import DatasetSplit, SampleState
from backend.inference import AnnotationAlgorithm


class AutoLabelCommand(BaseModel):
    """指定本次标注使用的算法和权重，不修改项目默认模型。"""

    algorithm: AnnotationAlgorithm
    model_name: str = Field(min_length=1, description="本次标注的模型权重名称")


class CreateSampleCommand(BaseModel):
    split: DatasetSplit = DatasetSplit.TRAIN
    file_id: int = Field(
        gt=0,
        description="description: attachment file id",
    )
    data: Union[dict, None] = Field(
        default=None,
        description="description: annotation result of sample",
    )


class DeleteSampleCommand(BaseModel):
    sample_ids: List[int] = Field(
        min_length=1,
        description="description: attachment file id",
    )


class PatchSampleCommand(BaseModel):
    split: DatasetSplit | None = None
    data: Union[dict, None] = Field(
        default=None,
        description="description: sample data, include result",
    )
    annotated_count: Union[int, None] = Field(
        default=0, description="description: annotate result count"
    )
    state: Union[SampleState, None] = Field(
        default=None,
        description="description: sample file state, must be 'SKIPPED', 'NEW', or None",
    )
