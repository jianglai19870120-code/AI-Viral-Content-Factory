#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


PPT_PAGE_HEIGHT_CM = 19.05
RESERVED_ZONE_SIZE_CM = [3, 3]
RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT = round(RESERVED_ZONE_SIZE_CM[1] / PPT_PAGE_HEIGHT_CM, 5)
# The reserved area is not merely "mostly background".  It is a pixel-exact
# export contract: every pixel must be the declared page background RGB value.
# A tolerance or ratio threshold lets a near-colour placeholder rectangle pass.
RESERVED_ZONE_COLOR_TOLERANCE = 0
RESERVED_ZONE_MAX_NON_BACKGROUND_RATIO = 0.0
MICRO_VISUAL_STYLE = "handdrawn-card-icon-module"
IP_VISUAL_CONTRACT_VERSION = "4.1.0"
OUTPUT_SEMANTIC_REVIEW_FILENAME = "visual-output-semantic-review.json"
OUTPUT_SEMANTIC_REVIEW_SCHEMA = "ip-visual-output-semantic-review-v4.1"
MICRO_VISUAL_STYLE_COMPONENTS = {
    "handdrawn-card-or-node-container",
    "semantic-handdrawn-icon-or-mini-scene",
    "source-rooted-short-label",
    "restrained-flat-color-accent",
}

