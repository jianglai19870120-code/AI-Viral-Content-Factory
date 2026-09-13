from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workflow.benchmark_cases as cases


class BenchmarkCaseSyncTests(unittest.TestCase):
    def fixture(self, *, new_body: str = "new", duplicate: bool = False, unchanged: bool = False):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        registry = root / "registry.json"
        audit = root / "audit"
        breakdown = root / "breakdowns"
        source = root / "sources"
        sync = root / "sync"
        source.mkdir(); breakdown.mkdir(); audit.mkdir()
        source_title = "推荐型_商业成长：来源（视频原文）"
        (source / f"{source_title}.md").write_text("原稿\n", encoding="utf-8")
        payload = {"schema": "benchmark-case-registry-v1", "manualEditPolicy": "owner-approved", "cases": [{
            "id": "TJX-001", "type": "推荐型", "sourceTitle": source_title,
            "breakdownTitle": "旧标题TJX-001", "breakdownPath": "missing/旧标题TJX-001.md",
        }]}
        registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        title = "推荐型_商业成长【新结构】TJX-001"
        body = f"# {title}\n\n来源：{source_title}.md；说明。\n\n{new_body}\n"
        current = breakdown / f"{title}.md"
        current.write_text(body, encoding="utf-8")
        old_hash = hashlib.sha256(current.read_bytes()).hexdigest() if unchanged else hashlib.sha256(b"old").hexdigest()
        (audit / "TJX-001_审核回执.json").write_text(json.dumps({
            "status": "approved", "benchmark_case_id": "TJX-001", "output_sha256": old_hash,
        }), encoding="utf-8")
        if duplicate:
            other = breakdown / "other"; other.mkdir()
            (other / f"推荐型_另一个【结构】TJX-001.md").write_text(
                f"# 推荐型_另一个【结构】TJX-001\n\n来源：{source_title}.md；说明。\n", encoding="utf-8")
        mocks = patch.multiple(cases, ROOT=root, REGISTRY=registry, AUDIT_ROOT=audit,
                               BREAKDOWN_ROOT=breakdown, SOURCE_ROOT=source, SYNC_ROOT=sync,
                               OWNER_APPROVAL_ROOT=audit / "owner-approved")
        return temporary, registry, mocks

    def test_unique_changed_file_syncs_as_owner_approved(self):
        temporary, registry, mocks = self.fixture()
        with temporary, mocks:
            result = cases.reconcile_case_registration("TJX-001")
            self.assertEqual(result["status"], "owner-approved")
            entry = json.loads(registry.read_text(encoding="utf-8"))["cases"][0]
            self.assertTrue(entry["breakdownPath"].endswith("TJX-001.md"))
            self.assertTrue(Path(result["sync_receipt"]).is_file())

    def test_duplicate_case_ids_are_rejected(self):
        temporary, _, mocks = self.fixture(duplicate=True)
        with temporary, mocks, self.assertRaisesRegex(ValueError, "多个同编号"):
            cases.reconcile_case_registration("TJX-001")

    def test_rename_only_is_owner_approved(self):
        temporary, _, mocks = self.fixture(unchanged=True)
        with temporary, mocks:
            result = cases.reconcile_case_registration("TJX-001")
            self.assertEqual(result["status"], "owner-approved")

    def test_owner_approval_rebinds_current_hash_without_audit(self):
        temporary, _, mocks = self.fixture()
        with temporary, mocks:
            result = cases.approved_case("TJX-001")
            self.assertEqual(result["audit"]["approval_basis"], "workspace-owner-manual-edit")
            self.assertEqual(result["audit"]["output_sha256"], cases._digest(result["breakdownPath"]))

    def test_invalid_h1_is_rejected(self):
        temporary, _, mocks = self.fixture()
        with temporary, mocks:
            path = next(cases.BREAKDOWN_ROOT.rglob("*TJX-001.md"))
            path.write_text("# 错误标题\n\n来源：推荐型_商业成长：来源（视频原文）.md；说明。\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "H1"):
                cases.reconcile_case_registration("TJX-001")

    def test_checked_owner_edit_rebinds_only_that_case_to_owner_approval(self):
        temporary, registry, mocks = self.fixture()
        with temporary, mocks:
            current = next(cases.BREAKDOWN_ROOT.rglob("*TJX-001.md"))
            payload = json.loads(registry.read_text(encoding="utf-8"))
            payload["cases"][0]["breakdownPath"] = current.relative_to(cases.ROOT).as_posix()
            registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            checked = current.with_name(f"√{current.name}")
            checked.write_text(
                f"# {current.stem}\n\n| 编号 | 大框架 | 大框架原文内容 |\n| --- | --- | --- |\n| 1 | 观点 | 内容 |\n",
                encoding="utf-8",
            )
            result = cases.record_owner_approved_case_edit(previous_breakdown=current, breakdown_markdown=checked)
            updated = json.loads(registry.read_text(encoding="utf-8"))["cases"][0]
            self.assertEqual(result["case_id"], "TJX-001")
            self.assertEqual(updated["manualEditPolicy"], "owner-approved")
            self.assertTrue(updated["breakdownPath"].endswith(checked.name))
            self.assertTrue(Path(result["receipt_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
