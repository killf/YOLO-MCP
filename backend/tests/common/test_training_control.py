"""使用已安装的框架验证检查点与训练范围；无训练依赖时跳过。

可单独执行：python -m unittest backend.tests.common.test_training_control
"""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(
    importlib.util.find_spec("ultralytics") and importlib.util.find_spec("torch"),
    "需要已安装的训练运行时",
)
class TrainingControlTest(unittest.TestCase):
    def test_checkpoint_resume_and_detection_head_scope(self):
        with tempfile.TemporaryDirectory(
            prefix="yolo-mcp-training-control-"
        ) as directory:
            root = Path(directory)
            with patch.dict(
                os.environ,
                {
                    "YOLO_MCP_DATA_DIR": str(root),
                    "YOLO_CONFIG_DIR": str(root / "config"),
                    "YOLO_AUTOINSTALL": "false",
                    "YOLO_OFFLINE": "true",
                },
            ):
                self._exercise_training(root)

    def _exercise_training(self, root):
        import torch
        import yaml
        from PIL import Image, ImageDraw
        from ultralytics import YOLO
        from backend.training.control import ControlledDetectionTrainer
        from backend.training.train import run_training, PAUSED_EXIT_CODE

        dataset = root / "source"
        (dataset / "images").mkdir(parents=True)
        (dataset / "labels").mkdir()
        for split, count in [("train", 4), ("test", 2)]:
            listing = []
            for index in range(count):
                name = f"{split}-{index}"
                image = Image.new("RGB", (64, 64), (80 + index * 10, 90, 100))
                ImageDraw.Draw(image).rectangle((16, 16, 48, 48), fill="white")
                image.save(dataset / "images" / f"{name}.png")
                (dataset / "labels" / f"{name}.txt").write_text("0 0.5 0.5 0.5 0.5\n")
                listing.append(f"images/{name}.png")
            (dataset / f"{split}.txt").write_text("\n".join(listing) + "\n")
        (dataset / "data.yaml").write_text(
            yaml.safe_dump(
                {"train": "train.txt", "test": "test.txt", "names": ["object"]}
            )
        )
        weights = root / "initial.pt"
        YOLO("yolo26n.yaml").save(weights)
        parameters = {
            "model": str(weights),
            "epochs": 3,
            "imgsz": 64,
            "batch": 2,
            "device": "0" if torch.cuda.is_available() else "cpu",
            "workers": 0,
            "nbs": 2,
            "warmup_epochs": 0,
            "amp": False,
            "plots": False,
            "close_mosaic": 0,
            "optimizer": "SGD",
            "augmentation": False,
            "training_scope": "head_then_full",
            "unfreeze_steps": 3,
        }
        workspace = root / "run"
        workspace.mkdir()
        (workspace / "pause.request").touch()
        result_file = workspace / "result.json"
        updates, starts, datasets = [], [], []
        setup = ControlledDetectionTrainer._setup_train
        update = ControlledDetectionTrainer._after_optimizer_step
        build = ControlledDetectionTrainer.build_dataset
        save = ControlledDetectionTrainer.save_model

        def observe_setup(trainer):
            setup(trainer)
            starts.append(trainer.optimizer_steps)
            trainer._test_weight = (
                next(trainer.model.model[0].parameters()).detach().clone()
            )
            trainer._test_bn = trainer.model.model[0].bn.running_mean.detach().clone()

        def observe_update(trainer, *args):
            update(trainer, *args)
            parameter = next(trainer.model.model[0].parameters())
            updates.append((trainer.optimizer_steps, parameter.requires_grad))

        def observe_dataset(trainer, *args, **kwargs):
            data = build(trainer, *args, **kwargs)
            if data.prefix.startswith("train") or "train" in data.prefix:
                self.assertEqual(data.augment, trainer.augmentation)
                datasets.append(data.augment)
            return data

        def observe_save(trainer):
            if trainer.training_scope == "head" or trainer.optimizer_steps < 3:
                self.assertTrue(
                    torch.equal(
                        next(trainer.model.model[0].parameters()), trainer._test_weight
                    )
                )
                self.assertTrue(
                    torch.equal(
                        trainer.model.model[0].bn.running_mean, trainer._test_bn
                    )
                )
            return save(trainer)

        with (
            patch.object(ControlledDetectionTrainer, "_setup_train", observe_setup),
            patch.object(
                ControlledDetectionTrainer, "_after_optimizer_step", observe_update
            ),
            patch.object(ControlledDetectionTrainer, "build_dataset", observe_dataset),
            patch.object(ControlledDetectionTrainer, "save_model", observe_save),
        ):
            code = run_training(
                dataset, parameters, workspace, result_file, root / "models"
            )
            self.assertEqual(code, PAUSED_EXIT_CODE)
            checkpoint = torch.load(
                workspace / "resume.pt", weights_only=False, map_location="cpu"
            )
            self.assertEqual(checkpoint["epoch"], 0)
            self.assertEqual(checkpoint["yolo_mcp_steps"], 2)
            self.assertIsNotNone(checkpoint["optimizer"])
            self.assertFalse((root / "models").exists())
            (workspace / "pause.request").unlink()
            code = run_training(
                workspace / "dataset",
                parameters,
                workspace,
                result_file,
                root / "models",
                workspace / "resume.pt",
            )
            self.assertEqual(code, 0)
            self.assertEqual(starts, [0, 2])
            self.assertEqual(updates[:3], [(1, False), (2, False), (3, True)])
            output = json.loads(result_file.read_text())
            self.assertTrue(Path(output["model_path"]).is_file())
            # 独立验证始终仅训练检测头，backbone 参数及 BN 统计均保持不变。
            parameters.update(epochs=1, training_scope="head", augmentation=True)
            self.assertEqual(
                run_training(
                    dataset,
                    parameters,
                    root / "head-run",
                    root / "head.json",
                    root / "models",
                ),
                0,
            )
        self.assertTrue(datasets)
        self.assertIn(False, datasets)
        self.assertIn(True, datasets)


if __name__ == "__main__":
    unittest.main()
