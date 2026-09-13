#!/usr/bin/env python3
"""refresh_topic_stats.py — 重算选题表顶部统计块 + 自动校正「状态」列。

用法：
    python scripts/refresh_topic_stats.py --root <workspace-root>
    python scripts/refresh_topic_stats.py --output-dir <选题库目录>

功能：
- 读取 6 张 .md 选题表
- 依据已审核的发布索引自动校正每张表的「状态」列（末列），五态 + 空：
    空         ：是否选中 为空（未进入流水线）
    待选中     ：是否选中 为空
    待生成结构 ：是否选中=是 且无当前行的已审核发布索引绑定
    已生成结构 ：发布索引存在输出 hash、候选 hash 与 approved 回执均可核验的绑定
    已手动优化 ：结构四固定10节点（兼容11），至少3个内容节点，且至少含1个误区与1组不少于2步的方案节点
    已生成正文 ：由正文发布方写入同一条可核验发布绑定（正式正文、哈希、approved 回执齐全）
  （每轮全量重算，取「成稿 > 手动优化 > 已生成结构 > 待生成结构」最高态，不降级）
- 重算顶部统计块（五态漏斗：待选中 / 待生成结构 / 已生成结构 / 已手动优化 / 已生成正文）
- 只原位更新第九列“状态”与顶部统计；不删除、合并、重排或改写前八列

注意：
    结构状态只读取“选题—结构发布索引”，绝不按文件名前缀推断。
"""

import argparse
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from workflow.topic_structure_releases import parse_benchmark_case_ids, row_fingerprint, verified_final_copy, verified_release_bindings

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

# 列索引（状态列恢复为末列）
COL_TOPIC = 1
COL_IS_SELECTED = 6
COL_BENCHMARK_CASE_ID = 7
COL_STATUS = 8

STATES = ["待选中", "待生成结构", "已生成结构", "已手动优化", "已生成正文"]
CHINESE_COUNT = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def find_root() -> Path:
    """向上查找项目根目录（含 AGENTS.md 的目录）。"""
    p = Path(__file__).resolve().parent
    for _ in range(10):
        if (p / "AGENTS.md").exists():
            return p
        p = p.parent
    return Path.cwd()


def parse_cells(row_line: str) -> list:
    """把 markdown 表格行拆成单元格列表。"""
    line = row_line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def parse_table_rows(content: str):
    """从 markdown 文件内容中提取表格数据行。

    返回 (header_line, separator_line, data_rows) 三元组。
    """
    lines = content.split("\n")
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and any(
            h in stripped for h in TABLE_HEADER[:3]
        ):
            header_idx = i
            break

    if header_idx is None:
        return None, None, []

    header_line = lines[header_idx]
    sep_idx = header_idx + 1
    sep_line = lines[sep_idx] if sep_idx < len(lines) else ""

    data_rows = []
    for i in range(header_idx + 2, len(lines)):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        data_rows.append(lines[i])

    return header_line, sep_line, data_rows


