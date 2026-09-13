#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from audit_visual_outputs import (
    collect_mic_pose_violations,
    collect_render_signature_repeat_violations,
    ensure_action_contract,
    ensure_explicit_heading_title_contract,
    ensure_identity_contract,
    ensure_micro_visual_style_contract,
    ensure_multi_role_contract,
    ensure_reserved_zone_contract,
    ensure_single_role_contract,
    ensure_semantic_text_contract,
    ensure_support_label_contract,
)


RECEIPT_FILENAME = "visual-preflight-audit.json"
SEMANTIC_REVIEW_FILENAME = "visual-semantic-review.json"
IP_VISUAL_CONTRACT_VERSION = "4.1.0"
RENDER_PLAN_VERSION = "render-plan-v4.1"
VISUAL_BLUEPRINT_VERSION = "visual-blueprint-v4.1"
TEXT_OVERLAY_VERSION = "model-integrated-text-layout-v1"
SEMANTIC_REVIEW_SCHEMA = "ip-visual-semantic-review-v4.1"
ATTEMPT_LEDGER_FILENAME = "attempt-ledger.json"
EMPTY_HANDOFF_CONCEPTS = {"问题", "事情", "这个", "内容", "重点", "东西", "信息"}
VALID_KEYWORD_SOURCE_FIELDS = {
    "display_title",
    "source_title_full",
    "page_body",
    "cue_phrases",
    "flow_labels",
    "support_labels",
    "must_show_source_quotes",
    "supporting_source_quotes",
    "formula_items",
}
VISUAL_FORM_MODULES = {
    "flow": {"arrow-flow", "step-ladder", "flow-path", "causal-chain"},
    "contrast": {"contrast-block", "before-after", "contrast-bridge"},
    "causal": {"causal-chain", "arrow-flow", "why-chain"},
    "action": {"action-node", "checklist-step", "step-ladder"},
    "question": {"question-ladder", "why-chain"},
    "formula": {"formula-board", "equation-tree", "variable-dashboard"},
    "object": {"icon-tag-block", "component-map", "variable-dashboard"},
    "conclusion": {"conclusion-anchor", "concept-anchor"},
}
POSTER_ONLY_MODULES = {"cover-hero", "poster-hero", "hero-poster", "slogan-poster"}
VISUAL_OBJECT_PLACEHOLDER_TERMS = ("具体手绘场景", "关系节点", "通用图标", "占位", "抽象节点")
PAGE_ALIGNMENT_FIELDS = (
    "page_title",
    "title_strategy",
    "display_title",
    "source_title_full",
    "page_body",
    "deck_title_context_only",
    "deck_title_visible_forbidden",
    "explicit_heading_title_required",
    "explicit_heading_source_level",
    "summary_title_exception_allowed",
    "summary_title_exception_source_quote",
    "cue_phrases",
    "cue_phrase_source_quotes",
    "flow_labels",
    "flow_label_source_quotes",
    "support_labels",
    "support_label_source_quotes",
    "visible_text_source_mode",
    "visible_text_repeat_forbidden",
    "visible_text_slot_dedup_required",
    "repeated_source_fragment_forbidden",
    "visible_text_overlap_forbidden",
    "text_slot_assignment",
    "source_fragment_overlap_groups",
    "text_slot_conflict_resolutions",
    "source_text_ledger",
    "evidence_nodes",
    "main_card_count",
    "parallel_branch_groups",
    "speech_clauses",
    "valid_clause_count",
    "visible_text_density_target",
    "visible_text_density_actual",
    "visible_text_density_required",
    "density_gap_reason",
    "parallel_items_must_show",
    "formula_or_equation_must_show",
    "semantic_units",
    "must_show_source_quotes",
    "supporting_source_quotes",
    "context_only_source_quotes",
    "discarded_transition_quotes",
    "key_information_types",
    "formula_items",
    "semantic_priority_order",
    "visual_module_assignments",
    "core_visual_keywords",
    "keyword_visual_mappings",
    "visual_blueprint",
    "visual_composition_mode",
    "poster_like_forbidden",
    "text_semantic_completeness_required",
    "transition_text_visible_forbidden",
    "formula_preservation_required",
    "red_accent_semantic_only",
    "uniform_label_container_forbidden",
    "label_module_required",
    "label_module_targets",
    "label_visual_pairing_required",
    "micro_visual_anchor_required",
    "module_block_count_target",
    "micro_visual_style",
    "micro_visual_style_label",
    "micro_visual_style_required",
    "micro_visual_container_required",
    "bare_line_icon_forbidden",
    "ui_flat_icon_forbidden",
    "sticker_style_forbidden",
    "realistic_micro_illustration_forbidden",
    "three_d_icon_forbidden",
    "micro_visual_style_consistency_required",
    "micro_visual_style_components",
    "role_count_target",
    "multi_role_required",
    "multi_role_trigger_type",
    "role_distribution_brief",
    "single_role_required",
    "role_action_family",
    "role_expression_family",
    "role_action_intent",
    "role_expression_intent",
    "role_pose_brief",
    "role_prop_intent",
    "role_framing_intent",
    "role_position_intent",
    "render_signature",
    "identity_anchor_required",
    "face_anchor_attached_required",
    "identity_drift_forbidden",
    "hair_variant_forbidden",
    "reserved_zone_enabled",
    "reserved_zone_scope",
    "reserved_zone_size_cm",
    "reserved_zone_side_ratio_of_height",
    "reserved_zone",
    "reserved_zone_rules",
    "visual_blueprint",
)
COVER_ALIGNMENT_FIELDS = (
    "title_text",
    "display_title",
    "source_title_full",
    "cue_phrases",
    "cue_phrase_source_quotes",
    "flow_labels",
    "flow_label_source_quotes",
    "support_labels",
    "support_label_source_quotes",
    "visible_text_source_mode",
    "source_text_ledger",
    "role_count_target",
    "single_role_required",
    "role_action_family",
    "role_expression_family",
    "role_action_intent",
    "role_expression_intent",
    "role_pose_brief",
    "role_prop_intent",
    "role_framing_intent",
    "role_position_intent",
    "render_signature",
    "identity_anchor_required",
    "face_anchor_attached_required",
    "identity_drift_forbidden",
    "hair_variant_forbidden",
    "reserved_zone_enabled",
    "reserved_zone_scope",
    "reserved_zone_size_cm",
    "reserved_zone_side_ratio_of_height",
    "reserved_zone",
    "reserved_zone_rules",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_text(value: Any) -> str:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    # Markdown emphasis is presentation syntax, not source content.  Strip it
    # before comparing a normalized source quote with the original page body.
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’()（）《》【】\[\]—\-*]+", "", str(value or "")).lower()


