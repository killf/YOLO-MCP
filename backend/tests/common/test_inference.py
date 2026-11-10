"""验证模型调用协议、精度、公共缓存和下载失败边界，替换权重计算。"""

import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from backend import inference
from backend.application.command.training import StartTrainingCommand
from backend.common.storage import get_storage


@pytest.mark.parametrize(
    "algorithm,weights",
    [
        ("florence2", "microsoft/Florence-2-base"),
        ("grounding_dino_sam", "grounding-dino-tiny+sam-vit-base"),
        ("sam3", "facebook/sam3"),
    ],
)
def test_model_loaders_share_public_cache_and_allow_downloads(
    monkeypatch, algorithm, weights
):
    runtime = SimpleNamespace(
        AutoProcessor=Mock(),
        AutoModelForCausalLM=Mock(),
        AutoModelForZeroShotObjectDetection=Mock(),
    )
    hub = SimpleNamespace(hf_hub_download=Mock(return_value="cached-sam3.pt"))
    monkeypatch.setitem(sys.modules, "transformers", runtime)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float32="float32"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(
        sys.modules,
        "sam3.model_builder",
        SimpleNamespace(build_sam3_image_model=Mock()),
    )
    monkeypatch.setitem(
        sys.modules,
        "sam3.model.sam3_image_processor",
        SimpleNamespace(Sam3Processor=Mock()),
    )
    monkeypatch.setattr(inference, "torch_device", lambda _value: "cpu")
    for _project in range(2):
        inference.load_detector(algorithm, weights, "cpu")
    calls = (
        hub.hf_hub_download.call_args_list
        if algorithm == "sam3"
        else runtime.AutoProcessor.from_pretrained.call_args_list
    )
    assert len(calls) == 2
    for call in calls:
        assert call.kwargs["cache_dir"] == str(get_storage().path("models/huggingface"))
        assert not call.kwargs.get("local_files_only", False)
    if algorithm != "sam3":
        factory = (
            runtime.AutoModelForCausalLM
            if algorithm == "florence2"
            else runtime.AutoModelForZeroShotObjectDetection
        )
        assert (
            factory.from_pretrained.call_args.kwargs["cache_dir"]
            == calls[0].kwargs["cache_dir"]
        )


@pytest.mark.parametrize(
    "error,expected",
    [
        (ImportError("private package location"), "缺少推理依赖"),
        (OSError("private url and token"), "权重下载或读取失败"),
        (PermissionError("private directory"), "缓存写入失败"),
        (RuntimeError("private backend detail"), "加载失败"),
    ],
)
def test_model_load_errors_are_actionable_and_do_not_expose_internal_details(
    error, expected
):
    message = inference.model_load_error(error, "facebook/sam3")
    assert "facebook/sam3" in message and expected in message
    assert "private" not in message


def test_wrapped_gated_model_error_explains_authorization():
    denied = RuntimeError("private authentication response")
    denied.response = SimpleNamespace(status_code=403)
    wrapped = OSError("could not load model")
    wrapped.__cause__ = denied
    assert "访问受限" in inference.model_load_error(wrapped, "facebook/sam3")


def test_unsupported_weights_fail_before_loading_runtime():
    with pytest.raises(ValueError):
        inference.load_detector("florence2", "../../untrusted", "cpu")


def test_florence_pixel_dtype_and_label_grounding(monkeypatch):
    pixels = Mock()
    inputs = {"pixel_values": pixels}
    batch = type("Batch", (dict,), {"to": lambda self, _device: self})(inputs)
    processor = Mock(return_value=batch)
    processor.batch_decode.return_value = ["generated"]
    processor.post_process_generation.side_effect = [
        {"<OD>": {"bboxes": [[1, 2, 5, 6]], "labels": ["person"]}},
        {"<CAPTION_TO_PHRASE_GROUNDING>": {"bboxes": [[3, 4, 7, 8]]}},
    ]
    detector = inference.FlorenceDetector.__new__(inference.FlorenceDetector)
    detector.processor = processor
    detector.model = SimpleNamespace(dtype="model-dtype", generate=Mock())
    detector.device = "cpu"
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    result = detector.predict(Image.new("RGB", (10, 10)), ["person", "vehicle"])
    assert [item.label for item in result] == ["person", "vehicle"]
    assert result[1].xyxy == [3, 4, 7, 8]
    pixels.to.assert_called_with("model-dtype")
    assert (
        processor.call_args_list[1].kwargs["text"]
        == "<CAPTION_TO_PHRASE_GROUNDING>vehicle"
    )


def test_grounding_returns_original_class_and_pixel_boxes(monkeypatch):
    boxes = Mock()
    boxes.tolist.return_value = [[1, 2, 5, 6]]
    scores = Mock()
    scores.tolist.return_value = [0.9]
    batch = type(
        "Batch", (dict,), {"to": lambda self, _device: self, "input_ids": [1]}
    )()
    detector = inference.GroundingDetector.__new__(inference.GroundingDetector)
    detector.device = "cpu"
    detector.model = Mock()
    detector.processor = Mock(return_value=batch)
    detector.processor.post_process_grounded_object_detection.return_value = [
        {"boxes": boxes, "scores": scores}
    ]
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    result = detector.predict(Image.new("RGB", (30, 20)), ["Vehicle"])
    assert result == [inference.Detection([1, 2, 5, 6], "Vehicle", 0.9)]
    assert detector.processor.post_process_grounded_object_detection.call_args.kwargs[
        "target_sizes"
    ] == [(20, 30)]


def test_sam3_resets_prompt_between_labels():
    processor = Mock()
    processor.set_image.return_value = {"feature": "shared"}
    tensor = Mock()
    tensor.tolist.return_value = []
    processor.set_text_prompt.return_value = {"boxes": tensor, "scores": tensor}
    detector = inference.Sam3Detector.__new__(inference.Sam3Detector)
    detector.processor = processor
    assert detector.predict(Image.new("RGB", (10, 10)), ["person", "car"]) == []
    assert processor.set_image.call_count == 1
    assert processor.reset_all_prompts.call_count == 2
    assert [call.args[0] for call in processor.set_text_prompt.call_args_list] == [
        "person",
        "car",
    ]


@pytest.mark.parametrize(
    "params",
    [
        {"lr0": -0.1},
        {"lr0": float("nan")},
        {"lr0": 1.1},
        {"lr0": 0.01, "extra_params": {"lr0": 0.1}},
    ],
)
def test_training_learning_rate_rejects_invalid_values_and_conflicts(params):
    with pytest.raises(ValueError):
        StartTrainingCommand.model_validate(params)
