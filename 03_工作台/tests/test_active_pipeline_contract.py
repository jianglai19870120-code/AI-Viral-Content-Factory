from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "03_工作台" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("active_workbench_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ActivePipelineContractTest(unittest.TestCase):
    def test_checked_complete_structure_save_records_owner_freeze(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "人工结构_TJX-001.md"
            source.write_text("# 文案结构｜人工冻结选题\n\n对标复刻拆解：TJX-001\n", encoding="utf-8")
            structure = "\n".join([
                "# 文案结构｜人工冻结选题", "", "对标复刻拆解：TJX-001", "", "## 结构四", "",
                "| 编号 | 核心大框架 | 核心内容 |", "| --- | --- | --- |",
                "| F02 | 第一点：案例 | 人工冻结内容 |", "",
            ])
            previous_root = server.TODAY_CANDIDATE_ROOT
            previous_resolver = server._today_editor_resolve_file
            server.TODAY_CANDIDATE_ROOT = Path(temporary)
            server._today_editor_resolve_file = lambda surface, file_id: source
            try:
                with patch.object(server, "record_owner_frozen_structure") as freeze:
                    result = server.save_today_editor_file(
                        "structure", "temporary-structure", server._sha256_file(source),
                        {"content": structure, "filename": "√人工结构_TJX-001.md"},
                    )
            finally:
                server.TODAY_CANDIDATE_ROOT = previous_root
                server._today_editor_resolve_file = previous_resolver
        self.assertTrue(result["formalUpdated"])
        self.assertEqual(result["structureFourFreezeStatus"], "owner-frozen")
        freeze.assert_called_once()
        self.assertTrue(freeze.call_args.kwargs["structure_markdown"].name.startswith("√"))

    def test_registry_steps_drive_the_pipeline_payload(self):
        server = load_server()
        snapshot = server._active_pipeline_snapshot()
        expected = ["源知识库", "爆款内容模块", "爆款选题", "对标爆款", "爆款结构文案", "爆款成稿"]
        self.assertEqual([item["label"] for item in snapshot["stages"]], expected)
        self.assertEqual(len(snapshot["stages"]), 6)

    def test_pipeline_counts_case_branches_and_landed_copy_assets(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            copy_root = Path(temporary) / "copies"
            copy_root.mkdir()
            (copy_root / "first.md").write_text("# 第一篇", encoding="utf-8")
            (copy_root / "√second.md").write_text("# 第二篇", encoding="utf-8")
            previous_root = server.COPY_ROOT
            previous_rows = server._topic_rows
            previous_cases = server._approved_case_ids
            server.COPY_ROOT = copy_root
            server._topic_rows = lambda: [
                {"selected": True, "benchmarkCaseId": "GHX-001<br>TJX-001"},
                {"selected": True, "benchmarkCaseId": "HKX-001"},
                {"selected": True, "benchmarkCaseId": "NOT-A-CASE"},
            ]
            server._approved_case_ids = lambda: {"GHX-001", "TJX-001", "HKX-001"}
            try:
                self.assertEqual(server._selected_topic_count(), 3)
                self.assertEqual(server._generated_copy_count(), 2)
            finally:
                server.COPY_ROOT = previous_root
                server._topic_rows = previous_rows
                server._approved_case_ids = previous_cases

    def test_today_payload_exposes_configured_asset_modules(self):
        server = load_server()
        groups = server.today_work_modules()["groups"]
        self.assertEqual([group["id"] for group in groups], ["input", "topics", "cases", "structures", "copies", "gallery"])
        self.assertEqual([item["label"] for item in groups[0]["modules"]], ["推荐好书", "热门播客", "热点事件", "视频文案", "今日复盘"])
        self.assertTrue(all(isinstance(item["currentCount"], int) for group in groups for item in group["modules"]))

    def test_video_pending_count_is_the_single_unreleased_source_backlog(self):
        server = load_server()
        previous_payload = server._input_inventory_payload
        server._input_inventory_payload = lambda: {"summary": {"video-sources": {"total": 12, "completed": 3, "pending": 2, "review": 7}}}
        try:
            self.assertEqual(server._module_counts(server._today_module_index()["video-sources"]), (3, 9))
        finally:
            server._input_inventory_payload = previous_payload

    def test_video_refresh_routes_an_unapproved_next_batch_to_source_correction(self):
        server = load_server()
        module = server._today_module_index()["video-sources"]
        correction = {"batch_number": 8, "sources": [{"source_id": "VS-test-000036", "source_path": "02_资产中心/示例.md"}]}
        prompt = server._today_module_prompt(module, ["VS-test-000036｜标准化源：02_资产中心/示例.md"], video_correction=correction)
        self.assertIn("$standardize-and-inventory-sources", prompt)
        self.assertIn("process_video_correction_batch.py --batch-number 8", prompt)
        self.assertIn("$breakdown-video-pain-cards", prompt)
        self.assertIn("小息校对", prompt)

    def test_video_refresh_accepts_user_confirmed_raw_files_without_an_extra_intake_step(self):
        server = load_server()
        module = server._today_module_index()["video-sources"]
        prompt = server._today_module_prompt(module, ["video-sources-x｜用户确认输入：02_资产中心/输入.xlsx"], video_source_import=[{
            "source_id": "video-sources-x", "source_path": "02_资产中心/输入.xlsx",
        }])
        self.assertIn("用户已手动放入视频文案输入目录", prompt)
        self.assertIn("$standardize-and-inventory-sources", prompt)
        self.assertIn("$breakdown-video-pain-cards", prompt)
        self.assertNotIn("待入库", prompt)

    def test_video_refresh_can_resume_an_active_batch_instead_of_reporting_no_batch(self):
        server = load_server()
        module = server._today_module_index()["video-sources"]
        active = {
            "batch_number": 3,
            "source_ids": ["VS-test-000011", "VS-test-000012"],
            "run_dir": ".runtime/video-pain-cards/rebuild-547-v2/state/batches/batch-0003",
            "phase": "machine_evidence",
        }
        prompt = server._today_module_prompt(module, ["VS-test-000011｜续接第 3 批"], video_continuation=active)
        self.assertIn("不是新开批次", prompt)
        self.assertIn("续接正在进行的第 3 批", prompt)
        self.assertIn("不得重新校对", prompt)

    def test_work_plans_accept_every_registered_content_type(self):
        server = load_server()
        expected = {"dry-goods", "recommend", "acquisition", "hot-events", "podcast"}
        registered = {item["id"] for item in server.content_types()}
        self.assertEqual(registered, expected)
        for type_id in registered:
            plan = server._plan_payload({"contentType": type_id, "startDate": "2026-09-07", "repeatRule": "none", "targetCount": 1})
            self.assertEqual(plan["content_type"], type_id)

    def test_owner_topic_save_overwrites_formal_topic_table_without_candidate(self):
        server = load_server()
        formal_template = next(path for path in server._today_editor_paths("topics") if path.is_file())
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "topics.md"
            source.write_text(formal_template.read_text(encoding="utf-8"), encoding="utf-8")
            before = source.read_text(encoding="utf-8")
            table = server._parse_markdown_table(source)
            previous_root = server.TODAY_CANDIDATE_ROOT
            previous_resolver = server._today_editor_resolve_file
            server.TODAY_CANDIDATE_ROOT = Path(temporary)
            server._today_editor_resolve_file = lambda surface, file_id: source
            try:
                result = server.save_today_editor_file("topics", "temporary-topic", server._sha256_file(source), {"rows": table["rows"]})
                saved_text = source.read_text(encoding="utf-8")
            finally:
                server.TODAY_CANDIDATE_ROOT = previous_root
                server._today_editor_resolve_file = previous_resolver
        self.assertTrue(result["saved"])
        self.assertTrue(result["formalUpdated"])
        self.assertEqual(result["candidateStatus"], "none")
        self.assertEqual(saved_text.rstrip(), before.rstrip())

    def test_checked_structure_filename_is_immediately_filled(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            checked = Path(temporary) / "√手动确认的爆款结构.md"
            checked.write_text("# 结构尚未完整填写\n", encoding="utf-8")
            state = server._structure_four_editor_state(checked)
        self.assertTrue(state["structureFourFilled"])
        self.assertEqual(state["structureFourStatus"], "已填写结构四")
        self.assertEqual(state["structureFourReason"], "")

    def test_structure_card_counts_every_file_and_only_unchecked_files_as_pending(self):
        server = load_server()
        module = server._today_module_index()["structures"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("√已填写一.md", "✓已填写二.md", "待填写结构四.md"):
                (root / name).write_text("# 结构\n", encoding="utf-8")
            previous_module_root = server._module_root
            previous_candidates = server.generation_candidates
            server._module_root = lambda candidate, key="root": root if candidate.get("id") == "structures" and key == "root" else previous_module_root(candidate, key)
            server.generation_candidates = lambda module_id: {"candidates": []}
            try:
                self.assertEqual(server._module_work_counts(module), {"currentCount": 3, "refreshCount": 0, "editCount": 1, "pictureCount": 0})
                self.assertEqual(server._module_counts(module), (3, 1))
            finally:
                server._module_root = previous_module_root
                server.generation_candidates = previous_candidates

    def test_structure_card_does_not_count_an_unchecked_historical_revision_twice(self):
        server = load_server()
        module = server._today_module_index()["structures"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "选题_TJX-001_20260910-124832.md"
            current = root / "选题_TJX-001_20260910-161330.md"
            confirmed = root / "√另一选题_GHX-001_20260910-120000.md"
            for path in (old, current, confirmed):
                path.write_text("# 结构\n", encoding="utf-8")
            base = time.time()
            os.utime(old, (base - 20, base - 20))
            os.utime(current, (base - 10, base - 10))
            previous_module_root = server._module_root
            previous_candidates = server.generation_candidates
            server._module_root = lambda candidate, key="root": root if candidate.get("id") == "structures" and key == "root" else previous_module_root(candidate, key)
            server.generation_candidates = lambda module_id: {"candidates": []}
            try:
                self.assertEqual(server._module_work_counts(module), {"currentCount": 3, "refreshCount": 0, "editCount": 1, "pictureCount": 0})
                self.assertEqual(server._module_counts(module), (3, 1))
            finally:
                server._module_root = previous_module_root
                server.generation_candidates = previous_candidates

    def test_today_module_payload_exposes_explicit_actionable_counts(self):
        server = load_server()
        groups = server.today_work_modules()["groups"]
        modules = [item for group in groups for item in group["modules"]]
        self.assertTrue(all(isinstance(item["refreshCount"], int) for item in modules))
        self.assertTrue(all(isinstance(item["editCount"], int) for item in modules))
        self.assertTrue(all(isinstance(item["pictureCount"], int) for item in modules))
        gallery = next(item for item in modules if item["id"] == "gallery")
        self.assertEqual(gallery["refreshCount"], 0)
        self.assertEqual(gallery["editCount"], 0)

    def test_copy_card_keeps_history_in_total_but_not_in_edit_backlog(self):
        server = load_server()
        module = server._today_module_index()["copies"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / "选题_TJX-001_20260910-120000.md"
            current = root / "√选题_TJX-001_20260910-130000.md"
            old.write_text("# 正文\n", encoding="utf-8")
            current.write_text("# 正文\n", encoding="utf-8")
            base = time.time()
            os.utime(old, (base - 10, base - 10))
            previous_module_root = server._module_root
            previous_candidates = server.generation_candidates
            server._module_root = lambda candidate, key="root": root if candidate.get("id") == "copies" and key == "root" else previous_module_root(candidate, key)
            server.generation_candidates = lambda module_id: {"candidates": []}
            try:
                self.assertEqual(server._module_work_counts(module), {"currentCount": 2, "refreshCount": 0, "editCount": 0, "pictureCount": 0})
            finally:
                server._module_root = previous_module_root
                server.generation_candidates = previous_candidates

    def test_checked_case_edit_is_direct_owner_confirmation(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "干货型_测试【观点】GHX-001.md"
            content = "# 干货型_测试【观点】GHX-001\n\n| 编号 | 大框架 | 小框架 | 小框架原文内容 |\n| --- | --- | --- | --- |\n| F01 | 观点 | 核心观点 | 内容 |\n"
            source.write_text(content, encoding="utf-8")
            previous_root = server.TODAY_CANDIDATE_ROOT
            previous_resolver = server._today_editor_resolve_file
            server.TODAY_CANDIDATE_ROOT = Path(temporary)
            server._today_editor_resolve_file = lambda surface, file_id: source
            try:
                with patch.object(server, "validate_owner_approved_case_edit") as validate, patch.object(server, "record_owner_approved_case_edit", return_value={"receipt_path": "receipt.json"}) as record:
                    result = server.save_today_editor_file(
                        "cases", "temporary-case", server._sha256_file(source),
                        {"content": content, "filename": "√干货型_测试【观点】GHX-001.md"},
                    )
            finally:
                server.TODAY_CANDIDATE_ROOT = previous_root
                server._today_editor_resolve_file = previous_resolver
        self.assertTrue(result["formalUpdated"])
        self.assertFalse(result["pending"])
        self.assertEqual(result["caseOwnerApprovalStatus"], "owner-approved")
        validate.assert_called_once()
        record.assert_called_once()

    def test_unchecked_case_edit_is_direct_owner_confirmation_and_marks_it_checked(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "推荐型_测试【观点】TJX-001.md"
            content = "# 推荐型_测试【观点】TJX-001\n\n| 编号 | 大框架 | 小框架 | 小框架原文内容 |\n| --- | --- | --- | --- |\n| F01 | 观点 | 核心观点 | 内容 |\n"
            source.write_text(content, encoding="utf-8")
            previous_root = server.TODAY_CANDIDATE_ROOT
            previous_resolver = server._today_editor_resolve_file
            server.TODAY_CANDIDATE_ROOT = Path(temporary)
            server._today_editor_resolve_file = lambda surface, file_id: source
            try:
                with patch.object(server, "validate_owner_approved_case_edit") as validate, patch.object(server, "record_owner_approved_case_edit", return_value={"receipt_path": "receipt.json"}) as record:
                    result = server.save_today_editor_file(
                        "cases", "temporary-case", server._sha256_file(source), {"content": content}
                    )
            finally:
                server.TODAY_CANDIDATE_ROOT = previous_root
                server._today_editor_resolve_file = previous_resolver
        self.assertTrue(result["formalUpdated"])
        self.assertFalse(result["pending"])
        self.assertEqual(result["caseOwnerApprovalStatus"], "owner-approved")
        self.assertTrue(result["label"].startswith("√"))
        self.assertTrue(Path(result["relativePath"]).name.startswith("√"))
        validate.assert_called_once()
        record.assert_called_once()

    def test_checked_case_save_repairs_a_legacy_missing_divider(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "推荐型_测试【观点】TJX-001.md"
            malformed = "# 推荐型_测试【观点】TJX-001\n\n| 编号 | 大框架 | 小框架 | 小框架原文内容 |\n| F01 | 观点 | 判断 | 内容 |\n"
            source.write_text(malformed, encoding="utf-8")
            previous_root = server.TODAY_CANDIDATE_ROOT
            previous_resolver = server._today_editor_resolve_file
            server.TODAY_CANDIDATE_ROOT = Path(temporary)
            server._today_editor_resolve_file = lambda surface, file_id: source
            try:
                with patch.object(server, "validate_owner_approved_case_edit"), patch.object(server, "record_owner_approved_case_edit", return_value={"receipt_path": "receipt.json"}):
                    server.save_today_editor_file(
                        "cases", "temporary-case", server._sha256_file(source),
                        {"content": malformed, "filename": "√推荐型_测试【观点】TJX-001.md"},
                    )
            finally:
                server.TODAY_CANDIDATE_ROOT = previous_root
                server._today_editor_resolve_file = previous_resolver
            saved = next(Path(temporary).glob("√*.md")).read_text(encoding="utf-8")
        self.assertIn("| --- | --- | --- | --- |", saved)

    def test_refresh_prompt_carries_the_actual_scope_not_a_generic_placeholder(self):
        server = load_server()
        module = server._today_module_index()["cases"]
        prompt = server._today_module_prompt(module, ["02_资产中心/05_案例库/01_对标视频原文/A.md"])
        self.assertIn("本次刷新扫描清单", prompt)
        self.assertIn("A.md", prompt)
        self.assertNotIn("模块当前待处理范围", prompt)

    def test_gallery_refresh_forbids_textless_and_runtime_contract_edits(self):
        server = load_server()
        module = server._today_module_index()["gallery"]
        prompt = server._today_module_prompt(module, ["02_资产中心/03_输出库/01_干货型成稿/√示例.md"])
        self.assertIn("不得编辑 Skill、生成程序或小审程序", prompt)
        self.assertIn("原生生图必须一次返回含标题", prompt)
        self.assertIn("4.1.0", prompt)
        self.assertIn("evidence_nodes", prompt)
        self.assertIn("逐主卡、逐证据", prompt)
        self.assertIn("禁止无文字候选、空白主卡/证据槽", prompt)
        self.assertIn("合格成图品质参考", prompt)
        self.assertIn("哈希绑定 approved 回执", prompt)
        self.assertIn("配图门禁退回进入修复循环", prompt)
        self.assertIn("配图任务不得以 `rejected` 结束", prompt)

    def test_structure_pending_excludes_selected_rows_without_a_valid_case_or_existing_structure(self):
        server = load_server()
        rows = [
            {"title": "缺少编号", "selected": True, "benchmarkCaseId": "", "status": "待生成结构"},
            {"title": "已经生成", "selected": True, "benchmarkCaseId": "TJX-001", "status": "待生成结构"},
            {"title": "可执行选题", "selected": True, "benchmarkCaseId": "HKX-001", "status": "待生成结构"},
            {"title": "未选中", "selected": False, "benchmarkCaseId": "HKX-001", "status": "待生成结构"},
        ]
        previous_rows = server._topic_rows
        previous_titles = server._output_structure_titles
        previous_ids = server._approved_case_ids
        server._topic_rows = lambda: rows
        server._output_structure_titles = lambda: {"已经生成"}
        server._approved_case_ids = lambda: {"TJX-001", "HKX-001"}
        try:
            self.assertEqual(server._structure_pending_count(), 1)
            module = server._today_module_index()["structures"]
            self.assertEqual(server._module_pending_items(module), ["可执行选题"])
        finally:
            server._topic_rows = previous_rows
            server._output_structure_titles = previous_titles
            server._approved_case_ids = previous_ids

    def test_every_available_today_skill_prompt_has_its_registered_route_and_audit_gate(self):
        server = load_server()
        for module_id, module in server._today_module_index().items():
            if not module.get("skill"):
                continue
            prompt = server._today_module_prompt(module, ["02_资产中心/示例.md"])
            self.assertIn(f"执行 Skill：${module['skill']}", prompt, module_id)
            self.assertIn(f"执行人：{module['agent']}", prompt, module_id)
            self.assertIn("小审审核", prompt, module_id)
            self.assertIn("不得直接覆盖未审核正式资产", prompt, module_id)

    def test_one_click_prompt_locks_one_topic_and_the_final_copy_skill(self):
        server = load_server()
        prompt = server._one_click_pipeline_prompt(
            {"title": "测试选题", "table": "测试选题表.md", "benchmarkCaseId": "GHX-001"},
            regenerate=True,
        )
        self.assertIn("唯一选题：测试选题", prompt)
        self.assertIn("对标复刻拆解编号：GHX-001", prompt)
        self.assertIn("执行 Skill：$final-copy-generation", prompt)
        self.assertIn("重新生成（保留历史版本）", prompt)
        self.assertIn("交小审独立审核", prompt)

    def test_copy_scope_only_contains_explicitly_frozen_published_structures(self):
        server = load_server()
        module = server._today_module_index()["copies"]
        with tempfile.TemporaryDirectory() as temporary:
            structure = Path(temporary) / "approved-structure.md"
            structure.write_text("# structure", encoding="utf-8")
            previous_paths, previous_state = server._published_structure_paths, server._structure_four_editor_state
            server._published_structure_paths = lambda: {structure}
            server._structure_four_editor_state = lambda path: {"structureFourFilled": True}
            try:
                scope = server._module_pending_items(module)
            finally:
                server._published_structure_paths, server._structure_four_editor_state = previous_paths, previous_state
        self.assertEqual(scope, [server._project_relative_path(structure)])

    def test_structure_generation_catalog_keeps_unchecked_generated_assets_selectable(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            structure = Path(temporary) / "生成过但未确认.md"
            structure.write_text("# 文案结构：已经生成\n", encoding="utf-8")
            rows = [
                {"id": "topics.md:1", "title": "已经生成", "selected": True, "benchmarkCaseId": "GHX-001", "tableFile": "topics.md", "tablePath": "topics.md"},
                {"id": "topics.md:2", "title": "缺少对标", "selected": True, "benchmarkCaseId": "", "tableFile": "topics.md", "tablePath": "topics.md"},
            ]
            previous_rows, previous_cases, previous_structure = server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case
            server._topic_rows = lambda: rows
            server._approved_case_ids = lambda: {"GHX-001"}
            server._latest_structure_for_topic_case = lambda title, case_id: structure if title == "已经生成" and case_id == "GHX-001" else None
            try:
                catalog = server.generation_candidates("structures")["candidates"]
            finally:
                server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case = previous_rows, previous_cases, previous_structure
        generated, blocked = catalog
        self.assertTrue(generated["generated"])
        self.assertEqual("regenerate", generated["generationMode"])
        self.assertTrue(generated["eligible"])
        self.assertFalse(generated["ownerConfirmed"])
        self.assertFalse(blocked["eligible"])
        self.assertIn("已审核对标", blocked["reason"])

    def test_generation_catalog_always_displays_its_benchmark_case_id(self):
        server = load_server()
        rows = [{"id": "topics.md:1", "title": "单一对标选题", "selected": True, "benchmarkCaseId": "GHX-001", "tableFile": "topics.md", "tablePath": "topics.md"}]
        previous = (server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case)
        server._topic_rows = lambda: rows
        server._approved_case_ids = lambda: {"GHX-001"}
        server._latest_structure_for_topic_case = lambda title, case_id: None
        try:
            candidate = server.generation_candidates("structures")["candidates"][0]
        finally:
            server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case = previous
        self.assertEqual(candidate["title"], "单一对标选题 · GHX-001")

    def test_copy_generation_catalog_requires_owner_checked_structure(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            structure = Path(temporary) / "结构.md"
            copy = Path(temporary) / "正文未打勾.md"
            structure.write_text("# 文案结构：测试选题\n", encoding="utf-8")
            copy.write_text("# 测试选题\n", encoding="utf-8")
            rows = [{"id": "topics.md:1", "title": "测试选题", "selected": True, "benchmarkCaseId": "GHX-001", "tableFile": "topics.md", "tablePath": "topics.md"}]
            previous = (server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case, server._structure_four_editor_state, server._latest_copy_for_topic_case)
            server._topic_rows = lambda: rows
            server._approved_case_ids = lambda: {"GHX-001"}
            server._latest_structure_for_topic_case = lambda title, case_id: structure
            server._structure_four_editor_state = lambda path: {"structureFourFilled": True, "structureFourStatus": "已冻结结构四"}
            server._latest_copy_for_topic_case = lambda title, case_id: copy
            try:
                unchecked = server.generation_candidates("copies")["candidates"][0]
                checked_structure = structure.with_name("√结构.md")
                structure.rename(checked_structure)
                server._latest_structure_for_topic_case = lambda title, case_id: checked_structure
                candidate = server.generation_candidates("copies")["candidates"][0]
            finally:
                (server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case, server._structure_four_editor_state, server._latest_copy_for_topic_case) = previous
        self.assertFalse(unchecked["eligible"])
        self.assertIn("打 √", unchecked["reason"])
        self.assertTrue(candidate["eligible"])
        self.assertTrue(candidate["generated"])
        self.assertEqual("regenerate", candidate["generationMode"])
        self.assertFalse(candidate["ownerConfirmed"])

    def test_gallery_candidates_split_checked_copies_by_gallery_folder(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, redo = root / "√未生成正文.md", root / "√已生成正文.md"
            first.write_text("# 未生成正文\n", encoding="utf-8")
            redo.write_text("# 已生成正文\n", encoding="utf-8")
            gallery_directory = root / "已生成正文"
            gallery_directory.mkdir()
            previous_paths, previous_completed = server._owner_confirmed_copy_paths, server._gallery_completed_directories
            server._owner_confirmed_copy_paths = lambda: [first, redo]
            server._gallery_completed_directories = lambda: {server._gallery_topic_key("已生成正文"): gallery_directory}
            try:
                candidates = server.today_gallery_candidates()["candidates"]
            finally:
                server._owner_confirmed_copy_paths, server._gallery_completed_directories = previous_paths, previous_completed
        modes = {item["title"]: item["generationMode"] for item in candidates}
        self.assertEqual(modes, {"未生成正文": "initial", "已生成正文": "regenerate"})

    def test_copy_generation_marks_existing_unchecked_copy_as_generated(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_root = root / "copies"
            copy_root.mkdir()
            copy = copy_root / "未打勾正文_GHX-001_20260910.md"
            copy.write_text("# 测试选题\n", encoding="utf-8")
            structure = root / "√结构.md"
            structure.write_text("# 文案结构：测试选题\n", encoding="utf-8")
            rows = [{"id": "topics.md:1", "title": "测试选题", "selected": True, "benchmarkCaseId": "GHX-001", "tableFile": "topics.md", "tablePath": "topics.md"}]
            previous = (server.COPY_ROOT, server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case)
            server.COPY_ROOT = copy_root
            server._topic_rows = lambda: rows
            server._approved_case_ids = lambda: {"GHX-001"}
            server._latest_structure_for_topic_case = lambda title, case_id: structure
            try:
                candidate = server.generation_candidates("copies")["candidates"][0]
            finally:
                server.COPY_ROOT, server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case = previous
        self.assertTrue(candidate["generated"])
        self.assertEqual("regenerate", candidate["generationMode"])
        self.assertFalse(candidate["ownerConfirmed"])

    def test_copy_catalog_splits_multiple_case_ids_and_finds_each_branch(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ghx_structure = root / "√结构_GHX-001_.md"
            tjx_structure = root / "√结构_TJX-001_.md"
            tjx_copy = root / "正文_TJX-001_.md"
            for path in (ghx_structure, tjx_structure, tjx_copy):
                path.write_text("# 做对的事\n", encoding="utf-8")
            rows = [{
                "id": "topics.md:1", "title": "做对的事", "selected": True,
                "benchmarkCaseId": "GHX-001<br>TJX-001", "tableFile": "topics.md", "tablePath": "topics.md",
            }]
            previous = (server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case, server._latest_copy_for_topic_case)
            server._topic_rows = lambda: rows
            server._approved_case_ids = lambda: {"GHX-001", "TJX-001"}
            server._latest_structure_for_topic_case = lambda title, case_id: {"GHX-001": ghx_structure, "TJX-001": tjx_structure}.get(case_id)
            server._latest_copy_for_topic_case = lambda title, case_id: tjx_copy if case_id == "TJX-001" else None
            try:
                candidates = server.generation_candidates("copies")["candidates"]
            finally:
                (server._topic_rows, server._approved_case_ids, server._latest_structure_for_topic_case, server._latest_copy_for_topic_case) = previous
        self.assertEqual({item["benchmarkCaseId"] for item in candidates}, {"GHX-001", "TJX-001"})
        self.assertNotEqual(candidates[0]["id"], candidates[1]["id"])
        tjx = next(item for item in candidates if item["benchmarkCaseId"] == "TJX-001")
        self.assertEqual(tjx["title"], "做对的事 · TJX-001")
        self.assertTrue(tjx["generated"])
        self.assertTrue(tjx["eligible"])

    def test_case_candidates_split_generated_and_sort_newest_breakdown_first(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "sources"
            source_root.mkdir()
            old_source = source_root / "旧视频（视频原文）.md"
            new_source = source_root / "新视频（视频原文）.md"
            waiting_source = source_root / "待拆视频（视频原文）.md"
            for source in (old_source, new_source, waiting_source):
                source.write_text("原文", encoding="utf-8")
            asset_root = root / "assets"
            breakdown_root = asset_root / "05_案例库" / "02_对标复刻拆解"
            breakdown_root.mkdir(parents=True)
            old_breakdown = breakdown_root / "旧拆解.md"
            new_breakdown = breakdown_root / "新拆解.md"
            old_breakdown.write_text("旧", encoding="utf-8")
            new_breakdown.write_text("新", encoding="utf-8")
            base = time.time()
            os.utime(old_breakdown, (base - 20, base - 20))
            os.utime(new_breakdown, (base - 10, base - 10))
            previous = (server.ASSET_ROOT, server._module_root, server._case_registry_entries)
            server.ASSET_ROOT = asset_root
            server._module_root = lambda module, key="root": source_root if module.get("id") == "cases" and key == "sourceRoot" else previous[1](module, key)
            server._case_registry_entries = lambda: [
                {"id": "GHX-001", "sourceTitle": old_source.stem, "breakdownPath": str(old_breakdown)},
                {"id": "TJX-001", "sourceTitle": new_source.stem, "breakdownPath": str(new_breakdown)},
            ]
            try:
                candidates = server.today_case_candidates()["candidates"]
            finally:
                server.ASSET_ROOT, server._module_root, server._case_registry_entries = previous
        generated = [item for item in candidates if item["generated"]]
        waiting = [item for item in candidates if not item["generated"]]
        self.assertEqual([item["title"] for item in generated], [new_source.stem, old_source.stem])
        self.assertEqual(generated[0]["caseId"], "TJX-001")
        self.assertEqual([item["title"] for item in waiting], [waiting_source.stem])

    def test_case_refresh_requires_an_explicit_selection(self):
        server = load_server()
        with self.assertRaisesRegex(ValueError, "至少选择一条"):
            server.create_today_module_task("cases")

    def test_generation_selection_rejects_stale_or_ineligible_browser_rows(self):
        server = load_server()
        current = {"id": "topics.md:1", "moduleId": "structures", "title": "测试", "eligible": True, "generationMode": "initial", "benchmarkCaseId": "GHX-001", "currentFormalPath": "", "currentFormalSha256": "", "structurePath": "", "structureSha256": ""}
        current["fingerprint"] = server._generation_candidate_fingerprint(current)
        previous = server.generation_candidates
        server.generation_candidates = lambda module_id: {"candidates": [current]}
        try:
            self.assertEqual([current], server._validated_generation_selection("structures", [{"id": current["id"], "fingerprint": current["fingerprint"]}]))
            with self.assertRaisesRegex(ValueError, "已变化"):
                server._validated_generation_selection("structures", [{"id": current["id"], "fingerprint": "stale"}])
        finally:
            server.generation_candidates = previous

    def test_final_copy_candidate_requires_publication_record_and_approved_receipt(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_root = root / "copies"
            audit_root = root / "final-copy"
            copy_root.mkdir()
            audit_root.mkdir()
            formal = copy_root / "approved.md"
            formal.write_text("approved", encoding="utf-8")
            receipt = audit_root / "receipt.json"
            receipt.write_text(json.dumps({"artifactType": "final-copy-v3", "status": "approved"}), encoding="utf-8")
            publication = audit_root / "publication.json"
            publication.write_text(json.dumps({"schema": "final-copy-publication-v1", "status": "published", "formalPath": str(formal), "formalSha256": server._sha256_file(formal), "auditReceipt": str(receipt)}), encoding="utf-8")
            previous_copy, previous_audit = server.COPY_ROOT, server.FORMAL_AUDIT_ROOT
            server.COPY_ROOT, server.FORMAL_AUDIT_ROOT = copy_root, root
            try:
                self.assertEqual({str(path.resolve()).lower() for path in server._published_copy_paths()}, {str(formal.resolve()).lower()})
                formal.write_text("changed", encoding="utf-8")
                self.assertEqual(server._published_copy_paths(), set())
            finally:
                server.COPY_ROOT, server.FORMAL_AUDIT_ROOT = previous_copy, previous_audit

    def test_final_copy_v3_publication_is_counted(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); copy_root = root / "copies"; audit_root = root / "final-copy"
            copy_root.mkdir(); audit_root.mkdir()
            formal = copy_root / "approved-v3.md"; formal.write_text("# V3 正文\n", encoding="utf-8")
            receipt = audit_root / "receipt.json"
            receipt.write_text(json.dumps({"schema": "audit-receipt-v3", "artifactType": "final-copy-v3", "status": "approved"}), encoding="utf-8")
            publication = audit_root / "publication.json"
            publication.write_text(json.dumps({"schema": "final-copy-publication-v1", "status": "published", "formalPath": str(formal), "formalSha256": server._sha256_file(formal), "auditReceipt": str(receipt)}), encoding="utf-8")
            previous_copy, previous_audit = server.COPY_ROOT, server.FORMAL_AUDIT_ROOT
            server.COPY_ROOT, server.FORMAL_AUDIT_ROOT = copy_root, root
            try:
                self.assertEqual(server._published_copy_paths(), {formal.resolve()})
                self.assertEqual(server._output_copy_titles(), {"V3正文"})
            finally:
                server.COPY_ROOT, server.FORMAL_AUDIT_ROOT = previous_copy, previous_audit


if __name__ == "__main__":
    unittest.main()
