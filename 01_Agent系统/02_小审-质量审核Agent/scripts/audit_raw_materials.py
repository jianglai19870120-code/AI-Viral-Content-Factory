from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import sys
from pathlib import Path
_SELF = Path(__file__).resolve()
for _p in _SELF.parents:
    if (_p / "workflow" / "common.py").exists():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
from workflow.common import append_brand_footer_text as append_brand_footer

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


READABLE_MIN_CHARS = 300
BAD_PATTERNS = [
    "版权归原作者所有",
    "仅供学习交流",
    "免费下载",
    "更多电子书",
    "扫描整理",
]


@dataclass
class AuditItem:
    path: Path
    passed: bool
    issues: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="原始资料入库审核")
    default_root = Path(__file__).resolve().parents[3]
    parser.add_argument("--root", default=str(default_root))
    parser.add_argument("--scope", choices=["main"], default="main")
    parser.add_argument("--category", default="", help="指定分类目录，如 01_科学创业")
    parser.add_argument("--write-report", action="store_true", help="写入审核记录")
    parser.add_argument("--cleanup-source-files", action="store_true", help="审核通过后删除同目录旧原文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    base_dir = root / "02_资产中心" / "01_输入库" / "01_推荐好书-源文件"
    ledger_path = root / "02_资产中心" / "01_输入库" / "清单" / "书籍清单.md"
    report_dir = root / "01_Agent系统" / "02_小审-质量审核Agent" / "99_审核记录"
    target_dirs = [d for d in sorted(base_dir.iterdir()) if d.is_dir()]
    if args.category:
        target_dirs = [d for d in target_dirs if d.name == args.category]

    ledger_text = ledger_path.read_text(encoding="utf-8", errors="ignore") if ledger_path.exists() else ""
    results: list[AuditItem] = []

    for category_dir in target_dirs:
        for file_path in sorted(category_dir.glob("*.md")):
            results.append(audit_one(file_path, ledger_text))

    print_summary(results)
    deleted_files: list[Path] = []
    if args.cleanup_source_files:
        deleted_files = cleanup_source_files(results)
        if deleted_files:
            print(f"cleanup\t{len(deleted_files)}")
            for item in deleted_files:
                print(f"deleted\t{item}")
    if args.write_report:
        report_path = write_report(report_dir, args.scope, args.category or "全部分类", results, deleted_files)
        print(f"report\t{report_path}")
        refresh_dashboard(root)
    return 0 if all(item.passed for item in results) else 1


def audit_one(file_path: Path, ledger_text: str) -> AuditItem:
    issues: list[str] = []

    if file_path.suffix.lower() != ".md":
        issues.append("不是正式 md")

    if not re.match(r"^《[^》]+》\.md$", file_path.name):
        issues.append("文件名不符合《书名》.md")

    text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
    if len(text) < READABLE_MIN_CHARS:
        issues.append("正文过短，疑似不可读或未完整转码")

    hit_bad = [pattern for pattern in BAD_PATTERNS if pattern in text]
    if len(hit_bad) >= 2:
        issues.append("正文含较多下载站/扫描站噪音")

    if "## 第1页" in text and len(text.replace("## 第1页", "").strip()) < READABLE_MIN_CHARS:
        issues.append("疑似仅保留分页框架，正文不足")

    normalized_path = str(file_path).replace("\\", "/")
    marker = "02_资产中心/"
    rel_path = marker + normalized_path.split(marker, 1)[-1] if marker in normalized_path else file_path.name
    if f"`{rel_path}`" not in ledger_text:
        issues.append("未登记到书籍清单")

    return AuditItem(path=file_path, passed=not issues, issues=issues)


def print_summary(results: list[AuditItem]) -> None:
    passed = sum(1 for x in results if x.passed)
    failed = len(results) - passed
    print(f"[原始资料入库审核] passed={passed} failed={failed}")
    for item in results:
        if item.passed:
            print(f"pass\t{item.path}")
        else:
            print(f"fail\t{item.path}\t{'；'.join(item.issues)}")


def parse_title_author(stem: str) -> tuple[str, str]:
    stem = stem.strip()
    m = re.match(r"^《(?P<title>.+?)》$", stem)
    if m:
        return m.group("title").strip(), ""
    m = re.match(r"^《(?P<title>.+?)》(?P<author>.+)$", stem)
    if m:
        return m.group("title").strip(), m.group("author").strip()
    parts = re.split(r"[-_—｜|]+", stem)
    if len(parts) >= 2:
        return parts[0].strip(), parts[-1].strip()
    return stem, ""


def clean_title_text(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^《(.+?)》$", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[（(][^)）]{0,60}(完整版|全彩|扫描版|珍藏版|修订版|升级版|pdf|PDF|epub|mobi|azw3)[^)]*[)）]$", "", text)
    text = re.sub(r"(完整版|全彩版|扫描版|修订版|升级版|电子书|pdf|PDF|epub|mobi|azw3)$", "", text)
    text = re.sub(r"[【\[].*?(公众号|下载|资源|扫描|整理).*?[】\]]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -_—｜|")
    return text or "未命名资料"


def cleanup_source_files(results: list[AuditItem]) -> list[Path]:
    deleted: list[Path] = []
    for item in results:
        if not item.passed:
            continue
        md_path = item.path
        clean_title = clean_title_text(md_path.stem.strip("《》"))
        for sibling in md_path.parent.iterdir():
            if not sibling.is_file() or sibling == md_path:
                continue
            if sibling.suffix.lower() == ".md":
                continue
            title, _ = parse_title_author(sibling.stem)
            if clean_title_text(title) != clean_title:
                continue
            try:
                sibling.unlink()
                deleted.append(sibling)
            except Exception:
                continue
    return deleted


def write_report(report_dir: Path, scope: str, category: str, results: list[AuditItem], deleted_files: list[Path]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = report_dir / f"{stamp}_原始资料入库审核_{scope}_{category}.md"
    passed = sum(1 for x in results if x.passed)
    failed = len(results) - passed

    lines = [
        "# 原始资料入库审核记录",
        "",
        f"- 审核范围：{scope} / {category}",
        f"- 审核时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 审核结论：{'通过' if failed == 0 else ('退回' if passed == 0 else '部分退回')}",
        f"- 通过数：{passed}",
        f"- 退回数：{failed}",
        "",
        "## 审核结果",
        "",
    ]

    for item in results:
        if item.passed:
            lines.append(f"- 通过：`{item.path}`")
        else:
            lines.append(f"- 退回：`{item.path}`")
            for issue in item.issues:
                lines.append(f"  - {issue}")

    lines += [
        "",
        "## 原文件清理结果",
        "",
    ]
    if deleted_files:
        lines.append("- 本次已删除以下旧原文件，只保留正式 md：")
        for item in deleted_files:
            lines.append(f"  - `{item}`")
    else:
        lines.append("- 本次没有删除旧原文件。")

    report_path.write_text(append_brand_footer("\n".join(lines)), encoding="utf-8")
    return report_path


def refresh_dashboard(root: Path) -> None:
    script = root / "tools" / "build_xiaojiang_dashboard.py"
    if not script.exists():
        return
    subprocess.run([sys.executable, str(script)], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