ACTION_CONTRACT_FIELDS = (
    "role_action_match_required",
    "role_action_match_basis",
    "role_action_family",
    "role_expression_family",
    "role_action_intent",
    "role_expression_intent",
    "role_pose_brief",
    "role_prop_intent",
    "role_framing_intent",
    "role_position_intent",
    "hair_expression_mode",
    "render_signature",
    "identity_anchor_required",
    "face_anchor_attached_required",
    "identity_drift_forbidden",
    "hair_variant_forbidden",
    "global_render_signature_unique_required",
    "mic_pose_limited_once",
    "support_labels_required",
    "source_rooted_labels_required",
    "deck_title_context_only",
    "deck_title_visible_forbidden",
    "visible_text_source_mode",
    "visible_text_repeat_forbidden",
    "visible_text_slot_dedup_required",
    "repeated_source_fragment_forbidden",
    "visible_text_overlap_forbidden",
    "text_slot_assignment",
    "source_fragment_overlap_groups",
    "text_slot_conflict_resolutions",
    "source_text_ledger",
    "speech_clauses",
    "valid_clause_count",
    "visible_text_density_target",
    "visible_text_density_actual",
    "visible_text_density_required",
    "density_gap_reason",
    "parallel_items_must_show",
    "formula_or_equation_must_show",
    "cue_phrase_source_quotes",
    "flow_label_source_quotes",
    "support_label_source_quotes",
    "role_count_decision_mode",
    "role_count_target",
    "multi_role_required",
    "multi_role_trigger_type",
    "role_distribution_brief",
    "label_anchor_targets",
    "label_module_required",
    "label_module_targets",
    "label_visual_pairing_required",
    "micro_visual_anchor_required",
    "module_block_count_target",
    "single_role_required",
    "allowed_role_framings",
    "action_reference_optional",
)
SINGLE_ROLE_TARGETS = {"page-01", "cover-3x4", "cover-4x3"}
MIC_PROP_SIGNATURES = {"mic", "speaking-mic"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_archive_contract_file(output: Path, filename: str) -> Path:
    """Only v4.1 evidence/ is a valid contract location."""
    return output / "evidence" / filename


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_post_render_review_scaffold(output: Path) -> Path:
    """Create a non-approving, image-hash-bound review form for 小审.

    This is deliberately separate from the pre-render prompt review.  The form
    is created only after the final PNGs exist, so a reviewer must attest to
    each actual module in the image that will be delivered.
    """
    evidence_dir = output / "evidence"
    pages_spec_path = evidence_dir / "pages-spec.json"
    handoff_path = evidence_dir / "codex-handoff.json"
    if not pages_spec_path.is_file() or not handoff_path.is_file():
        raise FileNotFoundError("缺少 evidence/pages-spec.json 或 evidence/codex-handoff.json，不能建立成图审核表")
    handoff = load_json(handoff_path)
    page_items = list(handoff.get("pages") or [])
    if not page_items:
        raise ValueError("codex-handoff.json 不含正文页，不能建立成图审核表")

    image_sha256_by_page: dict[str, str] = {}
    for page in page_items:
        label = f"page-{int(page.get('page_index', 0)):02d}"
        image_path = output / f"{label}.png"
        if not image_path.is_file():
            raise FileNotFoundError(f"缺少原生图文一体最终图 {image_path}，不能建立成图审核表")
        image_sha256_by_page[label] = sha256_file(image_path)

    review_path = evidence_dir / OUTPUT_SEMANTIC_REVIEW_FILENAME
    if review_path.is_file():
        existing = load_json(review_path)
        if existing.get("status") == "approved":
            raise ValueError("已有 approved 成图审核表；如需重画，请先建立新的工作包，不得覆盖既有回执")

    def expected_source_text_ledger(page: dict[str, Any]) -> list[dict[str, Any]]:
        """Use the generated source ledger, never a separate text vocabulary."""
        return list(page.get("source_text_ledger") or [])

    review = {
        "schema": OUTPUT_SEMANTIC_REVIEW_SCHEMA,
        "auditor": "xiaoshen",
        "reviewer": "xiaoshen",
        "review_stage": "post-render",
        "independent_review": True,
        "status": "needs-review",
        "subject": {
            "pages_spec_sha256": sha256_file(pages_spec_path),
            "handoff_sha256": sha256_file(handoff_path),
            "image_sha256_by_page": image_sha256_by_page,
        },
        "checks": {
            "title_and_source_cards_visible": "needs-review",
            "all_visible_chinese_source_traced": "needs-review",
            "keyword_visual_modules_visible": "needs-review",
            "evidence_nodes_visible": "needs-review",
            "non_poster_composition": "needs-review",
            "cross_page_visual_duplicate_check": "needs-review",
            "raw_background_rejected": "needs-review",
            "blank_text_regions_absent": "needs-review",
            "approved_quality_baseline_match": "needs-review",
        },
        "cross_page_duplicate_visuals": [],
        "pages": [
            {
                "page_index": int(page.get("page_index", 0)),
                "visual_blueprint_hash": str(page.get("visual_blueprint_hash") or ""),
                "status": "needs-review",
                "source_text_ledger": expected_source_text_ledger(page),
                "observed_visible_chinese": [],
                "all_visible_chinese_source_traced": "needs-review",
                "untraced_visible_chinese": [],
                "blank_text_regions": [],
                "keyword_visual_reviews": [
                    {
                        "keyword": str(mapping.get("keyword") or ""),
                        "source_quote": str(mapping.get("source_quote") or ""),
                        "expected_visual_module": str(mapping.get("expected_visual_module") or ""),
                        "actual_visual_module": "",
                        "image_sha256": image_sha256_by_page[f"page-{int(page.get('page_index', 0)):02d}"],
                        "actual_visual_evidence": "",
                        "assessment": "",
                        "status": "needs-review",
                    }
                    for mapping in (page.get("keyword_visual_mappings") or [])
                ],
                "evidence_node_reviews": [
                    {
                        "evidence_id": str(node.get("evidence_id") or ""),
                        "text": str(node.get("text") or ""),
                        "source_quote": str(node.get("source_quote") or ""),
                        "parent_visual_module_id": str(node.get("parent_visual_module_id") or ""),
                        "expected_visual_module": str(node.get("visual_module_id") or ""),
                        "actual_visible_chinese": "",
                        "actual_visual_relation": "",
                        "image_sha256": image_sha256_by_page[f"page-{int(page.get('page_index', 0)):02d}"],
                        "assessment": "",
                        "status": "needs-review",
                    }
                    for mapping in (page.get("keyword_visual_mappings") or [])
                    for node in (mapping.get("evidence_nodes") or [])
                ],
                "non_poster_review": {
                    "status": "needs-review",
                    "image_sha256": image_sha256_by_page[f"page-{int(page.get('page_index', 0)):02d}"],
                    "evidence": "",
                    "assessment": "",
                },
                "quality_baseline_review": {
                    "status": "needs-review",
                    "image_sha256": image_sha256_by_page[f"page-{int(page.get('page_index', 0)):02d}"],
                    "evidence": "",
                    "assessment": "",
                },
            }
            for page in page_items
        ],
        "issues": [],
    }
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return review_path


def ensure_post_render_keyword_visual_review(
    output: Path,
    handoff: dict[str, Any],
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str]]:
    """Bind independent per-keyword visual judgments to the rendered PNGs.

    No OCR or image generation happens here.  The mechanical layer verifies
    that an independent semantic reviewer described each actual visual module
    and signed the exact pages-spec, handoff and image hashes.  Merely copying
    the planning fields cannot satisfy the evidence/assessment requirements.
    """
    failed_pages: list[str] = []
    non_poster_failed_pages: list[str] = []
    review_path = resolve_archive_contract_file(output, OUTPUT_SEMANTIC_REVIEW_FILENAME)
    expected_labels = [f"page-{int(item.get('page_index', 0)):02d}" for item in page_items]
    if not review_path.is_file():
        checks.append({
            "layer": "semantic-review",
            "name": "post-render-keyword-visual-review",
            "status": "failed",
            "detail": f"缺少 {OUTPUT_SEMANTIC_REVIEW_FILENAME}",
        })
        issues.append("缺少成图后逐主卡和逐证据独立视觉复核文件")
        return expected_labels, expected_labels

    review = load_json(review_path)
    pages_spec_path = resolve_archive_contract_file(output, "pages-spec.json")
    handoff_path = resolve_archive_contract_file(output, "codex-handoff.json")
    expected_image_hashes = {
        label: sha256_file(output / f"{label}.png")
        for label in expected_labels
        if (output / f"{label}.png").is_file()
    }
    subject = review.get("subject") or {}
    subject_ok = (
        review.get("schema") == OUTPUT_SEMANTIC_REVIEW_SCHEMA
        and review.get("status") == "approved"
        and review.get("review_stage") == "post-render"
        and review.get("independent_review") is True
        and review.get("reviewer") == "xiaoshen"
        and pages_spec_path.is_file()
        and handoff_path.is_file()
        and subject.get("pages_spec_sha256") == sha256_file(pages_spec_path)
        and subject.get("handoff_sha256") == sha256_file(handoff_path)
        and subject.get("image_sha256_by_page") == expected_image_hashes
        and not (review.get("issues") or [])
        and (review.get("checks") or {})
        and all(value == "passed" for value in (review.get("checks") or {}).values())
    )
    review_pages = review.get("pages") or []
    by_index = {int(item.get("page_index", 0)): item for item in review_pages}
    if set(by_index) != {int(item.get("page_index", 0)) for item in page_items} or len(by_index) != len(review_pages):
        subject_ok = False

    for page in page_items:
        index = int(page.get("page_index", 0))
        label = f"page-{index:02d}"
        page_review = by_index.get(index) or {}
        mappings = {
            str(item.get("keyword") or ""): item
            for item in (page.get("keyword_visual_mappings") or [])
            if str(item.get("keyword") or "").strip()
        }
        keyword_reviews = page_review.get("keyword_visual_reviews") or []
        reviews_by_keyword = {str(item.get("keyword") or ""): item for item in keyword_reviews}
        expected_evidence = {
            str(node.get("evidence_id") or ""): node
            for mapping in mappings.values()
            for node in (mapping.get("evidence_nodes") or [])
        }
        evidence_reviews = page_review.get("evidence_node_reviews") or []
        reviews_by_evidence = {str(item.get("evidence_id") or ""): item for item in evidence_reviews}
        expected_ledger = list(page.get("source_text_ledger") or [])
        expected_visible = [str(entry.get("text") or "").strip() for entry in expected_ledger]
        page_ok = (
            page_review.get("status") == "approved"
            and page_review.get("visual_blueprint_hash") == page.get("visual_blueprint_hash")
            and bool(expected_ledger)
            and page_review.get("source_text_ledger") == expected_ledger
            and page_review.get("observed_visible_chinese") == expected_visible
            and page_review.get("all_visible_chinese_source_traced") == "passed"
            and not (page_review.get("untraced_visible_chinese") or [])
            and not (page_review.get("blank_text_regions") or [])
            and bool(mappings)
            and set(reviews_by_keyword) == set(mappings)
            and len(reviews_by_keyword) == len(keyword_reviews)
            and bool(expected_evidence)
            and set(reviews_by_evidence) == set(expected_evidence)
            and len(reviews_by_evidence) == len(evidence_reviews)
        )
        for keyword, mapping in mappings.items():
            item = reviews_by_keyword.get(keyword) or {}
            page_ok = page_ok and (
                item.get("status") == "passed"
                and item.get("source_quote") == mapping.get("source_quote")
                and item.get("expected_visual_module") == mapping.get("expected_visual_module")
                and item.get("actual_visual_module") == mapping.get("expected_visual_module")
                and item.get("image_sha256") == expected_image_hashes.get(label)
                and len(str(item.get("actual_visual_evidence") or "").strip()) >= 12
                and len(str(item.get("assessment") or "").strip()) >= 12
            )
        for evidence_id, evidence in expected_evidence.items():
            item = reviews_by_evidence.get(evidence_id) or {}
            page_ok = page_ok and (
                item.get("status") == "passed"
                and item.get("text") == evidence.get("text")
                and item.get("source_quote") == evidence.get("source_quote")
                and item.get("parent_visual_module_id") == evidence.get("parent_visual_module_id")
                and item.get("expected_visual_module") == evidence.get("visual_module_id")
                and item.get("actual_visible_chinese") == evidence.get("text")
                and item.get("image_sha256") == expected_image_hashes.get(label)
                and len(str(item.get("actual_visual_relation") or "").strip()) >= 12
                and len(str(item.get("assessment") or "").strip()) >= 12
            )
        non_poster = page_review.get("non_poster_review") or {}
        non_poster_ok = (
            non_poster.get("status") == "passed"
            and non_poster.get("image_sha256") == expected_image_hashes.get(label)
            and len(str(non_poster.get("evidence") or "").strip()) >= 12
            and len(str(non_poster.get("assessment") or "").strip()) >= 12
        )
        quality_review = page_review.get("quality_baseline_review") or {}
        quality_ok = (
            quality_review.get("status") == "passed"
            and quality_review.get("image_sha256") == expected_image_hashes.get(label)
            and len(str(quality_review.get("evidence") or "").strip()) >= 12
            and len(str(quality_review.get("assessment") or "").strip()) >= 12
        )
        page_ok = page_ok and quality_ok
        if not page_ok:
            failed_pages.append(label)
        if not non_poster_ok:
            non_poster_failed_pages.append(label)

    duplicate_visuals_ok = not (review.get("cross_page_duplicate_visuals") or [])
    checks_payload = review.get("checks") or {}
    duplicate_visuals_ok = duplicate_visuals_ok and checks_payload.get("all_visible_chinese_source_traced") == "passed" and checks_payload.get("cross_page_visual_duplicate_check") == "passed"
    ok = subject_ok and duplicate_visuals_ok and not failed_pages and not non_poster_failed_pages
    checks.append({
        "layer": "semantic-review",
        "name": "post-render-keyword-visual-review",
        "status": "passed" if ok else "failed",
        "detail": "" if ok else "逐主卡与逐证据实际可见中文、对象关系、原文清单、跨页组合、非海报化判断或哈希绑定不完整",
    })
    if not ok:
        issues.append("成图后逐主卡和逐证据独立视觉复核未通过，不能仅凭 pages-spec 或 --human-approved 放行")
        if not subject_ok:
            failed_pages = sorted(set(failed_pages + expected_labels))
    return sorted(set(failed_pages)), sorted(set(non_poster_failed_pages))


