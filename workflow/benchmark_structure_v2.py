"""The single, big-framework-only benchmark breakdown contract."""
from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from pathlib import Path
from typing import Iterable


TABLE_HEADER = ["编号", "大框架", "大框架原文内容"]
BLOCK_ID = re.compile(r"^F(\d{2})$")
FOOTER_MARKER = "• 带你3小时跑通用AI做IP，批量出爆款。"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    result: list[str] = []
    cell: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            cell.extend(("\\", char)); escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            result.append("".join(cell).strip()); cell = []
        else:
            cell.append(char)
    if escaped:
        cell.append("\\")
    result.append("".join(cell).strip())
    return result


def _next(lines: list[str], index: int) -> int:
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _unescape_cell(value: str) -> str:
    return value.replace("<br>", "\n").replace("\\|", "|").strip()


def parse_markdown(path: Path) -> list[dict[str, str]]:
    """Parse precisely one V2 structure table, never the old breakdown format."""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if split_row(line) == TABLE_HEADER]
    if len(starts) != 1:
        raise ValueError("对标拆解必须且只能有一张三列结构总表")
    index = starts[0] + 2
    rows: list[dict[str, str]] = []
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        values = split_row(lines[index])
        if len(values) != 3:
            raise ValueError("结构总表只能有编号、大框架、大框架原文内容三列")
        rows.append({"编号": values[0], "大框架": values[1], "大框架原文内容": _unescape_cell(values[2])})
        index += 1
    if not rows:
        raise ValueError("结构总表不能为空")
    previous = 0
    for row in rows:
        match = BLOCK_ID.fullmatch(row["编号"])
        if not match or int(match.group(1)) != previous + 1:
            raise ValueError("大框架编号必须连续为 F01、F02……")
        if not row["大框架"].strip() or not row["大框架原文内容"].strip():
            raise ValueError("大框架和大框架原文内容不能为空")
        previous += 1
    return rows


def source_without_footer(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return text.split("\n---\n", 1)[0].strip()


def normalize_source(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\\|", "|"))


def assert_source_coverage(rows: Iterable[dict[str, str]], source: Path) -> None:
    expected = normalize_source(source_without_footer(source))
    actual = normalize_source("\n".join(row["大框架原文内容"] for row in rows))
    if actual != expected:
        raise ValueError("大框架原文内容必须按顺序完整覆盖清洗后源稿，不得遗漏、重复或改写")


def framework_payload(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {"id": row["编号"], "name": row["大框架"], "source_sha256": hashlib.sha256(row["大框架原文内容"].encode("utf-8")).hexdigest()}
        for row in rows
    ]


def escaped_table_value(value: str) -> str:
    return value.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")


def extract_legacy_frameworks(path: Path) -> list[dict[str, str]]:
    """Read the old evidence table solely for one-time V2 migration."""
    old_header = ["大框架区块", "编号", "大框架", "小框架", "小框架作用", "小结构原文内容"]
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if split_row(line) == old_header]
    if len(starts) != 1:
        raise ValueError("迁移源必须含唯一旧结构总表")
    grouped: OrderedDict[str, dict[str, str]] = OrderedDict()
    index = starts[0] + 2
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        values = split_row(lines[index])
        if len(values) != len(old_header):
            raise ValueError("旧结构总表列数错误")
        block, _, name, _, _, text = values
        current = grouped.setdefault(block, {"编号": block, "大框架": name, "大框架原文内容": ""})
        if current["大框架"] != name:
            raise ValueError(f"旧表 {block} 存在不一致的大框架名称")
        current["大框架原文内容"] += _unescape_cell(text)
        index += 1
    rows = list(grouped.values())
    for number, row in enumerate(rows, 1):
        row["编号"] = f"F{number:02d}"
    return rows
