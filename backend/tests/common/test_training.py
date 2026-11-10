import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from PIL import Image

from backend.training import train
from backend.common.storage import LocalStorage


def test_training_help_does_not_load_model_runtime(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["yolo-mcp-train", "--help"])
    with pytest.raises(SystemExit) as result:
        train.main()
    assert result.value.code == 0
    assert "--data" in capsys.readouterr().out
    assert "torch" not in sys.modules
    assert "ultralytics" not in sys.modules


@pytest.fixture
def local_dataset(tmp_path):
    directory = tmp_path / "project"
    (directory / "images").mkdir(parents=True)
    (directory / "labels").mkdir()
    config = {
        "path": ".",
        "train": "train.txt",
        "val": "test.txt",
        "test": "test.txt",
        "names": ["person"],
        "download": "must-not-execute",
    }
    (directory / "data.yaml").write_text(yaml.safe_dump(config))
    for split in ["train", "test"]:
        Image.new("RGB", (10, 8), "blue").save(directory / "images" / f"{split}.png")
        (directory / f"{split}.txt").write_text(f"images/{split}.png\n")
    (directory / "labels/test.txt").write_text("")
    return directory


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("device", ["cpu", "0,1"])
def test_training_shares_official_weights_and_reports_download_failure(
    local_dataset, tmp_path, monkeypatch, failed, device
):
    class Paused(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "backend.training.control",
        SimpleNamespace(
            ControlledDetectionTrainer=Mock(),
            TrainingPaused=Paused,
        ),
    )
    best = tmp_path / "best.pt"
    best.write_bytes(b"trained model")
    downloads = []
    name = "yolo26l.pt" if failed else "yolo26m.pt"
    storage = LocalStorage()
    storage.root = tmp_path / "shared-cache"
    monkeypatch.setattr("backend.common.storage.get_storage", lambda: storage)
    cached = storage.path(f"models/ultralytics/{name}")
    run_ids = iter(["cache-first", "cache-second"])
    monkeypatch.setattr(train, "_next_run_id", lambda _directory: next(run_ids))

    def load_model(weights):
        assert Path(weights) == cached
        if not cached.exists():
            downloads.append(weights)
            if failed:
                raise ConnectionError("synthetic private download address")
            cached.write_bytes(b"downloaded official weights")
        return SimpleNamespace(
            train=Mock(), trainer=SimpleNamespace(best=best, metrics={})
        )

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=load_model))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace())
    for index in range(2):
        workspace = tmp_path / f"project-{index}" / "run"
        result = workspace / "result.json"
        code = train.run_training(
            local_dataset,
            {"model": name, "device": device},
            work_dir=workspace,
            result_file=result,
        )
        assert code == (1 if failed else 0)
        response = json.loads(result.read_text(encoding="utf-8"))
        if failed:
            assert "权重下载或读取失败" in response["error_message"]
            assert "private" not in response["error_message"]
            assert not cached.exists()
        else:
            assert Path(response["model_path"]).is_file()
    assert len(downloads) == (2 if failed else 1)


def test_local_dataset_snapshot_is_independent(local_dataset, tmp_path):
    target = tmp_path / "snapshot-data"
    originals = tmp_path / "originals"
    config_file = train.prepare_dataset(local_dataset, target, originals)
    config = yaml.safe_load(config_file.read_text())
    assert config["path"] == str(target.resolve())
    assert config["val"] == config["test"] == "test.txt"
    assert "download" not in config
    assert not (target / "val.txt").exists()
    assert "download" in yaml.safe_load((originals / "data.yaml").read_text())
    assert (target / "labels/test.txt").read_bytes() == b""
    assert not (target / "labels/train.txt").exists()
    before = (target / "images/train.png").read_bytes()
    (local_dataset / "images/train.png").write_bytes(b"changed after snapshot")
    assert (target / "images/train.png").read_bytes() == before
    assert (target / "train.txt").read_text().strip() == "./images/train.png"


def test_snapshot_rejects_traversal(local_dataset, tmp_path):
    (local_dataset / "train.txt").write_text("images/../../outside.png\n")
    with pytest.raises(ValueError, match="Invalid dataset-relative path"):
        train.prepare_dataset(local_dataset, tmp_path / "data-copy", tmp_path / "input")


def test_snapshot_requires_completed_test_images(local_dataset, tmp_path):
    (local_dataset / "test.txt").write_text("")
    with pytest.raises(ValueError, match="test.txt contains no images"):
        train.prepare_dataset(local_dataset, tmp_path / "data-copy", tmp_path / "input")


@pytest.mark.parametrize(
    "parameters",
    [
        None,
        [],
        "invalid",
        {"epochs": 3},
        {"data": "elsewhere"},
        {"save": False},
        {"lr0": float("nan")},
    ],
)
def test_custom_parameters_reject_invalid_objects_and_reserved_fields(parameters):
    with pytest.raises((ValueError, TypeError)):
        train.validate_training_options(parameters)


def test_custom_parameters_use_framework_validation(monkeypatch):
    cfg = ModuleType("ultralytics.cfg")
    cfg.DEFAULT_CFG_DICT = {"lr0": 0.01, "amp": True}
    cfg.get_cfg = Mock()
    monkeypatch.setitem(sys.modules, "ultralytics", ModuleType("ultralytics"))
    monkeypatch.setitem(sys.modules, "ultralytics.cfg", cfg)
    parameters = {"lr0": 0.001, "amp": False}
    assert train.validate_training_options(parameters) == parameters
    cfg.get_cfg.assert_called_once_with(overrides=parameters)
    with pytest.raises(ValueError, match="未知训练参数"):
        train.validate_training_options({"typo_parameter": 1})
    cfg.get_cfg.side_effect = TypeError("amp must be boolean")
    with pytest.raises(ValueError, match="amp must be boolean"):
        train.validate_training_options({"amp": "invalid"})


