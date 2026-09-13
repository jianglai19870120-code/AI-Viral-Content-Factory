#!/usr/bin/env python3
"""Losslessly remove only the retired ``文案结构`` column from six topic tables."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.topic_structure_releases import TOPIC_FILES, TOPIC_HEADER, split_row

LEGACY_HEADER = TOPIC_HEADER + ["文案结构"]


def render(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def migrate(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.strip().startswith("|") and split_row(line) in (TOPIC_HEADER, LEGACY_HEADER)), None)
    if header_index is None:
        raise ValueError(f"{path.name} 找不到 v4.1/v4.2 选题表")
    if split_row(lines[header_index]) == TOPIC_HEADER:
        return False
    if header_index + 1 >= len(lines):
        raise ValueError(f"{path.name} 缺少表格分隔行")
    rewritten = lines[:]
    rewritten[header_index] = render(TOPIC_HEADER)
    rewritten[header_index + 1] = render(split_row(lines[header_index + 1])[:len(TOPIC_HEADER)])
    for index in range(header_index + 2, len(lines)):
        if not lines[index].strip().startswith("|"):
            break
        cells = split_row(lines[index])
        if len(cells) != len(LEGACY_HEADER):
            raise ValueError(f"{path.name} 第{index + 1}行不是十列；已停止迁移")
        rewritten[index] = render(cells[:len(TOPIC_HEADER)])
    path.write_text("\n".join(rewritten) + "\n", encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="只删除选题表末列“文案结构”；前九列和状态原样保留")
    parser.add_argument("--topic-dir", type=Path, default=ROOT / "02_资产中心" / "04_选题库" / "02_选题分类")
    args = parser.parse_args()
    changed = [filename for filename in TOPIC_FILES if migrate(args.topic_dir / filename)]
    print({"schema": "benchmark-topic-v4.2", "migrated": changed, "unchanged": len(TOPIC_FILES) - len(changed)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