def normalize_source_text(text: str) -> str:
    normalized = str(text or "")
    normalized = normalized.replace("**", "")
    normalized = "".join(normalized.split())
    return normalized.strip("，,。！？；;：:“”\"'（）()《》【】[] ")


def ensure_semantic_text_contract(
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str], list[str]]:
    missing_key_information: list[str] = []
    formula_omissions: list[str] = []
    transition_misuse: list[str] = []
    incomplete_phrases: list[str] = []
    semantic_priority_failed: list[str] = []
    visual_module_mismatch: list[str] = []
    visible_text_density_failed: list[str] = []
    weak_fragment_re = re.compile(
        r"(?:只要懂|沉迷于找|应该先|必须有明确的|才能实现真正|我总结了\d+个|"
        r"那我是应该先|还是去找|还是应该先|我就发现|而这些人都有|"
        r"其实很简单|原因很简单)$"
    )
    for item in page_items:
        label = f"page-{int(item.get('page_index', 0)):02d}"
        visible = [
            str(entry.get("text") or "")
            for entry in (item.get("source_text_ledger") or [])
            if str(entry.get("text") or "").strip()
        ]
        visible_normalized = [normalize_source_text(text) for text in visible]
        formulas = item.get("formula_items") or []
        discarded = [str(text) for text in (item.get("discarded_transition_quotes") or [])]
        keyword_mappings = item.get("keyword_visual_mappings") or []
        evidence_nodes = [node for mapping in keyword_mappings for node in (mapping.get("evidence_nodes") or [])]

        ledger_entries = item.get("source_text_ledger") or []
        key_ok = (
            2 <= len(keyword_mappings) <= 5
            and int(item.get("main_card_count") or 0) == len(keyword_mappings)
            and len(ledger_entries) == len(keyword_mappings) + len(evidence_nodes) + 1
            and all(1 <= len(mapping.get("evidence_nodes") or []) <= 3 for mapping in keyword_mappings)
            and all(
                any(
                    entry.get("kind") == "evidence-node"
                    and entry.get("text") == node.get("text")
                    and entry.get("visual_module_id") == node.get("visual_module_id")
                    and entry.get("parent_visual_module_id") == node.get("parent_visual_module_id")
                    for entry in ledger_entries
                )
                for node in evidence_nodes
            )
            and all(str(entry.get("source_quote") or "").strip() for entry in ledger_entries)
        )
        checks.append({"layer": "semantic-contract", "name": f"{label}-key-information", "status": "passed" if key_ok else "failed", "detail": "" if key_ok else "本页未形成标题、2–5 张主卡及每张 1–3 条可回溯证据"})
        if not key_ok:
            missing_key_information.append(label)
            issues.append(f"missing-key-information-rejected: {label}")

        formula_texts = [str(entry.get("text") or "") for entry in formulas]
        formula_ok = all(normalize_source_text(formula) in visible_normalized for formula in formula_texts)
        checks.append({"layer": "semantic-contract", "name": f"{label}-formula-preservation", "status": "passed" if formula_ok else "failed", "detail": "" if formula_ok else "公式未完整进入本页原文文字清单"})
        if not formula_ok:
            formula_omissions.append(label)
            issues.append(f"formula-omission-rejected: {label}")

        transition_ok = all(normalize_source_text(text) not in visible_normalized for text in discarded)
        checks.append({"layer": "semantic-contract", "name": f"{label}-transition-exclusion", "status": "passed" if transition_ok else "failed", "detail": "" if transition_ok else "过渡句进入可见文字"})
        if not transition_ok:
            transition_misuse.append(label)
            issues.append(f"transition-text-misused-rejected: {label}")

        semantic_visible = visible[1:]
        complete_ok = all(not weak_fragment_re.search(normalize_source_text(text)) for text in semantic_visible)
        checks.append({"layer": "semantic-contract", "name": f"{label}-semantic-completeness", "status": "passed" if complete_ok else "failed", "detail": "" if complete_ok else "存在被截断或无独立意义的片段"})
        if not complete_ok:
            incomplete_phrases.append(label)
            issues.append(f"incomplete-phrase-rejected: {label}")

        priorities = [int(mapping.get("priority") or 0) for mapping in keyword_mappings]
        priority_ok = bool(keyword_mappings) and priorities == list(range(1, len(keyword_mappings) + 1))
        checks.append({"layer": "semantic-contract", "name": f"{label}-semantic-priority", "status": "passed" if priority_ok else "failed", "detail": "" if priority_ok else "语义优先级为空或指向非可见文字"})
        if not priority_ok:
            semantic_priority_failed.append(label)
            issues.append(f"semantic-priority-rejected: {label}")

        ledger_by_module_id = {
            str(entry.get("visual_module_id") or ""): entry
            for entry in (item.get("source_text_ledger") or [])
            if str(entry.get("visual_module_id") or "").strip()
        }
        module_ok = bool(keyword_mappings) and all(
            str(mapping.get("visual_module_id") or "") in ledger_by_module_id
            and ledger_by_module_id[str(mapping.get("visual_module_id") or "")].get("text") == mapping.get("source_label")
            and ledger_by_module_id[str(mapping.get("visual_module_id") or "")].get("visual_objects") == mapping.get("visual_objects")
            and ledger_by_module_id[str(mapping.get("visual_module_id") or "")].get("action_or_relation") == mapping.get("action_or_relation")
            for mapping in keyword_mappings
        )
        checks.append({"layer": "semantic-contract", "name": f"{label}-visual-module-mapping", "status": "passed" if module_ok else "failed", "detail": "" if module_ok else "重点文字与视觉模块映射不一致"})
        if not module_ok:
            visual_module_mismatch.append(label)
            issues.append(f"visual-module-mismatch-rejected: {label}")
        density_required = bool(item.get("visible_text_density_required"))
        density_target = len(keyword_mappings) + len(evidence_nodes)
        density_actual = max(0, len(visible) - 1)
        density_ok = (
            not density_required
            or density_actual >= density_target
        )
        checks.append({
            "layer": "semantic-contract",
            "name": f"{label}-visible-text-density",
            "status": "passed" if density_ok else "failed",
            "detail": "" if density_ok else f"页面证据密度不足: actual={density_actual}, target={density_target}",
        })
        if not density_ok:
            visible_text_density_failed.append(label)
            issues.append(f"visible-text-density-rejected: {label}")
    return (
        missing_key_information,
        formula_omissions,
        transition_misuse,
        incomplete_phrases,
        semantic_priority_failed,
        visual_module_mismatch,
        visible_text_density_failed,
    )


def png_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    return width, height


