from __future__ import annotations

import json
import importlib.util
import hashlib
import tempfile
import unittest
from pathlib import Path

from workflow.asset_paths import active_paths
from workflow import data_center


ROOT = Path(__file__).resolve().parents[2]
TODAY_MODULES = ROOT / "03_工作台" / "config" / "today-work-modules.json"
SYSTEM_REGISTRY = ROOT / "00_系统说明" / "system-registry.json"
CASE_REGISTRY = ROOT / "00_系统说明" / "benchmark-case-registry.json"
WEAPON_ROOT = ROOT / "10_Skills武器库"
CODEX_SKILL_ROOT = ROOT / ".agents" / "skills"
FORMAL_AUDIT_ROOT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "00_正式审核回执" / "benchmark-video-structure"
OWNER_APPROVAL_ROOT = ROOT / "01_Agent系统" / "01_小姜-CEO助理Agent" / "人工确认回执" / "benchmark-video-structure"
SERVER = ROOT / "03_工作台" / "server.py"
FRONTEND = ROOT / "03_工作台" / "frontend" / "app.js"
FIXED_CANVAS = ROOT / "03_工作台" / "frontend" / "fixed-canvas.css"
MOTION_SYSTEM = ROOT / "03_工作台" / "frontend" / "motion-system.css"
BRAND_PORTRAITS = ROOT / "03_工作台" / "01_品牌设计系统" / "人物头像" / "正式头像"
FOLDER_AGENT = ROOT / "03_工作台" / "scripts" / "codex_desktop_bridge_agent.py"
DESKTOP_BRIDGE = ROOT / "03_工作台" / "scripts" / "codex_desktop_bridge.py"
VISIBLE_EVENT_REPORTER = ROOT / "03_工作台" / "scripts" / "report_visible_task_event.py"
GALLERY_ADAPTER = CODEX_SKILL_ROOT / "generate-ip-ppt" / "SKILL.md"
GALLERY_MANIFEST = CODEX_SKILL_ROOT / "generate-ip-ppt" / ".generated-manifest.json"
GALLERY_SOURCE = WEAPON_ROOT / "IP视觉PPT生成Skill" / "SKILL.md"


def skill_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("---"):
        _, _, text = text[3:].partition("---")
    return text.strip()


