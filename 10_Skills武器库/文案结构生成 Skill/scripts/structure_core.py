"""Versionless internal engine used exclusively by the active V19 structure flow."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from workflow.benchmark_cases import approved_case
from workflow.benchmark_structure_v3 import parse_markdown

STRUCTURES = ("structure_one", "structure_two", "structure_three")
TITLE_FIELDS = ("audience", "title_promise", "core_conflict", "terminal_conclusion", "completion_criteria")


def normalized(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def section_text(path: Path, section: str) -> str:
    text = path.read_text(encoding="utf-8")
    if not section.strip():
        return text
    marker = re.compile(rf"(?m)^#+\s+{re.escape(section.strip())}\s*$")
    found = marker.search(text)
    if not found:
        return text if section.strip() in text else ""
    following = re.search(r"(?m)^#+\s+", text[found.end():])
    return text[found.start(): found.end() + following.start()] if following else text[found.start():]


def _small_context(benchmark_id: str) -> list[dict]:
    case = approved_case(benchmark_id)
    rows = parse_markdown(Path(str(case["breakdownPath"])))
    ordinals: dict[str, int] = {}
    result: list[dict] = []
    for row in rows:
        block = str(row["编号"])
        ordinals[block] = ordinals.get(block, 0) + 1
        result.append({"small_framework_id": f"SF-{block}-{ordinals[block]:02d}", "framework_block_id": block, "ordinal": ordinals[block], "small_framework_name": str(row["小框架"]), "source_content": str(row["小框架原文内容"])})
    return result


def build_handoff(*, topic: str, benchmark_id: str, topic_table_binding: dict | None = None) -> dict:
    """Build V19's immutable source map directly from the approved V3 case.

    This intentionally has no dependency on former V1--V18 handoff builders.
    """
    case = approved_case(benchmark_id)
    benchmark = Path(str(case["breakdownPath"])).resolve()
    cards = _small_context(benchmark_id)
    rows = parse_markdown(benchmark)
    big: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        block = str(row["编号"])
        if block in seen:
            continue
        seen.add(block)
        previous = big[-1]["framework_block_id"] if big else ""
        big.append({"core_framework_id": f"CF-{block}", "framework_block_id": block, "framework_label": str(row["大框架"]), "framework_function": "承担该 FNN 区块的推进功能，并承接前后大框架。", "previous_framework_id": previous, "formal_framework_type": None, "asset_framework_type": None})
    for index, item in enumerate(big):
        item["next_framework_id"] = big[index + 1]["framework_block_id"] if index + 1 < len(big) else ""
    return {"schema": "copy-structure-handoff-v19", "topic": topic, "benchmark_case_id": benchmark_id, "benchmark_path": str(benchmark), "benchmark_audit_receipt": str(Path(str(case["auditPath"])).resolve()), "benchmark_sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest(), "topic_table_binding": topic_table_binding, "big_frameworks": big, "core_frameworks": big, "small_framework_context": cards, "final_copy_only_frameworks": [], "structure_generation_rule": "结构一、二逐小框架填写；结构三无正式来源时整卡留空；结构四留给用户填写。"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _cards(row: dict, context: list[dict], structure: str) -> list[dict]:
    expected = [item for item in context if item["framework_block_id"] == row.get("framework_block_id")]
    authored = row.get("small_framework_cards") if isinstance(row.get("small_framework_cards"), list) else []
    if structure == "structure_four":
        return [{"small_framework_id": item["small_framework_id"], "small_framework_name": item["small_framework_name"], "content": ""} for item in expected]
    if [item.get("small_framework_id") for item in authored if isinstance(item, dict)] != [item["small_framework_id"] for item in expected]:
        raise ValueError(f"{structure}/{row.get('core_framework_id')} 必须逐个、按原顺序覆盖全部小框架")
    result = []
    for source, written in zip(expected, authored):
        content = _text(written.get("content"))
        if structure in {"structure_one", "structure_two"} and not content:
            raise ValueError(f"{structure}/{row.get('core_framework_id')} 的每个小框架必须有对应内容")
        result.append({"small_framework_id": source["small_framework_id"], "small_framework_name": source["small_framework_name"], "content": content})
    return result


def build_candidate(handoff_path: Path, authoring_path: Path, output: Path) -> None:
    handoff = json.loads(handoff_path.read_text(encoding="utf-8")); authored = json.loads(authoring_path.read_text(encoding="utf-8"))
    if handoff.get("schema") != "copy-structure-handoff-v19":
        raise ValueError("仅接受 copy-structure-handoff-v19")
    title = authored.get("title_contract") if isinstance(authored.get("title_contract"), dict) else {}
    if any(not _text(title.get(field)) for field in TITLE_FIELDS):
        raise ValueError("title_contract 必须完整")
    base = handoff.get("big_frameworks") if isinstance(handoff.get("big_frameworks"), list) else []
    expected = [str(row.get("core_framework_id") or "") for row in base]
    result: dict[str, dict] = {}
    for name in STRUCTURES:
        plan = ((authored.get("structures") or {}).get(name) or {})
        rows = plan.get("core_frameworks") if isinstance(plan, dict) and isinstance(plan.get("core_frameworks"), list) else []
        if [str(row.get("core_framework_id") or "") for row in rows if isinstance(row, dict)] != expected:
            raise ValueError(f"{name} 必须完整保持 FNN 大框架顺序")
        merged = []
        for source, row in zip(base, rows):
            item = dict(source) | dict(row); item["small_framework_cards"] = _cards(item, handoff["small_framework_context"], name); merged.append(item)
        result[name] = dict(plan) | {"core_frameworks": merged}
    result["structure_four"] = {"core_frameworks": [dict(row) | {"small_framework_cards": _cards(row, handoff["small_framework_context"], "structure_four")} for row in base]}
    payload = {key: handoff.get(key) for key in ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_sha256", "topic_table_binding", "big_frameworks", "small_framework_context", "final_copy_only_frameworks")} | {"schema": "copy-structure-v19", "producer": {"agent_id": "xiaochai"}, "title_contract": title, "structures": result}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(handoff: dict, candidate: dict) -> list[str]:
    errors: list[str] = []
    if (handoff.get("schema"), candidate.get("schema")) != ("copy-structure-handoff-v19", "copy-structure-v19"):
        return ["handoff/candidate 必须同时为 V19"]
    for key in ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_sha256", "topic_table_binding", "big_frameworks", "small_framework_context"):
        if candidate.get(key) != handoff.get(key): errors.append(f"候选未锁定 handoff 的 {key}")
    expected = [str(row.get("core_framework_id") or "") for row in handoff.get("big_frameworks", []) if isinstance(row, dict)]
    for name, plan in (candidate.get("structures") or {}).items():
        rows = plan.get("core_frameworks") if isinstance(plan, dict) else []
        if [str(row.get("core_framework_id") or "") for row in rows if isinstance(row, dict)] != expected:
            errors.append(f"{name} 未完整保持 FNN 大框架顺序"); continue
        for row in rows:
            try: _cards(row, handoff["small_framework_context"], name)
            except ValueError as exc: errors.append(str(exc))
    return errors
