"""在训练开始时从项目原图和数据库标注生成本次运行的 YOLO 数据集。"""

import json
from io import BytesIO
from pathlib import Path, PurePosixPath

import yaml
from fastapi import HTTPException
from loguru import logger
from PIL import Image
from sqlalchemy.orm import Session

from backend.common.storage import get_storage
from backend.domain.models.sample import DatasetSplit, SampleState, ProjectSample
from backend.domain.models.project import Project


def dataset_classes(config: dict) -> list[dict]:
    """按配置顺序返回检测类别，顺序决定 YOLO 类别编号。"""
    tools = config.get("tools", [])
    if any(tool["tool"] != "rectTool" for tool in tools):
        raise HTTPException(422, "当前 YOLO 数据集使用图片矩形框标注")

    attributes = list(config.get("attributes", []))
    for tool in tools:
        attributes.extend(tool.get("config", {}).get("attributes", []))
    if not attributes:
        raise HTTPException(422, "请配置目标检测类别")
    return attributes


def _image_name(sample: ProjectSample) -> str:
    return f"{sample.id}{PurePosixPath(sample.file.filename).suffix.lower()}"


def _label_text(result: dict, classes: list[dict], width: int, height: int) -> str:
    """裁剪并归一化有效框；背景样本返回空标签，非法框返回 422。"""
    class_ids = {attribute["value"]: index for index, attribute in enumerate(classes)}
    lines = []
    for box in result.get("rectTool", {}).get("result", []):
        if not box.get("valid", True):
            continue
        x1, y1 = max(0, box["x"]), max(0, box["y"])
        x2 = min(width, box["x"] + box["width"])
        y2 = min(height, box["y"] + box["height"])
        if x2 <= x1 or y2 <= y1:
            raise HTTPException(422, "标注框必须与图片相交并具有正的宽高")
        if box["label"] not in class_ids:
            raise HTTPException(422, "标注类别不在当前项目配置中")
        lines.append(
            f"{class_ids[box['label']]} {(x1 + x2) / (2 * width):.8f} "
            f"{(y1 + y2) / (2 * height):.8f} {(x2 - x1) / width:.8f} "
            f"{(y2 - y1) / height:.8f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def render_sample(
    sample: ProjectSample, classes: list[dict], data: dict | None = None
) -> tuple[bytes, str]:
    """读取原图和标注，返回方向一致的图片字节及 YOLO 标签，不修改原图。"""
    content = get_storage().read_bytes(sample.file.path)
    annotation = json.loads(sample.data) if data is None else data
    result = json.loads(annotation["result"])
    with Image.open(BytesIO(content)) as original:
        image_format = original.format
        if result.get("rotate"):
            image = original.rotate(result["rotate"], expand=True)
            try:
                buffer = BytesIO()
                image.save(buffer, format=image_format)
                content = buffer.getvalue()
                width, height = image.size
            finally:
                image.close()
        else:
            width, height = original.size
    return content, _label_text(result, classes, width, height)


def create_run_dataset(db: Session, project: Project, directory: Path) -> None:
    """按当前类别、标注和数据划分写入独立 run，已删除或未完成样本不进入快照。"""
    # 1. 一次读取本次完成样本，后续项目修改不再参与该次训练。
    classes = dataset_classes(json.loads(project.config))
    samples = (
        db.query(ProjectSample)
        .filter(
            ProjectSample.project_id == project.id,
            ProjectSample.deleted_at.is_(None),
            ProjectSample.state == SampleState.DONE.value,
        )
        .order_by(ProjectSample.id)
        .all()
    )
    if not {"train", "test"}.issubset({sample.split for sample in samples}):
        raise HTTPException(422, "训练集和测试集都需要至少一张已完成标注的图片")

    try:
        directory.mkdir()
        (directory / "images").mkdir()
        (directory / "labels").mkdir()
        listings = {split.value: [] for split in DatasetSplit}

        # 2. 每张图片和标签独立写入快照，旋转仅作用于训练副本。
        for sample in samples:
            image, label = render_sample(sample, classes)
            name = _image_name(sample)
            (directory / "images" / name).write_bytes(image)
            (directory / "labels" / f"{sample.id}.txt").write_text(
                label, encoding="utf-8"
            )
            listings[sample.split].append(f"./images/{name}")

        # 3. 清单只记录本次样本，路径相对于当前 run 的 dataset/。
        for split, lines in listings.items():
            (directory / f"{split}.txt").write_text(
                "".join(f"{line}\n" for line in lines), encoding="utf-8"
            )
        data = {
            "path": str(directory.resolve()),
            "train": "train.txt",
            "val": "test.txt",
            "test": "test.txt",
            "names": [attribute["key"] for attribute in classes],
        }
        (directory / "data.yaml").write_text(
            yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
        )
    except OSError:
        logger.error("Run dataset creation failed: project_id={}", project.id)
        raise HTTPException(500, "训练数据集生成失败，请检查本地文件后重试") from None
