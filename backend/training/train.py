"""使用本地图片与 YOLO 标注训练，模型和日志保存在项目目录。"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
from datetime import datetime
from functools import partial
from pathlib import Path, PurePosixPath
from typing import TextIO
from zoneinfo import ZoneInfo

import yaml

from backend.application.command.training import (
    RESERVED_TRAINING_PARAMETERS,
    validate_extra_params,
)

LOGGER = logging.getLogger("backend.training")
OFFICIAL_MODELS = {f"yolo26{size}.pt" for size in "nsmlx"}
PAUSED_EXIT_CODE = 75

# 中文说明覆盖当前框架参数；框架新增字段时保留配置文件中的原文说明。
PARAMETER_DESCRIPTIONS = {
    "time": "最长训练时间（小时）；设置后优先于训练轮数。",
    "patience": "验证指标连续多少轮未改善后提前停止。",
    "save_period": "每隔多少轮保存检查点；小于 1 时禁用周期保存。",
    "cache": "图片缓存：false 禁用，true 或 ram 使用内存，disk 使用磁盘。",
    "cls_remap": "微调不同数据集时，按类别名称匹配并重映射分类头权重。",
    "optimizer": "优化器：auto、SGD、MuSGD、Adam、Adamax、AdamW、NAdam、RAdam、RMSProp。",
    "verbose": "是否输出详细日志。",
    "seed": "随机种子（整数）。",
    "deterministic": "是否启用确定性计算，以提高可复现性，可能降低速度。",
    "single_cls": "是否把所有类别合并为单一类别。",
    "rect": "是否使用矩形批次训练，减少图片填充。",
    "cos_lr": "是否使用余弦学习率调度。",
    "close_mosaic": "最后多少轮关闭 Mosaic 增强；0 表示始终开启。",
    "amp": "训练精度：true 或 fp16 为自动混合精度，bf16 为 BF16，false 或 fp32 为全精度。",
    "fraction": "训练数据使用比例或数量；1.0 使用全部数据，整数大于 1 表示数量。",
    "profile": "是否在训练过程中分析 ONNX 和 TensorRT 的推理速度。",
    "freeze": "冻结前 N 层，或指定层索引、模块名列表；null 表示不冻结。",
    "multi_scale": "多尺度训练相对图片尺寸的变化幅度；0 表示关闭。",
    "compile": "是否使用 torch.compile，可传 false、true 或受支持的编译模式字符串。",
    "channels_last": "是否使用 channels-last 内存布局；null 表示按设备与平台自动选择。",
    "overlap_mask": "仅分割：训练时是否将实例掩码合并到同一张掩码。",
    "mask_ratio": "仅分割：训练掩码的下采样倍数。",
    "dropout": "仅分类：分类头的 Dropout 概率。",
    "val": "训练过程中是否执行验证。",
    "split": "独立验证使用的数据划分：val、test 或 train。",
    "save_json": "验证时是否保存 COCO 格式结果；部分算法保存专用格式。",
    "conf": "预测或验证的置信度阈值；null 使用框架默认阈值。",
    "iou": "非极大值抑制（NMS）的 IoU 阈值，范围 0–1。",
    "max_det": "每张图片最多保留的检测目标数量。",
    "quantize": "计算或导出精度，如 fp16、fp32、int8；训练时 int8 用于量化感知训练。",
    "dnn": "仅 ONNX 推理：是否使用 OpenCV DNN 后端。",
    "plots": "是否保存训练、验证图表及可视化图片。",
    "nms": "是否启用 NMS；null 使用默认处理，false 对可用模型使用无 NMS 检测头。",
    "source": "仅预测：图片、目录、视频、URL 或流地址。",
    "vid_stride": "仅视频预测：每隔多少帧读取一次。",
    "stream_buffer": "仅流预测：是否缓存所有帧；false 优先处理最新帧。",
    "visualize": "是否可视化预测特征，或验证时的正确、漏检和误检结果。",
    "augment": "仅预测：是否使用测试时增强。",
    "agnostic_nms": "是否使用不区分类别的 NMS。",
    "classes": "按类别编号筛选目标，支持单个整数或整数列表。",
    "retina_masks": "仅分割预测：是否使用高分辨率掩码。",
    "embed": "仅预测：返回指定层索引的特征向量。",
    "show": "仅预测：是否在窗口中显示结果。",
    "save_frames": "仅视频预测：是否保存单帧结果。",
    "save_txt": "是否将预测结果保存为文本。",
    "save_conf": "保存文本结果时是否包含置信度。",
    "save_crop": "仅预测：是否保存检测目标的裁剪图片。",
    "show_labels": "可视化时是否显示类别名称。",
    "show_conf": "可视化时是否显示置信度。",
    "show_boxes": "可视化时是否绘制边界框。",
    "line_width": "可视化边界框线宽（像素）；null 表示自动选择。",
    "format": "仅导出：目标格式，如 torchscript、onnx、engine、openvino。",
    "optimize": "仅 DEEPX 导出：是否采用更高等级的编译优化。",
    "dynamic": "仅导出：是否启用动态输入尺寸。",
    "simplify": "仅导出：是否简化 ONNX 中间计算图。",
    "opset": "仅 ONNX 相关导出：指定算子集版本；null 使用框架默认值。",
    "workspace": "仅 TensorRT 导出：工作空间大小（GiB）。",
    "lr0": "初始学习率；常用值 SGD 为 0.01，Adam/AdamW 为 0.001。",
    "lrf": "最终学习率系数；最终学习率等于 lr0 × lrf。",
    "momentum": "SGD 动量或 Adam 的 beta1 系数。",
    "weight_decay": "权重衰减（L2 正则化系数）。",
    "warmup_epochs": "学习率预热轮数，允许小数。",
    "warmup_momentum": "预热阶段的初始动量。",
    "warmup_bias_lr": "预热阶段偏置参数的初始学习率。",
    "distill_model": "知识蒸馏使用的教师模型路径；null 表示不指定。",
    "dis": "知识蒸馏损失权重。",
    "box": "边界框回归损失权重。",
    "cls": "分类损失权重。",
    "cls_pw": "类别不平衡权重指数；0 禁用，1 按类别频率倒数加权。",
    "dfl": "边界框距离损失权重；YOLO26 的无 DFL 检测头使用 L1 距离。",
    "pose": "仅姿态估计：姿态损失权重。",
    "kobj": "仅姿态估计：关键点目标存在性损失权重。",
    "rle": "仅姿态估计：RLE 损失权重。",
    "angle": "仅旋转框检测：角度损失权重。",
    "dlog": "仅深度估计：对数深度损失权重。",
    "dgrad": "仅深度估计：梯度损失权重。",
    "dlam": "仅深度估计：尺度不变损失系数；1 为尺度不变，0 为对数 RMSE。",
    "nbs": "标称批量大小；框架据此计算梯度累积次数。",
    "hsv_h": "HSV 色调增强幅度。",
    "hsv_s": "HSV 饱和度增强幅度。",
    "hsv_v": "HSV 明度增强幅度。",
    "degrees": "随机旋转角度的正负范围（度）。",
    "translate": "随机平移相对于图片尺寸的比例。",
    "scale": "随机缩放幅度；通常传数值，具体格式由当前框架校验。",
    "shear": "随机错切角度的正负范围（度）。",
    "perspective": "随机透视变换幅度，常用范围 0–0.001。",
    "flipud": "垂直翻转概率，范围 0–1。",
    "fliplr": "水平翻转概率，范围 0–1。",
    "bgr": "交换 RGB 与 BGR 通道的概率。",
    "mosaic": "Mosaic 拼图增强概率。",
    "mixup": "MixUp 图像混合增强概率。",
    "cutmix": "CutMix 区域混合增强概率。",
    "copy_paste": "仅分割、语义分割或旋转框：复制粘贴增强比例。",
    "copy_paste_mode": "复制粘贴策略：flip 翻转或 mixup 混合。",
    "auto_augment": "仅分类：自动增强策略，支持 randaugment、autoaugment、augmix。",
    "erasing": "仅分类：随机擦除概率，范围 0–1。",
    "tracker": "仅跟踪：跟踪器配置文件名。",
}


def training_parameter_catalog() -> list[dict]:
    """读取框架默认值并补充中文说明，新增参数保留原文，排除系统管理字段。"""
    from ultralytics.cfg import DEFAULT_CFG_DICT
    from ultralytics.utils import DEFAULT_CFG_PATH

    descriptions = {}
    for line in Path(DEFAULT_CFG_PATH).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(\w+):.*?#\s*(.+)$", line)
        if match:
            descriptions[match[1]] = match[2]

    return [
        {
            "name": name,
            "default": value,
            "description": PARAMETER_DESCRIPTIONS.get(
                name, descriptions.get(name, "当前框架未提供参数说明")
            ),
        }
        for name, value in DEFAULT_CFG_DICT.items()
        if name not in RESERVED_TRAINING_PARAMETERS
    ]


def validate_training_options(parameters: dict) -> dict:
    """使用当前 Ultralytics 校验附加参数名称、类型和范围，不加载模型。"""
    parameters = validate_extra_params(parameters)
    if not parameters:
        return parameters

    from ultralytics.cfg import DEFAULT_CFG_DICT, get_cfg

    unknown = parameters.keys() - DEFAULT_CFG_DICT.keys()
    if unknown:
        raise ValueError("未知训练参数：" + ", ".join(sorted(unknown)))
    try:
        get_cfg(overrides=parameters.copy())
    except (TypeError, ValueError, SyntaxError) as error:
        raise ValueError(str(error).splitlines()[0]) from None
    return parameters


class Tee(io.TextIOBase):
    """将终端输出同时写入训练日志，保留框架的进度信息。"""

    def __init__(self, terminal: TextIO, logfile: TextIO) -> None:
        self.terminal = terminal
        self.logfile = logfile

    def write(self, text: str) -> int:
        self.terminal.write(text)
        self.logfile.write(text)
        self.logfile.flush()

        return len(text)

    def flush(self) -> None:
        self.terminal.flush()
        self.logfile.flush()


def _dataset_file(directory: Path, value: str) -> Path:
    """解析数据集内的相对文件名，拒绝路径越界和链接逃逸。"""
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or any(char in value for char in ("\\", ":", "\x00", "\r", "\n"))
    ):
        raise ValueError(f"Invalid dataset-relative path: {value!r}")
    resolved = (directory / path).resolve()
    if not resolved.is_relative_to(directory.resolve()):
        raise ValueError(f"Invalid dataset-relative path: {value!r}")
    return resolved


def prepare_dataset(dataset: Path, destination: Path, snapshot: Path) -> Path:
    """准备独立训练数据；已有 run 快照原地校验，不重复复制图片和输入清单。"""
    # 1. 外部数据复制到 run；页面已冻结的输入直接使用，禁用下载脚本。
    in_place = dataset.resolve() == destination.resolve()
    if not in_place:
        snapshot.mkdir(parents=True, exist_ok=True)
    destination.mkdir(parents=True, exist_ok=True)
    original = _dataset_file(dataset, "data.yaml")
    data = yaml.safe_load(original.read_text(encoding="utf-8-sig"))
    if not in_place:
        shutil.copy2(original, snapshot / "data.yaml")
    data.pop("download", None)
    data["path"] = str(destination.resolve())

    # 2. 只维护训练、测试两份清单，逐张复制图片和标签以冻结本次输入。
    copied = set()
    backgrounds = 0
    for split in ("train", "test"):
        filename = data.get(split)
        if filename != f"{split}.txt":
            raise ValueError(f"data.yaml {split} must reference {split}.txt")
        listing = _dataset_file(dataset, filename)
        if not in_place:
            shutil.copy2(listing, snapshot / filename)
        images = []
        for value in listing.read_text(encoding="utf-8-sig").splitlines():
            value = value.strip()
            if not value:
                continue
            relative = PurePosixPath(value)
            if len(relative.parts) < 2 or relative.parts[0] != "images":
                raise ValueError(f"{filename} must reference files under images/")
            source = _dataset_file(dataset, value)
            target = _dataset_file(destination, value)
            if not source.is_file():
                raise ValueError(f"Dataset image does not exist: {value!r}")
            if value not in copied:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not in_place:
                    shutil.copy2(source, target)
                label = str(
                    PurePosixPath("labels", *relative.parts[1:]).with_suffix(".txt")
                )
                original_label = _dataset_file(dataset, label)
                if original_label.is_file():
                    target_label = _dataset_file(destination, label)
                    target_label.parent.mkdir(parents=True, exist_ok=True)
                    if not in_place:
                        shutil.copy2(original_label, target_label)
                else:
                    backgrounds += 1
                copied.add(value)
            images.append(f"./{relative.as_posix()}")
        if not images:
            raise ValueError(f"{filename} contains no images")
        (destination / filename).write_text(
            "".join(f"{image}\n" for image in images), encoding="utf-8"
        )

    # 3. 测试集同时用于每轮验证和最优权重选择，没有第三份评估数据。
    data["val"] = "test.txt"
    config = destination / "data.yaml"
    config.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    LOGGER.info("Prepared %s local images, %s backgrounds", len(copied), backgrounds)
    return config


def _next_run_id(dataset: Path) -> str:
    """按现有模型和运行目录生成日期编号，不创建占号或锁。"""
    day = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d")
    number = 0
    for directory in (dataset / "models", dataset / "runs"):
        for path in directory.glob(f"{day}-*"):
            match = re.match(rf"{day}-(\d+)(?:-|\.|$)", path.name)
            if match:
                number = max(number, int(match[1]))
    return f"{day}-{number + 1}"


def error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _initial_weights(model: str) -> str:
    """官方初始权重跨项目共用，用户提供的项目权重或路径保持原样。"""
    if model not in OFFICIAL_MODELS:
        return model
    from backend.common.storage import get_storage

    path = get_storage().path(f"models/ultralytics/{model}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def run_training(
    dataset: Path,
    parameters: dict[str, object],
    work_dir: Path | None = None,
    result_file: Path | None = None,
    models_dir: Path | None = None,
    resume_checkpoint: Path | None = None,
) -> int:
    """冻结本地输入并训练，将最佳权重复制到项目 models/，日志留在 runs/。"""
    dataset = dataset.resolve()
    models = (models_dir or dataset / "models").resolve()
    run_id = _next_run_id(models.parent)
    if work_dir is None:
        parent = dataset / "runs"
        parent.mkdir(parents=True, exist_ok=True)
        run_dir = Path(tempfile.mkdtemp(prefix=f"{run_id}-", dir=parent))
    else:
        run_dir = work_dir.resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

    # 1. 独立进程内同时记录控制台和训练日志，便于页面查看。
    with (
        (run_dir / "train.log").open(
            "a" if resume_checkpoint else "w", encoding="utf-8", buffering=1
        ) as logfile,
        Tee(sys.stdout, logfile) as stdout,
        Tee(sys.stderr, logfile) as stderr,
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
        try:
            LOGGER.info("Run %s, local dataset %s", run_id, dataset)
            data = prepare_dataset(dataset, run_dir / "dataset", run_dir / "input")
            train_args = parameters.copy()

            # 2. 复用当前 Python 的 GPU 后端，测试集验证结果决定 best.pt。
            import torch
            from ultralytics import YOLO
            from backend.training.control import (
                ControlledDetectionTrainer,
                TrainingPaused,
            )

            if "device" not in train_args:
                train_args["device"] = (
                    "0"
                    if torch.cuda.is_available()
                    else "mps" if torch.backends.mps.is_available() else "cpu"
                )
            LOGGER.info(
                "Training device: %s, parameters: %s", train_args["device"], train_args
            )
            multi_device = "," in str(train_args["device"]) or isinstance(
                train_args["device"], (list, tuple)
            )
            augmentation = train_args.pop("augmentation", True)
            training_scope = train_args.pop("training_scope", "full")
            unfreeze_steps = train_args.pop("unfreeze_steps", 100)
            if multi_device and (
                not augmentation or training_scope != "full" or resume_checkpoint
            ):
                raise ValueError(
                    "暂停恢复与检测头训练目前仅支持单设备，请设置 YOLO_MCP_DEVICE 为单个设备"
                )
            trainer = (
                None
                if multi_device
                else partial(
                    ControlledDetectionTrainer,
                    augmentation=augmentation,
                    training_scope=training_scope,
                    unfreeze_steps=unfreeze_steps,
                    control_dir=run_dir,
                )
            )
            initial_model = train_args.pop("model")
            try:
                model = YOLO(
                    str(resume_checkpoint)
                    if resume_checkpoint
                    else _initial_weights(initial_model)
                )
            except Exception as error:
                from backend.inference import model_load_error

                message = model_load_error(error, Path(initial_model).name)
                if result_file is not None:
                    result_file.write_text(
                        json.dumps({"error_message": message}), encoding="utf-8"
                    )
                raise RuntimeError(message) from None
            try:
                model.train(
                    trainer=trainer,
                    resume=str(resume_checkpoint) if resume_checkpoint else False,
                    data=str(data),
                    project=str(run_dir),
                    name="training",
                    **train_args,
                )
            except TrainingPaused:
                if result_file is not None:
                    result_file.write_text(
                        json.dumps({"status": "PAUSED"}), encoding="utf-8"
                    )
                LOGGER.info("Training paused after checkpoint save")
                return PAUSED_EXIT_CODE

            # 3. 只发布最佳权重，其他训练文件保留在本次工作目录。
            best = Path(model.trainer.best)
            models.mkdir(parents=True, exist_ok=True)
            published = models / f"{run_id}.pt"
            shutil.copy2(best, published)
            LOGGER.info("Saved model: %s", published)
            if result_file is not None:
                result_file.write_text(
                    json.dumps(
                        {
                            "run_id": run_id,
                            "model_name": published.name,
                            "model_path": str(published),
                            "metrics": {
                                key: float(value)
                                for key, value in model.trainer.metrics.items()
                            },
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            return 0
        except (Exception, KeyboardInterrupt) as exc:
            LOGGER.error("Run %s failed: %s", run_id, error_text(exc))
            return 1
        finally:
            LOGGER.removeHandler(handler)


def terminate(signum: int, frame: object) -> None:
    raise KeyboardInterrupt(f"Received signal {signum}")


def main() -> int:
    """解析命令行参数，启动一次离线训练。"""
    # 1. 解析工作目录、训练参数和数据增强参数。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="YOLO 数据目录，内含 data.yaml、train.txt、test.txt、images/ 和 labels/",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=None,
        help="产出模型目录，默认 --data 目录下的 models/；页面训练使用项目 models/",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="训练快照、权重和日志目录，默认 --data 目录下的 runs/<编号>/",
    )
    parser.add_argument(
        "--result-file",
        type=Path,
        help="将训练编号、模型地址和指标写入 JSON，供页面训练记录读取",
    )
    parser.add_argument(
        "--extra-params",
        default="{}",
        help='附加训练参数的 JSON 对象，例如 \'{"lr0": 0.001, "amp": false}\'',
    )
    parser.add_argument(
        "--resume-checkpoint", type=Path, help="从本次运行的暂停检查点继续"
    )
    parser.add_argument(
        "--augmentation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="启用训练图像增强",
    )
    parser.add_argument(
        "--training-scope",
        choices=["full", "head", "head_then_full"],
        default="full",
        help="训练全部参数、仅检测头或检测头预热后解冻",
    )
    parser.add_argument(
        "--unfreeze-steps", type=int, default=100, help="解冻前检测头的优化器更新次数"
    )

    # 模型、训练规模和计算设备。
    parser.add_argument(
        "--model", default="yolo26s.pt", help="初始权重名称或本地路径，默认 yolo26s.pt"
    )
    parser.add_argument("--epochs", type=int, default=100, help="训练轮数，默认 100")
    parser.add_argument(
        "--imgsz", type=int, default=1024, help="训练输入目标尺寸，单位像素，默认 1024"
    )
    parser.add_argument(
        "--batch", type=int, default=-1, help="每批图片数；-1 使用 YOLO 自动 batch"
    )
    parser.add_argument(
        "--device", help="计算设备，如 0、0,1、mps、cpu；不传则选择 PyTorch 可用后端"
    )
    parser.add_argument(
        "--workers", type=int, help="数据加载进程数，未指定时使用 YOLO 默认值"
    )

    # 优化、随机性与训练输出。
    parser.add_argument("--lr0", type=float, help="初始学习率，范围 0 至 1")
    parser.add_argument(
        "--optimizer", help="优化器名称，如 SGD、AdamW、auto，默认由 YOLO 决定"
    )
    parser.add_argument(
        "--seed", type=int, help="随机种子，用于复现实验，默认由 YOLO 决定"
    )
    parser.add_argument(
        "--amp", action=argparse.BooleanOptionalAction, help="启用或关闭混合精度训练"
    )
    parser.add_argument(
        "--plots",
        action=argparse.BooleanOptionalAction,
        help="生成或关闭训练和评估图表",
    )

    # 输入尺寸、几何变化和颜色增强；概率或幅度沿用 YOLO 的参数含义。
    parser.add_argument(
        "--rect",
        action=argparse.BooleanOptionalAction,
        help="按宽高比分组，减少训练补边",
    )
    parser.add_argument(
        "--multi-scale",
        type=float,
        help="输入尺寸随机变化比例，如 0.25 表示正负百分之 25",
    )
    parser.add_argument(
        "--close-mosaic", type=int, help="训练结束前关闭 Mosaic 增强的轮数"
    )
    parser.add_argument("--hsv-h", type=float, help="色相随机扰动幅度")
    parser.add_argument("--hsv-s", type=float, help="饱和度随机扰动幅度")
    parser.add_argument("--hsv-v", type=float, help="亮度随机扰动幅度")
    parser.add_argument("--translate", type=float, help="水平和垂直随机平移的最大比例")
    parser.add_argument(
        "--scale", type=float, help="随机缩放幅度，如 0.5 表示约 0.5 至 1.5 倍"
    )
    parser.add_argument("--fliplr", type=float, help="水平翻转概率，取值 0 至 1")
    parser.add_argument("--flipud", type=float, help="垂直翻转概率，取值 0 至 1")
    parser.add_argument("--degrees", type=float, help="随机旋转的最大角度，单位度")
    parser.add_argument(
        "--mosaic", type=float, help="使用四图拼接增强的概率，取值 0 至 1"
    )
    parser.add_argument(
        "--mixup", type=float, help="混合两张图片及其标注的概率，取值 0 至 1"
    )

    args = parser.parse_args()

    # 字体与框架配置跨训练共用，必须在参数校验首次导入 Ultralytics 前设置。
    from backend.common.storage import get_storage

    os.environ.setdefault("YOLO_CONFIG_DIR", str(get_storage().path(".ultralytics")))

    # 2. 分离工作目录，未设置的可选参数不传给 YOLO。
    parameters = vars(args).copy()
    dataset = parameters.pop("data").resolve()
    models_dir = parameters.pop("models_dir")
    work_dir = parameters.pop("work_dir")
    result_file = parameters.pop("result_file")
    resume_checkpoint = parameters.pop("resume_checkpoint")
    extra_params = parameters.pop("extra_params")
    parameters = {key: value for key, value in parameters.items() if value is not None}

    # JSON 参数只补充未指定的可选参数，冲突或非法输入在启动训练前返回。
    try:
        overrides = validate_training_options(json.loads(extra_params))
        if parameters["unfreeze_steps"] < 1:
            raise ValueError("解冻步数必须为正整数")
        if parameters["training_scope"] != "full" and (
            overrides.get("freeze") is not None or overrides.get("compile")
        ):
            raise ValueError("检测头训练不能同时设置 freeze 或 compile")
        conflicts = parameters.keys() & overrides.keys()
        if conflicts:
            raise ValueError("重复训练参数：" + ", ".join(sorted(conflicts)))
    except (ImportError, ValueError, TypeError) as error:
        parser.error(str(error))
    parameters.update(overrides)

    # 3. 训练入口不安装依赖，不修改既有 PyTorch 运行时。
    previous = signal.signal(signal.SIGTERM, terminate)
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    try:
        return run_training(
            dataset, parameters, work_dir, result_file, models_dir, resume_checkpoint
        )
    except (Exception, KeyboardInterrupt) as exc:
        print(error_text(exc), file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    raise SystemExit(main())