def page_label(item: dict[str, Any]) -> str:
    return f"page-{int(item.get('page_index', 0)):02d}"


def _keyword_mapping_index(item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for mapping in item.get("keyword_visual_mappings") or []:
        keyword = str(mapping.get("keyword") or "").strip()
        if keyword:
            result[keyword] = mapping
    return result


def ensure_keyword_visual_contract(
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Validate keyword coverage, source traceability, visual fit and prompt carriage.

    This is intentionally mechanical.  It proves the handoff, source fields and
    actual prompt agree; it does not claim the rendered image is semantically
    correct.  That judgment is made in the independent semantic review.
    """
    missing_pages: list[str] = []
    source_failed_pages: list[str] = []
    form_failed_pages: list[str] = []
    prompt_failed_pages: list[str] = []
    for item in page_items:
        label = page_label(item)
        keywords = [str(value).strip() for value in (item.get("core_visual_keywords") or []) if str(value).strip()]
        mappings = item.get("keyword_visual_mappings") or []
        mapping_index = _keyword_mapping_index(item)
        complete = bool(keywords) and len(keywords) == len(set(keywords)) and len(mappings) == len(mapping_index) and set(keywords) == set(mapping_index)
        checks.append({
            "layer": "mechanical",
            "name": f"{label}-keyword-mapping-completeness",
            "status": "passed" if complete else "failed",
            "detail": "" if complete else "core_visual_keywords 与 keyword_visual_mappings 必须非空、唯一且一一对应",
        })
        if not complete:
            missing_pages.append(label)
            issues.append(f"keyword-mapping-incomplete-rejected: {label} 核心关键词映射不完整")

        module_ids: list[str] = []
        visual_object_signatures: list[tuple[str, ...]] = []
        source_ok = complete
        form_ok = complete
        prompt_ok = complete
        prompt_file = Path(str(item.get("prompt_file") or ""))
        prompt_text = prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else ""
        evidence_nodes = [node for mapping in mappings for node in (mapping.get("evidence_nodes") or [])]
        for keyword in keywords:
            mapping = mapping_index.get(keyword) or {}
            source_field = str(mapping.get("source_field") or "")
            source_quote = str(mapping.get("source_quote") or "").strip()
            source_value = item.get(source_field) if source_field in VALID_KEYWORD_SOURCE_FIELDS else None
            current_source_ok = (
                source_field in VALID_KEYWORD_SOURCE_FIELDS
                and bool(source_quote)
                and normalized_text(source_quote) in normalized_text(source_value)
                and normalized_text(keyword) in normalized_text(source_quote)
            )
            source_ok = source_ok and current_source_ok

            visual_form = str(mapping.get("visual_form") or "").strip()
            expected_module = str(mapping.get("expected_visual_module") or "").strip()
            visual_module_id = str(mapping.get("visual_module_id") or "").strip()
            prompt_fragment = str(mapping.get("prompt_fragment") or "").strip()
            module_ids.append(visual_module_id)
            visual_object_signatures.append(tuple(normalized_text(value) for value in (mapping.get("visual_objects") or [])))
            allowed_modules = VISUAL_FORM_MODULES.get(visual_form) or set()
            current_form_ok = (
                bool(visual_module_id)
                and expected_module in allowed_modules
                and expected_module not in POSTER_ONLY_MODULES
                and bool(mapping.get("visual_objects"))
                and not any(
                    placeholder in str(visual_object)
                    for visual_object in (mapping.get("visual_objects") or [])
                    for placeholder in VISUAL_OBJECT_PLACEHOLDER_TERMS
                )
            )
            form_ok = form_ok and current_form_ok
            current_prompt_ok = (
                bool(prompt_text)
                and bool(prompt_fragment)
                and keyword in prompt_text
                and expected_module in prompt_text
                and prompt_fragment in prompt_text
            )
            prompt_ok = prompt_ok and current_prompt_ok
            mapping_evidence = mapping.get("evidence_nodes") or []
            current_evidence_ok = 1 <= len(mapping_evidence) <= 3 and all(
                str(node.get("text") or "").strip()
                and normalized_text(node.get("text")) in normalized_text(node.get("source_quote"))
                and normalized_text(node.get("source_quote")) in normalized_text(item.get(str(node.get("source_field") or "")))
                and node.get("parent_visual_module_id") == visual_module_id
                and str(node.get("visual_module_id") or "").strip()
                and str(node.get("text") or "") in prompt_text
                for node in mapping_evidence
            )
            source_ok = source_ok and current_evidence_ok
            form_ok = form_ok and current_evidence_ok
            prompt_ok = prompt_ok and current_evidence_ok
        if any(not value for value in module_ids) or len(module_ids) != len(set(module_ids)):
            form_ok = False
        if any(not value for value in visual_object_signatures) or len(visual_object_signatures) != len(set(visual_object_signatures)):
            form_ok = False

        non_poster_ok = (
            item.get("visual_composition_mode") == "visual-note"
            and item.get("poster_like_forbidden") is True
            and int(item.get("module_block_count_target") or 0) >= 2
            and item.get("label_module_required") is True
            and item.get("micro_visual_container_required") is True
            and str((item.get("render_plan") or {}).get("scene", {}).get("layout_family") or "") not in POSTER_ONLY_MODULES
        )
        form_ok = form_ok and non_poster_ok

        branch_matches = list(re.finditer(r"(?m)^\s*第\s*[0-9一二三四五六七八九十]+\s*个[，,、:：]?", str(item.get("page_body") or "")))
        branch_blocks = [
            str(item.get("page_body") or "")[match.start():branch_matches[index + 1].start() if index + 1 < len(branch_matches) else None]
            for index, match in enumerate(branch_matches)
        ]
        branch_counts = [
            sum(normalized_text(mapping.get("source_label")) in normalized_text(block) for mapping in mappings)
            for block in branch_blocks
        ]
        branch_ok = not branch_blocks or (
            all(count <= 1 for count in branch_counts)
            and (len(branch_blocks) > 5 or all(count == 1 for count in branch_counts))
        )
        form_ok = form_ok and branch_ok
        if not branch_ok:
            issues.append(f"parallel-branch-fragmentation-rejected: {label} 并列分支被从属条件拆碎为多张主卡")

        for name, ok, target, detail, issue in (
            ("keyword-source-backtrace", source_ok, source_failed_pages, "关键词与正文来源字段无法逐项反查", "关键词来源反查失败"),
            ("visual-form-fit", form_ok, form_failed_pages, "视觉形式、模块或非海报化合同不匹配", "视觉形式匹配或非海报化合同失败"),
            ("prompt-keyword-carriage", prompt_ok, prompt_failed_pages, "Prompt 未真实携带关键词、预期模块或映射片段", "Prompt 未真实携带关键词视觉合同"),
        ):
            checks.append({"layer": "mechanical", "name": f"{label}-{name}", "status": "passed" if ok else "failed", "detail": "" if ok else detail})
            if not ok:
                target.append(label)
                issues.append(f"{issue}: {label}")
    return missing_pages, source_failed_pages, form_failed_pages, prompt_failed_pages


def ensure_formal_directory_cleanliness(
    workdir: Path,
    page_items: list[dict[str, Any]],
    cover_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> list[str]:
    """Reject runtime/evidence artefacts leaked into formal image directories."""
    failed: list[str] = []
    formal_dirs = {
        Path(str(item.get("output_image") or "")).resolve().parent
        for item in page_items + cover_items
        if str(item.get("output_image") or "").strip()
    }
    runtime_names = {
        "pages-spec.json", "codex-handoff.json", "codex-workflow.txt",
        "codex-render-job.json", "visual-semantic-review.json",
        "visual-output-semantic-review.json", "visual-preflight-audit.json",
        "attempt-ledger.json",
        "prompts", "prompt", "work", "tmp", ".tmp",
    }
    for formal_dir in sorted(formal_dirs, key=str):
        label = str(formal_dir)
        leaked: list[str] = []
        if formal_dir == workdir or workdir in formal_dir.parents:
            leaked.append("formal-directory-under-runtime-workdir")
        if formal_dir.is_dir():
            leaked.extend(child.name for child in formal_dir.iterdir() if child.name.lower() in runtime_names)
        ok = not leaked
        checks.append({
            "layer": "mechanical",
            "name": f"formal-directory-cleanliness:{label}",
            "status": "passed" if ok else "failed",
            "detail": "" if ok else ", ".join(leaked),
        })
        if not ok:
            failed.append(label)
            issues.append(f"formal-directory-polluted-rejected: {label} 含运行态或审核证据文件")
    return failed


def ensure_independent_semantic_review(
    workdir: Path,
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], dict[str, list[str]]]:
    review_path = workdir / SEMANTIC_REVIEW_FILENAME
    page_labels = [f"page-{int(item.get('page_index', 0)):02d}" for item in page_items]
    failure_fields = {
        "missing_key_information_pages": [],
        "formula_omission_pages": [],
        "transition_text_misused_pages": [],
        "incomplete_phrase_pages": [],
        "semantic_priority_failed_pages": [],
        "visual_module_mismatch_pages": [],
        "visible_text_density_failed_pages": [],
    }
    if not review_path.is_file():
        checks.append({"layer": "semantic-review", "name": "independent-semantic-review", "status": "failed", "detail": "缺少 visual-semantic-review.json"})
        issues.append("缺少小审独立视觉语义复核文件")
        return page_labels, failure_fields
    review = load_json(review_path)
    expected_pages_spec_hash = sha256_file(workdir / "pages-spec.json")
    expected_handoff_hash = sha256_file(workdir / "codex-handoff.json")
    expected_prompt_hashes = {
        page_label(item): sha256_file(Path(str(item.get("prompt_file") or "")))
        for item in page_items
        if Path(str(item.get("prompt_file") or "")).is_file()
    }
    subject = review.get("subject") or {}
    checks_payload = review.get("checks") or {}
    reviewed_pages = review.get("pages") or []
    reviewed_indexes = {int(item.get("page_index", 0)) for item in reviewed_pages if item.get("status") == "approved"}
    expected_indexes = {int(item.get("page_index", 0)) for item in page_items}
    review_by_index = {int(item.get("page_index", 0)): item for item in reviewed_pages}
    keyword_review_ok = True
    expected_review_checks = {
        "key_information_selection",
        "formula_preservation",
        "semantic_completeness",
        "transition_text_exclusion",
        "semantic_priority",
        "visual_module_mapping",
        "source_text_ledger_traceability",
        "evidence_node_traceability",
        "parallel_branch_integrity",
    }
    for page in page_items:
        index = int(page.get("page_index", 0))
        expected_mappings = _keyword_mapping_index(page)
        page_review = review_by_index.get(index) or {}
        if page_review.get("source_text_ledger") != page.get("source_text_ledger"):
            keyword_review_ok = False
        reviews = page_review.get("keyword_visual_reviews") or []
        reviews_by_keyword = {str(item.get("keyword") or ""): item for item in reviews}
        if set(reviews_by_keyword) != set(expected_mappings) or len(reviews) != len(reviews_by_keyword):
            keyword_review_ok = False
            continue
        prompt_path = Path(str(page.get("prompt_file") or ""))
        prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.is_file() else ""
        for keyword, mapping in expected_mappings.items():
            item = reviews_by_keyword[keyword]
            prompt_evidence = str(item.get("prompt_evidence") or "").strip()
            if not (
                item.get("status") == "passed"
                and item.get("source_quote") == mapping.get("source_quote")
                and item.get("expected_visual_module") == mapping.get("expected_visual_module")
                and item.get("actual_visual_module") == mapping.get("expected_visual_module")
                and len(prompt_evidence) >= 8
                and prompt_evidence in prompt_text
                and len(str(item.get("assessment") or "").strip()) >= 12
            ):
                keyword_review_ok = False
        expected_evidence = {
            str(node.get("evidence_id") or ""): node
            for mapping in expected_mappings.values()
            for node in (mapping.get("evidence_nodes") or [])
        }
        evidence_reviews = page_review.get("evidence_node_reviews") or []
        reviews_by_evidence = {str(node.get("evidence_id") or ""): node for node in evidence_reviews}
        if set(reviews_by_evidence) != set(expected_evidence) or len(evidence_reviews) != len(reviews_by_evidence):
            keyword_review_ok = False
        for evidence_id, evidence in expected_evidence.items():
            node_review = reviews_by_evidence.get(evidence_id) or {}
            prompt_evidence = str(node_review.get("prompt_evidence") or "").strip()
            if not (
                node_review.get("status") == "passed"
                and node_review.get("text") == evidence.get("text")
                and node_review.get("source_quote") == evidence.get("source_quote")
                and node_review.get("parent_visual_module_id") == evidence.get("parent_visual_module_id")
                and node_review.get("expected_visual_module") == evidence.get("visual_module_id")
                and prompt_evidence in prompt_text
                and len(str(node_review.get("assessment") or "").strip()) >= 12
            ):
                keyword_review_ok = False
        non_poster = page_review.get("non_poster_review") or {}
        if not (
            non_poster.get("status") == "passed"
            and len(str(non_poster.get("evidence") or "").strip()) >= 8
            and len(str(non_poster.get("assessment") or "").strip()) >= 12
        ):
            keyword_review_ok = False

    ok = (
        review.get("schema") == SEMANTIC_REVIEW_SCHEMA
        and review.get("status") == "approved"
        and review.get("review_stage") == "pre-render"
        and review.get("independent_review") is True
        and review.get("reviewer") == "xiaoshen"
        and subject.get("pages_spec_sha256") == expected_pages_spec_hash
        and subject.get("handoff_sha256") == expected_handoff_hash
        and subject.get("prompt_sha256_by_page") == expected_prompt_hashes
        and checks_payload
        and expected_review_checks.issubset(checks_payload)
        and all(value == "passed" for value in checks_payload.values())
        and reviewed_indexes == expected_indexes
        and keyword_review_ok
        and not (review.get("issues") or [])
    )
    checks.append({
        "layer": "semantic-review",
        "name": "independent-semantic-review",
        "status": "passed" if ok else "failed",
        "detail": "" if ok else "语义复核未独立 approved、哈希失效、关键词视觉证据不足或逐页确认不完整",
    })
    for field in failure_fields:
        failure_fields[field] = [str(item) for item in (review.get(field) or [])]
    failed_pages = [] if ok else page_labels
    if not ok:
        issues.append("visual-semantic-review 未通过逐主卡和逐证据独立复核，机械预审不得自动放行")
    return failed_pages, failure_fields


def receipt_path(workdir: Path) -> Path:
    return workdir / RECEIPT_FILENAME


def write_receipt(workdir: Path, receipt: dict[str, Any]) -> Path:
    path = receipt_path(workdir)
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compare_contract_fields(
    spec_item: dict[str, Any],
    handoff_item: dict[str, Any],
    fields: tuple[str, ...],
) -> list[str]:
    mismatches: list[str] = []
    for field in fields:
        if spec_item.get(field) != handoff_item.get(field):
            mismatches.append(field)
    return mismatches


def ensure_required_files(workdir: Path, checks: list[dict[str, str]], issues: list[str]) -> None:
    required = (
        "pages-spec.json",
        "codex-handoff.json",
        "codex-workflow.txt",
        "codex-render-job.json",
        ATTEMPT_LEDGER_FILENAME,
        "prompts",
    )
    for name in required:
        path = workdir / name
        ok = path.exists()
        checks.append({"layer": "mechanical", "name": name, "status": "passed" if ok else "failed", "detail": ""})
        if not ok:
            issues.append(f"缺少{name}")


def ensure_pages_spec_alignment(
    workdir: Path,
    handoff: dict[str, Any],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str]]:
    mismatched_pages: list[str] = []
    mismatched_covers: list[str] = []
    specs_payload = load_json(workdir / "pages-spec.json")
    page_specs = specs_payload.get("pages") or []
    cover_specs = specs_payload.get("cover_outputs") or []
    page_specs_by_index = {int(item["page_index"]): item for item in page_specs if item.get("page_index")}
    cover_specs_by_type = {str(item.get("cover_type")): item for item in cover_specs if item.get("cover_type")}
    handoff_pages = handoff.get("pages") or []
    handoff_covers = handoff.get("covers") or []
    selected_pages = handoff.get("selected_pages") or []

    selected_ok = [int(item.get("page_index", 0)) for item in handoff_pages] == [int(page) for page in selected_pages]
    checks.append(
        {
            "layer": "mechanical",
            "name": "selected-pages-contract",
            "status": "passed" if selected_ok else "failed",
            "detail": "" if selected_ok else "handoff.pages 与 selected_pages 不一致",
        }
    )
    if not selected_ok:
        issues.append("selected_pages 与 handoff.pages 不一致")

    count_ok = len(handoff_pages) == len(selected_pages) and all(page in page_specs_by_index for page in selected_pages)
    checks.append(
        {
            "layer": "mechanical",
            "name": "pages-spec-page-count-contract",
            "status": "passed" if count_ok else "failed",
            "detail": "" if count_ok else "pages-spec.json 页数与 handoff 不一致",
        }
    )
    if not count_ok:
        issues.append("pages-spec.json 页数与 handoff 不一致")

    for item in handoff_pages:
        page_index = int(item.get("page_index", 0))
        label = f"page-{page_index:02d}"
        spec_item = page_specs_by_index.get(page_index)
        ok = spec_item is not None
        mismatches: list[str] = []
        if spec_item is not None:
            mismatches = compare_contract_fields(spec_item, item, PAGE_ALIGNMENT_FIELDS)
            ok = not mismatches
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-spec-handoff-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else f"字段不一致: {', '.join(mismatches) if mismatches else '缺少 spec 页'}",
            }
        )
        if not ok:
            mismatched_pages.append(label)
            issues.append(f"{label} pages-spec 与 handoff 合同不一致")

    cover_count_ok = len(handoff_covers) == len(cover_specs)
    checks.append(
        {
            "layer": "mechanical",
            "name": "pages-spec-cover-count-contract",
            "status": "passed" if cover_count_ok else "failed",
            "detail": "" if cover_count_ok else "cover_outputs 与 handoff.covers 数量不一致",
        }
    )
    if not cover_count_ok:
        issues.append("cover_outputs 与 handoff.covers 数量不一致")

    for item in handoff_covers:
        cover_type = str(item.get("cover_type") or "")
        spec_item = cover_specs_by_type.get(cover_type)
        ok = spec_item is not None
        mismatches: list[str] = []
        if spec_item is not None:
            mismatches = compare_contract_fields(spec_item, item, COVER_ALIGNMENT_FIELDS)
            ok = not mismatches
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{cover_type}-spec-handoff-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else f"字段不一致: {', '.join(mismatches) if mismatches else '缺少 cover spec'}",
            }
        )
        if not ok:
            mismatched_covers.append(cover_type)
            issues.append(f"{cover_type} cover spec 与 handoff 合同不一致")
    return mismatched_pages, mismatched_covers


def ensure_prompt_contract(
    handoff: dict[str, Any],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str]]:
    """Validate the active v4.1 compact prompt and visual-blueprint contract."""
    bad_pages: list[str] = []
    bad_covers: list[str] = []
    is_v4 = handoff.get("contract_version") == IP_VISUAL_CONTRACT_VERSION

    def anchor_hash_ok(item: dict[str, Any], image_key: str, hash_key: str) -> bool:
        image = Path(str(item.get(image_key) or ""))
        expected = str(item.get(hash_key) or "")
        return bool(expected and image.is_file() and hashlib.sha256(image.read_bytes()).hexdigest() == expected)

    def compact_ok(item: dict[str, Any], prompt_text: str, limit: int, *, cover: bool) -> bool:
        plan = item.get("render_plan") or {}
        overlay = item.get("text_overlay_plan") or {}
        overlay_file = Path(str(item.get("text_overlay_plan_file") or ""))
        action_hash_ok = (
            anchor_hash_ok(item, "role_action_reference_image", "role_action_reference_sha256")
            if item.get("role_action_reference_image") else True
        )
        quality_hash_ok = (
            anchor_hash_ok(item, "quality_reference_image", "quality_reference_sha256")
            if item.get("quality_reference_required") else True
        )
        mappings = item.get("keyword_visual_mappings") or []
        blueprint = item.get("visual_blueprint") or {}
        blueprint_maps = blueprint.get("keyword_visual_mappings") or []
        blueprint_slots = blueprint.get("text_slots") or []
        evidence_nodes = [node for mapping in mappings for node in (mapping.get("evidence_nodes") or [])]
        source_text_ledger = plan.get("source_text_ledger") or []
        active_source_text_ledger = source_text_ledger[:1] if cover and str(item.get("cover_text_mode") or "") == "title-only" else source_text_ledger
        ledger_ok = (
            bool(source_text_ledger)
            and source_text_ledger == blueprint.get("source_text_ledger")
            and active_source_text_ledger == overlay.get("source_text_ledger")
            and [str(entry.get("text") or "") for entry in active_source_text_ledger]
            == [str(item.get("text") or "") for item in (overlay.get("items") or [])]
        )
        mapping_contract_ok = True if cover else (
            2 <= len(mappings) <= 5
            and plan.get("keyword_visual_mappings") == mappings
            and plan.get("main_card_count") == len(mappings)
            and plan.get("evidence_nodes") == blueprint.get("evidence_nodes")
            and {str(node.get("evidence_id") or "") for node in plan.get("evidence_nodes") or []}
            == {str(node.get("evidence_id") or "") for node in evidence_nodes}
            and blueprint.get("version") == VISUAL_BLUEPRINT_VERSION
            and blueprint_maps == mappings
            and len(blueprint_slots) == len(mappings) + len(evidence_nodes) + 1
            and all(1 <= len(mapping.get("evidence_nodes") or []) <= 3 for mapping in mappings)
            and all(
                node.get("parent_visual_module_id") == mapping.get("visual_module_id")
                and node.get("text") in prompt_text
                for mapping in mappings for node in (mapping.get("evidence_nodes") or [])
            )
            and all(isinstance(slot.get("rect"), list) and len(slot["rect"]) == 4 for slot in blueprint_slots)
        )
        required = (
            plan.get("version") == RENDER_PLAN_VERSION
            and plan.get("render_profile") == "creative"
            and mapping_contract_ok
            and blueprint.get("version") == VISUAL_BLUEPRINT_VERSION
            and bool(blueprint.get("content_hash"))
            and bool(blueprint.get("text_slots"))
        ) and (
            plan.get("text_strategy", {}).get("mode") == "model-integrated-chinese"
            and plan.get("text_strategy", {}).get("generator_text_forbidden") is False
            and plan.get("text_strategy", {}).get("model_renders_exact_chinese") is True
            and plan.get("text_strategy", {}).get("source_text_ledger_required") is True
            and plan.get("text_strategy", {}).get("cross_page_unjustified_motif_reuse_forbidden") is True
            and plan.get("text_strategy", {}).get("program_draws_card_surface") is False
            and plan.get("text_strategy", {}).get("generator_blank_card_slots_forbidden") is True
            and plan.get("text_strategy", {}).get("final_visual_note_required") is True
            and plan.get("text_strategy", {}).get("raw_background_delivery_forbidden") is True
            and plan.get("text_strategy", {}).get("all_source_cards_must_be_filled") is True
            and plan.get("text_strategy", {}).get("main_card_evidence_nodes_required") is True
            and plan.get("text_strategy", {}).get("model_draws_module_card_and_micro_visual") is True
            and plan.get("text_strategy", {}).get("text_overlay_must_not_cover_micro_visual") is True
            and overlay.get("version") == TEXT_OVERLAY_VERSION
            and overlay.get("generator_text_forbidden") is False
            and overlay.get("model_renders_exact_chinese") is True
            and overlay.get("program_overlay_forbidden") is True
            and ledger_ok
            and overlay.get("visual_blueprint_hash") == blueprint.get("content_hash")
            and overlay_file.is_file()
            and anchor_hash_ok(item, "role_face_anchor_image", "role_face_anchor_sha256")
            and action_hash_ok
            and quality_hash_ok
        )
        module_slots_ok = cover or all(
            isinstance(slot.get("module_rect"), list) and len(slot["module_rect"]) == 4
            and isinstance(slot.get("icon_rect"), list) and len(slot["icon_rect"]) == 4
            for slot in blueprint_slots if slot.get("kind") == "source-label-card"
        )
        prompt_lower = prompt_text.lower()
        ledger_rule_ok = "source text ledger" in prompt_lower
        integrated_text_ok = (
            "render each listed phrase exactly" in prompt_lower
            and "text_layer: model-integrated-chinese" in prompt_lower
            and "blank title" in prompt_lower
        )
        prompt_ok = bool(prompt_text) and len(prompt_text) <= limit and f"render_plan: {RENDER_PLAN_VERSION}" in prompt_text and ledger_rule_ok and integrated_text_ok and "flat solid exact background" in prompt_lower and "approved quality baseline" in prompt_lower and "final delivery rule" in prompt_lower and module_slots_ok
        if not cover:
            prompt_ok = prompt_ok and "VISUAL KEYWORD MAP" in prompt_text and all(
                str(mapping.get("prompt_fragment") or "") in prompt_text
                for mapping in mappings
            )
        if cover:
            mode = str(item.get("cover_text_mode") or "source-labels")
            required = required and mode in {"source-labels", "title-only"}
        return bool(required and prompt_ok)

    for item in handoff.get("pages") or []:
        page_index = int(item.get("page_index", 0))
        label = f"page-{page_index:02d}"
        prompt_file = Path(str(item.get("prompt_file") or ""))
        prompt_text = prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else ""
        if is_v4:
            ok = compact_ok(item, prompt_text, 5000, cover=False)
        else:
            ok = False
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-prompt-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else "prompt 与 handoff 的关键合同不一致或 prompt 缺失",
            }
        )
        if not ok:
            bad_pages.append(label)
            issues.append(f"prompt-handoff-mismatch-rejected: {label} prompt 未完整承接 handoff 合同")

    for item in handoff.get("covers") or []:
        cover_type = str(item.get("cover_type") or "")
        prompt_file = Path(str(item.get("prompt_file") or ""))
        prompt_text = prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else ""
        if is_v4:
            ok = compact_ok(item, prompt_text, 1800, cover=True)
        else:
            ok = False
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{cover_type}-prompt-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else "cover prompt 与 handoff 的关键合同不一致或 prompt 缺失",
            }
        )
        if not ok:
            bad_covers.append(cover_type)
            issues.append(f"prompt-handoff-mismatch-rejected: {cover_type} prompt 未完整承接 handoff 合同")
    return bad_pages, bad_covers


def ensure_render_job_contract(
    workdir: Path,
    handoff: dict[str, Any],
    checks: list[dict[str, str]],
    issues: list[str],
) -> bool:
    job = load_json(workdir / "codex-render-job.json")
    selected_pages = [int(page.get("page_index", 0)) for page in handoff.get("pages") or [] if page.get("page_index")]
    include_covers = bool(handoff.get("covers"))
    quality_reference = job.get("quality_reference_image") or {}
    quality_path = Path(str(quality_reference.get("path") or ""))
    render_rules = job.get("render_rules") or {}
    def same_path(actual: Any, expected: Path) -> bool:
        """Compare resolved paths so Windows short-name aliases cannot invalidate a v4.1 job."""
        try:
            return Path(str(actual or "")).resolve() == expected.resolve()
        except OSError:
            return False

    ok = (
        job.get("selected_pages") == selected_pages
        and bool(job.get("include_covers")) == include_covers
        and same_path(job.get("handoff_file"), workdir / "codex-handoff.json")
        and same_path(job.get("pages_spec_file"), workdir / "pages-spec.json")
        and same_path(job.get("workflow_file"), workdir / "codex-workflow.txt")
        and quality_path.is_file()
        and quality_reference.get("sha256") == sha256_file(quality_path)
        and quality_reference.get("attachment_required") is True
        and quality_reference.get("must_be_real_image_input") is True
        and render_rules.get("quality_reference_must_be_shown_every_run") is True
        and render_rules.get("model_integrated_chinese_required") is True
        and render_rules.get("blank_text_region_forbidden") is True
        and render_rules.get("program_text_overlay_forbidden") is True
        and job.get("intermediate_render_allowed") is False
    )
    checks.append(
        {
            "layer": "mechanical",
            "name": "codex-render-job-contract",
            "status": "passed" if ok else "failed",
            "detail": "" if ok else "render job 与当前工作包关键路径或页码不一致",
        }
    )
    if not ok:
        issues.append("codex-render-job.json 与当前工作包关键路径或页码不一致")
    return ok


def ensure_attempt_ledger_contract(
    workdir: Path,
    handoff: dict[str, Any],
    checks: list[dict[str, str]],
    issues: list[str],
) -> bool:
    path = workdir / ATTEMPT_LEDGER_FILENAME
    ledger = load_json(path) if path.is_file() else {}
    expected = []
    for item in list(handoff.get("pages") or []) + list(handoff.get("covers") or []):
        asset_id = page_label(item) if item.get("page_index") else str(item.get("cover_type") or "")
        expected.append((asset_id, str(item.get("visual_blueprint_hash") or "")))
    indexed = {str(item.get("asset_id") or ""): item for item in ledger.get("assets") or []}
    ok = (
        ledger.get("schema") == "ip-visual-attempt-ledger-v4.1"
        and ledger.get("contract_version") == IP_VISUAL_CONTRACT_VERSION
        and ledger.get("retry_policy") == "single-asset-unlimited-until-approved"
        and set(indexed) == {asset_id for asset_id, _ in expected}
        and all(indexed[asset_id].get("visual_blueprint_hash") == blueprint_hash for asset_id, blueprint_hash in expected)
    )
    checks.append({
        "layer": "mechanical",
        "name": "v4.1-attempt-ledger-contract",
        "status": "passed" if ok else "failed",
        "detail": "" if ok else "attempt-ledger 缺失、资产范围或蓝图哈希不一致",
    })
    if not ok:
        issues.append("attempt-ledger 与 v4.1 handoff 蓝图合同不一致")
    return ok


def audit(workdir: Path) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    issues: list[str] = []
    workdir = workdir.resolve()
    ensure_required_files(workdir, checks, issues)

    if issues:
        return {
            "schema": "visual-work-package-preflight-audit-result-v4.1",
            "auditor": "xiaoshen",
            "auditor_version": "4.1.0",
            "audit_contract": "ip-visual-work-package-preflight-v4.1",
            "subject": str(workdir),
            "status": "rejected",
            "checks": checks,
            "issues": issues,
            "rejected_pages": [],
            "rejected_covers": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    handoff = load_json(workdir / "codex-handoff.json")
    specs_payload = load_json(workdir / "pages-spec.json")
    page_items = handoff.get("pages") or []
    cover_items = handoff.get("covers") or []
    version_ok = (
        handoff.get("contract_version") == IP_VISUAL_CONTRACT_VERSION
        and specs_payload.get("contract_version") == handoff.get("contract_version")
    )
    checks.append({
        "layer": "mechanical",
        "name": "generate-ip-ppt-contract-version",
        "status": "passed" if version_ok else "failed",
            "detail": "" if version_ok else "新任务 pages-spec/codex-handoff contract_version 必须一致，且只能为 4.1.0",
    })
    if not version_ok:
        issues.append("generate-ip-ppt 工作包合同版本不受支持或 pages-spec/handoff 不一致")

    ensure_action_contract(page_items + cover_items, checks, issues)
    repeated_pages = collect_render_signature_repeat_violations(page_items, cover_items, checks, issues)
    mic_pose_violations = collect_mic_pose_violations(page_items, cover_items, checks, issues)
    (
        missing_support_labels,
        failed_label_anchor_contract,
        visible_text_source_failed,
        support_label_source_mismatch,
        cue_phrase_source_mismatch,
        deck_title_visible_pages,
        visible_text_repeat_failed,
        visible_text_overlap_failed,
        label_module_contract_failed,
        micro_visual_pairing_failed,
        source_text_ledger_failed,
    ) = ensure_support_label_contract(page_items, checks, issues)
    (
        mechanical_missing_key_information_pages,
        mechanical_formula_omission_pages,
        mechanical_transition_text_misused_pages,
        mechanical_incomplete_phrase_pages,
        mechanical_semantic_priority_failed_pages,
        mechanical_visual_module_mismatch_pages,
        mechanical_visible_text_density_failed_pages,
    ) = ensure_semantic_text_contract(page_items, checks, issues)
    semantic_review_failed_pages, semantic_review_failures = ensure_independent_semantic_review(
        workdir, page_items, checks, issues
    )
    missing_key_information_pages = sorted(set(
        mechanical_missing_key_information_pages + semantic_review_failures["missing_key_information_pages"]
    ))
    formula_omission_pages = sorted(set(
        mechanical_formula_omission_pages + semantic_review_failures["formula_omission_pages"]
    ))
    transition_text_misused_pages = sorted(set(
        mechanical_transition_text_misused_pages + semantic_review_failures["transition_text_misused_pages"]
    ))
    incomplete_phrase_pages = sorted(set(
        mechanical_incomplete_phrase_pages + semantic_review_failures["incomplete_phrase_pages"]
    ))
    semantic_priority_failed_pages = sorted(set(
        mechanical_semantic_priority_failed_pages + semantic_review_failures["semantic_priority_failed_pages"]
    ))
    visual_module_mismatch_pages = sorted(set(
        mechanical_visual_module_mismatch_pages + semantic_review_failures["visual_module_mismatch_pages"]
    ))
    visible_text_density_failed_pages = sorted(set(
        mechanical_visible_text_density_failed_pages + semantic_review_failures.get("visible_text_density_failed_pages", [])
    ))
    (
        micro_visual_style_drift_pages,
        bare_line_icon_violation_pages,
        ui_icon_style_violation_pages,
        micro_visual_container_missing_pages,
    ) = ensure_micro_visual_style_contract(page_items, checks, issues)
    (
        explicit_heading_title_failed_pages,
        summary_title_exception_failed_pages,
    ) = ensure_explicit_heading_title_contract(page_items, checks, issues)
    single_role_violations = ensure_single_role_contract(page_items, cover_items, checks, issues)
    body_reserved_zone_contract_failed_pages, _, cover_reserved_zone_inheritance_failed_covers = ensure_reserved_zone_contract(
        page_items, cover_items, checks, issues, output_dir=None, audit_pixels=False
    )
    multi_role_contract_failed = ensure_multi_role_contract(page_items, checks, issues)
    (
        identity_anchor_missing_pages,
        face_identity_drift_pages,
        hair_identity_drift_pages,
        style_identity_drift_pages,
    ) = ensure_identity_contract(page_items + cover_items, checks, issues)
    spec_handoff_mismatch_pages, spec_handoff_mismatch_covers = ensure_pages_spec_alignment(workdir, handoff, checks, issues)
    prompt_handoff_mismatch_pages, prompt_handoff_mismatch_covers = ensure_prompt_contract(handoff, checks, issues)
    (
        keyword_mapping_incomplete_pages,
        keyword_source_backtrace_failed_pages,
        visual_form_mismatch_pages,
        prompt_keyword_carriage_failed_pages,
    ) = ensure_keyword_visual_contract(page_items, checks, issues)
    formal_directory_pollution_targets = ensure_formal_directory_cleanliness(
        workdir, page_items, cover_items, checks, issues
    )
    ensure_render_job_contract(workdir, handoff, checks, issues)
    ensure_attempt_ledger_contract(workdir, handoff, checks, issues)

    rejected_pages = sorted(set(
        repeated_pages
        + mic_pose_violations
        + missing_support_labels
        + failed_label_anchor_contract
        + visible_text_source_failed
        + support_label_source_mismatch
        + cue_phrase_source_mismatch
        + deck_title_visible_pages
        + visible_text_repeat_failed
        + visible_text_overlap_failed
        + label_module_contract_failed
        + micro_visual_pairing_failed
        + source_text_ledger_failed
        + missing_key_information_pages
        + formula_omission_pages
        + transition_text_misused_pages
        + incomplete_phrase_pages
        + semantic_priority_failed_pages
        + visual_module_mismatch_pages
        + visible_text_density_failed_pages
        + micro_visual_style_drift_pages
        + bare_line_icon_violation_pages
        + ui_icon_style_violation_pages
        + micro_visual_container_missing_pages
        + semantic_review_failed_pages
        + explicit_heading_title_failed_pages
        + summary_title_exception_failed_pages
        + [item for item in single_role_violations if item.startswith("page-")]
        + body_reserved_zone_contract_failed_pages
        + multi_role_contract_failed
        + [item for item in identity_anchor_missing_pages if item.startswith("page-")]
        + [item for item in face_identity_drift_pages if item.startswith("page-")]
        + [item for item in hair_identity_drift_pages if item.startswith("page-")]
        + [item for item in style_identity_drift_pages if item.startswith("page-")]
        + spec_handoff_mismatch_pages
        + prompt_handoff_mismatch_pages
        + keyword_mapping_incomplete_pages
        + keyword_source_backtrace_failed_pages
        + visual_form_mismatch_pages
        + prompt_keyword_carriage_failed_pages
    ))
    rejected_covers = sorted(set(
        [item for item in repeated_pages if item.startswith("cover-")]
        + [item for item in mic_pose_violations if item.startswith("cover-")]
        + [item for item in single_role_violations if item.startswith("cover-")]
        + cover_reserved_zone_inheritance_failed_covers
        + [item for item in identity_anchor_missing_pages if item.startswith("cover-")]
        + [item for item in face_identity_drift_pages if item.startswith("cover-")]
        + [item for item in hair_identity_drift_pages if item.startswith("cover-")]
        + [item for item in style_identity_drift_pages if item.startswith("cover-")]
        + spec_handoff_mismatch_covers
        + prompt_handoff_mismatch_covers
    ))
    status = "approved" if not any(check.get("status") == "failed" for check in checks) and not issues else "rejected"
    return {
        "schema": "visual-work-package-preflight-audit-result-v4.1",
        "auditor": "xiaoshen",
        "auditor_version": "4.1.0",
        "audit_contract": "ip-visual-work-package-preflight-v4.1",
        "subject": str(workdir),
        "status": status,
        "checks": checks,
        "issues": issues,
        "rejected_pages": rejected_pages,
        "rejected_covers": rejected_covers,
        "missing_support_labels_pages": missing_support_labels,
        "label_anchor_contract_failed_pages": failed_label_anchor_contract,
        "visible_text_source_contract_failed_pages": visible_text_source_failed,
        "support_label_source_mismatch_pages": support_label_source_mismatch,
        "cue_phrase_source_mismatch_pages": cue_phrase_source_mismatch,
        "deck_title_visible_pages": deck_title_visible_pages,
        "visible_text_repeat_contract_failed_pages": visible_text_repeat_failed,
        "visible_text_overlap_contract_failed_pages": visible_text_overlap_failed,
        "label_module_contract_failed_pages": label_module_contract_failed,
        "micro_visual_pairing_contract_failed_pages": micro_visual_pairing_failed,
        "source_text_ledger_failed_pages": source_text_ledger_failed,
        "semantic_review_failed_pages": semantic_review_failed_pages,
        "missing_key_information_pages": missing_key_information_pages,
        "formula_omission_pages": formula_omission_pages,
        "transition_text_misused_pages": transition_text_misused_pages,
        "incomplete_phrase_pages": incomplete_phrase_pages,
        "semantic_priority_failed_pages": semantic_priority_failed_pages,
        "visual_module_mismatch_pages": visual_module_mismatch_pages,
        "visible_text_density_failed_pages": visible_text_density_failed_pages,
        "micro_visual_style_drift_pages": micro_visual_style_drift_pages,
        "bare_line_icon_violation_pages": bare_line_icon_violation_pages,
        "ui_icon_style_violation_pages": ui_icon_style_violation_pages,
        "micro_visual_container_missing_pages": micro_visual_container_missing_pages,
        "explicit_heading_title_contract_failed_pages": explicit_heading_title_failed_pages,
        "summary_title_exception_failed_pages": summary_title_exception_failed_pages,
        "single_role_contract_failed_targets": single_role_violations,
        "body_reserved_zone_contract_failed_pages": body_reserved_zone_contract_failed_pages,
        "reserved_zone_violation_pages": [],
        "cover_reserved_zone_inheritance_failed_covers": cover_reserved_zone_inheritance_failed_covers,
        "multi_role_contract_failed_pages": multi_role_contract_failed,
        "render_signature_repeat_pages": repeated_pages,
        "mic_pose_violation_pages": mic_pose_violations,
        "identity_anchor_missing_pages": identity_anchor_missing_pages,
        "face_identity_drift_pages": face_identity_drift_pages,
        "hair_identity_drift_pages": hair_identity_drift_pages,
        "style_identity_drift_pages": style_identity_drift_pages,
        "spec_handoff_mismatch_pages": spec_handoff_mismatch_pages,
        "spec_handoff_mismatch_covers": spec_handoff_mismatch_covers,
        "prompt_handoff_mismatch_pages": prompt_handoff_mismatch_pages,
        "prompt_handoff_mismatch_covers": prompt_handoff_mismatch_covers,
        "keyword_mapping_incomplete_pages": keyword_mapping_incomplete_pages,
        "keyword_source_backtrace_failed_pages": keyword_source_backtrace_failed_pages,
        "visual_form_mismatch_pages": visual_form_mismatch_pages,
        "prompt_keyword_carriage_failed_pages": prompt_keyword_carriage_failed_pages,
        "formal_directory_pollution_targets": formal_directory_pollution_targets,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="审核 IP 视觉工作包是否具备正式进入生图阶段的资格")
    ap.add_argument("workdir", help="工作包目录")
    args = ap.parse_args()
    workdir = Path(args.workdir).expanduser().resolve()
    receipt = audit(workdir)
    write_receipt(workdir, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt.get("status") == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