def parse_hex_color(value: str) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        return None
    return tuple(int(text[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]


def reserved_zone_side_px(image_height: int) -> int:
    return max(1, round(image_height * RESERVED_ZONE_SIZE_CM[1] / PPT_PAGE_HEIGHT_CM))


def reserved_zone_has_intrusion(path: Path, background_color: str) -> tuple[bool, str]:
    expected = parse_hex_color(background_color)
    if expected is None:
        return False, f"无法解析背景色 {background_color}"
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        side = min(reserved_zone_side_px(height), width, height)
        crop = rgb.crop((0, height - side, side, height))
        pixels = list(crop.getdata())
    non_background = sum(1 for pixel in pixels if pixel != expected)
    ratio = non_background / max(1, len(pixels))
    return ratio > RESERVED_ZONE_MAX_NON_BACKGROUND_RATIO, (
        f"zone={side}px x {side}px expected_rgb={expected} mismatched_pixels={non_background} "
        f"mismatch_ratio={ratio:.6f} required_rgb_exact_match=true"
    )


def ensure_reserved_zone_contract(
    page_items: list[dict[str, Any]],
    cover_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
    output_dir: Path | None = None,
    audit_pixels: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    body_contract_failed: list[str] = []
    body_pixel_failed: list[str] = []
    cover_inheritance_failed: list[str] = []
    for item in page_items:
        page_index = int(item.get("page_index", 0))
        label = f"page-{page_index:02d}"
        zone = item.get("reserved_zone") or {}
        size = item.get("reserved_zone_size_cm")
        ratio = item.get("reserved_zone_side_ratio_of_height")
        contract_ok = (
            item.get("reserved_zone_enabled") is True
            and item.get("reserved_zone_scope") == "body-page-only"
            and size == RESERVED_ZONE_SIZE_CM
            and abs(float(ratio or 0) - RESERVED_ZONE_SIDE_RATIO_OF_HEIGHT) < 0.00001
            and isinstance(zone, dict)
            and zone.get("position") == "bottom-left"
            and zone.get("size_cm") == "3 x 3"
            and zone.get("fill_mode") == "pure-background-no-draw"
        )
        checks.append({
            "layer": "mechanical",
            "name": f"{label}-body-reserved-zone-contract",
            "status": "passed" if contract_ok else "failed",
            "detail": "" if contract_ok else "正文页必须声明 3cm x 3cm bottom-left body-page-only 禁绘区",
        })
        if not contract_ok:
            body_contract_failed.append(label)
            issues.append(f"body-reserved-zone-contract-rejected: {label} 正文页未满足 3cm 留白合同")
        if audit_pixels and output_dir is not None:
            image_path = output_dir / f"{label}.png"
            if image_path.is_file() and contract_ok:
                has_intrusion, detail = reserved_zone_has_intrusion(
                    image_path,
                    str(item.get("background_color") or ""),
                )
                checks.append({
                    "layer": "mechanical",
                    "name": f"{label}-reserved-zone-pixel-check",
                    "status": "failed" if has_intrusion else "passed",
                    "detail": detail,
                })
                if has_intrusion:
                    body_pixel_failed.append(label)
                    issues.append(f"reserved-zone-violation-rejected: {label} 左下角 3cm 检测区存在非背景元素")
    for item in cover_items:
        cover_type = str(item.get("cover_type") or "")
        contract_ok = (
            item.get("reserved_zone_enabled") is False
            and item.get("reserved_zone_scope") == "none"
            and item.get("reserved_zone") is None
            and not (item.get("reserved_zone_rules") or [])
        )
        checks.append({
            "layer": "mechanical",
            "name": f"{cover_type}-cover-reserved-zone-contract",
            "status": "passed" if contract_ok else "failed",
            "detail": "" if contract_ok else "封面不得继承正文页左下角禁绘区",
        })
        if not contract_ok:
            cover_inheritance_failed.append(cover_type)
            issues.append(f"cover-reserved-zone-inheritance-rejected: {cover_type} 封面错误继承正文留白合同")
    return body_contract_failed, body_pixel_failed, cover_inheritance_failed


def ensure_action_contract(items: list[dict[str, Any]], checks: list[dict[str, str]], issues: list[str]) -> None:
    for item in items:
        item_name = item.get("cover_type") or f"page-{int(item.get('page_index', 0)):02d}"
        missing = [field for field in ACTION_CONTRACT_FIELDS if field not in item]
        ok = not missing
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{item_name}-action-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else f"缺少字段: {', '.join(missing)}",
            }
        )
        if missing:
            issues.append(f"{item_name} 缺少动作合同字段: {', '.join(missing)}")
            continue
        if not item.get("role_action_family"):
            issues.append(f"{item_name} 缺少 role_action_family")
        if not item.get("role_expression_family"):
            issues.append(f"{item_name} 缺少 role_expression_family")
        if not item.get("allowed_role_framings"):
            issues.append(f"{item_name} allowed_role_framings 为空")


def ensure_single_role_contract(
    page_items: list[dict[str, Any]],
    cover_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> list[str]:
    violations: list[str] = []
    targets: list[tuple[str, dict[str, Any]]] = []
    if page_items:
        targets.append(("page-01", page_items[0]))
    for cover in cover_items:
        cover_type = str(cover.get("cover_type") or "")
        if cover_type in SINGLE_ROLE_TARGETS:
            targets.append((cover_type, cover))
    for label, item in targets:
        ok = bool(item.get("single_role_required")) and item.get("role_count_min") == 1 and item.get("role_count_max") == 1
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-single-role-contract",
                "status": "passed" if ok else "failed",
                "detail": "single-role-only" if ok else "single_role_required 或 role_count_min/max 不符",
            }
        )
        if not ok:
            violations.append(label)
            issues.append(f"{label} 未满足 single-role-only 合同")
    return violations


