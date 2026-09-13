"""Semantic-shape validator for copy-structure V12 candidates.

V12 deliberately validates content contracts before prose quality.  Xiaoshen
still performs the independent semantic review; this validator prevents an
authoring payload from silently degrading a case, misconception or solution
into a generic one-line claim.
"""
from __future__ import annotations

import re
from pathlib import Path


STRUCTURES = ("structure_one", "structure_two", "structure_three", "structure_four")
FINGERPRINT_FIELDS = ("mother_proposition", "critical_target", "causal_mechanism", "evidence_strategy", "solution_direction")
EVIDENCE_METHODS = {"机制解释", "对照", "反问", "因果推演", "情境", "结果", "步骤验证", "条件限定", "证据"}


def norm(value: object) -> str:
    return re.sub(r"\W+", "", str(value or ""))


def statement(value: object) -> bool:
    text = str(value or "").strip()
    return 6 <= len(text) <= 180 and "\n" not in text and "<br>" not in text


def spoken_text(value: object) -> bool:
    text = str(value or "").strip()
    if not statement(text) or len(text) > 120:
        return False
    return not re.match(r"^(?:本(?:节点|段|部分|内容)|该(?:节点|段|部分)|此处)", text)


def spoken_claim(value: object) -> bool:
    text = str(value or "").strip()
    return len(text) <= 72 and spoken_text(text)


def content(row: dict) -> str:
    return " ".join([str(row.get("core_claim") or "")] + [str(item.get("text") or "") for item in row.get("evidence_chain", []) if isinstance(item, dict)])