def test_parameter_catalog_matches_runtime_and_excludes_managed_fields(
    monkeypatch, tmp_path
):
    config = tmp_path / "default.yaml"
    config.write_text(
        "lr0: 0.01 # initial learning rate\n"
        "future_option: null # new runtime option\n",
        encoding="utf-8",
    )
    cfg = ModuleType("ultralytics.cfg")
    cfg.DEFAULT_CFG_DICT = {
        "lr0": 0.01,
        "future_option": None,
        "model": None,
        "epochs": 100,
        "device": None,
    }
    utils = ModuleType("ultralytics.utils")
    utils.DEFAULT_CFG_PATH = config
    monkeypatch.setitem(sys.modules, "ultralytics", ModuleType("ultralytics"))
    monkeypatch.setitem(sys.modules, "ultralytics.cfg", cfg)
    monkeypatch.setitem(sys.modules, "ultralytics.utils", utils)
    catalog = train.training_parameter_catalog()
    assert [entry["name"] for entry in catalog] == ["lr0", "future_option"]
    assert catalog[0]["default"] == 0.01
    assert "初始学习率" in catalog[0]["description"]
    assert catalog[1] == {
        "name": "future_option",
        "default": None,
        "description": "new runtime option",
    }


@pytest.mark.parametrize("prepared", [False, True])
@pytest.mark.parametrize("custom_config", [False, True])
def test_cli_custom_parameters_reach_yolo_and_result(
    local_dataset, tmp_path, monkeypatch, prepared, custom_config
):
    """核对真实 CLI、快照和产物流程，固定运行编号并替换模型计算。"""

    class Paused(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "backend.training.control",
        SimpleNamespace(
            ControlledDetectionTrainer=Mock(),
            TrainingPaused=Paused,
        ),
    )
    best = tmp_path / "best.pt"
    best.write_bytes(b"test-only model")
    model = SimpleNamespace(
        train=Mock(), trainer=SimpleNamespace(best=best, metrics={"mAP": 0.5})
    )
    runtime = ModuleType("ultralytics")
    runtime.YOLO = Mock(return_value=model)
    cfg = ModuleType("ultralytics.cfg")
    cfg.DEFAULT_CFG_DICT = {"lr0": 0.01, "amp": True, "seed": 0}
    cfg.get_cfg = Mock()
    monkeypatch.setitem(sys.modules, "ultralytics", runtime)
    monkeypatch.setitem(sys.modules, "ultralytics.cfg", cfg)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
    )
    storage = LocalStorage()
    storage.root = tmp_path / "shared-cache"
    monkeypatch.setattr("backend.common.storage.get_storage", lambda: storage)
    if custom_config:
        config_dir = tmp_path / "custom-ultralytics"
        monkeypatch.setenv("YOLO_CONFIG_DIR", str(config_dir))
    else:
        config_dir = storage.path(".ultralytics")
        monkeypatch.delenv("YOLO_CONFIG_DIR", raising=False)

    def check_config(**_kwargs):
        assert Path(os.environ["YOLO_CONFIG_DIR"]) == config_dir

    cfg.get_cfg.side_effect = check_config
    monkeypatch.setenv("YOLO_AUTOINSTALL", "false")
    monkeypatch.setattr(train, "_next_run_id", lambda _dataset: "test-parameters")
    result = tmp_path / "result.json"
    work_dir = tmp_path / "page-run"
    model_dir = tmp_path / "project-models"
    if prepared:
        train.prepare_dataset(local_dataset, work_dir / "dataset", tmp_path / "input")
        local_dataset = work_dir / "dataset"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "yolo-mcp-train",
            "--data",
            str(local_dataset),
            *(
                ["--work-dir", str(work_dir), "--models-dir", str(model_dir)]
                if prepared
                else []
            ),
            "--model",
            "bootstrap.pt",
            "--epochs",
            "2",
            "--imgsz",
            "640",
            "--batch",
            "2",
            "--no-augmentation",
            "--training-scope",
            "head_then_full",
            "--unfreeze-steps",
            "7",
            "--result-file",
            str(result),
            "--extra-params",
            json.dumps({"lr0": 0.001, "amp": False, "seed": 7}),
        ],
    )
    assert train.main() == 0
    assert Path(os.environ["YOLO_CONFIG_DIR"]) == config_dir
    passed = model.train.call_args.kwargs
    assert passed["lr0"] == 0.001 and passed["amp"] is False and passed["seed"] == 7
    assert passed["epochs"] == 2 and passed["imgsz"] == 640 and passed["batch"] == 2
    assert passed["trainer"].keywords["augmentation"] is False
    assert passed["trainer"].keywords["training_scope"] == "head_then_full"
    assert passed["trainer"].keywords["unfreeze_steps"] == 7
    assert Path(passed["data"]).is_file()
    output = json.loads(result.read_text())
    assert Path(output["model_path"]).read_bytes() == best.read_bytes()
    if prepared:
        assert Path(output["model_path"]).parent == model_dir
        assert not (work_dir / "input").exists()


@pytest.mark.parametrize("value", ["{", "[]", '{"epochs": 2}', '{"amp": false}'])
def test_cli_rejects_bad_json_and_duplicate_options(tmp_path, monkeypatch, value):
    monkeypatch.setattr(train, "validate_training_options", train.validate_extra_params)
    worker = Mock()
    monkeypatch.setattr(train, "run_training", worker)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "yolo-mcp-train",
            "--data",
            str(tmp_path),
            "--amp",
            "--extra-params",
            value,
        ],
    )
    with pytest.raises(SystemExit) as result:
        train.main()
    assert result.value.code == 2
    worker.assert_not_called()
