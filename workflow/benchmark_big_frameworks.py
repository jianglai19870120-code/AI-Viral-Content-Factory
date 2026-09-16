"""Contracts for the reviewed, dictionary-first big-framework stage."""
from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

from workflow.benchmark_framework_naming import digest as naming_dictionary_sha256
from workflow.benchmark_framework_naming import framework_metadata
from workflow.benchmark_temporary_framework_naming import load_approved_temporary_names
from workflow.benchmark_structure_v3 import BLOCK_ID, FOOTER_MARKER, normalize_source, source_without_footer, split_row


TABLE_HEADER = ["编号", "大框架", "大框架原文内容"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unescape(value: str) -> str:
    return value.replace("<br>", "\n").replace("\\|", "|").strip()


def _divider(line: str) -> bool:
    cells = split_row(line)
    return len(cells) == 3 and all(re.fullmatch(r":?-{3,}:?", item.replace(" ", "")) for item in cells)


def framework_kind(label: str, *, block_id: str | None = None, temporary_names: dict[str, dict[str, Any]] | None = None) -> str:
    """Return the processing module, or the canonical support label, from the owner dictionary."""
    metadata = framework_naming(label, block_id=block_id, temporary_names=temporary_names)
    return str(metadata["processingModule"] or metadata["canonicalName"])


def framework_naming(label: str, *, block_id: str | None = None, temporary_names: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """Expose auditable dictionary metadata without changing the visible label."""
    try:
        return framework_metadata(label)
    except ValueError:
        temporary = (temporary_names or {}).get(str(block_id or ""))
        if temporary and str(temporary.get("canonicalName") or "") == str(label or "").strip():
            return dict(temporary)
        raise


def parse_markdown_text(content: str, *, validate_names: bool = True, temporary_names: dict[str, dict[str, Any]] | None = None) -> list[dict[str, str]]:
    lines = content.replace("\r\n", "\n").splitlines()
    starts = [index for index, line in enumerate(lines) if split_row(line) == TABLE_HEADER]
    if len(starts) != 1:
        raise ValueError("大框架候选必须且只能有一张三列表")
    index = starts[0] + 1
    if index >= len(lines) or not _divider(lines[index]):
        raise ValueError("大框架三列表表头后必须保留 Markdown 分隔行")
    rows: list[dict[str, str]] = []
    index += 1
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        values = split_row(lines[index])
        if len(values) != 3:
            raise ValueError("大框架候选只能有编号、大框架、大框架原文内容三列")
        rows.append({"编号": values[0], "大框架": values[1], "大框架原文内容": _unescape(values[2])})
        index += 1
    if not rows:
        raise ValueError("大框架候选不能为空")
    for expected, row in enumerate(rows, 1):
        match = BLOCK_ID.fullmatch(row["编号"])
        if not match or int(match.group(1)) != expected:
            raise ValueError("大框架编号必须连续为 F01、F02……")
        if not row["大框架原文内容"]:
            raise ValueError("大框架原文内容不能为空")
        if validate_names:
            framework_naming(row["大框架"], block_id=row["编号"], temporary_names=temporary_names)
    return rows


def temporary_naming_context(path: Path, *, source: Path | None = None, temporary_naming_review: Path | None = None) -> dict[str, dict[str, Any]]:
    temporary_names: dict[str, dict[str, Any]] = {}
    if temporary_naming_review is not None:
        if source is None:
            raise ValueError("临时大框架命名审核必须同时提供源稿")
        temporary_names = load_approved_temporary_names(
            temporary_naming_review, source=source, candidate=path, dictionary_sha256=dictionary_sha256(),
        )
    return temporary_names


def parse_markdown(path: Path, *, source: Path | None = None, temporary_naming_review: Path | None = None) -> list[dict[str, str]]:
    temporary_names = temporary_naming_context(path, source=source, temporary_naming_review=temporary_naming_review)
    return parse_markdown_text(path.read_text(encoding="utf-8"), temporary_names=temporary_names)


def temporary_naming_context_from_big_audit(big_framework: Path, source: Path, big_audit: Path) -> dict[str, dict[str, Any]]:
    """Recover the candidate-scoped exception needed to read its frozen four-table."""
    try:
        audit = json.loads(big_audit.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"大框架审核回执不可读取：{exc}") from exc
    review_text = str(audit.get("temporary_naming_review_path") or "").strip()
    review_hash = str(audit.get("temporary_naming_review_sha256") or "")
    if not review_text and not review_hash:
        return {}
    review = Path(review_text).resolve()
    if not review.is_file() or digest(review) != review_hash:
        raise ValueError("大框架审核绑定的临时名称审核不可用或已漂移")
    return temporary_naming_context(big_framework, source=source, temporary_naming_review=review)


def parse_for_naming_suggestions(path: Path) -> list[dict[str, str]]:
    """Read a syntactically valid three-column candidate before its names are approved."""
    return parse_markdown_text(path.read_text(encoding="utf-8"), validate_names=False)


def assert_source_coverage(rows: list[dict[str, str]], source: Path) -> None:
    expected = normalize_source(source_without_footer(source))
    actual = normalize_source("\n".join(row["大框架原文内容"] for row in rows))
    if actual != expected:
        raise ValueError("大框架原文内容必须按顺序完整覆盖清洗后源稿")


def payload(rows: list[dict[str, str]], *, temporary_names: dict[str, dict[str, Any]] | None = None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        naming = framework_naming(row["大框架"], block_id=row["编号"], temporary_names=temporary_names)
        result.append({
            "id": row["编号"],
            "name": row["大框架"],
            "kind": str(naming["processingModule"] or naming["canonicalName"]),
            "dictionary_entry_id": str(naming["dictionaryEntryId"]),
            "role": str(naming["role"]),
            "processing_module": str(naming["processingModule"] or ""),
            "temporary_naming": bool(naming.get("temporary")),
            "source_sha256": hashlib.sha256(row["大框架原文内容"].encode("utf-8")).hexdigest(),
        })
    return result


def dictionary_sha256() -> str:
    return naming_dictionary_sha256()


def assert_matches_frozen_big_frameworks(small_rows: list[dict[str, str]], big_rows: list[dict[str, str]]) -> None:
    grouped: OrderedDict[str, dict[str, str]] = OrderedDict()
    for row in small_rows:
        block = grouped.setdefault(row["编号"], {"name": row["大框架"], "content": ""})
        if block["name"] != row["大框架"]:
            raise ValueError("同一 FNN 的大框架名称必须一致")
        block["content"] += row["小框架原文内容"]
    if list(grouped) != [row["编号"] for row in big_rows]:
        raise ValueError("四列表 FNN 必须与已审核大框架候选完全一致")
    for big in big_rows:
        current = grouped[big["编号"]]
        if current["name"] != big["大框架"]:
            raise ValueError(f"{big['编号']} 不得重命名已审核大框架")
        if normalize_source(current["content"]) != normalize_source(big["大框架原文内容"]):
            raise ValueError(f"{big['编号']} 的小框架不得跨越、合并或改变已审核大框架原文")


def validate_candidate_document(path: Path, source: Path, *, temporary_naming_review: Path | None = None) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    if text.count(FOOTER_MARKER) != 1:
        raise ValueError("大框架候选必须有且只有一个品牌尾注")
    rows = parse_markdown(path, source=source, temporary_naming_review=temporary_naming_review)
    assert_source_coverage(rows, source)
    return rows
