"""V15 structure contract: lock a title-bound causal chain before authoring cards."""
from __future__ import annotations

import json
from pathlib import Path

from structure_v14 import FORMAL, build_handoff_v14

TITLE_FIELDS = ("audience", "title_promise", "core_conflict", "terminal_conclusion", "completion_criteria")
CHAIN_FIELDS = ("answering_question", "previous_dependency", "necessary_conclusion", "removal_impact", "next_question")
STRUCTURES = ("structure_one", "structure_two", "structure_three")


def _text(value: object) -> str:
    return str(value or "").strip()


def validate_title_contract(value: object) -> list[str]:
    data = value if isinstance(value, dict) else {}
    return [f"title_contract 缺少 {field}" for field in TITLE_FIELDS if not _text(data.get(field))]


def validate_logic_chain(plan: object, expected_ids: list[str], label: str) -> list[str]:
    data = plan if isinstance(plan, dict) else {}
    chain = data.get("logic_chain") if isinstance(data.get("logic_chain"), dict) else {}
    errors: list[str] = []
    if not _text(chain.get("mother_logic")):
        errors.append(f"{label} 缺少母逻辑")
    if not _text(chain.get("terminal_conclusion")):
        errors.append(f"{label} 缺少最终结论")
    nodes = chain.get("nodes") if isinstance(chain.get("nodes"), dict) else {}
    if list(nodes) != expected_ids:
        return errors + [f"{label} 逻辑链未逐项覆盖核心 FNN"]
    for ident in expected_ids:
        node = nodes.get(ident) if isinstance(nodes.get(ident), dict) else {}
        for field in CHAIN_FIELDS:
            if not _text(node.get(field)):
                errors.append(f"{label}/{ident} 缺少 {field}")
    return errors


def build_handoff_v15(*, topic: str, benchmark_id: str, topic_table_binding: dict | None = None) -> dict:
    payload = build_handoff_v14(topic=topic, benchmark_id=benchmark_id, topic_table_binding=topic_table_binding)
    payload["schema"] = "copy-structure-handoff-v15"
    return payload


def _merge_rows(base_rows: list[dict], authored_rows: object, name: str) -> list[dict]:
    rows = authored_rows if isinstance(authored_rows, list) else []
    expected = [str(row.get("core_framework_id") or "") for row in base_rows]
    actual = [str(row.get("core_framework_id") or "") for row in rows if isinstance(row, dict)]
    if actual != expected:
        raise ValueError(f"{name} 必须逐个覆盖已锁定的正式大框架")
    merged: list[dict] = []
    for base, authored in zip(base_rows, rows):
        if not isinstance(authored, dict):
            raise ValueError(f"{name} 含非法大框架行")
        # The audited FNN identity always wins; authoring may only add content.
        conflicting = [key for key in ("framework_block_id", "framework_label", "framework_function", "formal_framework_type", "asset_framework_type") if key in authored and authored[key] != base.get(key)]
        if conflicting:
            raise ValueError(f"{name} 不得改写大框架元数据：{'、'.join(conflicting)}")
        merged.append(dict(base) | authored)
    return merged


def build_candidate_v15(handoff_path: Path, authoring_path: Path, output: Path) -> None:
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff.get("schema") != "copy-structure-handoff-v15":
        raise ValueError("仅接受 copy-structure-handoff-v15")
    authored = json.loads(authoring_path.read_text(encoding="utf-8"))
    plans = authored.get("structures") if isinstance(authored.get("structures"), dict) else {}
    title_contract = authored.get("title_contract")
    errors = validate_title_contract(title_contract)
    if errors:
        raise ValueError("；".join(errors))
    base_rows = handoff.get("core_frameworks") if isinstance(handoff.get("core_frameworks"), list) else []
    expected = [str(row.get("core_framework_id") or "") for row in base_rows]
    result: dict[str, dict] = {}
    for name in STRUCTURES:
        authored_plan = plans.get(name) if isinstance(plans.get(name), dict) else {}
        rows = _merge_rows(base_rows, authored_plan.get("core_frameworks"), name)
        plan = dict(authored_plan) | {"core_frameworks": rows}
        errors = validate_logic_chain(plan, expected, name)
        if errors:
            raise ValueError("；".join(errors))
        nodes = plan["logic_chain"]["nodes"]
        for row in rows:
            row["logic_chain"] = nodes[str(row["core_framework_id"])]
        if name in {"structure_one", "structure_two"}:
            for row in rows:
                if not _text(row.get("core_claim")) or not isinstance(row.get("evidence_chain"), list) or not row["evidence_chain"]:
                    raise ValueError(f"{name}/{row['core_framework_id']} 必须在逻辑链锁定后填写核心内容")
        else:
            for row in rows:
                has_content = bool(_text(row.get("core_claim")))
                sources = row.get("processing_sources")
                if "source_note" in row:
                    raise ValueError("structure_three 禁止 source_note；出处只能来自处理库模块")
                if has_content and not isinstance(sources, list):
                    raise ValueError("structure_three 的非空内容必须提供 processing_sources")
                if not has_content and sources:
                    raise ValueError("structure_three 未命中时内容与出处必须同时留空")
        result[name] = plan
    result["structure_four"] = {"core_frameworks": [dict(row) | {"core_claim": "", "evidence_chain": [], "solution_steps": []} for row in base_rows]}
    keys = ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_sha256", "big_frameworks", "final_copy_only_frameworks", "topic_table_binding")
    payload = {key: handoff.get(key) for key in keys} | {
        "schema": "copy-structure-v15",
        "producer": {"agent_id": "xiaochai"},
        "title_contract": title_contract,
        "structure_four_status": "user-pending",
        "structures": result,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
