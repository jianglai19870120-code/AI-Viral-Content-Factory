from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow import topic_structure_releases as releases


def structure_markdown(*, content: str = "用户自己的最终逻辑", label: str = "开场") -> str:
    return "\n".join([
        "# 文案结构｜测试选题", "", "对标复刻拆解：GHX-001", "", "## 结构四", "",
        "| 编号 | 大框架 | 核心内容 |", "| --- | --- | --- |",
        f"| F01 | {label} | {content} |", "",
    ])


class FilledStructureInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "人工填写结构.md"
        self.source.write_text(structure_markdown(), encoding="utf-8")
        self.candidate = self.root / "candidate.json"
        self.candidate.write_text(json.dumps({
            "schema": "copy-structure-v19",
            "structures": {"structure_four": {"core_frameworks": [
                {"framework_block_id": "F01", "framework_label": "开场"},
            ]}},
        }, ensure_ascii=False), encoding="utf-8")
        self.receipt = self.root / "audit.json"
        self.receipt.write_text("{}", encoding="utf-8")
        self.entry = {
            "topic": "测试选题", "benchmark_case_id": "GHX-001",
            "output_path": str(self.root / "published.md"), "output_sha256": "published-sha",
            "candidate_path": str(self.candidate), "candidate_sha256": hashlib.sha256(self.candidate.read_bytes()).hexdigest(),
            "audit_receipt_path": str(self.receipt),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _resolve(self) -> dict:
        with patch.object(releases, "load_release_index", return_value={"entries": [self.entry]}), patch.object(releases, "_approved_structure_evidence", return_value=(self.candidate, self.receipt)):
            return releases.resolve_filled_structure_input(structure_markdown=self.source)

    def test_complete_unchecked_structure_is_direct_input_without_freezing(self) -> None:
        resolved = self._resolve()
        self.assertEqual(resolved["structure_input_authority"], "owner-filled-direct")
        self.assertFalse(resolved["structure_four_frozen"])
        self.assertEqual(resolved["output_path"], str(self.source.resolve()))
        self.assertEqual(resolved["output_sha256"], hashlib.sha256(self.source.read_bytes()).hexdigest())

    def test_direct_input_rejects_framework_label_drift(self) -> None:
        self.source.write_text(structure_markdown(label="被改坏的名称"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "当前已审核 V19"):
            self._resolve()


if __name__ == "__main__":
    unittest.main()