def _path_ref(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def generated_label(count: int) -> str:
    return f"已生成{CHINESE_COUNT[count]}" if 0 < count < len(CHINESE_COUNT) else f"已生成{count}"


def derive_status(topic: str, is_selected: bool, benchmark_case_id: str, fingerprint: str) -> str:
    """Only a current release-index binding can prove a structure status."""
    if not is_selected:
        return ""  # 空：未选中，不进入流水线
    try:
        case_ids = parse_benchmark_case_ids(benchmark_case_id)
    except ValueError:
        return "待生成结构"
    bindings = verified_release_bindings()
    entries = [bindings.get((topic, case_id)) for case_id in case_ids]
    released = [entry for entry in entries if entry and str(entry.get("row_fingerprint") or "") == fingerprint]
    if len(case_ids) > 1:
        return generated_label(len(released)) if released else "待生成结构"
    entry = released[0] if released else None
    if entry and str(entry.get("row_fingerprint") or "") == fingerprint:
        if verified_final_copy(entry):
            return "已生成正文"
        return "已手动优化" if entry.get("structure_four_frozen") is True else "已生成结构"
    return "待生成结构"


def rebuild_file(path: Path) -> bool:
    """重写文件：替换统计块 + 校正「状态」列（保留所有行，不删除）。"""
    content = path.read_text(encoding="utf-8")
    header_line, sep_line, data_rows = parse_table_rows(content)
    if header_line is None:
        print(f"  [跳过] {path.name}：未找到表格头")
        return False

    funnel = {s: 0 for s in STATES}
    new_rows = []
    changed = False

    # 只更新派生状态列；任何业务字段、行顺序和重复记录均保持原样。
    for row_line in data_rows:
        cells = parse_cells(row_line)
        if len(cells) != len(TABLE_HEADER):
            raise ValueError(f"{path.name} 不是 benchmark-topic-v4.2 九列合同；请先执行迁移")
        topic = cells[COL_TOPIC].strip()
        is_sel = cells[COL_IS_SELECTED].strip()
        if not is_sel:
            funnel["待选中"] += 1
            st = ""  # 空
        elif is_sel != "是":
            st = ""  # 「否」明确排除在流水线及漏斗外
        else:
            fingerprint = row_fingerprint(dict(zip(TABLE_HEADER, cells)) | {"topic_table_relative_path": _path_ref(path)})
            st = derive_status(topic, True, cells[COL_BENCHMARK_CASE_ID].strip(), fingerprint)
            funnel["已生成结构" if st.startswith("已生成") else st] += 1

        cells[COL_STATUS] = st
        new_row = "| " + " | ".join(cells) + " |"
        if new_row != row_line.rstrip():
            changed = True
        new_rows.append(new_row)

    # 与旧统计块比对
    old = {}
    for line in content.split("\n"):
        for s in STATES:
            m = re.search(rf"{s}.*?共\s*(\d+)\s*条", line)
            if m:
                old[s] = int(m.group(1))

    stats_changed = not all(old.get(s) == funnel[s] for s in STATES)
    if not (stats_changed or changed):
        print(
            f"  [无变化] {path.name}："
            f"待选中={funnel['待选中']} 待生成结构={funnel['待生成结构']} "
            f"已生成结构={funnel['已生成结构']} 已手动优化={funnel['已手动优化']} "
            f"已生成正文={funnel['已生成正文']}"
        )
        return False

    sep_new = "| " + " | ".join(["----"] * len(TABLE_HEADER)) + " |"
    lines = []
    lines.append(f"# {path.stem}")
    lines.append("")
    lines.append("**统计：**")
    lines.append(f"*1、待选中选题（是否选中为空），共 {funnel['待选中']} 条*")
    lines.append(f"*2、待生成结构（已选中未生成），共 {funnel['待生成结构']} 条*")
    lines.append(f"*3、已生成结构，共 {funnel['已生成结构']} 条*")
    lines.append(f"*4、已手动优化，共 {funnel['已手动优化']} 条*")
    lines.append(f"*5、已生成正文，共 {funnel['已生成正文']} 条*")
    lines.append("")
    lines.append("| " + " | ".join(TABLE_HEADER) + " |")
    lines.append(sep_new)
    lines.extend(new_rows)
    lines.append("")
    lines.append("")

    # 保留文件末尾品牌尾注（如果有）
    footer_match = re.search(
        r"(\n---\n\n• 带你(?:30天|3小时).*?微信：\s*lact175.*?\n\n---)",
        content,
        re.DOTALL,
    )
    if footer_match:
        lines.append(footer_match.group(1))

    path.write_text("\n".join(lines), encoding="utf-8")
    changes = []
    if stats_changed:
        changes.append("统计块已更新")
    if changed:
        changes.append("状态列已校正")
    print(f"  [已更新] {path.name}：{'；'.join(changes)}")
    return True


def refresh_all(output_dir: Path) -> dict:
    """刷新所有选题表。返回汇总。"""
    summary = {"updated": 0, "unchanged": 0, "skipped": 0}
    for filename in TOPIC_FILES:
        path = output_dir / filename
        if not path.exists():
            print(f"  [跳过] {filename}：文件不存在")
            summary["skipped"] += 1
            continue
        changed = rebuild_file(path)
        if changed:
            summary["updated"] += 1
        else:
            summary["unchanged"] += 1
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="刷新选题表统计块（五态） + 自动校正状态列（待选中/待生成结构/已生成结构/已手动优化/已生成正文）"
    )
    parser.add_argument("--root", type=str, default=None, help="项目根目录（含 AGENTS.md）")
    parser.add_argument("--output-dir", type=str, default=None, help="选题库目录（默认 {root}/02_资产中心/04_选题库/02_选题分类）")
    args = parser.parse_args()

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        root = Path(args.root) if args.root else find_root()
        output_dir = root / "02_资产中心" / "04_选题库" / "02_选题分类"

    if not output_dir.exists():
        print(f"错误：选题库目录不存在：{output_dir}")
        sys.exit(1)

    print(f"刷新统计块 + 状态列：{output_dir}")
    print("状态来源：选题—结构发布索引（不按文件名推断）")
    summary = refresh_all(output_dir)
    print(
        f"\n汇总：更新 {summary['updated']} 张，"
        f"无变化 {summary['unchanged']} 张，跳过 {summary['skipped']} 张"
    )


if __name__ == "__main__":
    main()
