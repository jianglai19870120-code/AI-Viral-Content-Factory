from __future__ import annotations

import importlib.util
import hashlib
import json
import copy
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "10_Skills武器库" / "IP视觉PPT生成Skill" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load_module("ip_visual_builder_v4", "build_ip_ppt.py")
AUDIT_SCRIPTS = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts"
sys.path.insert(0, str(AUDIT_SCRIPTS))
audit = load_module("ip_visual_work_package_audit_v4", str(AUDIT_SCRIPTS / "audit_visual_work_package.py"))
output_audit = load_module("ip_visual_output_audit_v4", str(AUDIT_SCRIPTS / "audit_visual_outputs.py"))


def relax_fixture_text() -> str:
    """A self-contained source fixture; retired output-library files are not test dependencies."""
    return """# 要放松，不要自律
日程排得越满，心力越快耗尽；先放松才能恢复。

## 误区1：总想排满日程
把一天塞满任务，会让压力不断上升。

## 误区2：靠意志力硬扛
硬扛会触发破窗效应，最后彻底摆烂。

## 原因1：心力有限
心力有限，放松才能恢复；切换任务会消耗电量。

## 原因2：时间不等于专注
每个人都有24小时，但专注时长不同。

## 原因3：频繁切换更耗能
回复消息和刷手机，会让任务在分叉间切换。

## 方法1：给自己留白
安排休息椅和充电时间，恢复心力。

## 方法2：只做最重要的一件事
把唯一任务置顶，其他任务暂时放下。

## 方法3：建立节奏
用分段时间轴，安排深度思考和恢复。

## 总结：先放松再自律
放松不是偷懒，而是为了持续完成重要成果。
"""


def three_choices_fixture() -> tuple[str, str, list[dict[str, str]]]:
    title = "三种路径只能选一个"
    body = """第1个，餐饮。
先拿30万装修店面，后面还要招员工。
第2个，电商。
先囤20万的货，再做选品和投流。
第3个，技能。
先用技能接单，再验证客户是否愿意付费。"""
    assignments = [
        {"source_quote": "第1个，餐饮。\n先拿30万装修店面，后面还要招员工。", "visible_text": "餐饮", "information_type": "supporting-object"},
        {"source_quote": "第2个，电商。\n先囤20万的货，再做选品和投流。", "visible_text": "电商", "information_type": "supporting-object"},
        {"source_quote": "第3个，技能。\n先用技能接单，再验证客户是否愿意付费。", "visible_text": "技能", "information_type": "supporting-object"},
    ]
    return title, body, assignments


def sample_keyword_visual_mappings() -> list[dict[str, object]]:
    return [
        {
            "keyword": "心力", "source_quote": "心力有限，放松才能恢复。", "source_field": "page_body",
            "source_label": "心力", "concept": "心力", "semantic_role": "object",
            "visual_form": "object", "expected_visual_module": "component-map",
            "visual_module_id": "keyword-01-energy", "visual_objects": ["电量刻度", "可充电电池"],
            "action_or_relation": "用电量高低和充电状态表现可用心力", "page_slot": "support-side",
            "prompt_fragment": "关键词「心力」使用component-map模块：画出电量刻度、可充电电池；用电量高低和充电状态表现可用心力；放在support-side，直接填中文标签。",
            "priority": 1,
            "evidence_nodes": [{
                "evidence_id": "keyword-01-energy-evidence-01", "text": "放松才能恢复",
                "source_quote": "心力有限，放松才能恢复。", "source_field": "page_body",
                "parent_visual_module_id": "keyword-01-energy", "visual_module_id": "keyword-01-energy-evidence-01",
                "visual_objects": ["休息椅", "充电插头"], "action_or_relation": "用休息椅连接充电插头，表现恢复条件",
            }],
        },
        {
            "keyword": "放松", "source_quote": "心力有限，放松才能恢复。", "source_field": "page_body",
            "source_label": "放松", "concept": "放松", "semantic_role": "action",
            "visual_form": "action", "expected_visual_module": "action-node",
            "visual_module_id": "keyword-02-relax", "visual_objects": ["休息椅", "充电插头"],
            "action_or_relation": "让人物从休息椅获得充电，连接到恢复刻度", "page_slot": "upper-right",
            "prompt_fragment": "关键词「放松」使用action-node模块：画出休息椅、充电插头；让人物从休息椅获得充电，连接到恢复刻度；放在upper-right，直接填中文标签。",
            "priority": 2,
            "evidence_nodes": [{
                "evidence_id": "keyword-02-relax-evidence-01", "text": "休息后精力回升",
                "source_quote": "休息后精力回升。", "source_field": "page_body",
                "parent_visual_module_id": "keyword-02-relax", "visual_module_id": "keyword-02-relax-evidence-01",
                "visual_objects": ["电量刻度", "可充电电池"], "action_or_relation": "让电量刻度连接恢复动作，表现心力限制",
            }],
        },
    ]


def sample_spec() -> dict[str, object]:
    return {
        "page_index": 2,
        "page_title": "心力有限",
        "display_title": "心力有限",
        "source_title_full": "心力有限",
        "page_body": "心力有限，放松才能恢复。休息后精力回升。",
        "page_type": "观点页",
        "background_color": "#122142",
        "line_color": "white",
        "scene_concept": "concept-board",
        "role_action_intent": "嵌入结构并演示",
        "role_action_family": "thinking",
        "role_pose_key": "page-02-thinking",
        "role_position": "inside-right",
        "role_framing": "three-quarter",
        "role_count_target": 1,
        "reserved_zone_enabled": True,
        "keyword_visual_mappings": sample_keyword_visual_mappings(),
    }


