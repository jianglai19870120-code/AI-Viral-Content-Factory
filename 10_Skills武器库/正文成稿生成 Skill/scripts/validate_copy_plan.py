#!/usr/bin/env python3
"""Mechanical gate for a final-copy candidate's sentence-plan mapping."""
from __future__ import annotations

import argparse
import json
import re
import hashlib
from pathlib import Path


def count_units(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", text))


def in_range(text: str, declared: str) -> bool:
    try:
        lower, upper = (int(item) for item in str(declared).split("–", 1))
    except ValueError:
        return False
    return lower <= count_units(text) <= upper


def punctuation_sequence(text: str) -> str:
    return "".join(char for char in text if char in "，。！？：；、")


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


def validate_mechanism_realization(unit: dict, mapping: dict, allowed_anchor_ids: set[str], errors: list[str], index: int) -> None:
    """Require evidence that the benchmark's reasoning mechanism, not just its surface, was recreated."""
    contract = unit.get("mechanism_contract") if isinstance(unit.get("mechanism_contract"), dict) else None
    if not contract:
        return
    realization = mapping.get("mechanism_realization") if isinstance(mapping.get("mechanism_realization"), dict) else None
    label = f"第 {index + 1} 个复刻单元"
    if not realization:
        errors.append(f"{label} 缺少逐句机制实现记录")
        return
    if str(realization.get("source_unit_no") or "") != str(contract.get("source_unit_no") or unit.get("unit_no") or ""):
        errors.append(f"{label} 的逐句机制记录未绑定当前对标单元")
    source_anchor_ids = {str(value) for value in realization.get("source_anchor_ids", []) if isinstance(value, str) and value.strip()}
    declared_anchor_ids = {str(value) for value in ((mapping.get("intent_coverage") or {}).get("content_anchor_ids", [])) if isinstance(value, str) and value.strip()} if isinstance(mapping.get("intent_coverage"), dict) else set()
    if unit.get("content_anchors") and not source_anchor_ids:
        errors.append(f"{label} 的逐句机制记录未说明结构四内容来源")
    if not source_anchor_ids.issubset(allowed_anchor_ids):
        errors.append(f"{label} 的逐句机制记录引用了非本小结构内容锚点")
    if not source_anchor_ids.issubset(declared_anchor_ids):
        errors.append(f"{label} 的逐句机制记录与正文声明的内容锚点不一致")
    bindings = realization.get("role_bindings") if isinstance(realization.get("role_bindings"), list) else []
    expected_roles = {str(role).strip() for role in contract.get("required_role_slots", []) if str(role).strip()}
    bound_roles = {str(item.get("role") or "").strip() for item in bindings if isinstance(item, dict)}
    missing_roles = expected_roles - bound_roles
    if missing_roles:
        errors.append(f"{label} 未逐项实现对标句式角色：{'、'.join(sorted(missing_roles))}")
    binding_texts: list[tuple[str, str]] = []
    candidate_text = normalized(str(mapping.get("text") or ""))
    for binding in bindings:
        if not isinstance(binding, dict):
            errors.append(f"{label} 的句式角色绑定格式非法")
            continue
        if not str(binding.get("text") or "").strip():
            errors.append(f"{label} 的句式角色“{binding.get('role') or '未知'}”缺少实际文本")
        elif normalized(str(binding.get("text") or "")) not in candidate_text:
            errors.append(f"{label} 的句式角色“{binding.get('role') or '未知'}”没有落到实际正文")
        else:
            binding_texts.append((str(binding.get("role") or "未知").strip(), normalized(str(binding.get("text") or ""))))
        binding_sources = {str(value) for value in binding.get("source_anchor_ids", []) if isinstance(value, str) and value.strip()}
        if unit.get("content_anchors") and not binding_sources:
            errors.append(f"{label} 的句式角色“{binding.get('role') or '未知'}”未绑定结构四内容来源")
        if not binding_sources.issubset(allowed_anchor_ids):
            errors.append(f"{label} 的句式角色“{binding.get('role') or '未知'}”引用了跨框架内容")
        if not binding_sources.issubset(declared_anchor_ids):
            errors.append(f"{label} 的句式角色“{binding.get('role') or '未知'}”与正文内容锚点声明不一致")
    if len(expected_roles) > 1:
        duplicates = {text for _, text in binding_texts if text and sum(1 for _, other in binding_texts if other == text) > 1}
        if duplicates:
            errors.append(f"{label} 的不同句式角色不能重复绑定同一段正文")
        if any(text == candidate_text for _, text in binding_texts):
            errors.append(f"{label} 有多个句式角色时，单个角色不能用整段正文代替独立推理动作")
    if not str(realization.get("reasoning_preservation") or "").strip():
        errors.append(f"{label} 缺少对标推理关系保持说明")
    illustrations = realization.get("illustrations", [])
    if not isinstance(illustrations, list):
        errors.append(f"{label} 的说明性补充必须为列表")
    else:
        for illustration in illustrations:
            if not isinstance(illustration, dict) or not str(illustration.get("text") or "").strip() or not str(illustration.get("derivation_reason") or "").strip():
                errors.append(f"{label} 的说明性补充缺少文本或从结构四推导的理由")
                continue
            derived = {str(value) for value in illustration.get("derived_from_anchor_ids", []) if isinstance(value, str) and value.strip()}
            if not derived or not derived.issubset(allowed_anchor_ids):
                errors.append(f"{label} 的说明性补充没有来自本小结构的内容锚点")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验正文逐句复刻计划")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    units = plan.get("units") if isinstance(plan.get("units"), list) else []
    mappings = candidate.get("unit_mappings") if isinstance(candidate.get("unit_mappings"), list) else []
    errors: list[str] = []
    if candidate.get("schema") != "final-copy-v1":
        errors.append("schema 必须为 final-copy-v1")
    if candidate.get("benchmark_case_id") != plan.get("benchmark_case_id"):
        errors.append("正文候选的对标复刻拆解编号必须与逐句计划一致")
    if candidate.get("topic") != plan.get("topic") or candidate.get("structure_four_sha256") != plan.get("structure_four_sha256"):
        errors.append("正文候选必须绑定当前冻结结构四与选题")
    plan_sha256 = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    if candidate.get("sentence_plan_sha256") != plan_sha256:
        errors.append("正文候选必须绑定当前逐句复刻计划哈希")
    if len(mappings) != len(units):
        errors.append("正文候选必须逐单元完整映射")
    spoken_text = normalized("".join(str(mapping.get("text") or "") for mapping in mappings if isinstance(mapping, dict)))
    topic_terms = plan.get("topic_terms") if isinstance(plan.get("topic_terms"), list) else []
    topic_coverage = candidate.get("topic_coverage") if isinstance(candidate.get("topic_coverage"), dict) else {}
    if plan.get("structure_intent_map"):
        covered = topic_coverage.get("covered_terms") if isinstance(topic_coverage.get("covered_terms"), list) else []
        if set(covered) != set(topic_terms) or not str(topic_coverage.get("meaning_alignment") or "").strip():
            errors.append("正文候选缺少完整主题词覆盖或主题含义说明")
        for term in topic_terms:
            if not isinstance(term, str) or term.strip() not in spoken_text:
                errors.append(f"口播正文缺少主题词：{term}")
    texts_by_parent: dict[str, list[str]] = {}
    mappings_by_parent: dict[str, list[dict]] = {}
    anchor_texts: dict[str, list[str]] = {}
    anchor_claims: dict[str, set[str]] = {}
    plan_anchors: dict[str, dict] = {}
    for index, unit in enumerate(units):
        if index >= len(mappings) or not isinstance(mappings[index], dict):
            continue
        mapping = mappings[index]
        parent_id = str(unit.get("parent_small_framework_id") or "")
        if not parent_id:
            errors.append(f"第 {index + 1} 个复刻单元缺少所属结构四小框架")
        else:
            texts_by_parent.setdefault(parent_id, []).append(str(mapping.get("text") or ""))
            mappings_by_parent.setdefault(parent_id, []).append(mapping)
        if mapping.get("unit_no") != unit.get("unit_no") or mapping.get("unit_type") != unit.get("unit_type"):
            errors.append(f"第 {index + 1} 个复刻单元顺序或类型不一致")
        if not str(mapping.get("text") or "").strip():
            errors.append(f"第 {index + 1} 个复刻单元缺少正文")
        if mapping.get("small_structure_id") != unit.get("small_structure_id"):
            errors.append(f"第 {index + 1} 个复刻单元的小结构归属不一致")
        for field in ("replication_function", "template", "slot_rule", "mechanism", "style_tone", "rhythm", "sentence_shape", "clause_roles", "required_punctuation", "sentence_form"):
            if mapping.get(field) != unit.get(field):
                errors.append(f"第 {index + 1} 个复刻单元的 {field} 未按锁定计划执行")
        if not in_range(str(mapping.get("text") or ""), str(unit.get("word_range") or "")):
            errors.append(f"第 {index + 1} 个复刻单元净字数未落入锁定范围")
        if punctuation_sequence(str(mapping.get("text") or "")) != str(unit.get("required_punctuation") or ""):
            errors.append(f"第 {index + 1} 个复刻单元的连接标点未按锁定句式执行")
        if hashlib.sha256(str(mapping.get("text") or "").encode("utf-8")).hexdigest() == unit.get("source_text_sha256"):
            errors.append(f"第 {index + 1} 个复刻单元直接照搬了对标原句")
        if mapping.get("copy_check") != "passed":
            errors.append(f"第 {index + 1} 个复刻单元缺少禁止照搬检查")
        anchors = unit.get("content_anchors") if isinstance(unit.get("content_anchors"), list) else []
        allowed_anchor_ids = {str(value) for value in unit.get("allowed_content_anchor_ids", []) if str(value)}
        if anchors:
            for anchor in anchors:
                if isinstance(anchor, dict) and str(anchor.get("anchor_id") or ""):
                    anchor_id = str(anchor["anchor_id"])
                    previous = plan_anchors.get(anchor_id)
                    if previous and previous != anchor:
                        errors.append(f"内容锚点 {anchor_id} 在同一计划中定义不一致")
                    plan_anchors[anchor_id] = anchor
            coverage = mapping.get("intent_coverage") if isinstance(mapping.get("intent_coverage"), dict) else {}
            claimed_ids = {str(value) for value in coverage.get("content_anchor_ids", []) if isinstance(value, str) and value.strip()}
            if not claimed_ids:
                errors.append(f"第 {index + 1} 个复刻单元未声明结构四内容锚点")
            if not claimed_ids.issubset(allowed_anchor_ids):
                errors.append(f"第 {index + 1} 个复刻单元引用了不属于本框架小结构的内容锚点")
            for anchor_id in claimed_ids:
                anchor_texts.setdefault(anchor_id, []).append(str(mapping.get("text") or ""))
                anchor_claims.setdefault(anchor_id, set()).update(
                    str(term).strip() for term in coverage.get("covered_keywords", [])
                    if isinstance(term, str) and term.strip()
                )
            text = normalized(str(mapping.get("text") or ""))
            for term in unit.get("forbidden_cross_framework_terms", []):
                if isinstance(term, str) and term.strip() and term.strip() in text:
                    errors.append(f"第 {index + 1} 个复刻单元泄漏了其他核心大框架的专属内容：{term}")
        validate_mechanism_realization(unit, mapping, allowed_anchor_ids, errors, index)
        if unit.get("unit_type") == "句群":
            clauses = mapping.get("clauses") if isinstance(mapping.get("clauses"), list) else []
            expected = unit.get("clauses") if isinstance(unit.get("clauses"), list) else []
            if len(clauses) != len(expected):
                errors.append(f"第 {index + 1} 个句群分句数量不一致")
            for clause_index, expected_clause in enumerate(expected):
                if clause_index >= len(clauses) or not isinstance(clauses[clause_index], dict):
                    continue
                clause = clauses[clause_index]
                if clause.get("clause_no") != expected_clause.get("clause_no"):
                    errors.append(f"第 {index + 1} 个句群分句编号不一致")
                if clause.get("connector") != expected_clause.get("connector"):
                    errors.append(f"第 {index + 1} 个句群连接符顺序不一致")
                if not in_range(str(clause.get("text") or ""), str(expected_clause.get("word_range") or "")):
                    errors.append(f"第 {index + 1} 个句群分句字数未落入锁定范围")
                if hashlib.sha256(str(clause.get("text") or "").encode("utf-8")).hexdigest() == expected_clause.get("source_text_sha256"):
                    errors.append(f"第 {index + 1} 个句群分句直接照搬了对标原句")
            rebuilt = "".join(
                f"{str(clause.get('text') or '')}{str(clause.get('connector') or '')}"
                for clause in clauses if isinstance(clause, dict)
            )
            if normalized(rebuilt) != normalized(str(mapping.get("text") or "")):
                errors.append(f"第 {index + 1} 个句群正文必须由已校验分句及连接符原样组成")
    intents_by_parent: dict[str, dict] = {}
    for unit in units:
        if not isinstance(unit, dict):
            continue
        parent_id = str(unit.get("parent_small_framework_id") or "")
        if parent_id and unit.get("intent_id"):
            intents_by_parent.setdefault(parent_id, {key: unit.get(key) for key in ("intent_id", "intent_origin", "intent_main_meaning", "intent_required_keywords", "intent_auto_fill_reasoning")})
    for parent_id, intent in intents_by_parent.items():
        group_text = normalized("".join(texts_by_parent.get(parent_id, [])))
        group_mappings = mappings_by_parent.get(parent_id, [])
        coverage = [row.get("intent_coverage") for row in group_mappings if isinstance(row.get("intent_coverage"), dict)]
        origin = intent.get("intent_origin")
        if origin == "user-filled":
            terms = intent.get("intent_required_keywords") if isinstance(intent.get("intent_required_keywords"), list) else []
            if not terms or any(str(term).strip() not in group_text for term in terms):
                errors.append(f"结构四小框架 {parent_id} 未覆盖用户关键词")
            claimed = {str(term).strip() for item in coverage for term in (item.get("covered_keywords") if isinstance(item.get("covered_keywords"), list) else []) if str(term).strip()}
            if not set(terms).issubset(claimed):
                errors.append(f"结构四小框架 {parent_id} 未记录完整用户关键词覆盖")
            if not any(str(item.get("meaning_alignment") or "").strip() for item in coverage):
                errors.append(f"结构四小框架 {parent_id} 缺少用户主旨保持说明")
        elif origin == "auto-fill-required":
            if not any(str(item.get("auto_fill_reasoning") or "").strip() for item in coverage):
                errors.append(f"结构四小框架 {parent_id} 缺少空白行自动补全说明")
        else:
            errors.append(f"结构四小框架 {parent_id} 的意图来源非法")
    for anchor_id, anchor in plan_anchors.items():
        claimed_text = normalized("".join(anchor_texts.get(anchor_id, [])))
        terms = [str(value).strip() for value in anchor.get("required_keywords", []) if isinstance(value, str) and value.strip()]
        if not claimed_text:
            errors.append(f"结构四内容锚点 {anchor_id} 未被任何所属正文单元消费")
            continue
        if any(term not in claimed_text for term in terms):
            errors.append(f"结构四内容锚点 {anchor_id} 未在所属正文单元覆盖全部关键词")
        if not set(terms).issubset(anchor_claims.get(anchor_id, set())):
            errors.append(f"结构四内容锚点 {anchor_id} 未记录完整关键词覆盖")
    if errors:
        print("FAIL\n" + "\n".join(f"- {item}" for item in errors))
        return 1
    print(f"PASS: {len(mappings)} 个复刻单元")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
