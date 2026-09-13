"""好书解读-内容模块拆解 Skill —— 反模板门禁脚本（纯机械能力，不含任何自动生成）。

2026-08-06 范式反转后，本脚本只保留一项职责：

    validate_real_content(module_root, title)
        扫描指定书名下的 02_误区模块 / 03_步骤模块，命中旧版写死的六句通用废话即判定不合格。
        这是结构三（干货型文案结构生成）装配取用书源真实性的硬门禁。

正文创作由 LLM（Skill 流程）完成；晋升打标由 tools/promote_book_real.py 完成，
且 promote_book_real.py 会在打标前强制调用本门禁，0 命中才允许 source_quality:"real"。

本脚本**不再包含任何自动生成链路**（无 main 自动编排 / 无 candidate_quotes 硬编码金句池 /
无 infer_* 标题推导 / 无 promote_to_formal 候选晋升）。如需自动生成请回退到历史版本。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 锁死 ROOT：始终以本脚本所在位置向上 3 级推导项目根，不再读取 AI_TRAFFIC_FACTORY_ROOT，
# 避免输入/输出分裂到不同盘根（上一轮“重拆写错旧路径”事故的同源隐患）。
ROOT = Path(__file__).resolve().parents[3]

# 正式模块库（好书解读内容模块）固定派生自 ROOT，不再单独硬编码旧盘根路径。
PRIVATE_MODULE_ROOT = (
    ROOT / "02_资产中心" / "02_处理库" / "01_观点_内容模块" / "01_推荐好书"
)

# 反模板校验：旧版自动生成写死的六句通用废话。这是「唯一权威版本」，
# SKILL.md 中的六句必须与此逐字一致，禁止在派发 prompt 中改写其中任意一句。
GENERIC_MISTAKE_SENTENCES = (
    "把局部感受当成真实判断",
    "用完整计划逃避早期反馈",
    "忽略已经出现的反常信号",
)
GENERIC_STEP_SENTENCES = (
    "先把当前卡点写成可判断的问题",
    "再用一个低成本动作拿真实反馈",
    "最后根据反馈决定保留、调整或停止",
)

GENERIC_SENTENCES = GENERIC_MISTAKE_SENTENCES + GENERIC_STEP_SENTENCES


def _norm_title(title: str) -> str:
    return (title or "").strip().strip("《》").replace("（", "(").replace("）", ")")


def validate_real_content(module_root: Path, title: str) -> list[str]:
    """校验指定书名下的模块是否含旧版模板废话。

    返回不合格文件列表（空列表 = 该书全部合格）。
    仅扫描匹配该书名的文件（《书名》_NN_*.md），不影响其他书。
    """
    offenders: list[str] = []
    norm = _norm_title(title)
    for folder in ("02_误区模块", "03_步骤模块"):
        d = module_root / folder
        if not d.is_dir():
            continue
        for src in sorted(d.glob("*.md")):
            # 精确提取文件名中的《书名》并与书名比对，避免「习惯」误匹配「微习惯」。
            m = re.match(r"《(.+?)》", src.name)
            if not m or m.group(1) != norm:
                continue
            text = src.read_text(encoding="utf-8", errors="ignore")
            hit = [s for s in GENERIC_SENTENCES if s in text]
            if hit:
                offenders.append(f"{folder}/{src.name} <- {hit[0]}")
    return offenders


def main(argv: list[str] | None = None) -> int:
    """CLI：validate --title <书名>  返回命中列表，命中即退出码 1。"""
    parser = argparse.ArgumentParser(description="好书解读内容模块反模板门禁")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_val = sub.add_parser("validate", help="校验某本书的模块是否含模板废话")
    p_val.add_argument("--title", required=True, help="书名（可带或不带《》）")
    p_val.add_argument(
        "--root",
        default=str(PRIVATE_MODULE_ROOT),
        help="好书解读内容模块根目录（默认当前项目）",
    )
    args = parser.parse_args(argv)
    if args.cmd == "validate":
        offenders = validate_real_content(Path(args.root), args.title)
        if offenders:
            print(f"[门禁] title={args.title} 命中 {len(offenders)} 个不合格文件：")
            for o in offenders:
                print("  -", o)
            return 1
        print(f"[门禁] title={args.title} 通过：0 命中")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