def ensure_support_label_contract(
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str], list[str], list[str], list[str], list[str], list[str]]:
    missing_support_labels: list[str] = []
    failed_anchor_contract: list[str] = []
    visible_text_source_failed: list[str] = []
    support_label_mismatch: list[str] = []
    cue_phrase_mismatch: list[str] = []
    deck_title_visible_pages: list[str] = []
    visible_text_repeat_failed: list[str] = []
    visible_text_overlap_failed: list[str] = []
    label_module_failed: list[str] = []
    micro_visual_pairing_failed: list[str] = []
    source_text_ledger_failed: list[str] = []
    for item in page_items:
        label = f"page-{int(item.get('page_index', 0)):02d}"
        source_title = str(item.get("source_title_full") or item.get("page_title") or "")
        page_body = str(item.get("page_body") or "")
        page_title = str(item.get("page_title") or "").strip()
        source_pool = normalize_source_text(f"{source_title}\n{page_body}")
        support_labels = item.get("support_labels") or []
        cue_phrases = item.get("cue_phrases") or []
        flow_labels = item.get("flow_labels") or []
        label_targets = item.get("label_anchor_targets") or []
        support_required = bool(item.get("support_labels_required"))
        source_rooted_required = bool(item.get("source_rooted_labels_required"))
        visible_text_mode = str(item.get("visible_text_source_mode") or "").strip()
        ledger_text_items = [
            str(entry.get("text") or "")
            for entry in (item.get("source_text_ledger") or [])
            if str(entry.get("text") or "").strip()
        ]
        visible_text_quotes = {
            str(entry.get("text") or ""): str(entry.get("source_quote") or "")
            for entry in (item.get("source_text_ledger") or [])
            if str(entry.get("text") or "").strip()
        }
        support_label_quotes = item.get("support_label_source_quotes") or {}
        cue_phrase_quotes = item.get("cue_phrase_source_quotes") or {}
        flow_label_quotes = item.get("flow_label_source_quotes") or {}
        visible_text_repeat_forbidden = bool(item.get("visible_text_repeat_forbidden"))
        visible_text_slot_dedup_required = bool(item.get("visible_text_slot_dedup_required"))
        visible_text_overlap_forbidden = bool(item.get("visible_text_overlap_forbidden"))
        text_slot_assignment = item.get("text_slot_assignment") or {}
        source_fragment_overlap_groups = item.get("source_fragment_overlap_groups") or []
        text_slot_conflict_resolutions = item.get("text_slot_conflict_resolutions") or []
        repeated_source_fragment_forbidden = bool(item.get("repeated_source_fragment_forbidden"))
        source_text_ledger = item.get("source_text_ledger") or []
        deck_title = str(item.get("deck_title") or "").strip()
        display_title = str(item.get("display_title") or "").strip()
        deck_title_visible_forbidden = bool(item.get("deck_title_visible_forbidden"))
        deck_title_context_only = bool(item.get("deck_title_context_only"))
        label_module_required = bool(item.get("label_module_required"))
        label_module_targets = item.get("label_module_targets") or []
        label_visual_pairing_required = bool(item.get("label_visual_pairing_required"))
        micro_visual_anchor_required = bool(item.get("micro_visual_anchor_required"))
        module_block_count_target = int(item.get("module_block_count_target") or 0)
        micro_visuals = item.get("supporting_micro_visuals") or []
        ok = bool(support_labels) if support_required else True
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-support-label-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else "support_labels 为空",
            }
        )
        if not ok:
            missing_support_labels.append(label)
            issues.append(f"{label} 缺少原文短标签 support_labels")
        anchor_ok = (not source_rooted_required) or (bool(label_targets) and bool(support_labels))
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-label-anchor-contract",
                "status": "passed" if anchor_ok else "failed",
                "detail": "" if anchor_ok else "缺少标签锚点目标或 support_labels",
            }
        )
        if not anchor_ok:
            failed_anchor_contract.append(label)
            issues.append(f"{label} 未满足标签锚点合同")

        source_mode_ok = visible_text_mode == "exact-source-only"
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-visible-text-source-mode",
                "status": "passed" if source_mode_ok else "failed",
                "detail": "" if source_mode_ok else f"visible_text_source_mode={visible_text_mode}",
            }
        )
        if not source_mode_ok:
            visible_text_source_failed.append(label)
            issues.append(f"{label} 未声明 exact-source-only 可见文字合同")

        visible_items_ok = True
        for text_item in ledger_text_items:
            quote = str(visible_text_quotes.get(text_item) or "")
            if not quote or normalize_source_text(quote) not in source_pool:
                visible_items_ok = False
                break
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-visible-text-source-contract",
                "status": "passed" if visible_items_ok else "failed",
                "detail": "" if visible_items_ok else "source_text_ledger 中的文字或出处无法回指原文",
            }
        )
        if not visible_items_ok:
            visible_text_source_failed.append(label)
            issues.append(f"{label} 存在无法回指原文的页面可见文字")

        repeated_quote_detected = False
        if visible_text_repeat_forbidden or visible_text_slot_dedup_required or repeated_source_fragment_forbidden:
            ledger_text_keys = [normalize_source_text(text) for text in ledger_text_items[1:]]
            repeated_quote_detected = len(ledger_text_keys) != len(set(ledger_text_keys))
        repeat_ok = not repeated_quote_detected
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-visible-text-repeat-contract",
                "status": "passed" if repeat_ok else "failed",
                "detail": "" if repeat_ok else "同页可见文字槽位存在重复原文片段",
            }
        )
        if not repeat_ok:
            visible_text_repeat_failed.append(label)
            issues.append(f"{label} 同页可见文字重复引用同一原文片段")

        overlap_ok = True
        if visible_text_overlap_forbidden:
            ledger_text_keys = [normalize_source_text(text) for text in ledger_text_items[1:]]
            overlap_ok = not any(
                left != right
                and min(len(left), len(right)) >= 4
                and (left in right or right in left)
                for index, left in enumerate(ledger_text_keys)
                for right in ledger_text_keys[index + 1:]
            )
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-visible-text-overlap-contract",
                "status": "passed" if overlap_ok else "failed",
                "detail": "" if overlap_ok else "存在同源截断变体或包含关系冲突",
            }
        )
        if not overlap_ok:
            visible_text_overlap_failed.append(label)
            issues.append(f"{label} 存在同源截断变体重复")

        support_quote_ok = True
        for text_item in support_labels:
            quote = str(support_label_quotes.get(text_item) or "")
            if not quote or normalize_source_text(quote) not in source_pool or normalize_source_text(text_item) not in normalize_source_text(quote):
                support_quote_ok = False
                break
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-support-label-source-contract",
                "status": "passed" if support_quote_ok else "failed",
                "detail": "" if support_quote_ok else "support_labels 或 support_label_source_quotes 不能直接回指原文",
            }
        )
        if not support_quote_ok:
            support_label_mismatch.append(label)
            issues.append(f"{label} support_labels 不是当前页原文直引")

        cue_quote_ok = True
        for text_item in cue_phrases + flow_labels:
            quote_map = cue_phrase_quotes if text_item in cue_phrases else flow_label_quotes
            quote = str(quote_map.get(text_item) or "")
            if not quote or normalize_source_text(quote) not in source_pool or normalize_source_text(text_item) not in normalize_source_text(quote):
                cue_quote_ok = False
                break
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-cue-flow-source-contract",
                "status": "passed" if cue_quote_ok else "failed",
                "detail": "" if cue_quote_ok else "cue_phrases / flow_labels 不能直接回指原文",
            }
        )
        if not cue_quote_ok:
            cue_phrase_mismatch.append(label)
            issues.append(f"{label} cue_phrases 或 flow_labels 不是当前页原文直引")

        display_matches_explicit_page_title = bool(page_title) and normalize_source_text(display_title) == normalize_source_text(page_title)
        deck_title_ok = deck_title_context_only and deck_title_visible_forbidden and (
            not deck_title
            or normalize_source_text(display_title) != normalize_source_text(deck_title)
            or display_matches_explicit_page_title
        )
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-deck-title-visibility-contract",
                "status": "passed" if deck_title_ok else "failed",
                "detail": "" if deck_title_ok else "正文页仍允许或仍使用整篇选题标题",
            }
        )
        if not deck_title_ok:
            deck_title_visible_pages.append(label)
            issues.append(f"deck-title-visible-rejected: {label} 正文页出现整篇选题标题合同冲突")
        ledger_ok = bool(source_text_ledger) and all(
            str(entry.get("text") or "").strip()
            and str(entry.get("source_quote") or "").strip()
            and normalize_source_text(str(entry.get("source_quote") or "")) in source_pool
            and normalize_source_text(str(entry.get("text") or "")) in normalize_source_text(str(entry.get("source_quote") or ""))
            and str(entry.get("ledger_id") or "").strip()
            for entry in source_text_ledger
        )
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-source-text-ledger-contract",
                "status": "passed" if ledger_ok else "failed",
                "detail": "" if ledger_ok else "原文文字清单为空、缺少出处，或文字不能直接回指当前页原文",
            }
        )
        if not ledger_ok:
            source_text_ledger_failed.append(label)
            issues.append(f"{label} 未满足本页原文文字清单合同")
        label_module_ok = True
        if label_module_required:
            label_module_ok = bool(label_module_targets) and module_block_count_target >= 1 and bool(item.get("visual_module_assignments"))
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-label-module-contract",
                "status": "passed" if label_module_ok else "failed",
                "detail": "" if label_module_ok else "缺少标签模块目标、模块数量合同或可锚定标签",
            }
        )
        if not label_module_ok:
            label_module_failed.append(label)
            issues.append(f"{label} 未满足标签模块化合同")

        micro_visual_pairing_ok = True
        if label_visual_pairing_required or micro_visual_anchor_required:
            micro_visual_pairing_ok = bool(micro_visuals) and bool(label_module_targets)
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-micro-visual-pairing-contract",
                "status": "passed" if micro_visual_pairing_ok else "failed",
                "detail": "" if micro_visual_pairing_ok else "缺少 support_labels/flow_labels 与 supporting_micro_visuals 的配对合同",
            }
        )
        if not micro_visual_pairing_ok:
            micro_visual_pairing_failed.append(label)
            issues.append(f"{label} 缺少标签与 supporting_micro_visuals 的模块配对")
    return (
        missing_support_labels,
        failed_anchor_contract,
        sorted(set(visible_text_source_failed)),
        support_label_mismatch,
        cue_phrase_mismatch,
        deck_title_visible_pages,
        visible_text_repeat_failed,
        visible_text_overlap_failed,
        label_module_failed,
        micro_visual_pairing_failed,
        source_text_ledger_failed,
    )


