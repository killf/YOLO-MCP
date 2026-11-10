"""在框架训练流程中控制检测头训练、图像增强与 epoch 边界暂停。"""

from pathlib import Path

import torch
from ultralytics.models.yolo.detect import DetectionTrainer
from ultralytics.nn.modules import Detect
from ultralytics.utils.torch_utils import unwrap_model


class TrainingPaused(Exception):
    """检查点写入完成，交由调用方退出进程并释放 GPU。"""


class ControlledDetectionTrainer(DetectionTrainer):
    def __init__(
        self,
        *args,
        augmentation=True,
        training_scope="full",
        unfreeze_steps=100,
        control_dir: Path,
        **kwargs,
    ):
        self.augmentation = augmentation
        self.training_scope = training_scope
        self.unfreeze_steps = unfreeze_steps
        self.control_dir = control_dir
        self.optimizer_steps = 0
        self._baseline_frozen = None
        super().__init__(*args, **kwargs)

    def build_dataset(self, img_path, mode="train", batch=None):
        dataset = super().build_dataset(img_path, mode, batch)
        if mode == "train" and not self.augmentation:
            dataset.augment = False
            dataset.transforms = dataset.build_transforms(hyp=self.args)
        return dataset

    def _setup_train(self):
        # 1. 框架先创建完整优化器；冻结后保留全部参数组，解冻无需重置动量。
        super()._setup_train()
        network = unwrap_model(self.model)
        self._baseline_frozen = {
            name
            for name, parameter in network.named_parameters()
            if not parameter.requires_grad
        }
        self._baseline_layers = self.freeze_layer_names.copy()
        self._apply_scope()
        self.optimizer.register_step_post_hook(self._after_optimizer_step)

    def _apply_scope(self):
        if self._baseline_frozen is None:
            return
        network = unwrap_model(self.model)
        head_only = self.training_scope == "head" or (
            self.training_scope == "head_then_full"
            and self.optimizer_steps < self.unfreeze_steps
        )
        frozen = self._baseline_frozen.copy()
        self.freeze_layer_names = self._baseline_layers.copy()
        if head_only:
            head = network.model[-1]
            if not isinstance(head, Detect):
                raise ValueError("当前权重没有受支持的 Detect 检测头")
            head_parameters = {id(parameter) for parameter in head.parameters()}
            frozen.update(
                name
                for name, parameter in network.named_parameters()
                if id(parameter) not in head_parameters
            )
            self.freeze_layer_names.extend(
                f"model.{index}." for index in range(len(network.model) - 1)
            )
        for name, parameter in network.named_parameters():
            if parameter.dtype.is_floating_point:
                parameter.requires_grad_(name not in frozen)
        # 冻结参数时同时冻结 BN 统计，解冻时恢复训练模式。
        self._model_train()

    def _after_optimizer_step(self, optimizer, args, kwargs):
        # 2. 仅统计真实更新；梯度累积和 AMP 跳过的更新均不额外计数。
        self.optimizer_steps += 1
        if (
            self.training_scope == "head_then_full"
            and self.optimizer_steps == self.unfreeze_steps
        ):
            self._apply_scope()

    def _load_checkpoint_state(self, ckpt):
        super()._load_checkpoint_state(ckpt)
        self.optimizer_steps = ckpt.get("yolo_mcp_steps", self.optimizer_steps)
        self._apply_scope()

    def save_model(self):
        saved = super().save_model()
        # 3. 在验证和检查点保存完成后暂停；最终一轮和提前停止正常完成。
        if saved and not self.stop and (self.control_dir / "pause.request").is_file():
            checkpoint = torch.load(self.last, map_location="cpu", weights_only=False)
            checkpoint["yolo_mcp_steps"] = self.optimizer_steps
            temporary = self.control_dir / "resume.tmp"
            torch.save(checkpoint, temporary)
            temporary.replace(self.control_dir / "resume.pt")
            # 直接退出训练循环，避免 final_eval 清除优化器和 scaler 状态。
            raise TrainingPaused()
        return saved
