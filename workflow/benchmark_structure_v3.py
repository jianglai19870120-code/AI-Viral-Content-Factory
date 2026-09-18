"""The V3 benchmark breakdown contract: grouped big frameworks and small-framework evidence."""
from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from pathlib import Path
from typing import Iterable


TABLE_HEADER = ["编号", "大框架", "小框架", "小框架原文内容"]
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


def _unescape_cell(value: str) -> str:
    return value.replace("<br>", "\n").replace("\\|", "|").strip()


def _is_divider(line: str) -> bool:
    cells = split_row(line)
    return len(cells) == len(TABLE_HEADER) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def repair_table_divider(content: str) -> str:
    """Repair the historical client bug that serialized a data row as the divider.

    When the malformed first row appears again later in the same table, it was
    the duplicated final row used as a divider and must be replaced.  Otherwise
    a missing divider is inserted without losing the first real row.
    """
    newline = "\r\n" if "\r\n" in content else "\n"
    had_trailing_newline = content.endswith(("\n", "\r"))
    lines = content.replace("\r\n", "\n").split("\n")
    starts = [index for index, line in enumerate(lines) if split_row(line) == TABLE_HEADER]
    if len(starts) != 1:
        return content
    divider_index = starts[0] + 1
    if divider_index >= len(lines) or _is_divider(lines[divider_index]):
        return content
    malformed = lines[divider_index]
    first_cells = split_row(malformed)
    if len(first_cells) != len(TABLE_HEADER):
        return content
    later_rows = lines[divider_index + 1:]
    divider = "| " + " | ".join("---" for _ in TABLE_HEADER) + " |"
    if malformed in later_rows:
        lines[divider_index] = divider
    else:
        lines.insert(divider_index, divider)
    repaired = newline.join(lines)
    return repaired if had_trailing_newline else repaired.rstrip("\r\n")


def normalize_portable_case_markdown(content: str) -> str:
    """Keep a case document valid in both Obsidian and the workbench.

    A standalone ``<br>`` starts an HTML block in Obsidian's Markdown parser.
    When it appears before a heading or table, the following standard Markdown
    is rendered as literal text.  It was historically used only as vertical
    spacing in case documents, so replace that standalone spacer with a normal
    Markdown blank line.  ``<br>`` inside a table cell remains untouched.
    """
    newline = "\r\n" if "\r\n" in content else "\n"
    had_trailing_newline = content.endswith(("\n", "\r"))
    lines = content.replace("\r\n", "\n").split("\n")
    normalized = ["" if re.fullmatch(r"[ \t]*<br\s*/?>[ \t]*", line, re.IGNORECASE) else line for line in lines]
    result = newline.join(normalized)
    return result if had_trailing_newline else result.rstrip("\r\n")


def validate_portable_case_markdown(content: str) -> None:
    """Reject non-portable Markdown before it can render as raw pipes in Obsidian."""
    if content != normalize_portable_case_markdown(content):
        raise ValueError("对标拆解不得使用独立 <br>；请使用 Markdown 空行以兼容 Obsidian 与工作台")
    validate_table_layout(content)


def validate_table_layout(content: str) -> None:
    """Validate the Markdown table shape without changing owner-authored content."""
    lines = content.replace("\r\n", "\n").splitlines()
    starts = [index for index, line in enumerate(lines) if split_row(line) == TABLE_HEADER]
    if len(starts) != 1:
        raise ValueError("对标拆解必须且只能有一张四列结构总表")
    divider_index = starts[0] + 1
    if divider_index >= len(lines) or not _is_divider(lines[divider_index]):
        raise ValueError("四列结构总表表头后必须保留 Markdown 分隔行")
    rows = 0
    for line in lines[divider_index + 1:]:
        if not line.lstrip().startswith("|"):
            break
        if len(split_row(line)) != len(TABLE_HEADER):
            raise ValueError("结构总表只能有编号、大框架、小框架、小框架原文内容四列")
        rows += 1
    if not rows:
        raise ValueError("结构总表不能为空")