def ensure_explicit_heading_title_contract(
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str]]:
    explicit_heading_failed: list[str] = []
    summary_exception_failed: list[str] = []
    for item in page_items:
        label = f"page-{int(item.get('page_index', 0)):02d}"
        page_title = str(item.get("page_title") or "").strip()
        title_text = str(item.get("title_text") or "").strip()
        display_title = str(item.get("display_title") or "").strip()
        page_body = str(item.get("page_body") or "").strip()
        title_strategy = str(item.get("title_strategy") or "").strip()
        display_title_mode = str(item.get("display_title_mode") or "").strip()
        explicit_required = bool(item.get("explicit_heading_title_required"))
        heading_level = int(item.get("explicit_heading_source_level") or 0)
        summary_allowed = bool(item.get("summary_title_exception_allowed"))
        summary_quote = str(item.get("summary_title_exception_source_quote") or "").strip()
        source_pool = normalize_source_text(f"{page_title}\n{page_body}")

        if explicit_required and not summary_allowed:
            ok = (
                heading_level in {1, 2, 3}
                and page_title
                and title_text == page_title
                and display_title == page_title
                and display_title_mode == "exact"
                and title_strategy == "explicit-heading-title"
            )
            checks.append(
                {
                    "layer": "mechanical",
                    "name": f"{label}-explicit-heading-title-contract",
                    "status": "passed" if ok else "failed",
                    "detail": "" if ok else "显式标题页主标题未直取对应 # / ## / ### 标题",
                }
            )
            if not ok:
                explicit_heading_failed.append(label)
                issues.append(f"explicit-heading-title-rejected: {label} 主标题未直取当前页显式标题")
            continue

        if summary_allowed:
            exact_mode = (
                page_title
                and title_text == page_title
                and display_title == page_title
                and display_title_mode == "exact"
                and title_strategy == "explicit-heading-title"
            )
            quoted_mode = (
                bool(display_title)
                and title_strategy == "summary-body-source-title"
                and display_title_mode == "exact"
                and bool(summary_quote)
                and normalize_source_text(summary_quote) in source_pool
                and normalize_source_text(display_title) in normalize_source_text(summary_quote)
            )
            ok = exact_mode or quoted_mode
            checks.append(
                {
                    "layer": "mechanical",
                    "name": f"{label}-summary-title-exception-contract",
                    "status": "passed" if ok else "failed",
                    "detail": "" if ok else "总结页标题例外未回指当前页原文或错误改写标题",
                }
            )
            if not ok:
                summary_exception_failed.append(label)
                issues.append(f"summary-title-exception-rejected: {label} 总结页标题例外未满足原文回指合同")
    return explicit_heading_failed, summary_exception_failed


def ensure_micro_visual_style_contract(
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    style_drift_pages: list[str] = []
    bare_line_icon_pages: list[str] = []
    ui_icon_style_pages: list[str] = []
    container_missing_pages: list[str] = []
    for item in page_items:
        label = f"page-{int(item.get('page_index', 0)):02d}"
        style = str(item.get("micro_visual_style") or "").strip()
        components = set(str(value) for value in (item.get("micro_visual_style_components") or []))
        style_ok = (
            style == MICRO_VISUAL_STYLE
            and bool(item.get("micro_visual_style_required"))
            and bool(item.get("micro_visual_style_consistency_required"))
        )
        container_ok = bool(item.get("micro_visual_container_required")) and MICRO_VISUAL_STYLE_COMPONENTS.issubset(components)
        bare_line_ok = bool(item.get("bare_line_icon_forbidden"))
        ui_style_ok = (
            bool(item.get("ui_flat_icon_forbidden"))
            and bool(item.get("sticker_style_forbidden"))
            and bool(item.get("realistic_micro_illustration_forbidden"))
            and bool(item.get("three_d_icon_forbidden"))
        )
        checks.extend(
            [
                {
                    "layer": "mechanical",
                    "name": f"{label}-micro-visual-style-contract",
                    "status": "passed" if style_ok else "failed",
                    "detail": "" if style_ok else f"micro_visual_style 必须为 {MICRO_VISUAL_STYLE} 且声明整套一致",
                },
                {
                    "layer": "mechanical",
                    "name": f"{label}-micro-visual-container-contract",
                    "status": "passed" if container_ok else "failed",
                    "detail": "" if container_ok else "缺少卡片/节点容器、手绘图标/小场景、原文短标签、少量扁平色块四件套",
                },
                {
                    "layer": "mechanical",
                    "name": f"{label}-bare-line-icon-contract",
                    "status": "passed" if bare_line_ok else "failed",
                    "detail": "" if bare_line_ok else "未声明禁止裸线条图标散落",
                },
                {
                    "layer": "mechanical",
                    "name": f"{label}-ui-icon-style-contract",
                    "status": "passed" if ui_style_ok else "failed",
                    "detail": "" if ui_style_ok else "未声明禁止 UI 扁平图标、贴纸风、写实小插画或 3D 图标",
                },
            ]
        )
        if not style_ok:
            style_drift_pages.append(label)
            issues.append(f"micro-visual-style-drift-rejected: {label} 未锁定手绘卡片式图标模块风格")
        if not bare_line_ok:
            bare_line_icon_pages.append(label)
            issues.append(f"bare-line-icon-violation-rejected: {label} 未禁止裸线条图标散落")
        if not ui_style_ok:
            ui_icon_style_pages.append(label)
            issues.append(f"ui-icon-style-violation-rejected: {label} 未禁止 UI/贴纸/写实/3D 小模块风格")
        if not container_ok:
            container_missing_pages.append(label)
            issues.append(f"micro-visual-container-missing-rejected: {label} 小模块缺少统一容器四件套合同")
    return style_drift_pages, bare_line_icon_pages, ui_icon_style_pages, container_missing_pages


def ensure_multi_role_contract(
    page_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> list[str]:
    violations: list[str] = []
    for item in page_items:
        label = f"page-{int(item.get('page_index', 0)):02d}"
        target = int(item.get("role_count_target") or 0)
        required = bool(item.get("multi_role_required"))
        trigger = str(item.get("multi_role_trigger_type") or "").strip()
        distribution = str(item.get("role_distribution_brief") or "").strip()
        slots = item.get("role_slot_assignments") or []
        if not required:
            continue
        ok = target >= 2 and item.get("role_count_min") == target and item.get("role_count_max") == target and bool(trigger) and bool(distribution) and len(slots) >= target
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-multi-role-contract",
                "status": "passed" if ok else "failed",
                "detail": "" if ok else "multi_role_required 页缺少目标人数、触发类型或结构分工",
            }
        )
        if not ok:
            violations.append(label)
            issues.append(f"{label} 未满足多人物结构触发合同")
    return violations


