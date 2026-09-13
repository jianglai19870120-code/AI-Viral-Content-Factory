#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from workflow.common import BRAND_FOOTER_SENTINEL, append_brand_footer


FOOTER_BLOCK = re.compile(
    r"\n*---\s*\n+\s*• 带你(?:30天|3小时)跑通用AI做IP，批量出爆款。\s*\n+"
    r"\s*• 有任何使用问题，可加入我们会员答疑群。\s*\n+"
    r"\s*• 我是姜来已来，微信：\s*lact175\s*\n+(?:\s*---\s*\n*)?",
    re.MULTILINE,
)


def normalize(path: Path) -> bool:
    text = path.read_text(encoding="utf-8-sig")
    if text.count(BRAND_FOOTER_SENTINEL) <= 1 and "带你30天跑通用AI做IP，批量出爆款。" not in text:
        return False
    cleaned = FOOTER_BLOCK.sub("\n\n", text).rstrip() + "\n"
    path.write_text(cleaned, encoding="utf-8")
    append_brand_footer(path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="规范化重复品牌尾注，最终只保留文件末尾一个尾注块")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    changed = 0
    for raw in args.paths:
        base = Path(raw).resolve()
        candidates = base.rglob("*.md") if base.is_dir() else [base]
        for path in candidates:
            if normalize(path):
                changed += 1
                print(f"[NORMALIZED] {path}")
    print(f"normalized={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
