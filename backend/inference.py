"""在后端按需下载并加载检测模型，跨项目复用公共权重缓存。"""

from dataclasses import dataclass
from typing import Literal

from PIL import Image

from backend.common.storage import get_storage

AnnotationAlgorithm = Literal["yolo", "florence2", "grounding_dino_sam", "sam3"]

ANNOTATION_WEIGHTS = {
    "florence2": ("microsoft/Florence-2-base", "microsoft/Florence-2-large"),
    "grounding_dino_sam": ("grounding-dino-tiny+sam-vit-base",),
    "sam3": ("facebook/sam3",),
}


def model_load_error(error: Exception, weights: str) -> str:
    """只返回模型标识与可操作原因，不把下载异常中的凭据或内部路径传给用户。"""
    causes = []
    current = error
    while current is not None and all(current is not cause for cause in causes):
        causes.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(cause, ImportError) for cause in causes):
        return f"模型 {weights} 缺少推理依赖，请安装对应的 training、annotation 或官方 sam3 包"
    if any(
        type(cause).__name__ == "GatedRepoError"
        or getattr(getattr(cause, "response", None), "status_code", None) in {401, 403}
        for cause in causes
    ):
        return f"模型 {weights} 访问受限，请先取得模型访问权限并在服务运行环境完成 Hugging Face 登录"
    if any(isinstance(cause, PermissionError) for cause in causes):
        return (
            f"模型 {weights} 缓存写入失败，请检查 YOLO_MCP_DATA_DIR/models 的目录权限"
        )
    network_errors = {
        "RequestException",
        "HTTPError",
        "HfHubHTTPError",
        "LocalEntryNotFoundError",
        "ConnectionError",
        "Timeout",
        "TimeoutError",
        "RequestError",
    }
    if any(
        isinstance(cause, OSError)
        or any(base.__name__ in network_errors for base in type(cause).__mro__)
        for cause in causes
    ):
        return (
            f"模型 {weights} 权重下载或读取失败，请检查网络、磁盘空间和缓存目录后重试"
        )
    return f"模型 {weights} 加载失败，请检查推理依赖版本、设备及权重兼容性"


def _huggingface_cache() -> str:
    directory = get_storage().path("models/huggingface")
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


@dataclass
class Detection:
    """一条目标检测结果：原图像素坐标、类别名称与可选置信度。"""

    xyxy: list[float]
    label: str
    score: float | None = None


def torch_device(configured: str) -> str:
    """将已有 DEVICE 配置转换为 PyTorch 设备，不修改运行时。"""
    import torch

    if configured:
        return f"cuda:{configured}" if configured.isdecimal() else configured
    if torch.cuda.is_available():
        return "cuda:0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class FlorenceDetector:
    def __init__(self, weights: str, device: str):
        """按需下载到公共缓存，保留像素张量与模型精度一致。"""
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        self.device = device
        cache = _huggingface_cache()
        self.processor = AutoProcessor.from_pretrained(
            weights, trust_remote_code=True, cache_dir=cache
        )
        self.model = (
            AutoModelForCausalLM.from_pretrained(
                weights,
                trust_remote_code=True,
                cache_dir=cache,
                torch_dtype=(
                    torch.float16 if device.startswith("cuda") else torch.float32
                ),
                attn_implementation="eager",
            )
            .to(device)
            .eval()
        )

    def predict(self, image: Image.Image, labels: list[str]) -> list[Detection]:
        """先执行通用检测，再对未命中的项目类别执行短语定位。"""
        import torch

        def generate(task: str, text: str = "") -> dict:
            inputs = self.processor(
                text=task + text, images=image, return_tensors="pt"
            ).to(self.device)
            inputs["pixel_values"] = inputs["pixel_values"].to(self.model.dtype)
            with torch.inference_mode():
                output = self.model.generate(**inputs, max_new_tokens=1024, num_beams=3)
            return self.processor.post_process_generation(
                self.processor.batch_decode(output, skip_special_tokens=False)[0],
                task=task,
                image_size=image.size,
            ).get(task, {})

        # 1. 内置检测可覆盖常见类别；原始名称由业务层映射到项目类别。
        detected = generate("<OD>")
        results = [
            Detection(box, label)
            for box, label in zip(
                detected.get("bboxes", []), detected.get("labels", [])
            )
        ]
        covered = {item.label.casefold() for item in results}

        # 2. 单独提示缺失类别，避免多个短语的结果无法确定对应标签。
        for label in labels:
            if label.casefold() in covered:
                continue
            grounded = generate("<CAPTION_TO_PHRASE_GROUNDING>", label)
            results.extend(Detection(box, label) for box in grounded.get("bboxes", []))
        return results


class GroundingDetector:
    def __init__(self, weights: str, device: str):
        """加载 GroundingDINO；矩形检测只使用组合方案中的检测分支。"""
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        self.device = device
        model_id = "IDEA-Research/grounding-dino-tiny"
        cache = _huggingface_cache()
        self.processor = AutoProcessor.from_pretrained(model_id, cache_dir=cache)
        self.model = (
            AutoModelForZeroShotObjectDetection.from_pretrained(
                model_id, cache_dir=cache
            )
            .to(device)
            .eval()
        )

    def predict(self, image: Image.Image, labels: list[str]) -> list[Detection]:
        """按项目类别逐一定位目标，将框和分数转换为统一检测结果。"""
        import torch

        results = []
        for label in labels:
            inputs = self.processor(
                images=image, text=label + ".", return_tensors="pt"
            ).to(self.device)
            with torch.inference_mode():
                output = self.model(**inputs)
            prediction = self.processor.post_process_grounded_object_detection(
                output,
                inputs.input_ids,
                threshold=0.25,
                text_threshold=0.25,
                target_sizes=[(image.height, image.width)],
            )[0]
            results.extend(
                Detection(box, label, score)
                for box, score in zip(
                    prediction["boxes"].tolist(), prediction["scores"].tolist()
                )
            )
        return results


class Sam3Detector:
    def __init__(self, weights: str, device: str):
        """按需下载 SAM 3 检查点，复用跨项目公共缓存。"""
        from huggingface_hub import hf_hub_download
        from sam3.model_builder import build_sam3_image_model
        from sam3.model.sam3_image_processor import Sam3Processor

        checkpoint = hf_hub_download(weights, "sam3.pt", cache_dir=_huggingface_cache())
        model = (
            build_sam3_image_model(
                checkpoint_path=checkpoint, load_from_HF=False, device="cpu"
            )
            .to(device)
            .eval()
        )
        self.processor = Sam3Processor(model, device=device, confidence_threshold=0.25)

    def predict(self, image: Image.Image, labels: list[str]) -> list[Detection]:
        """复用图片特征，按项目类别生成框并重置上个类别的提示。"""
        state = self.processor.set_image(image)
        results = []
        for label in labels:
            self.processor.reset_all_prompts(state)
            prediction = self.processor.set_text_prompt(label, state)
            results.extend(
                Detection(box, label, score)
                for box, score in zip(
                    prediction["boxes"].tolist(), prediction["scores"].tolist()
                )
            )
        return results


def load_detector(algorithm: str, weights: str, configured_device: str):
    """校验选定权重，按算法加载检测器，缺少缓存时由官方 SDK 下载。"""
    if weights not in ANNOTATION_WEIGHTS.get(algorithm, ()):
        raise ValueError("所选权重不属于当前自动标注算法")
    detector = {
        "florence2": FlorenceDetector,
        "grounding_dino_sam": GroundingDetector,
        "sam3": Sam3Detector,
    }[algorithm]
    return detector(weights, torch_device(configured_device))
