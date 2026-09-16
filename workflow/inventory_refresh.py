"""One approved-only refresh path for source and benchmark inventories."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from workflow.benchmark_cases import get_case, load_registry, approved_case
from workflow.common import append_brand_footer
from workflow.input_inventory import TYPES, build_inventory


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _cell(value: object) -> str:
    """Render one GFM cell without allowing source text to break a row."""
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("\r", "<br>")
    )


def _table(title: str, headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    lines = [f"# {title}", "", "| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(_cell(value) for value in row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


def refresh_input_lists(project_root: Path, source_types: Iterable[str] | None = None) -> dict[str, int]:
    selected = set(source_types or TYPES)
    unknown = selected - set(TYPES)
    if unknown:
        raise ValueError(f"未知输入资料类型：{', '.join(sorted(unknown))}")
    rows = build_inventory(project_root)
    output = project_root / "02_资产中心" / "01_输入库" / "清单"
    written: dict[str, int] = {}
    for kind, (label, _) in TYPES.items():
        if kind not in selected:
            continue
        subset = [row for row in rows if row["source_type"] == kind]
        jsonl = output / f"{label}清单.jsonl"
        markdown = output / f"{label}清单.md"
        _atomic_write(jsonl, "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in subset))
        if kind == "work-journals":
            def journal_cards(row: dict[str, Any]) -> str:
                cards = row.get("case_cards") if isinstance(row.get("case_cards"), list) else []
                return "<br>".join(
                    f"{str(card.get('case_id') or '').strip()}｜{str(card.get('title') or '').strip()}"
                    for card in cards
                    if str(card.get("case_id") or "").strip()
                ) or "—"

            body = _table(label + "清单", ["source_id", "标题", "源文件路径", "案例卡", "状态", "状态原因"], (
                (row["source_id"], row["title"], row["source_path"], journal_cards(row), row["status"], row["status_reason"])
                for row in subset
            ))
        else:
            body = _table(label + "清单", ["source_id", "标题", "源文件路径", "处理输出数量", "状态", "状态原因"], (
                (row["source_id"], row["title"], row["source_path"], row["processing_output_count"], row["status"], row["status_reason"])
                for row in subset
            ))
        _atomic_write(markdown, body)
        append_brand_footer(markdown)
        written[kind] = len(subset)
    return written


def benchmark_case_rows(project_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in load_registry()["cases"]:
        case_id = str(case["id"])
        resolved = get_case(case_id)
        source = Path(resolved["sourcePath"])
        breakdown = Path(resolved["breakdownPath"])
        audit = Path(resolved["auditPath"])
        status, reason = "待审核", "尚无当前正式拆解的 approved 小审回执"
        try:
            approved = approved_case(case_id)
            audit = Path(approved["auditPath"])
            if approved.get("audit", {}).get("approval_basis") == "workspace-owner-manual-edit":
                status, reason = "已拆解", "当前四列表与源稿哈希均已获工作区所有者人工确认"
            else:
                status, reason = "已拆解", "当前四列表与源稿哈希均已获小审 approved"
        except ValueError:
            pass
        rows.append({
            "case_id": case_id,
            "type": str(case.get("type") or ""),
            "title": str(case.get("breakdownTitle") or case.get("sourceTitle") or case_id),
            "source_path": source.relative_to(project_root).as_posix() if source.is_file() else str(source),
            "breakdown_path": breakdown.relative_to(project_root).as_posix() if breakdown.is_file() else str(breakdown),
            "audit_status": status,
            "source_sha256": _sha256(source) if source.is_file() else "",
            "breakdown_sha256": _sha256(breakdown) if breakdown.is_file() else "",
            "audit_receipt_path": audit.relative_to(project_root).as_posix() if audit.is_file() else "",
            "status_reason": reason,
        })
    return rows


def refresh_benchmark_case_list(project_root: Path) -> int:
    rows = benchmark_case_rows(project_root)
    output = project_root / "02_资产中心" / "05_案例库" / "清单"
    _atomic_write(output / "对标案例清单.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    markdown_rows = (
        (row["case_id"], row["type"], row["title"], row["source_path"], row["breakdown_path"], row["audit_status"], row["source_sha256"], row["breakdown_sha256"], row["audit_receipt_path"], row["status_reason"])
        for row in rows
    )
    markdown = output / "对标案例清单.md"
    _atomic_write(markdown, _table("对标案例清单", ["案例编号", "类型", "案例标题", "源稿路径", "正式四列表路径", "审核状态", "源稿哈希", "拆解哈希", "审核回执路径", "状态原因"], markdown_rows))
    append_brand_footer(markdown)
    return len(rows)


def refresh_after_approved(*, project_root: Path, source_types: Iterable[str] = (), include_benchmarks: bool = False, producer: str, reason: str) -> dict[str, Any]:
    """Refresh only after a caller has completed its approved formal release."""
    inputs = refresh_input_lists(project_root, source_types) if source_types else {}
    benchmarks = refresh_benchmark_case_list(project_root) if include_benchmarks else 0
    from workflow.data_center import refresh_data_center
    snapshot = refresh_data_center(reason=reason, producer=producer)
    return {"inputs": inputs, "benchmarkCases": benchmarks, "dataCenterGeneratedAt": snapshot["generatedAt"], "refreshedAt": datetime.now(timezone.utc).isoformat()}