def parse_markdown_text(content: str, *, strict_small_names: bool = False) -> list[dict[str, str]]:
    """Parse one V3 table and reject non-contiguous or ambiguous framework groups."""
    lines = content.replace("\r\n", "\n").splitlines()
    validate_table_layout(content)
    starts = [index for index, line in enumerate(lines) if split_row(line) == TABLE_HEADER]
    rows: list[dict[str, str]] = []
    index = starts[0] + 2
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        values = split_row(lines[index])
        if len(values) != 4:
            raise ValueError("结构总表只能有编号、大框架、小框架、小框架原文内容四列")
        rows.append({
            "编号": values[0], "大框架": values[1], "小框架": values[2],
            "小框架原文内容": _unescape_cell(values[3]),
        })
        index += 1
    if not rows:
        raise ValueError("结构总表不能为空")

    previous_number = 0
    completed: set[str] = set()
    current_id = ""
    current_major = ""
    for row in rows:
        block_id, major, small, content = row["编号"], row["大框架"], row["小框架"], row["小框架原文内容"]
        if not major or not small or not content:
            raise ValueError("大框架、小框架和小框架原文内容不能为空")
        match = BLOCK_ID.fullmatch(block_id)
        if not match:
            raise ValueError("大框架编号必须使用 F01、F02……")
        if block_id != current_id:
            if current_id:
                completed.add(current_id)
            number = int(match.group(1))
            if number != previous_number + 1:
                raise ValueError("大框架编号必须连续为 F01、F02……")
            if block_id in completed:
                raise ValueError("同一 FNN 的小框架必须连续排列")
            previous_number, current_id, current_major = number, block_id, major
        elif major != current_major:
            raise ValueError("同一 FNN 的大框架名称必须一致")
    from workflow.benchmark_small_framework_naming import validate_small_framework_names
    validate_small_framework_names(rows, strict=strict_small_names)
    return rows


def parse_markdown(path: Path, *, strict_small_names: bool = False) -> list[dict[str, str]]:
    return parse_markdown_text(path.read_text(encoding="utf-8"), strict_small_names=strict_small_names)


def source_without_footer(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return text.split("\n---\n", 1)[0].strip()


def normalize_source(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\\|", "|"))


def assert_source_coverage(rows: Iterable[dict[str, str]], source: Path) -> None:
    expected = normalize_source(source_without_footer(source))
    actual = normalize_source("\n".join(row["小框架原文内容"] for row in rows))
    if actual != expected:
        raise ValueError("小框架原文内容必须按顺序完整覆盖清洗后源稿，不得遗漏、重复或改写")


def framework_payload(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Expose exactly the historical FNN payload consumed by downstream structure generation."""
    grouped: OrderedDict[str, dict[str, str]] = OrderedDict()
    for row in rows:
        current = grouped.setdefault(row["编号"], {"id": row["编号"], "name": row["大框架"], "content": ""})
        current["content"] += row["小框架原文内容"]
    return [
        {"id": item["id"], "name": item["name"], "source_sha256": hashlib.sha256(item["content"].encode("utf-8")).hexdigest()}
        for item in grouped.values()
    ]


def small_framework_payload(rows: Iterable[dict[str, str]]) -> list[dict[str, str | int]]:
    from workflow.benchmark_small_framework_naming import small_framework_role
    values = list(rows)
    group_sizes: dict[str, int] = {}
    for row in values:
        block_id = row["编号"]
        group_sizes[block_id] = group_sizes.get(block_id, 0) + 1
    ordinals: dict[str, int] = {}
    result: list[dict[str, str | int]] = []
    for row in values:
        block_id = row["编号"]
        ordinals[block_id] = ordinals.get(block_id, 0) + 1
        try:
            role = small_framework_role(row["大框架"], row["小框架"], group_sizes[block_id])
        except ValueError:
            # Historical owner-approved assets predate the display convention.
            # New candidates are already rejected by strict parsing before a
            # receipt can be created.
            role = row["小框架"]
        result.append({
            "block_id": block_id, "ordinal": ordinals[block_id], "name": row["小框架"],
            "role": role,
            "source_sha256": hashlib.sha256(row["小框架原文内容"].encode("utf-8")).hexdigest(),
        })
    return result


def escaped_table_value(value: str) -> str:
    return value.replace("|", "\\|").replace("\r\n", "\n").replace("\n", "<br>")
