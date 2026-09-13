#!/usr/bin/env python3
"""Create a fresh v8 runtime candidate from an unchanged historical v7 candidate.

This is a one-way runtime migration aid.  It never rewrites the v7 source and
only carries the old content statement forward after dropping the legacy
presentation label and the old how-to-say field.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def clean_statement(value: object) -> str:
    text = str(value or "").strip().replace("\n", " ")
    text = re.sub(r"^(?:\*\*[^*]+\*\*|【[^】]+】)\s*[：:]\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    if text and text[-1] not in "。！？!?":
        text += "。"
    if not text or "<br>" in text.lower() or re.search(r"(?:怎么讲|如何写|写作|展开|先.+再(?:讲|写|展开|说明|解释))", text):
        raise ValueError(f"旧内容无法无损迁移为单句 core_statement：{value!r}")
    return text


def historical_rows(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("small_framework_id") or ""): row
        for block in plan.get("core_frameworks", [])
        if isinstance(block, dict)
        for row in block.get("small_framework_rows", [])
        if isinstance(row, dict)
    }


def locked_block(block: dict[str, Any], old_rows: dict[str, dict[str, Any]], propositions: dict[str, dict[str, Any]], *, structure_four: bool) -> dict[str, Any]:
    copied = {key: value for key, value in block.items() if key != "small_framework_rows"}
    rows: list[dict[str, Any]] = []
    for locked in block.get("small_framework_rows", []):
        if not isinstance(locked, dict):
            continue
        row = dict(locked)
        old = old_rows.get(str(row.get("small_framework_id") or ""))
        if structure_four:
            row["core_statement"] = ""
        elif old:
            row["core_statement"] = clean_statement(old.get("what_to_say"))
            row["proposition_ids"] = list(old.get("proposition_ids") or [])
            for proposition_id in row["proposition_ids"]:
                proposition = propositions.get(str(proposition_id), {})
                expressions = proposition.get("accepted_expressions") if isinstance(proposition.get("accepted_expressions"), list) else []
                if expressions and not any(str(value) in row["core_statement"] for value in expressions):
                    anchor = str(proposition.get("original_phrase") or expressions[0]).strip()
                    row["core_statement"] = f"{anchor}，{row['core_statement']}"
            row["framework_answer_obligation_id"] = old.get("framework_answer_obligation_id")
            if isinstance(old.get("asset_calls"), list):
                row["asset_calls"] = old["asset_calls"]
        rows.append(row)
    copied["small_framework_rows"] = rows
    return copied


def migrate(handoff: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
    if handoff.get("schema") != "copy-structure-handoff-v9":
        raise ValueError("迁移目标必须是 copy-structure-handoff-v9")
    if legacy.get("schema") != "copy-structure-v7":
        raise ValueError("迁移输入必须是历史 copy-structure-v7 候选")
    output = {
        key: handoff[key]
        for key in (
            "topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt",
            "benchmark_framework_sha256", "processing_index_sha256", "pain_angle_index_sha256",
            "topic_structure_types", "topic_propositions", "topic_analysis_sha256",
        )
    }
    output.update({
        "schema": "copy-structure-v8",
        "structure_segments": handoff["structure_segments"],
        "structure_four_status": "user-pending",
        "producer": {
            "agent_id": "xiaochai",
            "run_mode": "runtime-candidate-v8-from-historical-v7",
            "contract": "per-small-framework-single-statement-v8",
        },
        "structures": {},
    })
    propositions = {str(item.get("proposition_id") or ""): item for item in handoff.get("topic_propositions", []) if isinstance(item, dict)}
    for name in ("structure_one", "structure_two", "structure_three", "structure_four"):
        old_plan = legacy.get("structures", {}).get(name, {})
        plan = {
            key: old_plan[key]
            for key in ("mainline", "non_overlap_rationale", "progression_logic")
            if key in old_plan
        }
        if name == "structure_four":
            plan["core_frameworks"] = [locked_block(block, {}, propositions, structure_four=True) for block in handoff["core_frameworks"]]
        else:
            old_by_id = historical_rows(old_plan)
            blocks: list[dict[str, Any]] = []
            for locked in handoff["core_frameworks"]:
                block = locked_block(locked, old_by_id, propositions, structure_four=False)
                if name == "structure_three":
                    block["small_framework_rows"] = [row for row in block["small_framework_rows"] if row.get("asset_calls")]
                    if not block["small_framework_rows"]:
                        continue
                blocks.append(block)
            plan["core_frameworks"] = blocks
            if name == "structure_three":
                plan["asset_gap_note"] = old_plan.get("asset_gap_note") or "**资产缺口说明**：未命中的小框架不伪造资产调用。"
        output["structures"][name] = plan
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="将历史 v7 运行区候选迁移为新的 v8 单句候选")
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--legacy-candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    legacy = json.loads(args.legacy_candidate.read_text(encoding="utf-8"))
    data = migrate(handoff, legacy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
