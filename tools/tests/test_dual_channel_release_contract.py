from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.release.publish_release import asset_change_summary, asset_inventory_from_public_manifest


ROOT = Path(__file__).resolve().parents[2]


class DualChannelReleaseContractTests(unittest.TestCase):
    def test_registry_declares_the_machine_readable_dual_channel_contract(self) -> None:
        registry = json.loads((ROOT / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
        contract = registry["release"]["dualChannelContract"]
        self.assertEqual(contract["versionPolicy"], "caller-explicit-semver-tag-never-overwrite")
        self.assertEqual(contract["defaultScope"], "all-current-workspace-changes-that-pass-gates-and-channel-policy")
        self.assertEqual(contract["feishu"]["mode"], "replace-single-zip-in-fixed-wiki-page")
        self.assertTrue(contract["feishu"]["preservePageText"])
        self.assertEqual(contract["assetDeletionPolicy"], "mirror-current-asset-library-in-active-deliveries")
        self.assertEqual(contract["credentials"], "environment-variables-only")

    def test_documentation_exposes_publish_and_recovery_prompts(self) -> None:
        text = (ROOT / "00_系统说明" / "双轨版本发布标准.md").read_text(encoding="utf-8")
        for marker in (
            "请按《双轨版本发布标准》发布 vX.Y.Z",
            "请按《双轨版本发布标准》恢复 vX.Y.Z 双轨发布",
            "python run.py publish --version vX.Y.Z --preflight",
            "不得修改飞书页面说明文字",
            "不得覆盖已有 Git 标签",
            "镜像删除",
        ):
            self.assertIn(marker, text)

    def test_asset_mirror_report_marks_removed_local_asset_as_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous, current = Path(directory) / "previous", Path(directory) / "current"
            (previous / "02_资产中心").mkdir(parents=True)
            (current / "02_资产中心").mkdir(parents=True)
            (previous / "02_资产中心/保留.md").write_text("旧版本", encoding="utf-8")
            (previous / "02_资产中心/已删除.md").write_text("应下线", encoding="utf-8")
            (current / "02_资产中心/保留.md").write_text("新版本", encoding="utf-8")
            summary = asset_change_summary(previous, current)
        self.assertEqual(summary["deleted"], ["02_资产中心/已删除.md"])
        self.assertEqual(summary["modified"], ["02_资产中心/保留.md"])

    def test_previous_asset_snapshot_comes_from_public_manifest_without_old_blobs(self) -> None:
        inventory = asset_inventory_from_public_manifest(json.dumps({"records": [
            {"path": "02_资产中心/保留.md", "status": "public", "sha256": "a"},
            {"path": "02_资产中心/资料（会员专享）/私有.md", "status": "private", "sha256": "b"},
            {"path": "02_资产中心/空目录/.gitkeep", "status": "public", "sha256": "c"},
        ]}, ensure_ascii=False))
        self.assertEqual(inventory, {"02_资产中心/保留.md": "a"})


if __name__ == "__main__":
    unittest.main()
