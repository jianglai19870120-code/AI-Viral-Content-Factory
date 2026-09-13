from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "audit_video_pain_cards.py"
SPEC = importlib.util.spec_from_file_location("audit_video_pain_cards", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class AuditVideoPainCardsTests(unittest.TestCase):
    def make_fixture(self) -> tuple[Path, Path, Path, Path]:
        temp = Path(tempfile.mkdtemp())
        source_root = temp / "sources"
        source_file = source_root / "账号" / "VS-jingwei-000001.md"
        source_file.parent.mkdir(parents=True)
        full_text = "做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去。他以为是平台不给流量，其实内容没有打中客户真正关心的问题，最后咨询越来越少，才意识到方向错了。"
        source_file.write_text(
            "---\nsource_id: VS-jingwei-000001\n---\n\n## 全文\n\n" + full_text + "\n",
            encoding="utf-8",
        )
        (source_root / "manifest.jsonl").write_text(json.dumps({
            "source_id": "VS-jingwei-000001", "relative_path": "账号/VS-jingwei-000001.md",
            "full_text_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
        }, ensure_ascii=False) + "\n", encoding="utf-8")
        taxonomy = temp / "痛点分类法.md"
        taxonomy.write_text("# 痛点分类法\n\n# 01_内容与流量\n\n## 选题与内容\n", encoding="utf-8")
        cards = temp / "cards"
        card = cards / "01_内容与流量" / "选题与内容" / "PAIN-001.md"
        card.parent.mkdir(parents=True)
        card.write_text("""---
schema: video-pain-card-v1
pain_id: PAIN-001
classification_path: 01_内容与流量/选题与内容
pain_definition: 内容持续更新但没有有效播放
target_people: 做获客短视频的专业人士
scene_tags: ["持续更新", "低播放"]
entry_angles: 用努力无效的反差切入
how_to_tell: 先讲每天更新却没播放的场景，再指出内容没有打中人
short_video_expression: 每天都在更，为什么播放还是起不来？
expression_provenance: 基于原文整理的可用表达
source_ids: ["VS-jingwei-000001"]
---

## 原文场景证据

> 做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去。
""", encoding="utf-8")
        index = temp / "index.jsonl"
        index.write_text(json.dumps({"pain_id": "PAIN-001", "path": str(card)}, ensure_ascii=False) + "\n", encoding="utf-8")
        return cards, source_root, taxonomy, index

    def test_approves_well_formed_pain_card(self) -> None:
        cards, sources, taxonomy, index = self.make_fixture()
        checks, _ = AUDIT.audit(cards, sources, taxonomy, index, [], "formal")
        self.assertTrue(all(check.status == "passed" for check in checks), [check.detail for check in checks])
        card_objects, _ = AUDIT.load_cards(cards)
        receipt_file = cards.parent / "receipt.json"
        mechanical, semantic = AUDIT.write_audit_records(receipt_file, checks, {})
        execution = cards.parent / "execution.json"
        execution.write_text("{}\n", encoding="utf-8")
        receipt = AUDIT.receipt_payload(
            "0123456789abcdef", 1, cards, card_objects, checks, mechanical, semantic,
            execution, "a" * 64,
        )
        self.assertEqual("approved", receipt["status"])
        self.assertEqual(receipt["original_outputs"], receipt["final_outputs"])
        schema = json.loads((ROOT / "schemas" / "audit-receipt-v3.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(receipt)))

    def test_rejects_untraceable_excerpt_and_pending_formal_card(self) -> None:
        cards, sources, taxonomy, index = self.make_fixture()
        card = next(cards.rglob("*.md"))
        card.write_text(card.read_text(encoding="utf-8").replace("做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去。", "这句不在来源全文。"), encoding="utf-8")
        pending = cards / "待归类" / "PAIN-002.md"
        pending.parent.mkdir()
        pending.write_text(card.read_text(encoding="utf-8").replace("PAIN-001", "PAIN-002"), encoding="utf-8")
        checks, _ = AUDIT.audit(cards, sources, taxonomy, index, [], "formal")
        results = {check.id: check for check in checks}
        self.assertEqual("failed", results["source-evidence"].status)
        self.assertEqual("failed", results["pending-placement"].status)

    def test_requires_original_locator_for_evidence_from_corrected_candidate(self) -> None:
        cards, sources, taxonomy, index = self.make_fixture()
        source = next((sources / "账号").glob("*.md"))
        raw_text = "做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去。他以为是平台不给流量，其实内容没有打中客户真正关心的问题，最后咨询越来越少，才意识到方向错了。"
        corrected_text = raw_text.replace("。", "！", 1)
        correction = cards.parent / "corrected.md"
        correction.write_text(
            "---\nsource_id: VS-jingwei-000001\nschema: video-source-correction-candidate-v1\n---\n\n## 校对后全文\n\n" + corrected_text,
            encoding="utf-8",
        )
        card = next(cards.rglob("PAIN-001.md"))
        card.write_text(card.read_text(encoding="utf-8").replace("\n## 原文场景证据\n\n> 每天都在更新，播放却一直上不去。\n", ""), encoding="utf-8")
        evidence_dir = cards / "evidence"
        evidence_dir.mkdir()
        first_sentence = "做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去"
        item = {
            "card_id": "PAIN-001", "source_id": "VS-jingwei-000001", "excerpt": first_sentence + "！",
            "start_offset": 0, "end_offset": len(first_sentence + "！"),
            "standardized_path": str(correction), "full_text_sha256": hashlib.sha256(corrected_text.encode()).hexdigest(),
        }
        (evidence_dir / "evidence.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        checks, _ = AUDIT.audit(cards, sources, taxonomy, index, [], "candidate")
        self.assertEqual("failed", {check.id: check for check in checks}["corrected-source-original-locator"].status)
        item.update({
            "original_source_path": str(source), "original_full_text_sha256": hashlib.sha256(raw_text.encode()).hexdigest(),
            "original_start_offset": 0, "original_end_offset": len(first_sentence + "。"),
            "original_excerpt": first_sentence + "。",
        })
        (evidence_dir / "evidence.json").write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        checks, _ = AUDIT.audit(cards, sources, taxonomy, index, [], "candidate")
        self.assertEqual("passed", {check.id: check for check in checks}["corrected-source-original-locator"].status)

    def test_approves_json_only_machine_candidate_without_browsing_card(self) -> None:
        _, sources, taxonomy, _ = self.make_fixture()
        full_text = "做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去。他以为是平台不给流量，其实内容没有打中客户真正关心的问题，最后咨询越来越少，才意识到方向错了。"
        source = next((sources / "账号").glob("*.md"))
        excerpt = full_text
        root = sources.parent / "machine-evidence"
        evidence_dir = root / "evidence"; evidence_dir.mkdir(parents=True)
        evidence = {
            "evidence_id": "EVD-001", "source_id": "VS-jingwei-000001", "source_excerpt": excerpt,
            "start_offset": 0, "end_offset": len(excerpt), "audiences": ["专业人士"], "scene_tags": ["低播放"],
            "expression_basis": "基于原文整理", "expression_mode": "direct_quote", "short_video_expression": excerpt,
            "expression_completeness": {"schema": "pain-expression-completeness-v1", "available_dimensions": ["object_or_person", "scene", "pain_or_contradiction", "consequence_or_realization"], "covered_dimensions": ["object_or_person", "scene", "pain_or_contradiction", "consequence_or_realization"], "unavailable_dimensions": [], "dimension_fragments": {"object_or_person": "做获客短视频的专业人士", "scene": "每天在办公室熬到深夜更新内容", "pain_or_contradiction": "播放却一直上不去", "consequence_or_realization": "最后咨询越来越少，才意识到方向错了"}, "unavailable_reasons": {}},
            "source_binding": {"standardized_path": str(source), "full_text_sha256": hashlib.sha256(full_text.encode()).hexdigest()},
            "original_source_path": str(source), "original_full_text_sha256": hashlib.sha256(full_text.encode()).hexdigest(),
            "original_start_offset": 0, "original_end_offset": len(excerpt), "original_excerpt": excerpt,
        }
        (evidence_dir / "PAIN-MACHINE-001.json").write_text(json.dumps({"items": [evidence]}, ensure_ascii=False), encoding="utf-8")
        review = {"schema": "pain-card-plain-language-v1", "title": "passed", "definition": "passed", "audience": "passed", "angle": "passed", "framing": "passed", "reader_test": "小学生能听懂，能直接说出口，不用专业词"}
        routed = {
            "schema": "video-module-machine-candidates-v2", "pain_cards": [{
                "pain_id": "PAIN-MACHINE-001", "pain_title": "每天更新，播放还是上不去", "pain_definition": "内容一直在发，可客户没觉得这事和自己有关，所以就是不点开。", "plain_language_review": review,
                "category_name": "01_内容与流量", "subcategory_name": "选题与内容", "audiences": ["每天拍获客视频的老板"], "scene_tags": ["低播放"],
                "angles": [{"angle_title": "忙到半夜发视频，还是没人看", "how_to_frame": "先讲忙到半夜还在发视频，再点出不是平台不推，是内容没说到客户心里。", "plain_language_review": review, "short_video_expression": excerpt, "evidence": [evidence]}],
            }], "micro_modules": [],
        }
        (root / "routed-modules.json").write_text(json.dumps(routed, ensure_ascii=False), encoding="utf-8")
        index = root / "candidate-module-index.jsonl"
        index.write_text(json.dumps({"card_id": "PAIN-MACHINE-001", "machine_candidate_path": str(evidence_dir / "PAIN-MACHINE-001.json")}, ensure_ascii=False) + "\n", encoding="utf-8")
        checks, notes = AUDIT.audit(root, sources, taxonomy, index, [], "candidate")
        self.assertTrue(notes["machine_candidate"])
        self.assertTrue(all(check.status == "passed" for check in checks), [check.detail for check in checks])
        routed["pain_cards"][0]["pain_definition"] = "内容策略没有对准客户。"
        (root / "routed-modules.json").write_text(json.dumps(routed, ensure_ascii=False), encoding="utf-8")
        checks, _ = AUDIT.audit(root, sources, taxonomy, index, [], "candidate")
        self.assertEqual("failed", {check.id: check for check in checks}["plain-language-reader-fields"].status)
        execution = root.parent / "execution-receipt.md"; execution.write_text("{}\n", encoding="utf-8")
        receipt_file = root.parent / "machine-audit-receipt.json"
        mechanical, semantic = AUDIT.write_audit_records(receipt_file, checks, notes)
        payload = AUDIT.receipt_payload("0123456789abcdef", 1, root, [], checks, mechanical, semantic, execution, "c" * 64)
        schema = json.loads((ROOT / "schemas" / "audit-receipt-v3.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(payload)))
        (root / "forbidden.md").write_text("# browse card", encoding="utf-8")
        checks, _ = AUDIT.audit(root, sources, taxonomy, index, [], "candidate")
        self.assertEqual("failed", {check.id: check for check in checks}["machine-candidate-boundary"].status)

    def test_rejects_isolated_conclusion_without_complete_original_context(self) -> None:
        source = "做获客短视频的专业人士每天在办公室熬到深夜更新内容，播放却一直上不去。他以为是平台不给流量，其实内容没有打中客户真正关心的问题，最后咨询越来越少，才意识到方向错了。"
        item = {"evidence_id": "EVD-short", "expression_mode": "direct_quote", "short_video_expression": "播放却一直上不去。"}
        issues = AUDIT.check_expression_completeness(item, source, "播放却一直上不去。")
        self.assertTrue(any("孤立结论" in issue for issue in issues), issues)
        self.assertTrue(any("完整性声明" in issue for issue in issues), issues)

    def test_rejects_light_splice_with_uncited_rewrite(self) -> None:
        source = "老板在办公室反复更新内容，播放却一直上不去，最后咨询越来越少。"
        item = {
            "evidence_id": "EVD-splice", "expression_mode": "light_splice", "short_video_expression": "老板努力更新内容，所以一定会爆。",
            "expression_source_fragments": [{"text": "老板在办公室反复更新内容", "start_offset": 0, "end_offset": 12}],
        }
        issues = AUDIT.check_expression_completeness(item, source, "")
        self.assertTrue(any("改写内容" in issue for issue in issues), issues)

    def test_cli_writes_schema_valid_v3_receipt(self) -> None:
        cards, sources, taxonomy, index = self.make_fixture()
        execution = cards.parent / "execution-receipt.json"
        execution.write_text("{}\n", encoding="utf-8")
        receipt = cards.parent / "audit-receipt.json"
        completed = subprocess.run([
            sys.executable, str(SCRIPT), "--candidate-root", str(cards), "--source-root", str(sources),
            "--taxonomy", str(taxonomy), "--index", str(index), "--mode", "formal",
            "--receipt", str(receipt), "--execution-receipt", str(execution),
            "--handoff-binding-sha256", "b" * 64,
        ], check=False, capture_output=True)
        diagnostics = (completed.stderr + completed.stdout).decode("utf-8", errors="replace")
        self.assertEqual(0, completed.returncode, diagnostics)
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        schema = json.loads((ROOT / "schemas" / "audit-receipt-v3.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(payload)))
        self.assertTrue(receipt.with_name("audit-receipt.mechanical.json").is_file())
        self.assertTrue(receipt.with_name("audit-receipt.semantic-review.json").is_file())


if __name__ == "__main__":
    unittest.main()