def load_server():
    spec = importlib.util.spec_from_file_location("workbench_v1_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorkbenchV1ContractTest(unittest.TestCase):
    def test_registered_asset_directories_are_real(self):
        missing = [key for key, item in active_paths(ROOT).items() if not item["exists"]]
        self.assertEqual(missing, [], f"现役资产目录不存在：{missing}")

    def test_today_refresh_routes_match_the_current_skill_contract(self):
        payload = json.loads(TODAY_MODULES.read_text(encoding="utf-8"))
        registry = json.loads(SYSTEM_REGISTRY.read_text(encoding="utf-8"))
        registered_skills = {str(item["id"]): item for item in registry["skills"]}
        modules = {}
        for group in payload["groups"]:
            if group["id"] == "input":
                modules.update({item["id"]: item for item in group["modules"]})
            else:
                modules[group["id"]] = group
        expected = {
            "books": "breakdown-book-modules",
            "podcasts": "breakdown-podcast-modules",
            "video-sources": "breakdown-video-pain-cards",
            "work-journals": "breakdown-work-journal",
            "topics": "classify-benchmark-topics",
            "cases": "benchmark-video-structure-breakdown",
            "structures": "copy-structure-generation",
            "copies": "final-copy-generation",
            "gallery": "generate-ip-ppt",
        }
        self.assertEqual({key: modules[key]["skill"] for key in expected}, expected)
        self.assertEqual(modules["events"]["refreshMode"], "waiting-integration")
        self.assertEqual(modules["events"]["skill"], "")
        for skill_id in expected.values():
            self.assertIn(skill_id, registered_skills, f"工作台路由未进入中央 Skill 注册表：{skill_id}")
            self.assertTrue((WEAPON_ROOT / str(registered_skills[skill_id]["sourceDir"]) / "SKILL.md").is_file(), f"工作台路由未绑定武器库源 Skill：{skill_id}")
            skill_file = CODEX_SKILL_ROOT / skill_id / "SKILL.md"
            self.assertTrue(skill_file.is_file(), f"工作台路由缺少已安装 Skill：{skill_id}")
            self.assertTrue(skill_body(skill_file), f"工作台路由 Skill 为空：{skill_id}")

    def test_registered_professional_skill_sources_and_codex_mirrors_exist(self):
        registry = json.loads(SYSTEM_REGISTRY.read_text(encoding="utf-8"))
        for item in registry["skills"]:
            skill_id = item["id"]
            source = WEAPON_ROOT / item["sourceDir"] / "SKILL.md"
            mirror = CODEX_SKILL_ROOT / skill_id / "SKILL.md"
            self.assertTrue(source.is_file(), f"武器库源 Skill 不存在：{skill_id}")
            self.assertTrue(mirror.is_file(), f"Codex 镜像 Skill 不存在：{skill_id}")
            self.assertTrue(skill_body(source), f"武器库源 Skill 为空：{skill_id}")
            self.assertTrue(skill_body(mirror), f"Codex 镜像 Skill 为空：{skill_id}")

    def test_reserved_team_members_are_registered_with_existing_portraits(self):
        registry = json.loads(SYSTEM_REGISTRY.read_text(encoding="utf-8"))
        agents = {str(item["id"]): item for item in registry["agents"]}
        expected = {
            "xiaoshu": ("小数", "09_小数-内容复盘Agent", "xiaoshu-v4.png"),
            "xiaojian": ("小剪", "10_小剪-视频制作Agent", "xiaojian-v4.png"),
            "xiaofa": ("小发", "11_小发-发布运营Agent", "xiaofa-v4.png"),
        }
        frontend = FRONTEND.read_text(encoding="utf-8")
        motion = MOTION_SYSTEM.read_text(encoding="utf-8")
        for agent_id, (display_name, agent_dir, portrait) in expected.items():
            self.assertIn(agent_id, agents)
            self.assertEqual(display_name, agents[agent_id]["displayName"])
            self.assertEqual(agent_dir, agents[agent_id]["dir"])
            self.assertEqual("planned", agents[agent_id]["status"])
            self.assertEqual("", agents[agent_id]["skill"])
            self.assertTrue((BRAND_PORTRAITS / portrait).is_file(), f"缺少待加入成员头像：{portrait}")
            self.assertIn(f"{agent_id}:", frontend)
        self.assertIn("data-team-stage", frontend)
        self.assertIn("data-team-motion", frontend)
        self.assertIn("motion-team-rail-light", motion)
        self.assertIn("motion-team-card-light", motion)

    def test_editor_focus_mode_collapses_the_file_sidebar_without_changing_document_scale(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        fixed_canvas = FIXED_CANVAS.read_text(encoding="utf-8")
        self.assertIn("fileSidebarCollapsed", frontend)
        self.assertIn("data-editor-files-toggle", frontend)
        self.assertIn("editor.fileSidebarCollapsed=editor.focusMode", frontend)
        self.assertIn("is-files-collapsed", fixed_canvas)
        self.assertIn("grid-template-columns: 0 minmax(0, 1fr)", fixed_canvas)
        self.assertIn(".today-editor-files-toggle", fixed_canvas)

    def test_plan_completion_overview_counts_only_due_occurrences(self):
        server = load_server()
        original_db_path, original_initialized = server.DB_PATH, server.STORE_INITIALIZED_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                server.DB_PATH = Path(tmpdir) / "workbench.db"
                server.STORE_INITIALIZED_PATH = None
                server.initialize_store()
                created = "2026-09-01T00:00:00+08:00"
                plans = [
                    ("once", "2026-09-10", "[]", "none", 0, "2026-09-10"),
                    ("weekly", "2026-09-01", "[0]", "weekly", 0, "2026-09-30"),
                    ("monthly", "2026-07-31", "[]", "monthly", 31, "2026-09-30"),
                    ("future", "2026-09-30", "[]", "none", 0, "2026-09-30"),
                ]
                with server._connection() as connection:
                    for plan_id, starts_at, weekdays, repeat_rule, monthly_day, ends_at in plans:
                        connection.execute(
                            "INSERT INTO plans (id,content_type,plan_date,weekdays,repeat_rule,monthly_day,ends_at,remind_time,target_count,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (plan_id, "dry-goods", starts_at, weekdays, repeat_rule, monthly_day, ends_at, "00:00", 1, created, created),
                        )
                    for plan_id, occurrence in (("once", "2026-09-10"), ("weekly", "2026-09-07"), ("future", "2026-09-30")):
                        connection.execute(
                            "INSERT INTO plan_completions (plan_id,occurrence_date,content_type,target_count,completed_at) VALUES (?,?,?,?,?)",
                            (plan_id, occurrence, "dry-goods", 1, created),
                        )
                overview = server.plan_completion_overview(server.date(2026, 9, 12))
                self.assertEqual({"totalDueOccurrences": 4, "completedOccurrences": 2, "completionRatePercent": 50}, overview)
        finally:
            server.DB_PATH, server.STORE_INITIALIZED_PATH = original_db_path, original_initialized

    def test_today_module_task_summaries_scan_sessions_once(self):
        server = load_server()
        original_rows = server._rows
        calls = []
        try:
            def rows(query, *_args):
                calls.append(query)
                return [
                    {"workflow_json": json.dumps({"todayModuleId": "topics"}), "updated_at": "2026-09-13T09:00:00+08:00", "status": "completed", "approval_status": "approved"},
                    {"workflow_json": json.dumps({"todayModuleId": "copies"}), "updated_at": "2026-09-13T08:00:00+08:00", "status": "running", "approval_status": "pending"},
                ]
            server._rows = rows
            summaries = server._module_last_tasks({"topics", "copies", "gallery"})
            self.assertEqual(1, len(calls))
            self.assertEqual("completed", summaries["topics"]["taskStatus"])
            self.assertEqual("running", summaries["copies"]["taskStatus"])
            self.assertEqual("尚未创建任务", summaries["gallery"]["taskStatus"])
        finally:
            server._rows = original_rows

    def test_dashboard_page_materializes_only_the_selected_page_data(self):
        server = load_server()
        originals = {name: getattr(server, name) for name in (
            "initialize_store", "load_snapshot", "content_types", "list_sessions", "bridge_status", "desktop_navigation_status", "_brand_info",
            "today_work_modules", "pipeline_snapshot", "copy_production_capability_status", "asset_overview", "_apply_snapshot_asset_counts",
            "agent_overview", "plan_completion_overview", "cumulative_output_by_content_type", "gallery_output_count",
        )}
        calls = []
        try:
            server.initialize_store = lambda: None
            server.load_snapshot = lambda: {}
            server.content_types = lambda: []
            server.list_sessions = lambda **_kwargs: []
            server.bridge_status = lambda: {}
            server.desktop_navigation_status = lambda: {}
            server._brand_info = lambda: {}
            server.today_work_modules = lambda: calls.append("today") or {}
            server.pipeline_snapshot = lambda: calls.append("pipeline") or {}
            server.copy_production_capability_status = lambda: calls.append("capability") or {}
            server.asset_overview = lambda: calls.append("assets") or {}
            server._apply_snapshot_asset_counts = lambda assets, _snapshot: assets
            server.agent_overview = lambda: calls.append("team") or {"agents": []}
            server.plan_completion_overview = lambda: calls.append("plans") or {}
            server.cumulative_output_by_content_type = lambda: calls.append("outputs") or []
            server.gallery_output_count = lambda: calls.append("gallery") or 0

            today = server.dashboard_page("today")
            self.assertEqual(["today"], calls)
            self.assertNotIn("sessions", today)
            self.assertNotIn("approvals", today)
            calls.clear()
            server.dashboard_page("pipeline")
            self.assertEqual(["pipeline", "capability"], calls)
            calls.clear()
            server.dashboard_page("data")
            self.assertEqual(["pipeline", "plans", "assets", "outputs", "gallery"], calls)
        finally:
            for name, value in originals.items():
                setattr(server, name, value)

    def test_frontend_navigation_cancels_stale_page_requests_and_reuses_today_snapshot(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        self.assertIn("new AbortController()", frontend)
        self.assertIn("requestVersion!==pageRequestVersion", frontend)
        self.assertIn("persistTodaySnapshot", frontend)
        self.assertIn("restoreTodaySnapshot", frontend)
        self.assertIn("Promise.all([dashboardRequest,calendarRequest])", frontend)

    def test_cumulative_outputs_keep_registry_order_and_ignore_non_markdown_assets(self):
        server = load_server()
        original_root, original_registry = server.ASSET_ROOT, server.CONTENT_TYPE_REGISTRY
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                asset_root = Path(tmpdir) / "assets"
                registry_path = Path(tmpdir) / "content-types.json"
                types = []
                for item_id, name, status, output in (
                    ("dry-goods", "干货型", "deployed", "outputs/dry"),
                    ("recommend", "推荐型", "deployed", "outputs/recommend"),
                    ("acquisition", "获客型", "not-deployed", None),
                    ("hot-events", "热点事件型", "not-deployed", None),
                    ("podcast", "播客解读型", "not-deployed", None),
                ):
                    types.append({"id": item_id, "name": name, "memberOnly": item_id != "dry-goods", "workflowMode": "full" if status == "deployed" else "assets-plan", "deploymentStatus": status, "roots": {"input": "inputs", "process": "process", "output": output}})
                registry_path.write_text(json.dumps({"schema": "ai-content-workbench-content-types-v1", "types": types}, ensure_ascii=False), encoding="utf-8")
                (asset_root / "outputs" / "dry" / "history").mkdir(parents=True)
                (asset_root / "outputs" / "dry" / "current.md").write_text("# current", encoding="utf-8")
                (asset_root / "outputs" / "dry" / "history" / "old.MD").write_text("# old", encoding="utf-8")
                (asset_root / "outputs" / "dry" / "image.png").write_bytes(b"png")
                (asset_root / "outputs" / "dry" / "README.md").write_text("ignored", encoding="utf-8")
                server.ASSET_ROOT, server.CONTENT_TYPE_REGISTRY = asset_root, registry_path
                result = server.cumulative_output_by_content_type()
                self.assertEqual(["干货型", "推荐型", "获客型", "热点事件型", "播客解读型"], [item["name"] for item in result])
                self.assertEqual([2, 0, 0, 0, 0], [item["count"] for item in result])
                self.assertEqual([True, True, False, False, False], [item["deployed"] for item in result])
        finally:
            server.ASSET_ROOT, server.CONTENT_TYPE_REGISTRY = original_root, original_registry

    def test_gallery_output_count_uses_topic_packages_not_individual_images(self):
        server = load_server()
        original_gallery_root = server.GALLERY_ROOT
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                gallery_root = Path(tmpdir) / "gallery"
                (gallery_root / "第一篇成稿").mkdir(parents=True)
                (gallery_root / "第一篇成稿" / "page-1.png").write_bytes(b"png")
                (gallery_root / "第一篇成稿" / "page-2.png").write_bytes(b"png")
                (gallery_root / "第二篇成稿").mkdir()
                (gallery_root / "README.md").write_text("not a package", encoding="utf-8")
                server.GALLERY_ROOT = gallery_root
                self.assertEqual(2, server.gallery_output_count())
        finally:
            server.GALLERY_ROOT = original_gallery_root

    def test_team_cycle_and_full_width_structure_table_contracts_are_present(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        table_styles = (ROOT / "03_工作台" / "frontend" / "today-v9.css").read_text(encoding="utf-8")
        self.assertIn("TEAM_CYCLE_INTERVAL_MS = 3000", frontend)
        self.assertIn("scheduleTeamCycle", frontend)
        self.assertIn("structureInlineMarkdownHTML", frontend)
        self.assertIn("structureEditableMarkdown", frontend)
        self.assertIn("table-layout: fixed", table_styles)
        self.assertIn("overflow-wrap: anywhere", table_styles)
        self.assertIn(".today-structure-table-wrap { min-width: 0; overflow: hidden", table_styles)

    def test_gallery_adapter_and_workbench_route_use_the_current_4_1_contract(self):
        server = load_server()
        adapter = GALLERY_ADAPTER.read_text(encoding="utf-8")
        source = GALLERY_SOURCE.read_text(encoding="utf-8")
        manifest = json.loads(GALLERY_MANIFEST.read_text(encoding="utf-8"))
        prompt = server._today_module_prompt(
            server._today_module_index()["gallery"],
            ["02_资产中心/03_输出库/01_干货型成稿/√示例.md"],
        )
        self.assertEqual("4.1.0", manifest["version"])
        # The repository adapter contract hashes the full generated payload,
        # not only SKILL.md; otherwise changes to Codex UI metadata drift
        # without being detected.
        from tools.platform.sync_skills import digest
        adapter_root = GALLERY_ADAPTER.parent
        self.assertEqual(
            digest({
                "SKILL.md": GALLERY_ADAPTER.read_bytes(),
                "agents/openai.yaml": (adapter_root / "agents" / "openai.yaml").read_bytes(),
            }),
            manifest["adapterPayloadSha256"],
        )
        self.assertIn("4.1.0", adapter)
        self.assertIn("4.1.0", source)
        self.assertIn("4.1.0", prompt)
        self.assertIn("evidence_nodes", prompt)
        self.assertIn("逐主卡、逐证据", prompt)
        self.assertIn("配图门禁退回进入修复循环", prompt)

    def test_gallery_visible_rejection_continues_the_repair_loop(self):
        server = load_server()
        original_db_path, original_initialized = server.DB_PATH, server.STORE_INITIALIZED_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                server.DB_PATH = Path(tmpdir) / "workbench.db"
                server.STORE_INITIALIZED_PATH = None
                server.initialize_store()
                session_id = "gallery-repair-loop"
                with server._connection() as connection:
                    connection.execute(
                        """INSERT INTO sessions
                        (id,title,message,action,status,approval_status,bridge_status,workflow_json,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (
                            session_id, "配图库刷新", "", "today-refresh", "running", "approved", "visible-task-reported",
                            json.dumps({"todayModuleId": "gallery"}), server.now(), server.now(),
                        ),
                    )
                result = server.report_visible_task_event({"sessionId": session_id, "event": "rejected"})
                self.assertEqual("repairing", result["status"])
                detail = server._rows("SELECT detail_json FROM events WHERE session_id=? ORDER BY id DESC LIMIT 1", (session_id,))[0]
                self.assertEqual("repairing", json.loads(detail["detail_json"])["effectiveEvent"])
        finally:
            server.DB_PATH, server.STORE_INITIALIZED_PATH = original_db_path, original_initialized

    def test_gallery_desktop_disconnect_queues_recovery_instead_of_blocking(self):
        server = load_server()
        original_db_path, original_initialized = server.DB_PATH, server.STORE_INITIALIZED_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                server.DB_PATH = Path(tmpdir) / "workbench.db"
                server.STORE_INITIALIZED_PATH = None
                server.initialize_store()
                session_id = "gallery-reconnect-loop"
                with server._connection() as connection:
                    connection.execute(
                        """INSERT INTO sessions
                        (id,title,message,action,status,approval_status,bridge_status,codex_thread_id,workflow_json,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (session_id, "配图库恢复", "", "today-refresh", "running", "approved", "reconnect-required", "01234567-89ab-cdef-0123-456789abcdef", json.dumps({"todayModuleId": "gallery"}), server.now(), server.now()),
                    )
                server.reconcile_interrupted_sessions()
                result = server._rows("SELECT status,bridge_status,recovery_next_at FROM sessions WHERE id=?", (session_id,))[0]
                self.assertEqual("reconnecting", result["status"])
                self.assertEqual("desktop-bridge-recovery-queued", result["bridge_status"])
                self.assertTrue(result["recovery_next_at"])
        finally:
            server.DB_PATH, server.STORE_INITIALIZED_PATH = original_db_path, original_initialized

    def test_case_registry_paths_and_audit_receipts_are_current(self):
        registry = json.loads(CASE_REGISTRY.read_text(encoding="utf-8"))
        for item in registry["cases"]:
            breakdown = ROOT / item["breakdownPath"]
            owner_approved = str(item.get("manualEditPolicy") or registry.get("manualEditPolicy") or "") == "owner-approved"
            receipt = (OWNER_APPROVAL_ROOT / f"{item['id']}_人工确认回执.json"
                       if owner_approved else FORMAL_AUDIT_ROOT / f"{item['id']}_审核回执.json")
            self.assertTrue(breakdown.is_file(), f"对标复刻拆解路径失效：{item['id']}")
            self.assertTrue(receipt.is_file(), f"对标复刻拆解缺少正式审核回执：{item['id']}")

    def test_desktop_bridge_never_treats_queueing_as_a_confirmed_open(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        server = SERVER.read_text(encoding="utf-8")
        agent = FOLDER_AGENT.read_text(encoding="utf-8")
        desktop_bridge = DESKTOP_BRIDGE.read_text(encoding="utf-8")
        reporter = VISIBLE_EVENT_REPORTER.read_text(encoding="utf-8")
        self.assertIn("requestDesktopFolder", frontend)
        self.assertIn("folder-status?requestId=", frontend)
        self.assertIn("已确认在本机打开", frontend)
        self.assertNotIn("toast('已发送打开请求')", frontend)
        self.assertIn("desktop-task-unconfirmed", server)
        self.assertIn('"submitted"', server.split("ACTIVE_SESSION_STATUSES", 1)[1].split("\n", 1)[0])
        self.assertIn("desktop-native-thread-created", server)
        self.assertIn("nativeTaskCreateAvailable", server)
        self.assertIn("folder_worker", agent)
        self.assertIn("资源管理器未显示目标文件夹，未确认打开成功", agent)
        self.assertIn("explorer_folder_paths", agent)
        self.assertNotIn("os.startfile", agent)
        task_creator = desktop_bridge.split("def create_visible_task", 1)[1].split("def main", 1)[0]
        self.assertIn('"create_thread"', task_creator)
        self.assertIn('"native-created"', task_creator)
        self.assertNotIn("hotkey(VK_N)", task_creator)
        self.assertIn("ProgramData", reporter)

    def test_desktop_bridge_discovers_current_desktop_app_tool_pipes(self):
        """New Desktop builds expose the pipe in their environment, not codex.exe args."""
        desktop_bridge = DESKTOP_BRIDGE.read_text(encoding="utf-8")
        candidate_block = desktop_bridge.split("def _native_pipe_candidates", 1)[1].split("def _native_read_exact", 1)[0]
        self.assertIn('os.environ.get("CODEX_APP_TOOLS_PIPE_PATH", "")', candidate_block)
        self.assertIn('"cmd.exe", "/d", "/s", "/c"', candidate_block)
        self.assertIn("codex-(?:browser-use|computer-use)", candidate_block)
        self.assertIn("tools/list", desktop_bridge)

    def test_all_approved_workbench_sessions_queue_a_visible_codex_task(self):
        server = SERVER.read_text(encoding="utf-8")
        approve_block = server.split("def approve_session", 1)[1].split("def report_visible_task_event", 1)[0]
        report_block = server.split("def report_visible_task_event", 1)[1].split("def _handle", 1)[0]
        self.assertIn("return _queue_visible_task(session_id)", approve_block)
        self.assertNotIn("bridge_status=?, codex_thread_id=?", approve_block)
        self.assertIn('workflow.get("todayModuleId")', report_block)
        self.assertIn("record_today_refresh_completion(", report_block)
        self.assertIn('refresh_module_id == "gallery" and event == "rejected"', report_block)
        self.assertIn('effective_event = "repairing"', report_block)

    def test_visible_codex_task_is_never_falsely_cancelled_by_the_retired_bridge(self):
        server = SERVER.read_text(encoding="utf-8")
        cancel_block = server.split("def cancel_session", 1)[1].split("def continue_session", 1)[0]
        self.assertIn("请在对应 Codex 任务里终止", cancel_block)
        self.assertNotIn("CODEX_BRIDGE.interrupt_task", cancel_block)

    def test_legacy_app_server_approval_cannot_reactivate_in_v1(self):
        server = SERVER.read_text(encoding="utf-8")
        approval_block = server.split("def respond_to_approval", 1)[1].split("def recover_session", 1)[0]
        self.assertIn("不再代理后台 App Server 审批", approval_block)
        self.assertNotIn("CODEX_BRIDGE.respond_to_server_request", approval_block)

    def test_frontend_uses_only_current_folder_open_routes(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn("/api/open-asset-directory", frontend)
        self.assertIn("/api/today/open-folder", frontend)
        self.assertNotIn("/api/open-folder", frontend)
        self.assertNotIn("/api/open-gallery", frontend)
        self.assertNotIn('path == "/api/open-folder"', server)
        self.assertNotIn('path == "/api/open-pipeline-stage"', server)

    def test_structure_and_copy_refresh_share_the_selectable_generation_window(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        server = SERVER.read_text(encoding="utf-8")
        self.assertIn("generationSelectionModal", frontend)
        self.assertIn("/api/today/generation-candidates", frontend)
        self.assertIn("caseSelectionModal", frontend)
        self.assertIn("/api/today/case-candidates", frontend)
        self.assertIn("moduleId==='cases'", frontend)
        self.assertIn("moduleId==='structures'||moduleId==='copies'", frontend)
        self.assertIn("generationSelectionModal('copies',{pipeline:true})", frontend)
        self.assertIn("{moduleId:button.dataset.generationModule,selected:selections}", frontend)
        self.assertIn("data-generation-feedback", frontend)
        self.assertIn("bindGenerationSubmit(document.querySelector('#modal [data-generation-submit]'))", frontend)
        self.assertNotIn("oneClickRegenerate", frontend)
        self.assertIn("def generation_candidates", server)
        self.assertIn("def today_case_candidates", server)
        self.assertIn("def _validated_generation_selection", server)
        self.assertIn('payload.get("selected") if "selected" in payload else payload.get("selections")', server)
        self.assertIn("generationSelections", server)

    def test_empty_heartbeat_does_not_discard_a_verified_window_for_same_agent(self):
        server = load_server()
        original_details = server.DESKTOP_BRIDGE_AGENT_DETAILS
        original_seen = server.DESKTOP_BRIDGE_AGENT_LAST_SEEN
        try:
            server.DESKTOP_BRIDGE_AGENT_DETAILS = {
                "agentId": "same-agent", "codexWindowDetected": True,
                "codexWindowHandle": 12345, "interactiveSession": True,
            }
            server.update_desktop_bridge_agent({
                "agentId": "same-agent", "windowsSessionId": 1,
                "interactiveSession": True, "codexWindowDetected": False,
                "codexWindowHandle": 0, "folderLaunchAvailable": True,
            })
            self.assertTrue(server.DESKTOP_BRIDGE_AGENT_DETAILS["codexWindowDetected"])
            self.assertEqual(server.DESKTOP_BRIDGE_AGENT_DETAILS["codexWindowHandle"], 12345)
        finally:
            server.DESKTOP_BRIDGE_AGENT_DETAILS = original_details
            server.DESKTOP_BRIDGE_AGENT_LAST_SEEN = original_seen

    def test_v1_catalog_pipeline_and_data_totals_share_live_sources(self):
        server = load_server()
        assets = server.asset_overview()
        catalog = {str(item["id"]): item for item in assets["catalog"]}
        skills = {str(item["id"]): item for item in catalog["skills"]["items"]}
        self.assertTrue(skills["skill-cases"]["memberOnly"])
        self.assertIn("会员专享", skills["skill-cases"]["label"])
        self.assertEqual(
            assets["stageTotals"],
            {stage: int(catalog[stage]["count"]) for stage in ("input", "process", "output")},
        )
        inventory = server._input_inventory_payload()["summary"]
        self.assertEqual(catalog["input"]["count"], sum(int(item["total"]) for item in inventory.values()))
        pipeline = {str(item["id"]): item for item in server.pipeline_snapshot()["stages"]}
        self.assertEqual(pipeline["source-knowledge"]["count"], catalog["input"]["count"])
        self.assertEqual(pipeline["content-modules"]["count"], catalog["process"]["count"])

    def test_data_center_uses_active_pipeline_counts_for_every_conversion_stage(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        render_data = frontend.split("function renderData", 1)[1].split("let modalCloseTimer", 1)[0]
        self.assertIn("const value=nf(stage.count||0);", render_data)
        self.assertNotIn("pipeline.filled", render_data)

    def test_data_center_distribution_covers_the_six_asset_libraries(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        styles = (ROOT / "03_工作台" / "frontend" / "app-pages-v10.css").read_text(encoding="utf-8")
        render_data = frontend.split("function renderData", 1)[1].split("let modalCloseTimer", 1)[0]
        self.assertIn("const sixLibraryIds=['input','process','output','topics','cases','gallery']", render_data)
        self.assertIn("<h2>六库资产分布</h2>", render_data)
        self.assertIn("data-distribution-segment", render_data)
        self.assertIn("function bindDistributionRing", frontend)
        self.assertIn(".distribution-ring", styles)
        self.assertIn("linear-gradient(135deg", styles)
        self.assertNotIn("<h2>三库资产分布</h2>", render_data)

    def test_data_center_uses_the_six_named_content_modules_in_a_radar_chart(self):
        frontend = FRONTEND.read_text(encoding="utf-8")
        styles = (ROOT / "03_工作台" / "frontend" / "app-pages-v10.css").read_text(encoding="utf-8")
        render_data = frontend.split("function renderData", 1)[1].split("let modalCloseTimer", 1)[0]
        self.assertIn("const moduleLabels=['观点','痛点','误区','解决方案','案例','推荐理由']", render_data)
        self.assertIn('<h2>内容模块</h2>${moduleRadar}', render_data)
        self.assertNotIn("处理库构成", render_data)
        self.assertIn(".module-radar", styles)

    def test_data_center_snapshot_uses_live_library_totals_and_registered_cumulative_outputs(self):
        server = load_server()
        _source_counts, totals, metrics = data_center._active_asset_counts()
        assets = server.asset_overview()
        pipeline = {str(item["id"]): item for item in server.pipeline_snapshot()["stages"]}
        self.assertEqual(totals, assets["stageTotals"])
        self.assertEqual(metrics["contentModules"], pipeline["content-modules"]["count"])
        cumulative = server.cumulative_output_by_content_type()
        self.assertEqual(["干货型", "推荐型", "获客型", "热点事件型", "播客解读型"], [item["name"] for item in cumulative])
        self.assertTrue(all(isinstance(item["count"], int) and item["count"] >= 0 for item in cumulative))
        self.assertIn("contentOutputStats", FRONTEND.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