def ensure_identity_contract(
    items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    missing_anchor_pages: list[str] = []
    face_drift_pages: list[str] = []
    hair_drift_pages: list[str] = []
    style_drift_pages: list[str] = []
    for item in items:
        label = str(item.get("cover_type") or f"page-{int(item.get('page_index', 0)):02d}")
        anchor_required = bool(item.get("identity_anchor_required"))
        face_anchor_attached_required = bool(item.get("face_anchor_attached_required"))
        anchor_image = str(item.get("role_face_anchor_image") or "").strip()
        identity_drift_forbidden = bool(item.get("identity_drift_forbidden"))
        hair_variant_forbidden = bool(item.get("hair_variant_forbidden"))
        hair_mode = str(item.get("hair_expression_mode") or "").strip()

        anchor_ok = anchor_required and face_anchor_attached_required and bool(anchor_image)
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-identity-anchor-contract",
                "status": "passed" if anchor_ok else "failed",
                "detail": "" if anchor_ok else "identity anchor required / face anchor attached required / role_face_anchor_image 不完整",
            }
        )
        if not anchor_ok:
            missing_anchor_pages.append(label)
            issues.append(f"identity-anchor-missing-rejected: {label} 未满足主脸锚点硬门禁")

        drift_ok = identity_drift_forbidden
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-identity-drift-contract",
                "status": "passed" if drift_ok else "failed",
                "detail": "" if drift_ok else "identity_drift_forbidden != true",
            }
        )
        if not drift_ok:
            face_drift_pages.append(label)
            style_drift_pages.append(label)
            issues.append(f"identity-face-drift-rejected: {label} 未声明人物身份漂移禁止")
            issues.append(f"identity-style-drift-rejected: {label} 未声明人物画风漂移禁止")

        hair_ok = hair_variant_forbidden and hair_mode == "slicked-back-side-part"
        checks.append(
            {
                "layer": "mechanical",
                "name": f"{label}-hair-lock-contract",
                "status": "passed" if hair_ok else "failed",
                "detail": "" if hair_ok else f"hair_variant_forbidden != true 或 hair_expression_mode={hair_mode}",
            }
        )
        if not hair_ok:
            hair_drift_pages.append(label)
            issues.append(f"identity-hair-drift-rejected: {label} 发型未锁死到主脸锚点主发型")
    return missing_anchor_pages, face_drift_pages, hair_drift_pages, style_drift_pages


