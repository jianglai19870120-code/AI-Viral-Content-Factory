from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DualChannelReleaseContractTests(unittest.TestCase):
    def test_registry_declares_the_machine_readable_dual_channel_contract(self) -> None:
        registry = json.loads((ROOT / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
        contract = registry["release"]["dualChannelContract"]
        self.assertEqual(contract["versionPolicy"], "caller-explicit-semver-tag-never-overwrite")
        self.assertEqual(contract["defaultScope"], "all-current-workspace-changes-that-pass-gates-and-channel-policy")
        self.assertEqual(contract["feishu"]["mode"], "replace-single-zip-in-fixed-wiki-page")
        self.assertTrue(contract["feishu"]["preservePageText"])
        self.assertEqual(contract["credentials"], "environment-variables-only")

    def test_documentation_exposes_publish_and_recovery_prompts(self) -> None:
        text = (ROOT / "00_系统说明" / "双轨版本发布标准.md").read_text(encoding="utf-8")
        for marker in (
            "请按《双轨版本发布标准》发布 vX.Y.Z",
            "请按《双轨版本发布标准》恢复 vX.Y.Z 双轨发布",
            "python run.py publish --version vX.Y.Z --preflight",
            "不得修改飞书页面说明文字",
            "不得覆盖已有 Git 标签",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
