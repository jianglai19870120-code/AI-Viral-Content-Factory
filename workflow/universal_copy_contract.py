"""Shared parsers and invariants for the universal copy-production pipeline."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

FUNCTION_HEADER = ["大框架区块", "小结构编号", "大框架功能", "通用复刻功能", "功能任务", "前置推进", "后续交付", "语气与笃定程度", "内容隔离边界"]
SENTENCE_HEADER = ["复刻单元号", "原句", "原文作用说明", "通用复刻功能", "与前后句的推进关系", "可复用句式模板", "槽位替换规则", "必须保留的结构机制", "禁止照搬项", "句式/语气", "节奏或标点提示", "原句净字数", "复刻字数范围"]
GROUP_HEADER = ["句群号", "原文句群", "句群作用", "固定修辞关系", "分句数量与连接符顺序", "句群总净字数", "句群复刻范围"]
CLAUSE_HEADER = ["分句号", "原分句", "分句作用", "分句模板", "槽位替换规则", "必须保留机制", "连接符", "原分句净字数", "分句复刻范围"]
SMALL_HEADING = re.compile(r"^## 小结构 (\d{2})｜(.+)$")
UNIT_HEADING = re.compile(r"^### 复刻单元 (\d{2})｜(单句|句群)$")
CLAUSE_HEADING = re.compile(r"^#### 句群 (\d{2}) 分句表$")
FORBIDDEN_FUNCTIONS = {"信息推进", "内容展开", "内容补充", "补充说明", "承接", "过渡"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_units(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", value))


def punctuation_sequence(value: str) -> str:
    """Expose only structural punctuation; never return benchmark sentence text."""
    return "".join(char for char in value if char in "，。！？：；、")


def sentence_form(value: str) -> str:
    stripped = value.strip()
    if stripped.endswith("？"):
        return "疑问句"
    if stripped.endswith("！"):
        return "感叹句"
    return "陈述句"


def split_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.extend(("\\", char)); escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip()); current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _next(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _table(lines: list[str], index: int, header: list[str]) -> tuple[list[dict[str, str]], int]:
    index = _next(lines, index)
    if index >= len(lines) or split_row(lines[index]) != header:
        raise ValueError("缺少预期表头：" + " | ".join(header))
    index += 2
    rows: list[dict[str, str]] = []
    while index < len(lines) and lines[index].startswith("|"):
        values = split_row(lines[index])
        if len(values) != len(header):
            raise ValueError("Markdown 表格列数错误")
        rows.append(dict(zip(header, values)))
        index += 1
    return rows, index


def parse_breakdown(path: Path) -> dict[str, Any]:
    """Read only the functional layer and reusable unit constraints.

    The returned payload deliberately excludes all benchmark source sentences and
    content evidence.  Original sentence text is used only to calculate a hash
    for direct-copy detection.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if split_row(line) == FUNCTION_HEADER]
    if len(starts) != 1:
        raise ValueError("对标拆解必须且只能有一张下游复刻功能蓝图")
    blueprint_rows, _ = _table(lines, starts[0], FUNCTION_HEADER)
    by_small = {row["小结构编号"]: row for row in blueprint_rows}
    if len(by_small) != len(blueprint_rows):
        raise ValueError("功能蓝图小结构编号重复")
    units: list[dict[str, Any]] = []
    current_small = ""
    for index, line in enumerate(lines):
        small = SMALL_HEADING.match(line.strip())
        if small:
            current_small = small.group(1)
            continue
        unit = UNIT_HEADING.match(line.strip())
        if not unit:
            continue
        if not current_small or current_small not in by_small:
            raise ValueError("复刻单元未归属有效小结构")
        unit_no, unit_type = unit.groups()
        blueprint = by_small[current_small]
        if unit_type == "单句":
            rows, _ = _table(lines, index + 1, SENTENCE_HEADER)
            if len(rows) != 1:
                raise ValueError(f"复刻单元 {unit_no} 单句表必须恰有一行")
            row = rows[0]
            if row["复刻单元号"] != unit_no:
                raise ValueError(f"复刻单元 {unit_no} 编号错误")
            units.append({
                "unit_no": unit_no, "unit_type": unit_type, "small_structure_id": current_small,
                "framework_block_id": blueprint["大框架区块"], "framework_function": blueprint["大框架功能"],
                "replication_function": row["通用复刻功能"], "function_task": blueprint["功能任务"],
                "input_relation": blueprint["前置推进"], "output_relation": blueprint["后续交付"],
                "tone_strength": blueprint["语气与笃定程度"], "content_firewall": blueprint["内容隔离边界"],
                "template": row["可复用句式模板"], "slot_rule": row["槽位替换规则"],
                "mechanism": row["必须保留的结构机制"], "style_tone": row["句式/语气"],
                "rhythm": row["节奏或标点提示"], "word_range": row["复刻字数范围"],
                "source_text_sha256": hashlib.sha256(row["原句"].encode("utf-8")).hexdigest(),
                "source_punctuation": punctuation_sequence(row["原句"]),
                "source_sentence_form": sentence_form(row["原句"]),
            })
        else:
            group_rows, next_index = _table(lines, index + 1, GROUP_HEADER)
            if len(group_rows) != 1:
                raise ValueError(f"句群 {unit_no} 总表必须恰有一行")
            clause_index = _next(lines, next_index)
            heading = CLAUSE_HEADING.match(lines[clause_index].strip()) if clause_index < len(lines) else None
            if not heading or heading.group(1) != unit_no:
                raise ValueError(f"句群 {unit_no} 缺少分句表")
            clauses, _ = _table(lines, clause_index + 1, CLAUSE_HEADER)
            group = group_rows[0]
            units.append({
                "unit_no": unit_no, "unit_type": unit_type, "small_structure_id": current_small,
                "framework_block_id": blueprint["大框架区块"], "framework_function": blueprint["大框架功能"],
                "replication_function": blueprint["通用复刻功能"], "function_task": blueprint["功能任务"],
                "input_relation": blueprint["前置推进"], "output_relation": blueprint["后续交付"],
                "tone_strength": blueprint["语气与笃定程度"], "content_firewall": blueprint["内容隔离边界"],
                "template": group["固定修辞关系"], "slot_rule": "按分句槽位规则替换", "mechanism": group["固定修辞关系"],
                "style_tone": blueprint["语气与笃定程度"], "rhythm": group["分句数量与连接符顺序"],
                "word_range": group["句群复刻范围"],
                "source_text_sha256": hashlib.sha256(group["原文句群"].encode("utf-8")).hexdigest(),
                "source_punctuation": punctuation_sequence(group["原文句群"]),
                "source_sentence_form": sentence_form(group["原文句群"]),
                "clauses": [{"clause_no": row["分句号"], "template": row["分句模板"], "slot_rule": row["槽位替换规则"], "mechanism": row["必须保留机制"], "connector": row["连接符"], "word_range": row["分句复刻范围"], "source_text_sha256": hashlib.sha256(row["原分句"].encode("utf-8")).hexdigest()} for row in clauses],
            })
    if not units:
        raise ValueError("对标拆解没有复刻单元")
    return {"functional_blueprint": blueprint_rows, "units": units}


def valid_function(value: str) -> bool:
    text = str(value or "").strip()
    return bool(text) and text not in FORBIDDEN_FUNCTIONS and not any(mark in text for mark in ("→", "；", "、", "/"))