def collect_render_signature_repeat_violations(
    page_items: list[dict[str, Any]],
    cover_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> list[str]:
    repeated: list[str] = []
    seen_signatures: dict[str, str] = {}
    items = page_items + cover_items
    for item in items:
        label = str(item.get("cover_type") or f"page-{int(item.get('page_index', 0)):02d}")
        render_signature = str(item.get("render_signature") or "").strip()
        if not render_signature:
            continue
        previous = seen_signatures.get(render_signature)
        if previous:
            repeated.extend([previous, label])
        else:
            seen_signatures[render_signature] = label
    repeated = sorted(set(repeated))
    ok = not repeated
    checks.append(
        {
            "layer": "mechanical",
            "name": "global-render-signature-uniqueness-contract",
            "status": "passed" if ok else "failed",
            "detail": "" if ok else ", ".join(repeated),
        }
    )
    if repeated:
        issues.append(f"render-signature-repeat-rejected: 全文最终演法重复: {', '.join(repeated)}")
    return repeated


def collect_mic_pose_violations(
    page_items: list[dict[str, Any]],
    cover_items: list[dict[str, Any]],
    checks: list[dict[str, str]],
    issues: list[str],
) -> list[str]:
    mic_labels: list[str] = []
    for item in page_items + cover_items:
        label = str(item.get("cover_type") or f"page-{int(item.get('page_index', 0)):02d}")
        prop_signature = str(item.get("prop_signature") or "").strip().lower()
        action_intent = str(item.get("role_action_intent") or "").strip().lower()
        prop_intent = str(item.get("role_prop_intent") or "").strip().lower()
        if prop_signature in MIC_PROP_SIGNATURES or prop_intent == "mic" or "mic" in action_intent:
            mic_labels.append(label)
    violations = mic_labels[1:]
    ok = len(mic_labels) <= 1
    checks.append(
        {
            "layer": "mechanical",
            "name": "mic-pose-limit-contract",
            "status": "passed" if ok else "failed",
            "detail": "" if ok else ", ".join(mic_labels),
        }
    )
    if violations:
        issues.append(f"mic-pose-overuse-rejected: 拿麦讲话超次数: {', '.join(mic_labels)}")
    return violations


def audit(output: Path, human_approved: bool = False) -> dict[str, Any]:
    checks: list[dict[str, str]] = []
    issues: list[str] = []
    output = output.resolve()
    pages = sorted(output.glob("page-*.png")) if output.is_dir() else []
    for required in ("pages-spec.json", "codex-handoff.json", "codex-workflow.txt"):
        contract_path = resolve_archive_contract_file(output, required)
        ok = contract_path.is_file()
        checks.append({"layer": "mechanical", "name": required, "status": "passed" if ok else "failed", "detail": ""})
        if not ok:
            issues.append(f"缺少{required}")

    handoff: dict[str, Any] = {}
    page_items: list[dict[str, Any]] = []
    cover_items: list[dict[str, Any]] = []
    handoff_path = resolve_archive_contract_file(output, "codex-handoff.json")
    if handoff_path.is_file():
        handoff = load_json(handoff_path)
        page_items = handoff.get("pages") or []
        cover_items = handoff.get("covers") or []
        pages_spec_path = resolve_archive_contract_file(output, "pages-spec.json")
        pages_spec = load_json(pages_spec_path) if pages_spec_path.is_file() else {}
        version_ok = (
            handoff.get("contract_version") == IP_VISUAL_CONTRACT_VERSION
            and pages_spec.get("contract_version") == IP_VISUAL_CONTRACT_VERSION
        )
        checks.append({
            "layer": "mechanical",
            "name": "generate-ip-ppt-contract-version",
            "status": "passed" if version_ok else "failed",
            "detail": "" if version_ok else "新任务成图审核只接受 contract_version=4.1.0",
        })
        if not version_ok:
            issues.append("成图审核拒绝非 4.1.0 的新任务工作包")
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
            missing_key_information_pages,
            formula_omission_pages,
            transition_text_misused_pages,
            incomplete_phrase_pages,
            semantic_priority_failed_pages,
            visual_module_mismatch_pages,
            visible_text_density_failed_pages,
        ) = ensure_semantic_text_contract(page_items, checks, issues)
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
        role_count_violations = ensure_single_role_contract(page_items, cover_items, checks, issues)
        body_reserved_zone_contract_failed_pages, reserved_zone_violation_pages, cover_reserved_zone_inheritance_failed_covers = ensure_reserved_zone_contract(
            page_items, cover_items, checks, issues, output_dir=output, audit_pixels=True
        )
        multi_role_contract_failed = ensure_multi_role_contract(page_items, checks, issues)
        (
            missing_identity_anchor_pages,
            face_drift_pages,
            hair_drift_pages,
            style_drift_pages,
        ) = ensure_identity_contract(page_items + cover_items, checks, issues)
    else:
        repeated_pages = []
        mic_pose_violations = []
        missing_support_labels = []
        failed_label_anchor_contract = []
        visible_text_source_failed = []
        support_label_source_mismatch = []
        cue_phrase_source_mismatch = []
        deck_title_visible_pages = []
        visible_text_repeat_failed = []
        visible_text_overlap_failed = []
        label_module_contract_failed = []
        micro_visual_pairing_failed = []
        source_text_ledger_failed = []
        explicit_heading_title_failed_pages = []
        summary_title_exception_failed_pages = []
        role_count_violations = []
        body_reserved_zone_contract_failed_pages = []
        reserved_zone_violation_pages = []
        cover_reserved_zone_inheritance_failed_covers = []
        multi_role_contract_failed = []
        missing_identity_anchor_pages = []
        face_drift_pages = []
        hair_drift_pages = []
        style_drift_pages = []
        missing_key_information_pages = []
        formula_omission_pages = []
        transition_text_misused_pages = []
        incomplete_phrase_pages = []
        semantic_priority_failed_pages = []
        visual_module_mismatch_pages = []
        visible_text_density_failed_pages = []
        micro_visual_style_drift_pages = []
        bare_line_icon_violation_pages = []
        ui_icon_style_violation_pages = []
        micro_visual_container_missing_pages = []

    if not pages:
        issues.append("没有page-*.png页面")
    for page in pages:
        try:
            width, height = png_size(page)
            ok = width >= 720 and height >= 720
            checks.append({"layer": "mechanical", "name": page.name, "status": "passed" if ok else "failed", "detail": f"{width}x{height}"})
            if not ok:
                issues.append(f"页面尺寸过小：{page.name} {width}x{height}")
        except Exception as exc:
            issues.append(f"PNG损坏：{page.name}: {exc}")

    for cover in cover_items:
        cover_type = str(cover.get("cover_type") or "")
        filename = f"{cover_type}.png"
        path = output / filename
        ok = path.is_file()
        checks.append({"layer": "mechanical", "name": filename, "status": "passed" if ok else "failed", "detail": ""})
        if not ok:
            issues.append(f"缺少{filename}")
            continue
        try:
            width, height = png_size(path)
            size_ok = width >= 720 and height >= 720
            checks.append({"layer": "mechanical", "name": f"{filename}-size", "status": "passed" if size_ok else "failed", "detail": f"{width}x{height}"})
            if not size_ok:
                issues.append(f"封面尺寸过小：{filename} {width}x{height}")
        except Exception as exc:
            issues.append(f"PNG损坏：{filename}: {exc}")

    keyword_visual_review_failed_pages, non_poster_review_failed_pages = ensure_post_render_keyword_visual_review(
        output, handoff, page_items, checks, issues
    )

    visual_items = [
        "文字截断与错别字",
        "角色一致性",
        "布局与对比度",
        "分页与步骤不混页",
        "显式标题页主标题是否与对应 # / ## / ### 一致",
        "非最后页是否错误使用了正文句子当主标题",
        "最后总结页若走例外是否直接回指该页正文原句",
        "动作与文案语义匹配",
        "表情是否服从该页文案语义",
        "道具是否服从该页文案语义",
        "全文最终演法是否重复",
        "拿麦讲话超次数",
        "主脸锚点是否真实挂入",
        "人物身份是否绝对稳定",
        "发型是否锁死到主脸锚点主发型",
        "封面单人物",
        "正文首图单人物",
        "原文短标签是否齐全",
        "主要结构块是否被原文标签锚住",
        "页面可见文字是否存在重复片段",
        "页面可见文字是否存在同源截断变体重复",
        "标签是否以模块化小图或节点块呈现",
        "supporting micro visuals 是否和标签形成配对",
        "小模块是否统一为手绘卡片式图标模块",
        "线条图标是否都进入卡片/节点容器而非裸露散落",
        "是否混入 UI 扁平图标、贴纸、写实小插画或 3D 图标",
        "整套小模块边框、纹理、色块和图标复杂度是否一致",
        "页面可见文字是否直接回指原文",
        "页面可见中文是否逐条回指本页原文文字清单",
        "标题栏和每个文字卡是否均已填入文字且无空白占位",
        "是否达到合格案例的图文一体、信息密度和手绘模块完成态",
        "正文页是否误显整篇选题标题",
        "多人物页是否按结构分工落位",
        "景别是否服从页语义",
        "是否遗漏本页最高价值信息",
        "公式、定义和关键结论是否完整保留",
        "可见文字是否具有独立完整含义",
        "是否误用过渡句或口语填充",
        "视觉模块是否真正解释对应重点",
        "标签是否避免机械套用同一种红框",
        "正文页左下角 3cm x 3cm 是否没有人物、文字、图标、箭头、线条或场景元素",
        "封面是否没有错误继承正文左下角禁绘区",
    ]
    review_bound = not keyword_visual_review_failed_pages and not non_poster_review_failed_pages
    visual_status = "passed" if human_approved and review_bound else "needs-agent"
    checks.extend(
        {
            "layer": "visual",
            "name": item,
            "status": visual_status,
            "detail": (
                "需人工或视觉模型逐页确认并写入哈希绑定的正式 semantic review"
                if not human_approved or not review_bound else "独立人工复核与当前图片哈希已绑定"
            ),
        }
        for item in visual_items
    )

    if issues:
        status = "rejected"
    elif human_approved:
        status = "approved"
    else:
        status = "needs-agent"
    return {
        "schema": "visual-output-audit-result-v4.1",
        "auditor": "xiaoshen",
        "auditor_version": "4.1.0",
        "audit_contract": "ip-visual-output-v5",
        "subject": str(output),
        "status": status,
        "page_count": len(pages),
        "checks": checks,
        "issues": issues,
        "action_match_failed_pages": [],
        "semantic_action_mismatch_pages": [],
        "action_repeat_pages": repeated_pages,
        "render_signature_repeat_pages": repeated_pages,
        "mic_pose_violation_pages": mic_pose_violations,
        "identity_anchor_missing_pages": missing_identity_anchor_pages,
        "face_identity_drift_pages": face_drift_pages,
        "hair_identity_drift_pages": hair_drift_pages,
        "style_identity_drift_pages": style_drift_pages,
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
        "explicit_heading_title_contract_failed_pages": explicit_heading_title_failed_pages,
        "summary_title_exception_failed_pages": summary_title_exception_failed_pages,
        "role_count_violation_pages": role_count_violations,
        "body_reserved_zone_contract_failed_pages": body_reserved_zone_contract_failed_pages,
        "reserved_zone_violation_pages": reserved_zone_violation_pages,
        "cover_reserved_zone_inheritance_failed_covers": cover_reserved_zone_inheritance_failed_covers,
        "multi_role_contract_failed_pages": multi_role_contract_failed,
        "missing_key_information_pages": missing_key_information_pages,
        "formula_omission_pages": formula_omission_pages,
        "transition_text_misused_pages": transition_text_misused_pages,
        "incomplete_phrase_pages": incomplete_phrase_pages,
        "semantic_priority_failed_pages": semantic_priority_failed_pages,
        "visual_module_mismatch_pages": visual_module_mismatch_pages,
        "keyword_visual_review_failed_pages": keyword_visual_review_failed_pages,
        "non_poster_review_failed_pages": non_poster_review_failed_pages,
        "visible_text_density_failed_pages": visible_text_density_failed_pages,
        "micro_visual_style_drift_pages": micro_visual_style_drift_pages,
        "bare_line_icon_violation_pages": bare_line_icon_violation_pages,
        "ui_icon_style_violation_pages": ui_icon_style_violation_pages,
        "micro_visual_container_missing_pages": micro_visual_container_missing_pages,
        "framing_violation_pages": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="小审：IP视觉PPT动作合同与视觉审核")
    parser.add_argument("output_dir")
    parser.add_argument("--receipt")
    parser.add_argument("--human-approved", action="store_true", help="仅在逐页人工确认后使用")
    parser.add_argument("--create-review-template", action="store_true", help="仅建立绑定最终 PNG 哈希的小审成图复核表，不会自动批准")
    args = parser.parse_args()
    if args.create_review_template:
        path = create_post_render_review_scaffold(Path(args.output_dir))
        print(json.dumps({"status": "needs-review", "review_template": str(path)}, ensure_ascii=False, indent=2))
        return 0
    receipt = audit(Path(args.output_dir), args.human_approved)
    if args.receipt:
        target = Path(args.receipt).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 1 if receipt["status"] == "rejected" else (3 if receipt["status"].startswith("needs-") else 0)


if __name__ == "__main__":
    raise SystemExit(main())
