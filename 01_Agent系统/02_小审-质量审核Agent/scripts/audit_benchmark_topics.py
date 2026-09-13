#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.common import BRAND_FOOTER_SENTINEL, append_brand_footer


TABLE_HEADER = [
    "核心关键词", "选题", "原爆款元素", "博主名",
    "点赞数", "链接", "是否选中", "对标复刻拆解编号", "状态",
]

TOPIC_FILES = [
    "01_科学创业选题表.md",
    "02_能力成长选题表.md",
    "03_赚钱财富选题表.md",
    "04_个人IP选题表.md",
    "05_AI科技选题表.md",
    "99_其他类型选题表.md",
]


def split_row(line: str) -> List[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def parse_table(path: Path) -> Tuple[List[str], List[List[str]]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    header: List[str] = []
    rows: List[List[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = split_row(stripped)
        if not header:
            if all(set(cell.replace(":", "")) <= {"-"} for cell in cells if cell):
                continue
            header = cells
            continue
        if all(set(cell.replace(":", "")) <= {"-"} for cell in cells if cell):
            continue
        if len(cells) == len(header):
            rows.append(cells)
    return header, rows


def audit_topics(topic_dir: Path) -> Tuple[List[str], Dict[str, int]]:
    issues: List[str] = []
    counts: Dict[str, int] = {}
    seen_links: Dict[str, str] = {}

    for filename in TOPIC_FILES:
        path = topic_dir / filename
        if not path.is_file():
            issues.append(f"{filename} 不存在或不是文件")
            counts[filename] = 0
            continue
        text = path.read_text(encoding="utf-8")
        if text.count(BRAND_FOOTER_SENTINEL) != 1:
            issues.append(f"{filename} 品牌尾注不是唯一一次")
        if "**统计：**" not in text:
            issues.append(f"{filename} 缺少统计块")

        header, rows = parse_table(path)
        counts[filename] = len(rows)
        if header != TABLE_HEADER:
            issues.append(f"{filename} 表头不是 benchmark-topic-v4.2 九列合同")
        if not rows:
            issues.append(f"{filename} 没有任何正式选题行")

        for line_no, cells in enumerate(rows, start=1):
            if len(cells) != len(TABLE_HEADER):
                issues.append(f"{filename} 第{line_no}条不是9列")
                continue
            keyword, topic, _element, blogger, _likes, link, is_selected, benchmark_id, status = cells
            if not keyword or not topic or not blogger:
                issues.append(f"{filename} 第{line_no}条缺少核心关键词/选题/博主名")
            if link:
                owner = seen_links.get(link)
                if owner:
                    issues.append(f"{filename} 第{line_no}条链接与 {owner} 重复")
                else:
                    seen_links[link] = f"{filename} 第{line_no}条"
            ids = [item.strip() for item in __import__("re").split(r"<br\s*/?>|\r?\n", benchmark_id, flags=__import__("re").I) if item.strip()]
            if benchmark_id and (not ids or len(set(ids)) != len(ids) or any(not __import__("re").fullmatch(r"[A-Z]{3}-\d{3}", item) for item in ids)):
                issues.append(f"{filename} 第{line_no}条对标复刻拆解编号格式非法")
            if status and status not in {"待生成结构", "已生成结构", "已手动优化", "已生成正文"} and not __import__("re").fullmatch(r"已生成[一二三四五六七八九十]|已生成\d+", status):
                issues.append(f"{filename} 第{line_no}条状态非法：{status}")

    if sum(counts.values()) == 0:
        issues.append("六张选题表总行数为0")
    return issues, counts


def write_audit_record(record_dir: Path, topic_dir: Path, issues: List[str], counts: Dict[str, int]) -> Path:
    record_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = record_dir / f"{stamp}_爆款选题表恢复审核.md"
    result = "✅ 已放行" if not issues else "❌ 已退回"
    lines = [
        "# 爆款选题表恢复审核",
        "",
        f"- 审核对象：{topic_dir}",
        "- 审核依据：benchmark-topic-v4.2 / 9列 Markdown 选题库合同",
        f"- 小审结论：{result}",
        "",
        "## 行数统计",
        "",
    ]
    lines.extend(f"- {name}：{count} 条" for name, count in counts.items())
    lines.extend(["", "## 审核问题", ""])
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("- 无")
    path.write_text("\n".join(lines), encoding="utf-8")
    append_brand_footer(path)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="审核六张爆款选题表是否满足 benchmark-topic-v4.2 九列合同")
    parser.add_argument("--root", default=None, help="项目根目录")
    parser.add_argument("--topic-dir", default=None, help="爆款选题表目录")
    parser.add_argument("--record-dir", default=None, help="审核记录输出目录")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else ROOT
    topic_dir = Path(args.topic_dir).resolve() if args.topic_dir else root / "02_资产中心" / "04_选题库" / "02_选题分类"
    record_dir = Path(args.record_dir).resolve() if args.record_dir else root / "01_Agent系统" / "02_小审-质量审核Agent" / "99_审核记录"

    issues, counts = audit_topics(topic_dir)
    record = write_audit_record(record_dir, topic_dir, issues, counts)
    print({"status": "approved" if not issues else "rejected", "issues": len(issues), "record": str(record)})
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
