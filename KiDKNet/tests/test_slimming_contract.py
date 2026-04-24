import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class KiDKNetSlimmingContractTests(unittest.TestCase):
    def test_only_convnext_backbone_family_is_registered(self):
        backbones_init = PROJECT_ROOT / "dknet" / "models" / "backbones" / "__init__.py"
        source = backbones_init.read_text(encoding="utf-8")

        forbidden_names = ("resnet", "vgg", "vit", "densenet", "swin", "maxvit")
        for name in forbidden_names:
            self.assertNotRegex(source, rf'["\']{name}["\']')
            self.assertNotIn(f"from .{name}", source)

        self.assertRegex(source, r'["\']convnext["\']\s*:\s*ConvNeXtBackbone')

    def test_convnext_all_sizes_remain_configurable(self):
        convnext_source = (
            PROJECT_ROOT
            / "dknet"
            / "models"
            / "backbones"
            / "convnext.py"
        ).read_text(encoding="utf-8")

        for size in ("tiny", "small", "base", "large"):
            self.assertRegex(convnext_source, rf'["\']{size}["\']\s*:')

    def test_removed_backbone_implementations_and_configs_are_absent(self):
        removed_backbones = (
            "resnet.py",
            "vgg.py",
            "vit.py",
            "densenet.py",
            "swin.py",
            "maxvit.py",
        )
        for filename in removed_backbones:
            self.assertFalse(
                (PROJECT_ROOT / "dknet" / "models" / "backbones" / filename).exists()
            )

        removed_configs = (
            "resnet101_config.yaml",
            "vgg16_config.yaml",
            "vit_b16_config.yaml",
            "dataset_split.json",
        )
        for filename in removed_configs:
            self.assertFalse((PROJECT_ROOT / "configs" / filename).exists())

    def test_configs_use_med_pipeline_data_path(self):
        config_dir = PROJECT_ROOT / "configs"
        for path in config_dir.glob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("../Obj_post/", text)
            if re.search(r"^\s*data_dir\s*:", text, re.MULTILINE):
                self.assertIn("../Deform_post/", text)

    def test_interpretability_validation_entrypoint_is_removed(self):
        checked_files = (
            PROJECT_ROOT / "main.py",
            PROJECT_ROOT / "scripts" / "evaluate.py",
        )
        for path in checked_files:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("interpretability_validation", source)
            self.assertNotIn("enable_interpretability_validation", source)


if __name__ == "__main__":
    unittest.main()
