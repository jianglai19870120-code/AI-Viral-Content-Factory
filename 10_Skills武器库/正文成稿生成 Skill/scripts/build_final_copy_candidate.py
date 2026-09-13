#!/usr/bin/env python3
"""Bind authored unit text to a frozen sentence plan without changing its constraints."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def build_group_clauses(unit: dict, authored_entry: dict) -> list[dict]:
    """Carry authored clause text into the candidate so the gate can verify every clause."""
    expected = unit.get("clauses") if isinstance(unit.get("clauses"), list) else []
    authored = authored_entry.get("clauses") if isinstance(authored_entry.get("clauses"), list) else []
    if len(authored) != len(expected):
        raise SystemExit(f"句群 {unit.get('unit_no')} 必须逐分句提供正文，数量必须为 {len(expected)}")
    result = []
    for index, expected_clause in enumerate(expected):
        item = authored[index]
        if not isinstance(item, dict) or not str(item.get("text") or "").strip():
            raise SystemExit(f"句群 {unit.get('unit_no')} 的第 {index + 1} 个分句缺少正文")
        result.append({
            "clause_no": expected_clause.get("clause_no"),
            "text": str(item["text"]).strip(),
            "connector": expected_clause.get("connector"),
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="将逐句正文文本绑定为 final-copy-v1 候选")
    parser.add_argument("--plan", type=Path, required=True); parser.add_argument("--texts", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); plan = json.loads(args.plan.read_text(encoding="utf-8")); authored = json.loads(args.texts.read_text(encoding="utf-8"))
    if not isinstance(authored, dict): raise SystemExit("texts 必须是以复刻单元号为键的 JSON 对象")
    units = plan.get("units") if isinstance(plan.get("units"), list) else []
    expected = {str(unit.get("unit_no") or "") for unit in units if isinstance(unit, dict)}
    active_intent_map = bool(plan.get("structure_intent_map"))
    authored_units = authored.get("texts") if active_intent_map and isinstance(authored.get("texts"), dict) else authored
    if set(authored_units) != expected: raise SystemExit("texts 必须且只能覆盖逐句计划的全部复刻单元")
    topic_coverage = authored.get("topic_coverage") if active_intent_map and isinstance(authored.get("topic_coverage"), dict) else {}
    mappings = []
    for unit in units:
        authored_entry = authored_units[str(unit["unit_no"])]
        if active_intent_map and not isinstance(authored_entry, dict): raise SystemExit("启用意图映射后每个正文单元必须提供 text 与 intent_coverage")
        text = str(authored_entry.get("text") if isinstance(authored_entry, dict) else authored_entry).strip()
        mapping = {key: unit.get(key) for key in ("unit_no", "unit_type", "small_structure_id", "replication_function", "template", "slot_rule", "mechanism", "style_tone", "rhythm", "sentence_shape", "clause_roles", "required_punctuation", "sentence_form")}
        mapping.update({"text": text, "copy_check": "passed"})
        if active_intent_map:
            coverage = authored_entry.get("intent_coverage") if isinstance(authored_entry.get("intent_coverage"), dict) else {}
            anchor_ids = coverage.get("content_anchor_ids") if isinstance(coverage.get("content_anchor_ids"), list) else []
            if unit.get("content_anchors") and not anchor_ids:
                raise SystemExit(f"复刻单元 {unit.get('unit_no')} 必须声明实际消费的结构四内容锚点")
            mapping["intent_coverage"] = coverage
        if isinstance(unit.get("mechanism_contract"), dict):
            realization = authored_entry.get("mechanism_realization") if isinstance(authored_entry, dict) else None
            if not isinstance(realization, dict):
                raise SystemExit(f"复刻单元 {unit.get('unit_no')} 必须声明逐句机制实现记录")
            mapping["mechanism_realization"] = realization
        if unit.get("unit_type") == "句群":
            mapping["clauses"] = build_group_clauses(unit, authored_entry if isinstance(authored_entry, dict) else {})
        mappings.append(mapping)
    payload = {"schema": "final-copy-v1", "producer": {"agent_id": "xiaoxie"}, "topic": plan.get("topic"), "benchmark_case_id": plan.get("benchmark_case_id"), "structure_four_sha256": plan.get("structure_four_sha256"), "sentence_plan_sha256": digest(args.plan), "unit_mappings": mappings}
    if active_intent_map: payload["topic_coverage"] = topic_coverage
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "built", "units": len(mappings)}, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
