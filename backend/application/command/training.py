import json
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)


def validate_extra_params(value: dict) -> dict:
    """校验附加参数为有限 JSON 对象，拒绝覆盖表单和项目文件、进程配置。"""
    if not isinstance(value, dict):
        raise ValueError("自定义训练参数必须是 JSON 对象")
    conflicts = RESERVED_TRAINING_PARAMETERS.intersection(value)
    if conflicts:
        raise ValueError("自定义参数不能覆盖：" + ", ".join(sorted(conflicts)))
    json.dumps(value, allow_nan=False)
    return value


RESERVED_TRAINING_PARAMETERS = {
    "algorithm",
    "initial_model",
    "model",
    "data",
    "epochs",
    "imgsz",
    "batch",
    "device",
    "workers",
    "project",
    "name",
    "exist_ok",
    "save_dir",
    "save",
    "task",
    "mode",
    "resume",
    "pretrained",
    "cfg",
    "work_dir",
    "models_dir",
    "result_file",
    "extra_params",
    "augmentation",
    "training_scope",
    "unfreeze_steps",
    "resume_checkpoint",
}


class StartTrainingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["yolo26_detect"] = Field(
        default="yolo26_detect", description="训练算法，目前仅支持 YOLO26 目标检测"
    )

    initial_model: str = Field(
        default="yolo26s.pt",
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.pt$",
        description="官方 YOLO26 权重名称，或当前项目已有的模型文件名",
    )
    epochs: int = Field(default=100, ge=1, le=10000, description="训练轮数")
    imgsz: int = Field(
        default=1024,
        ge=32,
        le=4096,
        multiple_of=32,
        description="输入图片尺寸，单位像素",
    )
    batch: int = Field(
        default=2, ge=-1, le=1024, description="每批图片数；-1 为自动选择"
    )
    lr0: float | None = Field(
        default=None, ge=0, le=1, allow_inf_nan=False, description="初始学习率"
    )
    augmentation: bool = Field(default=True, description="启用训练图像增强")
    training_scope: Literal["full", "head", "head_then_full"] = Field(
        default="full", description="全部参数、仅 Detect 检测头或检测头预热后解冻"
    )
    unfreeze_steps: int = Field(
        default=100, ge=1, le=10000000, description="解冻前检测头的优化器更新次数"
    )
    extra_params: dict[str, JsonValue] = Field(
        default_factory=dict, description="额外 YOLO 训练参数，不覆盖基础表单或项目路径"
    )

    @field_validator("extra_params")
    @classmethod
    def validate_extra_params(cls, value: dict) -> dict:
        return validate_extra_params(value)

    @model_validator(mode="after")
    def validate_learning_rate(self):
        if self.lr0 is not None and "lr0" in self.extra_params:
            raise ValueError("学习率已单独设置，自定义参数中不能重复设置 lr0")
        if (
            self.training_scope != "full"
            and self.extra_params.get("freeze") is not None
        ):
            raise ValueError("选择检测头训练时，不能在自定义参数中重复设置 freeze")
        if self.training_scope != "full" and self.extra_params.get("compile"):
            raise ValueError("检测头冻结与解冻暂不支持 compile，请关闭编译")
        return self

    @field_validator("batch")
    @classmethod
    def validate_batch(cls, value: int) -> int:
        if value == 0:
            raise ValueError("batch 必须为 -1 或正整数")
        return value
