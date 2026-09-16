from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import workflow.benchmark_cases as cases
from workflow.topic_structure_releases import parse_benchmark_case_ids


class BenchmarkCaseRegistrationTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        registry = root / "registry.json"
        source_root = root / "sources"
        breakdown_root = root / "breakdowns"
        source = source_root / "04_晒成果型原文（会员专享）" / "晒成果型_AI智能体：怎么用WorkBuddy制作一条10万+爆款视频.md"
        source.parent.mkdir(parents=True)
        source.write_text("完整原文", encoding="utf-8")
        registry.write_text(json.dumps({
            "schema": "benchmark-case-registry-v1", "manualEditPolicy": "audit-required",
            "typeCodes": {"干货型": "GHX"},
            "cases": [{"id": "GHX-001", "type": "干货型", "sourceTitle": "干货型_既有", "breakdownTitle": "既有", "breakdownPath": "old.md"}],
        }, ensure_ascii=False), encoding="utf-8")
        mocks = patch.multiple(cases, ROOT=root, REGISTRY=registry, SOURCE_ROOT=source_root,
                               BREAKDOWN_ROOT=breakdown_root, SYNC_ROOT=root / "sync")
        return temporary, registry, source, breakdown_root, mocks

    def test_new_member_type_plan_is_runtime_only_and_mirrors_directory(self):
        temporary, registry, source, breakdown_root, mocks = self.fixture()
        with temporary, mocks:
            plan = cases.plan_case_registration(source=source, type_code="SCHX")
            self.assertEqual(plan["case_id"], "SCHX-001")
            self.assertEqual(Path(plan["formal_directory"]).resolve(), (breakdown_root / "04_晒成果型拆解（会员专享）").resolve())
            self.assertFalse(Path(plan["formal_directory"]).exists())
            self.assertNotIn("晒成果型", json.loads(registry.read_text(encoding="utf-8"))["typeCodes"])

    def test_existing_type_allocates_next_sequence(self):
        temporary, registry, source, _, mocks = self.fixture()
        with temporary, mocks:
            payload = json.loads(registry.read_text(encoding="utf-8"))
            payload["typeCodes"]["晒成果型"] = "SCHX"
            payload["cases"].append({"id": "SCHX-001", "type": "晒成果型", "sourceTitle": "晒成果型_旧案例", "breakdownTitle": "旧案例", "breakdownPath": "old.md"})
            registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(cases.plan_case_registration(source=source)["case_id"], "SCHX-002")

    def test_registered_source_keeps_its_registered_output_directory(self):
        temporary, registry, source, breakdown_root, mocks = self.fixture()
        with temporary, mocks:
            payload = json.loads(registry.read_text(encoding="utf-8"))
            existing_path = "legacy/晒成果型_已审核SCHX-001.md"
            payload["typeCodes"]["晒成果型"] = "SCHX"
            payload["cases"].append({"id": "SCHX-001", "type": "晒成果型", "sourceTitle": source.stem, "breakdownTitle": "已审核", "breakdownPath": existing_path})
            registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            plan = cases.plan_case_registration(source=source)
            self.assertEqual(plan["status"], "registered")
            self.assertEqual(Path(plan["formal_directory"]).resolve(), (Path(temporary.name) / "legacy").resolve())

    def test_new_type_requires_non_conflicting_explicit_code(self):
        temporary, _, source, _, mocks = self.fixture()
        with temporary, mocks:
            with self.assertRaisesRegex(ValueError, "首次处理"):
                cases.plan_case_registration(source=source)
            with self.assertRaisesRegex(ValueError, "已被内容类型"):
                cases.plan_case_registration(source=source, type_code="GHX")

    def test_approved_output_commits_type_and_case_only_after_publication(self):
        temporary, registry, source, _, mocks = self.fixture()
        with temporary, mocks:
            plan = cases.plan_case_registration(source=source, type_code="SCHX")
            plan_path = cases.write_case_registration_plan(plan, runtime_root=Path(temporary.name) / "runtime")
            formal = Path(plan["formal_directory"]) / "晒成果型_AI智能体【观点】SCHX-001.md"
            formal.parent.mkdir(parents=True)
            formal.write_text("# 晒成果型_AI智能体【观点】SCHX-001\n", encoding="utf-8")
            result = cases.commit_published_case_registration(plan_path=plan_path, source=source, case_id="SCHX-001", formal_output=formal)
            updated = json.loads(registry.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "registered")
            self.assertEqual(updated["typeCodes"]["晒成果型"], "SCHX")
            self.assertEqual(updated["cases"][-1]["id"], "SCHX-001")

    def test_variable_length_case_ids_remain_valid_for_topic_bindings(self):
        self.assertEqual(parse_benchmark_case_ids("GHX-001<br>SCHX-001"), ("GHX-001", "SCHX-001"))

    def test_source_industry_excludes_original_topic_after_either_colon(self):
        self.assertEqual(cases.source_industry("晒成果型_AI智能体：怎么用WorkBuddy制作视频"), "AI智能体")
        self.assertEqual(cases.source_industry("获客型_个人IP:原文选题"), "个人IP")


if __name__ == "__main__":
    unittest.main()
