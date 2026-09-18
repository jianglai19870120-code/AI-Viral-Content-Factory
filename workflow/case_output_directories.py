"""Resolve formal output folders from an approved benchmark breakdown.

The breakdown category is the only authority for an output's ordinal, content
type and membership suffix.  This prevents an incomplete, hand-maintained
type map from silently publishing a file into the output-root directory.
"""
from __future__ import annotations

import re
from pathlib import Path

from workflow.benchmark_cases import get_case


ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_ROOT = ROOT / "02_资产中心" / "03_输出库" / "01_文案结构"
FINAL_COPY_ROOT = ROOT / "02_资产中心" / "03_输出库" / "02_正文成稿"
BREAKDOWN_ROOT = ROOT / "02_资产中心" / "05_案例库" / "02_对标复刻拆解"
BREAKDOWN_DIRECTORY = re.compile(r"^(?P<ordinal>\d{2})_(?P<type>.+)拆解(?P<member>（会员专享）)?$")


def _under(path: Path, parent: Path) -> bool:
    try:
        return path.resolve().is_relative_to(parent.resolve())
    except ValueError:
        return False


def output_directory_name(breakdown_directory: str, asset_kind: str) -> str:
    """Translate one ``NN_类型拆解（会员专享）`` name without guessing type."""
    match = BREAKDOWN_DIRECTORY.fullmatch(str(breakdown_directory or "").strip())
    if not match:
        raise ValueError("对标复刻拆解目录必须为“NN_类型拆解（会员专享）”")
    ordinal, content_type, member = match.group("ordinal"), match.group("type"), match.group("member") or ""
    if asset_kind == "structure":
        return f"{ordinal}_{content_type}文案结构{member}"
    if asset_kind == "final_copy":
        return f"{ordinal}_{content_type}{member}"
    raise ValueError("正式输出类型只能是 structure 或 final_copy")


def resolve_case_output_directory(case_id: str, asset_kind: str, *, create: bool = False) -> Path:
    """Return the sole legal formal output folder for an approved case.

    ``create`` establishes only the derived leaf folder.  It never creates a
    guessed category and never returns either formal output root itself.
    """
    case = get_case(case_id)
    breakdown = Path(str(case.get("breakdownPath") or "")).resolve()
    if not breakdown.is_file() or not _under(breakdown, BREAKDOWN_ROOT):
        raise ValueError("对标案例缺少案例库内的正式复刻拆解文件")
    root = STRUCTURE_ROOT if asset_kind == "structure" else FINAL_COPY_ROOT if asset_kind == "final_copy" else None
    if root is None:
        raise ValueError("正式输出类型只能是 structure 或 final_copy")
    target = (root / output_directory_name(breakdown.parent.name, asset_kind)).resolve()
    if target == root.resolve() or not _under(target, root):
        raise ValueError("派生后的正式输出目录非法")
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def assert_case_output_path(case_id: str, asset_kind: str, output_path: Path, *, create: bool = False) -> Path:
    """Require a formal file to sit directly in its case-derived category."""
    target = resolve_case_output_directory(case_id, asset_kind, create=create)
    output = output_path.resolve()
    if output.parent != target or output.suffix.lower() != ".md":
        raise ValueError(f"正式文件必须直接写入案例对应目录：{target}")
    return target