def validate(handoff: dict, candidate: dict) -> list[str]:
    errors: list[str] = []
    if handoff.get("schema") != "copy-structure-handoff-v12" or candidate.get("schema") != "copy-structure-v12":
        return ["handoff/candidate schema 必须为 v12/v12"]
    for key in ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_framework_sha256", "processing_index_sha256", "pain_angle_index_sha256", "topic_analysis_sha256", "topic_table_binding"):
        if candidate.get(key) != handoff.get(key):
            errors.append(f"候选未锁定 handoff 的 {key}")
    if candidate.get("structure_segments") != handoff.get("structure_segments"):
        errors.append("候选未锁定后台 structure_segments")

    frameworks = handoff.get("core_frameworks") if isinstance(handoff.get("core_frameworks"), list) else []
    expected = {str(row.get("core_framework_id")): row for row in frameworks if isinstance(row, dict)}
    contracts = handoff.get("framework_content_contracts") if isinstance(handoff.get("framework_content_contracts"), list) else []
    contract_by_id = {str(row.get("core_framework_id")): row for row in contracts if isinstance(row, dict)}
    if len(expected) != len(frameworks) or set(expected) != set(contract_by_id):
        errors.append("handoff 的大框架与内容功能合同不是一一对应")
        return errors

    props = {str(item.get("proposition_id")): item for item in handoff.get("topic_propositions", []) if isinstance(item, dict)}
    plans = candidate.get("structures") if isinstance(candidate.get("structures"), dict) else {}
    if set(plans) != set(STRUCTURES):
        errors.append("候选必须且只能包含结构一至四")
        return errors

    fingerprints: list[dict] = []
    for name in STRUCTURES:
        plan = plans.get(name) if isinstance(plans.get(name), dict) else {}
        rows = plan.get("core_frameworks") if isinstance(plan.get("core_frameworks"), list) else []
        ids = [str(row.get("core_framework_id")) for row in rows if isinstance(row, dict)]
        if ids != list(expected):
            errors.append(f"{name} 未完整保留锁定大框架顺序")
            continue
        seen_targets: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"{name} 含非法大框架行")
                continue
            ident = str(row.get("core_framework_id"))
            base, contract = expected[ident], contract_by_id[ident]
            for key in ("framework_block_id", "framework_label", "formal_framework_type", "asset_framework_type", "downstream_small_structure_ids"):
                if row.get(key) != base.get(key):
                    errors.append(f"{name}/{ident} 篡改大框架映射")
            if row.get("content_contract_id") != contract.get("content_contract_id"):
                errors.append(f"{name}/{ident} 未绑定本节点内容功能合同")
            chain = row.get("evidence_chain") if isinstance(row.get("evidence_chain"), list) else []
            if name == "structure_four":
                if candidate.get("structure_four_status") == "user-pending" and (row.get("core_claim") or chain):
                    errors.append(f"{name}/{ident} user-pending 时必须留空")
                if any(key in row for key in ("proposition_ids", "asset_calls", "asset_search")):
                    errors.append(f"{name}/{ident} 不得自动填命题或资产")
                continue
            calls = row.get("asset_calls") if isinstance(row.get("asset_calls"), list) else []
            if name == "structure_three" and not calls:
                if row.get("core_claim") or chain or row.get("proposition_ids"):
                    errors.append(f"{name}/{ident} 无正式资产时不得硬补内容")
                search = row.get("asset_search") if isinstance(row.get("asset_search"), dict) else {}
                if not str(search.get("gap_reason") or "").strip():
                    errors.append(f"{name}/{ident} 无资产时必须登记缺口")
                continue
            if not spoken_claim(row.get("core_claim")):
                errors.append(f"{name}/{ident} 缺少一句可直接讲出口的核心金句，或写成了书面节点摘要")
            low, high = int(contract.get("min_evidence_points", 2)), int(contract.get("max_evidence_points", 4))
            if not low <= len(chain) <= high:
                errors.append(f"{name}/{ident} 论据链必须有 {low}-{high} 条短论据")
            covered: set[str] = set()
            for index, item in enumerate(chain, 1):
                if not isinstance(item, dict) or not spoken_text(item.get("text")):
                    errors.append(f"{name}/{ident}/论据{index} 不是合格的人话短论据")
                    continue
                if item.get("evidence_method") not in EVIDENCE_METHODS:
                    errors.append(f"{name}/{ident}/论据{index} 缺少合法写作手法")
                roles = item.get("logic_roles") if isinstance(item.get("logic_roles"), list) else []
                if not roles or not all(str(role).strip() for role in roles):
                    errors.append(f"{name}/{ident}/论据{index} 缺少逻辑角色")
                covered.update(str(role).strip() for role in roles)
                if norm(item.get("text")) == norm(row.get("core_claim")):
                    errors.append(f"{name}/{ident}/论据{index} 不得复述论点")
            required = set(map(str, contract.get("required_logic_roles", [])))
            declared = set(map(str, row.get("contract_coverage", []))) if isinstance(row.get("contract_coverage"), list) else set()
            if not required.issubset(covered) or declared != covered:
                errors.append(f"{name}/{ident} 未完整覆盖或如实声明节点功能合同")
            ids = row.get("proposition_ids") if isinstance(row.get("proposition_ids"), list) else []
            if not ids or len(ids) != len(set(map(str, ids))):
                errors.append(f"{name}/{ident} 必须绑定不重复选题命题")
            for prop_id in map(str, ids):
                expressions = props.get(prop_id, {}).get("accepted_expressions", [])
                if prop_id not in props or not any(str(expression).strip() in content(row) for expression in expressions if str(expression).strip()):
                    errors.append(f"{name}/{ident} 未明确表达命题 {prop_id}")
            target = norm(row.get("distinct_target"))
            if not target or target in seen_targets:
                errors.append(f"{name}/{ident} 未声明唯一的本节点对象")
            seen_targets.add(target)
            if name in {"structure_one", "structure_two"} and ("asset_calls" in row or "asset_search" in row):
                errors.append(f"{name}/{ident} 不得检索或绑定正式资产")
            if name == "structure_three" and calls:
                search = row.get("asset_search") if isinstance(row.get("asset_search"), dict) else {}
                if search.get("framework_type") != base.get("asset_framework_type") or not search.get("selected_asset_ids"):
                    errors.append(f"{name}/{ident} 未按正确资产族登记检索")
                for call in calls:
                    if not isinstance(call, dict) or call.get("module_type") != base.get("asset_framework_type"):
                        errors.append(f"{name}/{ident} 资产调用类型与正式资产族不一致")
        if name != "structure_four":
            steps = plan.get("progression_logic") if isinstance(plan.get("progression_logic"), list) else []
            if any(not spoken_text(step) for step in steps):
                errors.append(f"{name} 的结构推进含书面节点摘要，必须改成读者能直接听懂的话")
            fingerprint = plan.get("angle_fingerprint") if isinstance(plan.get("angle_fingerprint"), dict) else {}
            if not all(statement(fingerprint.get(field)) for field in FINGERPRINT_FIELDS):
                errors.append(f"{name} 缺少完整路线角度指纹")
            else:
                fingerprints.append(fingerprint)
    if len(fingerprints) == 3:
        for left in range(3):
            for right in range(left + 1, 3):
                different = sum(norm(fingerprints[left][field]) != norm(fingerprints[right][field]) for field in FINGERPRINT_FIELDS)
                if different < 3:
                    errors.append(f"结构{left + 1}与结构{right + 1}的母角度少于三个实质差异字段")
    return errors
