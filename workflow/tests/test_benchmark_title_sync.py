from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workflow.benchmark_cases as cases


SCRIPT = Path(__file__).resolve().parents[2] / "10_Skills武器库" / "对标视频-结构拆解Skill（会员专享）" / "scripts" / "sync_case_titles.py"
SPEC = importlib.util.spec_from_file_location("benchmark_title_sync", SCRIPT)
assert SPEC and SPEC.loader
title_sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(title_sync)


class BenchmarkTitleSyncTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, Path, object]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        registry = root / "registry.json"
        breakdown_root = root / "breakdowns"
        source_root = root / "sources"
        owner_root = root / "owner"
        audit_root = root / "audit"
        entries = []
        for case_id, content_type, policy in (("GHX-001", "干货型", "owner-approved"), ("HKX-001", "获客型", "owner-approved"), ("SCHX-001", "晒成果型", "audit-required")):
            stem = f"{content_type}_行业：旧选题【旧结构】{case_id}"
            path = breakdown_root / f"{stem}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {stem}\n\n| 编号 | 大框架 | 小框架 | 小框架原文内容 |\n| --- | --- | --- | --- |\n| F01 | 当前结构 | 小框架 | 内容 |\n", encoding="utf-8")
            entries.append({"id": case_id, "type": content_type, "sourceTitle": f"{content_type}_行业：旧选题", "breakdownTitle": stem, "breakdownPath": path.relative_to(root).as_posix(), "manualEditPolicy": policy})
        registry.write_text(json.dumps({"schema": "benchmark-case-registry-v1", "manualEditPolicy": "audit-required", "typeCodes": {}, "cases": entries}, ensure_ascii=False), encoding="utf-8")
        mocks = patch.multiple(cases, ROOT=root, REGISTRY=registry, BREAKDOWN_ROOT=breakdown_root, SOURCE_ROOT=source_root, OWNER_APPROVAL_ROOT=owner_root, AUDIT_ROOT=audit_root)
        return temporary, root, registry, breakdown_root, mocks

    def test_mixed_owner_and_audit_cases_fail_before_any_write(self) -> None:
        temporary, root, registry, breakdown_root, mocks = self.fixture()
        with temporary, mocks, patch.object(title_sync, "ROOT", root), patch.object(title_sync, "REGISTRY", registry), patch.object(title_sync, "OWNER_APPROVAL_ROOT", root / "owner"):
            before = registry.read_bytes()
            with self.assertRaisesRegex(ValueError, "不是人工确认案例"):
                title_sync.apply_owners(["GHX-001", "SCHX-001"])
            self.assertEqual(registry.read_bytes(), before)
            self.assertEqual(len(list(breakdown_root.rglob("*GHX-001.md"))), 1)

    def test_batch_failure_restores_every_filename_and_h1_byte(self) -> None:
        temporary, root, registry, breakdown_root, mocks = self.fixture()
        with temporary, mocks, patch.object(title_sync, "ROOT", root), patch.object(title_sync, "REGISTRY", registry), patch.object(title_sync, "OWNER_APPROVAL_ROOT", root / "owner"):
            originals = {path.name: path.read_bytes() for path in breakdown_root.glob("*.md")}
            calls = 0
            def fail_second(**_: object) -> dict[str, str]:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated receipt failure")
                return {"receipt_path": "first.json"}
            with patch.object(title_sync, "record_owner_approved_case_edit", side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "simulated"):
                    title_sync.apply_owners(["GHX-001", "HKX-001"])
            self.assertEqual({path.name: path.read_bytes() for path in breakdown_root.glob("*.md")}, originals)

    def test_owner_title_sync_changes_only_h1_bytes(self) -> None:
        temporary, root, registry, breakdown_root, mocks = self.fixture()
        with temporary, mocks, patch.object(title_sync, "ROOT", root), patch.object(title_sync, "REGISTRY", registry), patch.object(title_sync, "OWNER_APPROVAL_ROOT", root / "owner"), patch.object(title_sync, "record_owner_approved_case_edit", return_value={"receipt_path": "receipt.json"}):
            old = next(breakdown_root.glob("*GHX-001.md"))
            original = old.read_bytes()
            result = title_sync.apply_owner("GHX-001")
            new = Path(result["target"])
            self.assertFalse(old.exists())
            self.assertTrue(new.is_file())
            self.assertEqual(original[original.index(b"\n") + 1:], new.read_bytes()[new.read_bytes().index(b"\n") + 1:])
            self.assertEqual(new.read_text(encoding="utf-8").splitlines()[0], "# 干货型_行业【当前结构】GHX-001")


if __name__ == "__main__":
    unittest.main()
