"""V19 FNN coverage with a hash-bound writing-expression contract V3."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from structure_core import build_candidate as build_candidate_core, build_handoff as build_handoff_core, validate as validate_core, normalized, section_text

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workflow.writing_contract import active_contract, guidance_snapshot, mechanical_checks_for, resolve_contract, rule_ids, validate_guidance_snapshot


FINGERPRINT_FIELDS = ("reader_entry", "reasoning_path", "delivery_form")
MECHANICAL_PATTERNS = (
    r"(?:提升|提高).{0,6}效率$", r"(?:形成|打造|构建).{0,6}闭环$",
    r"(?:构建|打造).{0,6}体系$", r"(?:沉淀|输出).{0,6}方法论$",
    r"(?:提供|创造).{0,6}价值$", r"(?:全链路|赋能|可复制)$",
)
CONCRETE_MARKERS = re.compile(r"\d|我|你|他|她|当|把|先|再|如果|不是|而是|因为|所以|今天|昨天|这周|打开|写|做|选|删|发|看|问|记录|审核|比较")


def writing_contract_binding() -> dict[str, str]:
    value = active_contract()
    return {key: value[key] for key in ("contract_id", "version", "sha256")}


def writing_contract_rule_ids(binding: dict[str, str], scope: str = "structure") -> list[str]:
    return rule_ids(binding, scope)


def build_handoff_v19(*, topic: str, benchmark_id: str, topic_table_binding: dict | None = None) -> dict:
    payload = build_handoff_core(topic=topic, benchmark_id=benchmark_id, topic_table_binding=topic_table_binding)
    payload["writing_contract"] = writing_contract_binding()
    payload["writing_contract_rule_ids"] = writing_contract_rule_ids(payload["writing_contract"])
    payload["writing_contract_guidance_snapshot"] = guidance_snapshot(payload["writing_contract"], "structure")
    payload["structure_generation_rule"] += " 每张非空小框架卡必须附 source_coverage（原小框架摘录和保留说明）；结构三还必须逐卡附 source_evidence。"
    return payload


def _authored_cards(authoring: dict, structure: str, framework_id: str) -> list[dict]:
    plan = (authoring.get("structures") or {}).get(structure)
    rows = plan.get("core_frameworks") if isinstance(plan, dict) and isinstance(plan.get("core_frameworks"), list) else []
    row = next((item for item in rows if isinstance(item, dict) and item.get("core_framework_id") == framework_id), {})
    return row.get("small_framework_cards") if isinstance(row.get("small_framework_cards"), list) else []


def _coverage(card: dict, source: dict, ident: str) -> dict:
    value = card.get("source_coverage") if isinstance(card.get("source_coverage"), dict) else {}
    excerpt = str(value.get("source_content_excerpt") or "").strip()
    explanation = str(value.get("preservation_explanation") or "").strip()
    if not excerpt or normalized(excerpt) not in normalized(source.get("source_content")):
        raise ValueError(f"{ident} 缺少可定位的原小框架内容摘录")
    if len(explanation) < 12:
        raise ValueError(f"{ident} 缺少具体的原要点保留说明")
    return {"source_content_excerpt": excerpt, "preservation_explanation": explanation}


def _source_evidence(card: dict, row: dict, ident: str) -> dict:
    proof = card.get("source_evidence") if isinstance(card.get("source_evidence"), dict) else {}
    required = ("source_index", "source_section", "excerpt", "evidence_role", "support_explanation")
    if any(not str(proof.get(key) or "").strip() for key in required if key != "source_index") or not isinstance(proof.get("source_index"), int):
        raise ValueError(f"{ident} 缺少逐卡正式来源证据")
    sources = row.get("processing_sources") if isinstance(row.get("processing_sources"), list) else []
    index = proof["source_index"]
    if not 0 <= index < len(sources) or not isinstance(sources[index], dict):
        raise ValueError(f"{ident} 来源证据未绑定 processing_sources")
    source = sources[index]
    if proof.get("source_section") != source.get("section"):
        raise ValueError(f"{ident} 来源证据章节与出处不一致")
    path = Path(__file__).resolve().parents[3] / str(source.get("path") or "")
    if not path.is_file() or normalized(proof["excerpt"]) not in normalized(section_text(path, str(source.get("section") or ""))):
        raise ValueError(f"{ident} 来源证据不在正式出处章节")
    return {key: proof[key] for key in required}


def _plain_language_errors(content: str, ident: str, binding: dict[str, str]) -> list[str]:
    text = content.strip()
    errors: list[str] = []
    if len(text) < 12:
        errors.append(f"{ident} 内容过短，无法形成可讲出口的完整意思")
    for check in mechanical_checks_for(binding, "structure"):
        if check.get("kind") == "forbidden-phrases" and any(str(value) in text for value in check.get("phrases", [])):
            errors.append(f"{ident}：{check['message']}")
        if check.get("kind") == "isolated-corporate-cliche" and any(re.search(str(pattern), text) for pattern in check.get("patterns", [])):
            errors.append(f"{ident}：{check['message']}")
    if not CONCRETE_MARKERS.search(text):
        errors.append(f"{ident} 未给出对象、场景、动作、结果或判断条件")
    return errors


def build_candidate_v19(handoff_path: Path, authoring_path: Path, output: Path) -> None:
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff.get("schema") != "copy-structure-handoff-v19":
        raise ValueError("仅接受 copy-structure-handoff-v19")
    if handoff.get("writing_contract") != writing_contract_binding():
        raise ValueError("V19 新结构必须绑定当前写作文案表达合同")
    if handoff.get("writing_contract_rule_ids") != writing_contract_rule_ids(handoff["writing_contract"]):
        raise ValueError("V19 新结构必须加载当前写作文案表达合同规则索引")
    build_candidate_core(handoff_path, authoring_path, output)
    candidate = json.loads(output.read_text(encoding="utf-8")); authoring = json.loads(authoring_path.read_text(encoding="utf-8"))
    source_by_id = {str(item.get("small_framework_id") or ""): item for item in handoff.get("small_framework_context", []) if isinstance(item, dict)}
    for structure, plan in candidate.get("structures", {}).items():
        rows = plan.get("core_frameworks") if isinstance(plan, dict) else []
        for row in rows if isinstance(rows, list) else []:
            authored = _authored_cards(authoring, structure, str(row.get("core_framework_id") or ""))
            authored_by_id = {str(item.get("small_framework_id") or ""): item for item in authored if isinstance(item, dict)}
            for card in row.get("small_framework_cards", []) if isinstance(row.get("small_framework_cards"), list) else []:
                card_id = str(card.get("small_framework_id") or ""); ident = f"{structure}/{row.get('core_framework_id')}/{card_id}"
                if structure == "structure_four":
                    continue
                content = str(card.get("content") or "").strip()
                if not content and structure == "structure_three":
                    continue
                written, source = authored_by_id.get(card_id, {}), source_by_id.get(card_id, {})
                if not written or not source:
                    raise ValueError(f"{ident} 缺少可追溯的作者输入")
                card["source_coverage"] = _coverage(written, source, ident)
                if structure == "structure_three":
                    card["source_evidence"] = _source_evidence(written, row, ident)
    candidate["schema"] = "copy-structure-v19"; candidate["writing_contract"] = handoff["writing_contract"]
    candidate["writing_contract_rule_ids"] = handoff["writing_contract_rule_ids"]
    candidate["writing_contract_guidance_snapshot"] = handoff["writing_contract_guidance_snapshot"]
    output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def validate_v19(handoff: dict, candidate: dict) -> list[str]:
    errors: list[str] = []
    if (handoff.get("schema"), candidate.get("schema")) != ("copy-structure-handoff-v19", "copy-structure-v19"):
        return ["handoff/candidate 必须同时为 V19"]
    if candidate.get("writing_contract") != handoff.get("writing_contract"):
        errors.append("V19 写作文案表达合同未随候选锁定")
    else:
        try:
            contract = resolve_contract(handoff.get("writing_contract") if isinstance(handoff.get("writing_contract"), dict) else {})
        except ValueError:
            errors.append("V19 写作文案表达合同缺失、版本错误或哈希漂移")
        else:
            expected_rules = writing_contract_rule_ids(handoff["writing_contract"])
            if handoff.get("writing_contract_rule_ids") != expected_rules or candidate.get("writing_contract_rule_ids") != expected_rules:
                errors.append("V19 写作文案表达合同规则索引未随交接和候选锁定")
            try:
                validate_guidance_snapshot(handoff.get("writing_contract_guidance_snapshot"), handoff["writing_contract"], "structure")
                validate_guidance_snapshot(candidate.get("writing_contract_guidance_snapshot"), handoff["writing_contract"], "structure")
            except ValueError:
                errors.append("V19 写作文案表达合同完整原文或规则快照未随交接和候选锁定")
    errors.extend(validate_core(handoff, candidate))
    context = {str(item.get("small_framework_id") or ""): item for item in handoff.get("small_framework_context", []) if isinstance(item, dict)}
    fingerprints: list[tuple[str, str, str]] = []
    for structure in ("structure_one", "structure_two", "structure_three"):
        plan = (candidate.get("structures") or {}).get(structure) or {}
        fingerprint = plan.get("angle_fingerprint") if isinstance(plan.get("angle_fingerprint"), dict) else {}
        values = tuple(str(fingerprint.get(field) or "").strip() for field in FINGERPRINT_FIELDS)
        if not all(values): errors.append(f"{structure} 缺少读者切口、推理路径或交付形态的角度指纹")
        else: fingerprints.append(values)
        for row in plan.get("core_frameworks", []) if isinstance(plan.get("core_frameworks"), list) else []:
            for card in row.get("small_framework_cards", []) if isinstance(row, dict) and isinstance(row.get("small_framework_cards"), list) else []:
                content = str(card.get("content") or "").strip(); card_id = str(card.get("small_framework_id") or ""); ident = f"{structure}/{row.get('core_framework_id')}/{card_id}"
                if not content and structure == "structure_three": continue
                source = context.get(card_id, {}); coverage = card.get("source_coverage") if isinstance(card.get("source_coverage"), dict) else {}
                excerpt = str(coverage.get("source_content_excerpt") or "").strip()
                if not excerpt or normalized(excerpt) not in normalized(source.get("source_content")) or len(str(coverage.get("preservation_explanation") or "").strip()) < 12:
                    errors.append(f"{ident} 未逐卡证明原小框架要点保留")
                errors.extend(_plain_language_errors(content, ident, handoff["writing_contract"]))
                if structure == "structure_three":
                    try: _source_evidence(card, row, ident)
                    except ValueError as exc: errors.append(str(exc))
    if len(fingerprints) == 3 and any(sum(left != right for left, right in zip(a, b)) < 3 for index, a in enumerate(fingerprints) for b in fingerprints[index + 1:]):
        errors.append("三套结构的角度指纹必须在三个维度均实质不同")
    return errors