class IpVisualV4ContractTest(unittest.TestCase):
    def test_render_plan_is_stable_and_text_is_model_integrated(self) -> None:
        spec = sample_spec()
        first = builder.build_render_plan(spec)
        second = builder.build_render_plan(dict(spec))
        self.assertEqual(first, second)
        self.assertEqual("creative", first["render_profile"])
        self.assertEqual("model-integrated-chinese", first["text_strategy"]["mode"])
        self.assertFalse(first["text_strategy"]["generator_text_forbidden"])
        self.assertTrue(first["text_strategy"]["model_renders_exact_chinese"])
        self.assertTrue(first["text_strategy"]["source_text_ledger_required"])
        self.assertTrue(first["text_strategy"]["cross_page_unjustified_motif_reuse_forbidden"])
        self.assertTrue(first["text_strategy"]["generator_blank_card_slots_forbidden"])
        self.assertFalse(first["text_strategy"]["program_draws_card_surface"])
        self.assertTrue(first["reserved_zone"]["exact_background_required"])

    def test_visual_blueprint_slots_and_attempt_ledger_are_immutable(self) -> None:
        spec = {**sample_spec(), "page_index": 1}
        plan = builder.build_render_plan(spec)
        blueprint = plan["visual_blueprint"]
        self.assertEqual("visual-blueprint-v4.1", blueprint["version"])
        self.assertEqual(len(sample_keyword_visual_mappings()) * 2 + 1, len(blueprint["text_slots"]))
        self.assertTrue(all(len(slot["rect"]) == 4 for slot in blueprint["text_slots"]))
        overlay = builder.build_text_overlay_plan({**spec, "render_plan": plan})
        self.assertEqual(blueprint["content_hash"], overlay["visual_blueprint_hash"])
        self.assertEqual([slot["rect"] for slot in blueprint["text_slots"]], [item["rect"] for item in overlay["items"]])
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prompt = root / "page-01.md"
            prompt.write_text(builder.build_prompt({**spec, "render_plan": plan}, {"slug": "host", "meta": {}}), encoding="utf-8")
            handoff = root / "codex-handoff.json"
            handoff.write_text(json.dumps({"pages": [{
                "page_index": 1,
                "visual_blueprint_hash": blueprint["content_hash"],
                "prompt_file": str(prompt),
            }], "covers": []}), encoding="utf-8")
            ledger_path = builder.initialize_attempt_ledger(root, handoff)
            builder.record_retry_attempt(ledger_path, "page-01", audit_status="rejected", reason="关键词模块不可见", correction_instruction="保留蓝图，强化模块")
            builder.record_retry_attempt(ledger_path, "page-01", audit_status="approved", reason="", correction_instruction="")
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            asset = ledger["assets"][0]
            self.assertEqual("approved", asset["status"])
            self.assertEqual(blueprint["content_hash"], asset["visual_blueprint_hash"])
            self.assertEqual(2, len(asset["attempts"]))

    def test_v4_work_package_preflight_accepts_a_complete_blueprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workdir, archive = root / "work", root / "archive"
            (workdir / "prompts").mkdir(parents=True)
            source = ROOT / "02_资产中心" / "06_配图库" / "01_干货型配图" / "要放松，不要自律" / "9月1日.txt"
            fixture = relax_fixture_text()
            parsed_pages = builder.parse_pages(fixture)
            deck_title, _ = builder.extract_deck_title(fixture)
            parsed_pages = builder.apply_deck_title(parsed_pages, deck_title)
            spec = builder.build_page_spec(parsed_pages[0], len(parsed_pages), parsed_pages)
            try:
                role = builder.load_character("zhifuxingqiu-host")
            except FileNotFoundError:
                self.skipTest("公开包未分发私有角色素材")
            builder.attach_page_role_chain([spec], role)
            spec["render_plan"] = builder.build_render_plan(spec)
            spec["visual_blueprint"] = spec["render_plan"]["visual_blueprint"]
            spec["source_text_ledger"] = spec["render_plan"]["source_text_ledger"]
            spec["text_overlay_plan"] = builder.build_text_overlay_plan(spec)
            overlay_path = workdir / "overlays" / "page-01.json"
            overlay_path.parent.mkdir()
            overlay_path.write_text(json.dumps(spec["text_overlay_plan"]), encoding="utf-8")
            spec["text_overlay_plan_file"] = str(overlay_path)
            prompt_path = workdir / "prompts" / "page-01.md"
            prompt_path.write_text(builder.build_prompt(spec, role), encoding="utf-8")
            cover_outputs = builder.build_cover_outputs([spec], deck_title, archive, source, "source-labels")
            builder.attach_cover_role_chain(cover_outputs, [spec], role)
            cover_prompt_paths = {}
            for cover in cover_outputs:
                cover["role_face_anchor_sha256"] = builder.file_sha256(cover.get("role_face_anchor_image"))
                cover["role_action_reference_sha256"] = builder.file_sha256(cover.get("role_action_reference_image"))
                cover["render_plan"] = builder.build_render_plan(cover, is_cover=True)
                cover["visual_blueprint"] = cover["render_plan"]["visual_blueprint"]
                cover["source_text_ledger"] = cover["render_plan"]["source_text_ledger"]
                cover["text_overlay_plan"] = builder.build_text_overlay_plan(cover, is_cover=True)
                cover_overlay = workdir / "overlays" / f"{cover['cover_type']}.json"
                cover_overlay.write_text(json.dumps(cover["text_overlay_plan"]), encoding="utf-8")
                cover["text_overlay_plan_file"] = str(cover_overlay)
                cover_prompt = workdir / "prompts" / f"{cover['cover_type']}.md"
                cover_prompt.write_text(builder.build_cover_prompt(cover, role), encoding="utf-8")
                cover_prompt_paths[cover["cover_type"]] = cover_prompt
            specs_path = workdir / "pages-spec.json"
            specs_path.write_text(json.dumps({"contract_version": builder.CONTRACT_VERSION, "pages": [spec], "cover_outputs": cover_outputs}), encoding="utf-8")
            handoff_path, _, _, _ = builder.build_codex_handoff(
                [spec], cover_outputs, [1], workdir, [prompt_path], [archive / "page-01.png"], cover_prompt_paths, role
            )
            builder.initialize_attempt_ledger(workdir, handoff_path)
            builder.ensure_visual_semantic_review_scaffold(workdir, specs_path, [spec])
            review_path = builder.refresh_visual_semantic_review_scaffold(workdir, specs_path, handoff_path, [spec], [prompt_path])
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["status"] = "approved"
            review["checks"] = {key: "passed" for key in review["checks"]}
            page_review = review["pages"][0]
            page_review["status"] = "approved"
            for item in page_review["keyword_visual_reviews"]:
                item["status"] = "passed"
                item["assessment"] = "关键词与可画模块已经逐项核验通过"
            for item in page_review["evidence_node_reviews"]:
                item["status"] = "passed"
                item["assessment"] = "证据短句、父主卡与提示词中的对象关系已经逐项核验通过"
            page_review["non_poster_review"] = {
                "status": "passed", "evidence": "页面以关系模块为主，人物嵌入结构。", "assessment": "不是标题加人物的海报构图。",
            }
            review_path.write_text(json.dumps(review), encoding="utf-8")
            job = json.loads((workdir / "codex-render-job.json").read_text(encoding="utf-8"))
            self.assertEqual([1], job["selected_pages"])
            self.assertTrue(job["include_covers"])
            self.assertEqual(str(handoff_path), job["handoff_file"])
            self.assertEqual(str(specs_path), job["pages_spec_file"])
            self.assertEqual(str(workdir / "codex-workflow.txt"), job["workflow_file"])
            checks, issues = [], []
            self.assertTrue(audit.ensure_render_job_contract(workdir.resolve(), json.loads(handoff_path.read_text(encoding="utf-8")), checks, issues), (job, checks, issues))
            receipt = audit.audit(workdir)
            self.assertEqual("approved", receipt["status"], json.dumps(receipt, ensure_ascii=False))

    def test_negative_hosting_language_cannot_request_microphone(self) -> None:
        self.assertEqual("none", builder.infer_prop_signature("不要主持姿态，也不要拿麦讲话"))
        self.assertEqual("mic", builder.infer_prop_signature("拿着麦克风演讲"))

    def test_page_prompt_includes_the_same_anchor_chain_as_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            face, action = root / "face.png", root / "action.png"
            Image.new("RGB", (10, 10), "#fcb537").save(face)
            Image.new("RGB", (10, 10), "#122142").save(action)
            spec = {**sample_spec(), "page_index": 1, "background_color": "#fcb537", "line_color": "black"}
            original = builder.split_role_reference_chain
            try:
                builder.split_role_reference_chain = lambda *_args, **_kwargs: (
                    {"file_path": face}, {"file_path": action}, "test-action-reference"
                )
                builder.attach_page_role_chain([spec], {})
            finally:
                builder.split_role_reference_chain = original
            prompt = builder.build_prompt(spec, {"slug": "host", "meta": {}})
            self.assertIn(str(face), prompt)
            self.assertIn(str(action), prompt)
            self.assertIn(spec["role_face_anchor_sha256"], prompt)
            self.assertRegex(spec["role_face_anchor_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(spec["role_action_reference_sha256"], hashlib.sha256(action.read_bytes()).hexdigest())

    def test_cover_modes_are_source_only(self) -> None:
        cover = {
            "display_title": "要放松，不要自律",
            "cue_phrases": ["越用力越累"],
            "support_labels": ["恢复"],
            "cover_text_mode": "source-labels",
        }
        source_overlay = builder.build_text_overlay_plan(cover, is_cover=True)
        source_texts = [entry["text"] for entry in source_overlay["source_text_ledger"]]
        self.assertEqual(["要放松，不要自律", "越用力越累", "恢复"], source_texts)
        self.assertFalse(any(any(char.isascii() and char.isalpha() for char in value) for value in source_texts))
        cover["cover_text_mode"] = "title-only"
        title_only_overlay = builder.build_text_overlay_plan(cover, is_cover=True)
        self.assertEqual(["要放松，不要自律"], [entry["text"] for entry in title_only_overlay["source_text_ledger"]])

    def test_post_render_review_template_binds_the_final_png_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir)
            evidence = output / "evidence"
            evidence.mkdir()
            Image.new("RGB", (1600, 900), "#fcb537").save(output / "page-01.png")
            mappings = sample_keyword_visual_mappings()
            source_ledger = builder.build_render_plan(sample_spec())["source_text_ledger"]
            (evidence / "pages-spec.json").write_text("{}", encoding="utf-8")
            (evidence / "codex-handoff.json").write_text(json.dumps({
                "pages": [{
                    "page_index": 1,
                    "visual_blueprint_hash": "blueprint-1",
                    "keyword_visual_mappings": mappings,
                    "source_text_ledger": source_ledger,
                }],
            }, ensure_ascii=False), encoding="utf-8")
            review_path = output_audit.create_post_render_review_scaffold(output)
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual("needs-review", review["status"])
            self.assertEqual("post-render", review["review_stage"])
            self.assertIn("blank_text_regions_absent", review["checks"])
            self.assertIn("approved_quality_baseline_match", review["checks"])
            self.assertEqual([], review["pages"][0]["blank_text_regions"])
            self.assertIn("quality_baseline_review", review["pages"][0])
            self.assertEqual(2, len(review["pages"][0]["keyword_visual_reviews"]))
            self.assertEqual(2, len(review["pages"][0]["evidence_node_reviews"]))
            self.assertEqual(["心力有限", "心力", "放松", "放松才能恢复", "休息后精力回升"], [entry["text"] for entry in review["pages"][0]["source_text_ledger"]])
            self.assertEqual(
                hashlib.sha256((output / "page-01.png").read_bytes()).hexdigest(),
                review["subject"]["image_sha256_by_page"]["page-01"],
            )
            image_hash = review["subject"]["image_sha256_by_page"]["page-01"]
            review["status"] = "approved"
            review["checks"] = {key: "passed" for key in review["checks"]}
            page_review = review["pages"][0]
            page_review["status"] = "approved"
            page_review["observed_visible_chinese"] = [entry["text"] for entry in source_ledger[:-1]]
            page_review["all_visible_chinese_source_traced"] = "passed"
            for item in page_review["keyword_visual_reviews"]:
                item.update({
                    "status": "passed",
                    "actual_visual_module": item["expected_visual_module"],
                    "image_sha256": image_hash,
                    "actual_visual_evidence": "成图中可见对应手绘对象与关系证据",
                    "assessment": "文字、对象和关系与原文语义一致通过",
                })
            page_review["non_poster_review"].update({
                "status": "passed",
                "image_sha256": image_hash,
                "evidence": "成图包含多个手绘模块和清晰信息关系",
                "assessment": "整体为视觉笔记结构而不是单一海报",
            })
            review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            checks, issues = [], []
            failed, _ = output_audit.ensure_post_render_keyword_visual_review(
                output,
                json.loads((evidence / "codex-handoff.json").read_text(encoding="utf-8")),
                [{
                    "page_index": 1,
                    "visual_blueprint_hash": "blueprint-1",
                    "keyword_visual_mappings": mappings,
                    "source_text_ledger": source_ledger,
                }],
                checks,
                issues,
            )
            self.assertEqual(["page-01"], failed)
            self.assertTrue(issues)

    def test_compact_prompts_and_v4_audit_contract(self) -> None:
        spec = {**sample_spec(), "page_index": 1, "background_color": "#fcb537", "line_color": "black"}
        role = {"slug": "host", "meta": {"display_name": "主讲人"}}
        prompt = builder.build_prompt(spec, role)
        self.assertLessEqual(len(prompt), 2800)
        self.assertIn("render each listed phrase exactly", prompt)
        self.assertIn("VISUAL KEYWORD MAP", prompt)
        self.assertIn("HAND-DRAWN MODULE CARDS", prompt)
        self.assertIn("SOURCE TEXT LEDGER", prompt)
        self.assertIn("approved-visual-note-page-01.png", prompt)
        self.assertTrue(builder.QUALITY_REFERENCE_IMAGE.is_file())
        self.assertIn("every motif must directly visualize a listed source label", prompt)
        self.assertIn("Flat solid exact background", prompt)
        for mapping in sample_keyword_visual_mappings():
            self.assertIn(mapping["prompt_fragment"], prompt)
        cover_prompt = builder.build_cover_prompt({**spec, "cover_type": "cover-3x4", "aspect_ratio": "3:4"}, role)
        self.assertLessEqual(len(cover_prompt), 1800)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            anchor = root / "anchor.png"
            Image.new("RGB", (10, 10), "#fcb537").save(anchor)
            overlay = root / "overlay.json"
            prompt_file = root / "page.md"
            prompt_file.write_text(prompt, encoding="utf-8")
            render_plan = builder.build_render_plan(spec)
            overlay_plan = builder.build_text_overlay_plan({**spec, "render_plan": render_plan})
            overlay.write_text(json.dumps(overlay_plan), encoding="utf-8")
            item = {
                "page_index": 1, "prompt_file": str(prompt_file),
                "role_face_anchor_image": str(anchor),
                "role_face_anchor_sha256": hashlib.sha256(anchor.read_bytes()).hexdigest(),
                "role_action_reference_image": "", "role_action_reference_sha256": "",
                "text_overlay_plan_file": str(overlay),
                "text_overlay_plan": overlay_plan,
                "render_plan": render_plan,
                "visual_blueprint": render_plan["visual_blueprint"],
                "visual_blueprint_hash": render_plan["visual_blueprint"]["content_hash"],
                "keyword_visual_mappings": sample_keyword_visual_mappings(),
            }
            checks, issues = [], []
            self.assertEqual(([], []), audit.ensure_prompt_contract({"contract_version": builder.CONTRACT_VERSION, "pages": [item], "covers": []}, checks, issues))
            self.assertFalse(issues)

            checks, issues = [], []
            self.assertEqual((["page-01"], []), audit.ensure_prompt_contract({"contract_version": "3.2.0", "pages": [item], "covers": []}, checks, issues))
            self.assertTrue(issues)

    def test_relax_fixture_generates_distinct_keyword_visual_maps(self) -> None:
        pages = builder.parse_pages(relax_fixture_text())
        specs = [builder.build_page_spec(page, len(pages), pages) for page in pages]
        page = next(spec for spec in specs if spec["page_title"] == "原因1：心力有限")
        mappings = page["keyword_visual_mappings"]
        self.assertEqual(10, len(specs))
        self.assertGreaterEqual(len(mappings), 2)
        self.assertLessEqual(len(mappings), 5)
        self.assertEqual([item["keyword"] for item in mappings], page["core_visual_keywords"])
        self.assertIn("心力", page["core_visual_keywords"])
        self.assertIn("放松", page["core_visual_keywords"])
        self.assertEqual(len(mappings), len({item["visual_module_id"] for item in mappings}))
        self.assertTrue(all(item["visual_objects"] and item["prompt_fragment"] for item in mappings))
        prompt = builder.build_prompt(page, {"slug": "host", "meta": {}})
        self.assertTrue(all(item["prompt_fragment"] in prompt for item in mappings))

    def test_title_is_not_promoted_to_a_main_card_and_negative_clause_stays_evidence(self) -> None:
        pages = builder.parse_pages(relax_fixture_text())
        specs = [builder.build_page_spec(page, len(pages), pages) for page in pages]
        summary = next(spec for spec in specs if spec["page_title"] == "总结：先放松再自律")
        mappings = summary["keyword_visual_mappings"]
        self.assertTrue(all(item["source_field"] == "page_body" for item in mappings))
        relax = next(item for item in mappings if item["source_label"] == "放松")
        self.assertIn("不是偷懒", [node["text"] for node in relax["evidence_nodes"]])
        builder.ensure_final_visible_text_contract(mappings, summary["page_title"])

    def test_evidence_rejects_transition_fragments_incomplete_steps_and_comparison_setup(self) -> None:
        # Evidence is rendered verbatim in a parent card.  Traceability alone
        # is not enough when the source fragment cannot carry that card's
        # object/relation by itself.
        rejected = [
            "你一定能听懂我下面讲的",
            "第一步应该是",
            "那如何把事情做对呢",
            "要想把事情做对",
            "有的人速度很快",
            "很多人做选择的时候",
            "第一反应都是",
        ]
        self.assertTrue(all(
            not builder._is_evidence_candidate_allowed(candidate)
            for candidate in rejected
        ))
        self.assertTrue(builder._is_evidence_candidate_allowed("先拿30万装修店面，后面还要招员工"))
        self.assertTrue(builder._is_evidence_candidate_allowed("想清楚什么不能做，甚至想清楚什么能做更重要"))

    def test_evidence_must_match_its_parent_card_not_merely_share_a_page(self) -> None:
        not_do = {
            "source_label": "什么不能做",
            "source_quote": "想清楚什么不能做，甚至想清楚什么能做更重要",
            "visual_objects": ["红色停止清单", "被划掉的任务卡"],
        }
        customer = {
            "source_label": "客户",
            "source_quote": "很多老师拍短视频，他们就喜欢把自己课堂的知识拍成视频，拍了几百条，没一条有流量，吸引来的全是同行，没有一个客户",
            "visual_objects": ["爆款视频卡", "粉丝与客户目标板"],
        }
        short_video = {
            "source_label": "短视频",
            "source_quote": "很多老师拍短视频，他们就喜欢把自己课堂的知识拍成视频",
            "visual_objects": ["个人技能工具箱", "客户订单"],
        }
        self.assertFalse(builder._evidence_supports_parent_mapping(
            "餐饮一年能赚100万", "餐饮一年能赚100万", not_do, is_local=False
        ))
        self.assertFalse(builder._evidence_supports_parent_mapping(
            "拍了几百条", customer["source_quote"], customer, is_local=True
        ))
        self.assertTrue(builder._evidence_supports_parent_mapping(
            "他们就喜欢把自己课堂的知识拍成视频",
            "很多老师拍短视频，他们就喜欢把自己课堂的知识拍成视频",
            short_video,
            is_local=True,
        ))

    def test_choice_and_execution_are_not_interchangeable_evidence(self) -> None:
        choice = {
            "source_label": "做对的事情",
            "source_quote": "聊了什么是做对的事情，那如何把事情做对呢",
            "visual_objects": ["方向指南针", "路线地图"],
        }
        iteration = {
            "source_label": "第3步，自我迭代",
            "source_quote": "第3步，自我迭代",
            "visual_objects": ["迭代循环箭头", "逐版升级稿"],
        }
        self.assertFalse(builder._evidence_supports_parent_mapping(
            "要想把事情做对", "要想把事情做对，必须允许自己犯错", choice, is_local=True
        ))
        source = "师傅领进门，修行在个人，这个修行的核心就是自我迭代"
        self.assertFalse(builder._evidence_supports_parent_mapping(
            "师傅领进门", source, iteration, is_local=True
        ))
        self.assertTrue(builder._evidence_supports_parent_mapping(
            "这个修行的核心就是自我迭代", source, iteration, is_local=True
        ))

    def test_numbered_choices_keep_three_main_cards_and_internal_evidence(self) -> None:
        title, body, assignments = three_choices_fixture()
        mappings = builder.build_keyword_visual_mappings(
            title, body, {"visual_module_assignments": assignments, "semantic_units": []}
        )
        self.assertEqual(["第1个，餐饮", "第2个，电商", "第3个，技能"], [item["source_label"] for item in mappings])
        self.assertNotIn("装修", [item["source_label"] for item in mappings])
        self.assertNotIn("囤20万的货", [item["source_label"] for item in mappings])
        evidence_texts = {node["text"] for item in mappings for node in item["evidence_nodes"]}
        self.assertTrue({"先拿30万装修店面", "先囤20万的货", "先用技能接单"}.issubset(evidence_texts))
        self.assertTrue(all(1 <= len(item["evidence_nodes"]) <= 3 for item in mappings))

    def test_numbered_steps_keep_every_step_and_only_own_evidence(self) -> None:
        title = "第三点，如何找到对的事"
        body = (
            "其实我用的方法非常简单，就3步\n"
            "第1步：先判断什么事坚决不做。就刚刚讲的建立不为清单。\n"
            "第2步：判断这件事长期来看是不是成立，能否建立一个长期稳定的系统，让我再系统内工作。"
            "比如我最近做的AI爆款内容工厂，就是一套系统，帮我持续产出爆款视频。\n"
            "第3步：发现错了，马上改。如果发现改都没有用，从根本上错了，就马上放弃，即使它还在赚钱。"
        )
        mappings = builder.build_keyword_visual_mappings(
            title, body, {"visual_module_assignments": [], "semantic_units": []}
        )
        self.assertEqual(
            [
                "第1步：先判断什么事坚决不做",
                "第2步：判断这件事长期来看是不是成立",
                "第3步：发现错了，马上改",
            ],
            [item["source_label"] for item in mappings],
        )
        self.assertTrue(all(1 <= len(item["evidence_nodes"]) <= 3 for item in mappings))
        self.assertTrue(all(
            item["source_label"] in node["source_quote"]
            for item in mappings
            for node in item["evidence_nodes"]
        ))
        self.assertFalse(any(
            node["text"] == "就3步"
            for item in mappings
            for node in item["evidence_nodes"]
        ))
        self.assertEqual(
            ["能否建立一个长期稳定的系统"],
            [node["text"] for node in mappings[1]["evidence_nodes"]],
        )
        third_step = mappings[2]
        self.assertTrue(any(
            "就马上放弃" in node["text"]
            for node in third_step["evidence_nodes"]
        ))

    def test_numbered_step_keeps_self_iteration_conclusion_without_proverb_prefix(self) -> None:
        body = (
            "第1步，定义结果\n你得先知道什么叫做成。\n"
            "第2步，找高手学\n向已经有结果的人学习，只学已经被验证的路径。\n"
            "第3步，自我迭代\n师傅领进门，修行在个人，这个修行的核心就是自我迭代。"
        )
        mappings = builder.build_keyword_visual_mappings(
            "如何把事情做对", body, {"visual_module_assignments": [], "semantic_units": []}
        )
        iteration = next(item for item in mappings if item["source_label"] == "第3步，自我迭代")
        self.assertEqual(
            ["这个修行的核心就是自我迭代"],
            [node["text"] for node in iteration["evidence_nodes"]],
        )

    def test_numbered_step_strips_bold_before_source_label_split(self) -> None:
        self.assertEqual(
            "第一步，把你每周重复做的事情列成清单",
            builder._complete_step_label("第一步，**把你每周重复做的事情列成清单。**\n打开清单，就知道该看什么。"),
        )

    def test_numbered_step_priority_condition_is_own_evidence(self) -> None:
        body = (
            "第一步，把你每周重复做的事情列成清单。\n打开清单，就知道该看什么、该怎么做。\n"
            "第二步，把重复动作做成模板和流程。\n最后做到别人照着你的流程，也能把事情做出来。\n"
            "第三步，每周只解决一个问题。\n哪里最浪费时间、最容易返工，就先改哪里。"
        )
        mappings = builder._build_numbered_step_mappings(body)
        third_step = mappings[2]
        self.assertEqual(
            ["哪里最浪费时间、最容易返工，就先改哪里"],
            [node["text"] for node in third_step["evidence_nodes"]],
        )
        self.assertTrue(all(
            builder._source_contains_fragment(node["source_quote"], node["text"])
            for node in third_step["evidence_nodes"]
        ))

    def test_numbered_step_source_rooted_visuals_are_distinct(self) -> None:
        body = (
            "第一步，把你每周重复做的事情列成清单。\n打开清单，就知道该看什么、该怎么做。\n"
            "第二步，把重复动作做成模板和流程。\n最后做到别人照着你的流程，也能把事情做出来。\n"
            "第三步，每周只解决一个问题。\n哪里最浪费时间、最容易返工，就先改哪里。"
        )
        mappings = builder.build_keyword_visual_mappings(
            "如何构建自己的系统思维？", body, {"visual_module_assignments": [], "semantic_units": []}
        )
        self.assertEqual(3, len(mappings))
        self.assertEqual(3, len({tuple(item["visual_objects"]) for item in mappings}))
        self.assertTrue(all(item["visual_objects"] for item in mappings))

    def test_missing_evidence_and_legacy_v4_work_packages_are_rejected(self) -> None:
        broken = sample_keyword_visual_mappings()
        broken[0] = {key: value for key, value in broken[0].items() if key != "evidence_nodes"}
        with self.assertRaisesRegex(ValueError, "evidence_nodes"):
            builder.validate_keyword_visual_mappings(
                broken, "心力有限", "心力有限，放松才能恢复。休息后精力回升。", context="test"
            )
        checks, issues = [], []
        self.assertEqual(
            (["page-01"], []),
            audit.ensure_prompt_contract({"contract_version": "4.0.0", "pages": [{"page_index": 1}], "covers": []}, checks, issues),
        )

    def test_preflight_rejects_missing_evidence_and_fragmented_parallel_branch(self) -> None:
        title, body, assignments = three_choices_fixture()
        mappings = builder.build_keyword_visual_mappings(
            title, body, {"visual_module_assignments": assignments, "semantic_units": []}
        )
        spec = {
            "page_index": 1, "page_title": title, "display_title": title, "title_text": title,
            "source_title_full": title, "page_body": body, "page_type": "对比页",
            "background_color": "#fcb537", "line_color": "black", "scene_concept": "choice-board",
            "role_action_intent": "嵌入结构并演示", "role_action_family": "explaining",
            "role_position": "inside-right", "role_framing": "three-quarter", "role_count_target": 1,
            "keyword_visual_mappings": mappings,
        }
        plan = builder.build_render_plan(spec)
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_path = Path(tmpdir) / "page-01.md"
            prompt_path.write_text(builder.build_prompt(spec, {"slug": "host", "meta": {}}), encoding="utf-8")
            item = {
                **spec, "render_plan": plan, "core_visual_keywords": [mapping["keyword"] for mapping in mappings],
                "prompt_file": str(prompt_path), "visual_composition_mode": "visual-note",
                "poster_like_forbidden": True, "module_block_count_target": 3,
                "label_module_required": True, "micro_visual_container_required": True,
            }
            checks, issues = [], []
            self.assertEqual(([], [], [], []), audit.ensure_keyword_visual_contract([item], checks, issues))

            missing_evidence = copy.deepcopy(item)
            missing_evidence["keyword_visual_mappings"][0]["evidence_nodes"] = []
            checks, issues = [], []
            self.assertIn("page-01", audit.ensure_keyword_visual_contract([missing_evidence], checks, issues)[1])

            fragmented = copy.deepcopy(item)
            child = copy.deepcopy(fragmented["keyword_visual_mappings"][0])
            child.update({"keyword": "装修", "source_label": "装修", "concept": "装修", "priority": 4, "visual_module_id": "keyword-04-decoration"})
            child["evidence_nodes"][0].update({
                "evidence_id": "keyword-04-decoration-evidence-01",
                "parent_visual_module_id": "keyword-04-decoration",
                "visual_module_id": "keyword-04-decoration-evidence-01",
            })
            fragmented["keyword_visual_mappings"].append(child)
            fragmented["core_visual_keywords"].append("装修")
            checks, issues = [], []
            self.assertIn("page-01", audit.ensure_keyword_visual_contract([fragmented], checks, issues)[2])

    def test_metrics_to_production_system_sentence_becomes_two_linked_contrast_cards(self) -> None:
        title = "构建AI内容生产系统"
        body = (
            "我从来不看视频数据，更不关心一条视频爆没爆，\n"
            "而是先去搭建一套持续稳定产出内容的生产系统。\n"
            "每天真正要做的，是找出系统里最慢的一环。"
        )
        mappings = builder.build_keyword_visual_mappings(title, body, {
            "visual_module_assignments": [], "semantic_units": [],
        })
        self.assertEqual(
            ["我从来不看视频数据", "持续稳定产出内容的生产系统"],
            [item["source_label"] for item in mappings],
        )
        data_card, system_card = mappings
        self.assertEqual("更不关心一条视频爆没爆", data_card["evidence_nodes"][0]["text"])
        self.assertEqual("而是先去搭建一套", system_card["evidence_nodes"][0]["text"])
        for card in mappings:
            relation = card["action_or_relation"]
            self.assertIn("视频数据仪表盘", "、".join(card["visual_objects"]))
            self.assertIn("转向", relation)
            self.assertEqual(card["visual_module_id"], card["evidence_nodes"][0]["parent_visual_module_id"])
            self.assertIn("内容生产", relation)

    def test_metrics_to_production_system_rule_requires_one_explicit_causal_sentence(self) -> None:
        split_claims = (
            "我从来不看视频数据，更不关心一条视频爆没爆。\n"
            "后来我去搭建一套持续稳定产出内容的生产系统。"
        )
        self.assertEqual([], builder._build_data_to_production_system_mappings(split_claims))

    def test_money_motif_is_source_supported_not_globally_banned(self) -> None:
        mappings = [{
            "keyword": "赚钱", "source_quote": "赚钱要先做对的事。", "source_field": "source_title_full",
            "source_label": "赚钱", "concept": "赚钱", "semantic_role": "result",
            "visual_form": "object", "expected_visual_module": "component-map",
            "visual_module_id": "keyword-01-money", "visual_objects": ["价值交换卡", "结果账本"],
            "action_or_relation": "用价值交换卡与结果账本表现原文明确提到的收入关系", "page_slot": "support-side",
            "prompt_fragment": "关键词「赚钱」使用component-map模块：画出价值交换卡、结果账本；用价值交换卡与结果账本表现原文明确提到的收入关系；放在support-side，直接填中文标签。",
            "priority": 1,
            "evidence_nodes": [{
                "evidence_id": "keyword-01-money-evidence-01", "text": "做对的事",
                "source_quote": "赚钱要先做对的事。", "source_field": "source_title_full",
                "parent_visual_module_id": "keyword-01-money", "visual_module_id": "keyword-01-money-evidence-01",
                "visual_objects": ["筛选漏斗", "保留任务卡"], "action_or_relation": "用筛选漏斗表现收入之前的选择条件",
            }],
        }, {
            "keyword": "做对的事", "source_quote": "赚钱要先做对的事。", "source_field": "source_title_full",
            "source_label": "做对的事", "concept": "做对的事", "semantic_role": "action",
            "visual_form": "action", "expected_visual_module": "action-node",
            "visual_module_id": "keyword-02-right", "visual_objects": ["筛选漏斗", "保留任务卡"],
            "action_or_relation": "让筛选漏斗留下做对的事", "page_slot": "upper-right",
            "prompt_fragment": "关键词「做对的事」使用action-node模块：画出筛选漏斗、保留任务卡；让筛选漏斗留下做对的事；放在upper-right，直接填中文标签。",
            "priority": 2,
            "evidence_nodes": [{
                "evidence_id": "keyword-02-right-evidence-01", "text": "赚钱要先做对的事",
                "source_quote": "赚钱要先做对的事。", "source_field": "source_title_full",
                "parent_visual_module_id": "keyword-02-right", "visual_module_id": "keyword-02-right-evidence-01",
                "visual_objects": ["价值交换卡", "结果账本"], "action_or_relation": "将选择条件连接到收入结果，表现原文顺序",
            }],
        }]
        validated = builder.validate_keyword_visual_mappings(mappings, "赚钱要先做对的事。", "", context="test")
        self.assertEqual("赚钱", validated[0]["keyword"])

    def test_untraced_visible_text_is_rejected(self) -> None:
        mappings = sample_keyword_visual_mappings()
        mappings[0] = {**mappings[0], "source_label": "原文没有的臆想词"}
        with self.assertRaisesRegex(ValueError, "直接来自 source_quote"):
            builder.validate_keyword_visual_mappings(mappings, "心力有限", "心力有限，放松才能恢复。", context="test")

    def test_keyword_extraction_prefers_complete_source_phrase_over_truncated_term(self) -> None:
        concepts = builder.extract_visual_concepts("而是：哪个机会最适合现在的我", "")
        self.assertEqual("哪个机会最适合现在的我", concepts[0])
        self.assertNotEqual("机会最适合", concepts[0])

    def test_meta_placeholder_visual_objects_are_rejected(self) -> None:
        mappings = sample_keyword_visual_mappings()
        mappings[0] = {**mappings[0], "visual_objects": ["心力具体手绘场景", "心力关系节点"]}
        with self.assertRaisesRegex(ValueError, "占位描述"):
            builder.validate_keyword_visual_mappings(
                mappings,
                "心力有限",
                "心力有限，放松才能恢复。",
                context="test",
            )

    def test_blank_title_is_rejected_before_rendering(self) -> None:
        spec = {**sample_spec(), "display_title": "", "title_text": ""}
        with self.assertRaisesRegex(ValueError, "标题为空"):
            builder.build_visual_blueprint(spec, sample_keyword_visual_mappings(), {}, is_cover=False)

    def test_identical_cross_page_text_objects_and_relation_are_rejected(self) -> None:
        first = {**sample_spec(), "page_index": 1}
        second = {**sample_spec(), "page_index": 2}
        with self.assertRaisesRegex(ValueError, "跨页重复主视觉组合"):
            builder.attach_cross_page_motif_guards([first, second])

    def test_same_concept_cannot_fill_two_cards_with_spoken_wrappers(self) -> None:
        mappings = sample_keyword_visual_mappings()
        duplicate = dict(mappings[1])
        duplicate.update({
            "keyword": "就是放松", "source_label": "就是放松", "concept": "就是放松",
            "source_quote": "心力有限，放松才能恢复；就是放松。", "priority": 3,
            "evidence_nodes": [{
                "evidence_id": "keyword-03-duplicate-evidence-01", "text": "心力有限，放松才能恢复",
                "source_quote": "心力有限，放松才能恢复；就是放松。", "source_field": "page_body",
                "parent_visual_module_id": "keyword-02-relax", "visual_module_id": "keyword-03-duplicate-evidence-01",
                "visual_objects": ["休息椅", "充电插头"], "action_or_relation": "用恢复动作说明重复概念",
            }],
        })
        second = {**mappings[1], "source_quote": "心力有限，放松才能恢复；就是放松。", "evidence_nodes": [{
            "evidence_id": "keyword-02-relax-evidence-01", "text": "就是放松",
            "source_quote": "心力有限，放松才能恢复；就是放松。", "source_field": "page_body",
            "parent_visual_module_id": "keyword-02-relax", "visual_module_id": "keyword-02-relax-evidence-01",
            "visual_objects": ["休息椅", "充电插头"], "action_or_relation": "让恢复动作回到放松",
        }]}
        with self.assertRaisesRegex(ValueError, "同一概念"):
            builder.validate_keyword_visual_mappings(
                [mappings[0], second, duplicate],
                "心力有限", "心力有限，放松才能恢复；就是放松。", context="test",
            )

    def test_spoken_filler_is_not_selected_over_concrete_steps(self) -> None:
        title = "第五点 那如何把事情做对呢？"
        body = (
            "其实我用的方法非常简单，也是就3步。\n"
            "第一步 定义结果。先写清交付标准。\n"
            "第二步 找高手学。向有结果的人请教。\n"
            "第三步 自我迭代。每周复盘并完善方法。"
        )
        assignments = [
            {"source_quote": "其实我用的方法非常简单，也是就3步", "visible_text": "其实我用的方法非常简单", "information_type": "context"},
            {"source_quote": "第一步 定义结果", "visible_text": "第一步 定义结果", "information_type": "action"},
            {"source_quote": "第二步 找高手学", "visible_text": "第二步 找高手学", "information_type": "action"},
            {"source_quote": "第三步 自我迭代", "visible_text": "第三步 自我迭代", "information_type": "action"},
        ]
        mappings = builder.build_keyword_visual_mappings(
            title,
            body,
            {"visual_module_assignments": assignments, "semantic_units": []},
        )
        self.assertEqual(["第一步 定义结果", "第二步 找高手学", "第三步 自我迭代"], [item["source_label"] for item in mappings])
        visible = [
            text
            for mapping in mappings
            for text in [mapping["source_label"]] + [node["text"] for node in mapping["evidence_nodes"]]
        ]
        self.assertFalse(any(
            builder._visible_texts_overlap(left, right)
            for index, left in enumerate(visible)
            for right in visible[index + 1:]
        ), visible)
        self.assertTrue(all(1 <= len(item["evidence_nodes"]) <= 3 for item in mappings))
        self.assertEqual(5, builder.KEYWORD_VISUAL_MAPPING_MAX)

    def test_cross_page_concept_reuse_is_allowed_when_relation_changes(self) -> None:
        first = {**sample_spec(), "page_index": 1}
        changed = [dict(item) for item in sample_keyword_visual_mappings()]
        changed[0] = {**changed[0], "action_or_relation": "让心力刻度连接到恢复动作，表达另一条原文关系"}
        changed[1] = {**changed[1], "action_or_relation": "让放松动作连接到长期节奏，表达另一条原文关系"}
        second = {**sample_spec(), "page_index": 2, "keyword_visual_mappings": changed}
        guarded = builder.attach_cross_page_motif_guards([first, second])
        self.assertEqual(2, len(guarded))
        self.assertEqual([], guarded[1]["prior_page_matching_motifs"])

    def test_cross_page_same_system_label_is_allowed_with_source_rooted_motif_change(self) -> None:
        source_motifs = [
            builder.translate_visual_concept("系统", "我是如何用系统思维驱动赚钱的", "causal"),
            builder.translate_visual_concept("系统", "就是因为做事不会构建系统。", "causal"),
            builder.translate_visual_concept("系统", "搭建一套持续稳定产出内容的生产系统", "causal"),
            builder.translate_visual_concept("系统", "去打造一套自己的内容生产系统。", "causal"),
            builder.translate_visual_concept("系统", "从每次都靠自己重新来一遍，变成一套可以重复运转的系统", "causal"),
            builder.translate_visual_concept("系统", "不断找到系统卡点，一个一个解决", "causal"),
        ]
        self.assertEqual(6, len({tuple(objects) for objects, _relation in source_motifs}))
        self.assertEqual(6, len({relation for _objects, relation in source_motifs}))
        first_objects, first_relation = source_motifs[1]
        second_objects, second_relation = source_motifs[2]
        first = {
            "page_index": 1,
            "keyword_visual_mappings": [{
                "keyword": "系统", "concept": "系统", "source_label": "系统",
                "visual_objects": first_objects, "action_or_relation": first_relation,
            }],
        }
        second = {
            "page_index": 2,
            "keyword_visual_mappings": [{
                "keyword": "系统", "concept": "系统", "source_label": "系统",
                "visual_objects": second_objects, "action_or_relation": second_relation,
            }],
        }
        guarded = builder.attach_cross_page_motif_guards([first, second])
        self.assertEqual([], guarded[1]["prior_page_matching_motifs"])

    def test_explicit_manual_to_repeatable_mechanism_uses_causal_form_only(self) -> None:
        mechanism = "把赚钱这件事，从每次都靠自己重新来一遍，变成一套可以重复运转的系统"
        self.assertEqual("causal", builder.infer_visual_form("supporting-object", "系统", mechanism))
        self.assertEqual("causal-chain", builder.VISUAL_FORM_TO_MODULE[builder.infer_visual_form("supporting-object", "赚钱", mechanism)])
        self.assertEqual(
            "object",
            builder.infer_visual_form("supporting-object", "系统", "我正在搭建自己的内容系统"),
        )

    def test_causal_main_cards_set_nonposter_module_count_independent_of_support_labels(self) -> None:
        page = {
            "index": 1,
            "title": "如何用系统思维帮我们赚钱？",
            "body": "说白了，就是把赚钱这件事，从每次都靠自己重新来一遍，变成一套可以重复运转的系统。",
            "pagination_mode": "explicit",
            "section_kind": "manual",
            "title_from_bold": False,
            "explicit_heading_level": 3,
            "step_label": "",
            "step_index": None,
            "step_page_index": 1,
            "step_page_total": 1,
            "is_continued": False,
        }
        spec = builder.build_page_spec(page, 1, [page])
        self.assertEqual(2, spec["main_card_count"])
        self.assertEqual(2, spec["module_block_count_target"])
        self.assertGreaterEqual(spec["module_block_count_target"], spec["main_card_count"])
        self.assertTrue(all(item["visual_form"] == "causal" for item in spec["keyword_visual_mappings"]))

    def test_formal_archive_rejects_runtime_files_at_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workdir, archive = root / "work", root / "archive"
            workdir.mkdir()
            archive.mkdir()
            (archive / "page-01.png").write_bytes(b"png")
            (archive / "evidence").mkdir()
            checks, issues = [], []
            clean = audit.ensure_formal_directory_cleanliness(
                workdir,
                [{"output_image": str(archive / "page-01.png")}],
                [], checks, issues,
            )
            self.assertEqual([], clean)
            (archive / "pages-spec.json").write_text("{}", encoding="utf-8")
            checks, issues = [], []
            polluted = audit.ensure_formal_directory_cleanliness(
                workdir,
                [{"output_image": str(archive / "page-01.png")}],
                [], checks, issues,
            )
            self.assertEqual([str(archive.resolve())], polluted)
            self.assertTrue(issues)

    def test_semantic_review_scaffold_carries_keyword_prompt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            spec = sample_spec()
            spec["page_index"] = 1
            spec["render_plan"] = builder.build_render_plan(spec)
            specs_path = workdir / "pages-spec.json"
            handoff_path = workdir / "codex-handoff.json"
            prompt_path = workdir / "page-01.md"
            specs_path.write_text(json.dumps({"pages": [spec]}, ensure_ascii=False), encoding="utf-8")
            handoff_path.write_text('{"pages": [{"page_index": 1}]}', encoding="utf-8")
            prompt_path.write_text(builder.build_prompt(spec, {"slug": "host", "meta": {}}), encoding="utf-8")
            builder.ensure_visual_semantic_review_scaffold(workdir, specs_path, [spec])
            review_path = builder.refresh_visual_semantic_review_scaffold(
                workdir, specs_path, handoff_path, [spec], [prompt_path]
            )
            review = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual("ip-visual-semantic-review-v4.1", review["schema"])
            self.assertEqual("needs-review", review["status"])
            self.assertEqual("needs-review", review["checks"]["source_text_ledger_traceability"])
            self.assertEqual(spec["render_plan"]["source_text_ledger"], review["pages"][0]["source_text_ledger"])
            reviews = review["pages"][0]["keyword_visual_reviews"]
            self.assertEqual([item["keyword"] for item in sample_keyword_visual_mappings()], [item["keyword"] for item in reviews])
            self.assertTrue(all(item["prompt_evidence"] for item in reviews))

    def test_evidence_archive_preserves_contracts_and_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workdir, archive = root / "work", root / "archive"
            workdir.mkdir()
            (workdir / "prompts").mkdir()
            (workdir / "pages-spec.json").write_text("{}", encoding="utf-8")
            (workdir / "codex-handoff.json").write_text("{}", encoding="utf-8")
            (workdir / "codex-workflow.txt").write_text("workflow", encoding="utf-8")
            (workdir / "prompts" / "page-01.md").write_text("prompt", encoding="utf-8")
            evidence = builder.archive_evidence(workdir, archive)
            self.assertTrue((evidence / "pages-spec.json").is_file())
            self.assertTrue((evidence / "prompts" / "page-01.md").is_file())
            manifest = json.loads((evidence / "evidence-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual("ip-visual-evidence-v1", manifest["schema"])

    def test_output_audit_contract_evidence_is_a_hash_bound_copy_of_this_work_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workdir, review_dir = root / "work", root / "final-review"
            workdir.mkdir()
            pages_spec = '{"contract_version":"4.1.0","pages":[{"page_index":1}]}'
            handoff = '{"contract_version":"4.1.0","pages":[{"page_index":1}]}'
            (workdir / "pages-spec.json").write_text(pages_spec, encoding="utf-8")
            (workdir / "codex-handoff.json").write_text(handoff, encoding="utf-8")
            evidence = builder.prepare_review_evidence(workdir, review_dir)
            manifest = json.loads((evidence / "evidence-manifest.json").read_text(encoding="utf-8"))
            bindings = manifest["output_audit_contract_evidence"]
            for filename in ("pages-spec.json", "codex-handoff.json"):
                self.assertEqual(
                    hashlib.sha256((workdir / filename).read_bytes()).hexdigest(),
                    bindings[filename]["work_package_sha256"],
                )
                self.assertEqual(
                    bindings[filename]["work_package_sha256"],
                    bindings[filename]["evidence_sha256"],
                )
                self.assertEqual(
                    (workdir / filename).read_bytes(),
                    (evidence / filename).read_bytes(),
                )

    def test_native_prompt_preserves_sensitive_title_and_role_geometry_contracts(self) -> None:
        role = {"slug": "host", "meta": {}}
        sensitive_specs = [
            (2, "没流量是你对干货的定义错了", "全身跨过错误节点，边躲边指认问题来源", "TITLE CONTRACT: top title must render exactly “没流量是你对干货的定义错了”"),
            (4, "那应该如何写好干货型视频呢？", "双手分别指向两侧内容，做取舍、对照和判断", "no chin-resting"),
            (5, "观察评论区验证视频好坏", "沿着流程节点推进、连接或跨越", "must visibly advance along, cross over, or operate the drawn arrow/node structure"),
            (6, "信任才是IP的终极目标", "看向空空的钱包、订单或结果面板，做出落差确认", "empty wallet, order, or result panel"),
        ]
        for page_index, title, action, expected in sensitive_specs:
            with self.subTest(page_index=page_index):
                spec = {
                    **sample_spec(),
                    "page_index": page_index,
                    "page_title": title,
                    "display_title": title,
                    "title_text": title,
                    "role_action_intent": action,
                    "role_action": action,
                }
                prompt = builder.build_prompt(spec, role)
                self.assertIn(expected, prompt)

    def test_rejected_preflight_never_creates_formal_archive_or_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workdir, archive = root / "work", root / "formal-archive"
            workdir.mkdir()
            (workdir / "pages-spec.json").write_text("{}", encoding="utf-8")
            evidence = builder.archive_evidence_after_approved(
                workdir, archive, {"status": "rejected"}
            )
            self.assertIsNone(evidence)
            self.assertFalse(archive.exists())


if __name__ == "__main__":
    unittest.main()
