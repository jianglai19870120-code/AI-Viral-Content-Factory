from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import workflow.benchmark_cases as cases


SCRIPT = Path(__file__).resolve().parents[2] / "10_Skills武器库" / "对标视频-结构拆解Skill（会员专享）" / "scripts" / "full_case_workflow.py"
SPEC = importlib.util.spec_from_file_location("benchmark_full_workflow", SCRIPT)
assert SPEC and SPEC.loader
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)


class FullWorkflowControllerTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        registry = root / "registry.json"
        source_root = root / "sources"
        breakdown_root = root / "breakdowns"
        source = source_root / "04_晒成果型原文（会员专享）" / "晒成果型_WorkBuddy流程.md"
        source.parent.mkdir(parents=True)
        source.write_text("原文", encoding="utf-8")
        registry.write_text(json.dumps({"schema": "benchmark-case-registry-v1", "manualEditPolicy": "audit-required", "typeCodes": {}, "cases": []}, ensure_ascii=False), encoding="utf-8")
        mocks = patch.multiple(cases, ROOT=root, REGISTRY=registry, SOURCE_ROOT=source_root, BREAKDOWN_ROOT=breakdown_root, SYNC_ROOT=root / "sync")
        return temporary, root, source, breakdown_root, mocks

    def test_start_reuses_one_runtime_plan_and_never_creates_formal_directory(self):
        temporary, root, source, breakdown_root, mocks = self.fixture()
        with temporary, mocks, patch.object(controller, "ROOT", root), patch.object(controller, "create_dispatch_record") as dispatch:
            dispatch.return_value = Namespace(path=root / "dispatch.md")
            args = Namespace(source=source, runtime_root=root / "runtime", type_code="SCHX", workbench_session="")
            first = controller.start(args)
            second = controller.start(args)
            self.assertEqual(first["status"], "started")
            self.assertEqual(second["status"], "resumed")
            self.assertEqual(first["case_id"], "SCHX-001")
            self.assertEqual(dispatch.call_count, 1)
            self.assertFalse((breakdown_root / "04_晒成果型拆解（会员专享）").exists())

    def test_formal_name_is_derived_from_source_and_frozen_big_framework_order(self):
        temporary, root, source, breakdown_root, mocks = self.fixture()
        with temporary, mocks:
            plan = cases.plan_case_registration(source=source, type_code="SCHX")
            big = root / "big.md"
            big.write_text("| 编号 | 大框架 | 大框架原文内容 |\n| --- | --- | --- |\n| F01 | 我的成就 | 原文一 |\n| F02 | 解决方案 | 原文二 |\n", encoding="utf-8")
            output = controller.formal_output(plan, big)
            self.assertEqual(output.parent.resolve(), (breakdown_root / "04_晒成果型拆解（会员专享）").resolve())
            self.assertEqual(output.name, "晒成果型_WorkBuddy流程【我的成就-解决方案】SCHX-001.md")

    def test_formal_name_excludes_topic_after_source_colon(self):
        temporary, root, source, _, mocks = self.fixture()
        renamed = source.with_name("晒成果型_AI智能体：怎么用WorkBuddy制作爆款视频.md")
        with temporary, mocks:
            source.replace(renamed)
            plan = cases.plan_case_registration(source=renamed, type_code="SCHX")
            big = root / "big.md"
            big.write_text("| 编号 | 大框架 | 大框架原文内容 |\n| --- | --- | --- |\n| F01 | 我的成就 | 原文一 |\n", encoding="utf-8")
            output = controller.formal_output(plan, big)
            self.assertEqual(output.name, "晒成果型_AI智能体【我的成就】SCHX-001.md")

    def test_repair_marks_only_the_returned_stage(self):
        temporary, root, _, _, mocks = self.fixture()
        with temporary, mocks, patch.object(controller, "report_workbench", return_value={"status": "not-requested"}):
            run_root = root / "runtime" / "run"
            controller.write_json(controller.state_path(run_root), {"case_id": "SCHX-001", "phase": "waiting-small-audit", "repair_attempts": [], "workbench_session": ""})
            result = controller.repair(Namespace(run_root=run_root, phase="small-framework", reason="小框架命名不清楚"))
            state = controller.load_state_for_case(run_root)
            self.assertEqual(result["status"], "repairing-small-framework")
            self.assertEqual(state["repair_attempts"][0]["phase"], "small-framework")

    def test_released_workbench_report_carries_audit_basis_and_receipt(self):
        with patch.object(controller, "run", return_value={"returncode": 0, "stdout": "ok", "stderr": ""}) as run:
            result = controller.report_workbench(
                "session-1", "released", "已发布", completion_basis="audit-approved", audit_receipt="receipt.json"
            )
        command = run.call_args.args[0]
        self.assertEqual(result["status"], "reported")
        self.assertIn("--completion-basis", command)
        self.assertIn("audit-approved", command)
        self.assertIn("--audit-receipt", command)
        self.assertIn("receipt.json", command)


if __name__ == "__main__":
    unittest.main()
