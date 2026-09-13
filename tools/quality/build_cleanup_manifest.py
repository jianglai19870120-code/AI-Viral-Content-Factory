#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ROOT_TEMP = re.compile(r"^(?:_|99_temp|rewrite_|err\.txt|__del_probe)")
TOOL_DATA_NAMES = {
    "all_candidates_dump.txt", "detail_dump.txt", "judge_input.json", "llm_recall_input.json",
    "llm_recall_results.json", "migration_input.json", "migration_output.json", "migration_batch.json",
}
OBSOLETE_TOOLS = {
    "rewrite_yinian_real.py", "migrate_checklist_v2.py", "patch_v6_residual.py", "upgrade_topic_tables_v4.py",
    "build_process_registry.py", "_tmp_migrate_old.py", "_tmp_scan_old.py", "_tmp_rescan.py", "_tmp_scan_modules.py",
    "_tmp_sync_skill.py", "_tmp_analyze_exec.py",
}
AGENT_DUPLICATES = {"README.md", "能力清单.md", "输入合同.md", "输出合同.md", "调用规则.md"}
SKILL_DUPLICATES = {
    "README.md", "输入说明.md", "输出说明.md", "依赖说明.md", "公开状态.md",
    "migration.json", "sample-prompts.md", "anti-patterns.md",
}
LEGACY_WRAPPERS = {
    "tools/run.py", "tools/check_system_consistency.py", "tools/check_skill_install_contract.ps1",
    "tools/sync_installed_skills.py", "tools/sync_workbuddy_skills.py", "tools/check_public_release.ps1",
    "tools/prepare_public_release.ps1", "tools/sync_public_chain.py",
}


def category(root: Path, path: Path) -> str | None:
    relative = path.relative_to(root)
    text = relative.as_posix()
    if relative.parts and relative.parts[0] == "dist":
        return None
    if "__pycache__" in relative.parts or path.suffix.lower() == ".pyc":
        return "python-cache"
    if text.startswith(".workbuddy/"):
        if text == ".workbuddy/memory/MEMORY.md":
            return None
        return "workbuddy-local-history"
    if text.startswith("tools/_tmp") or text.startswith("tools/_match_batches/") or path.name in TOOL_DATA_NAMES or path.name.startswith("judge_batch_"):
        return "tools-temporary-data"
    if path.parent == root and ROOT_TEMP.match(path.name):
        return "root-one-off-script"
    if any(part.startswith("99_") and any(word in part for word in ("运行记录", "执行记录", "审核记录", "本地运行记录", "历史处理记录")) for part in relative.parts):
        return "runtime-history"
    if text.startswith("workflow/.") and path.suffix == ".json":
        return "legacy-workflow-state"
    if path.parent == root / "tools" and path.name in OBSOLETE_TOOLS:
        return "obsolete-migration-tool"
    if path.name in {"test_dry_copy_generation_stages.py", "test_dry_copy_mainline_rules.py"}:
        return "obsolete-test"
    if path.name in {"golden-sentence-rules.md", "V9到V10优化说明.md"}:
        return "obsolete-contract-reference"
    if text in LEGACY_WRAPPERS:
        return "legacy-compatibility-wrapper"
    if len(relative.parts) >= 3 and relative.parts[0] == "01_Agent系统" and path.name in AGENT_DUPLICATES:
        if (path.parent / "AGENT.md").is_file():
            return "superseded-agent-contract"
    if len(relative.parts) >= 3 and relative.parts[0] == "10_Skills武器库" and path.name in SKILL_DUPLICATES:
        return "superseded-skill-document"
    if path.name == "audit_final_drafts.py" and "02_小审-质量审核Agent" in text:
        return "obsolete-audit-executor"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="生成深度清理删除申请清单，不执行删除")
    parser.add_argument("--root")
    parser.add_argument("--output")
    parser.add_argument("--summary")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    output = Path(args.output).resolve() if args.output else root / ".runtime" / "cleanup-manifest.json"
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or output == path:
            continue
        group = category(root, path)
        if group:
            records.append({"path": path.relative_to(root).as_posix(), "category": group, "size": path.stat().st_size})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema": "ai-traffic-cleanup-v1", "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = Counter(item["category"] for item in records)
    sizes = Counter()
    for item in records:
        sizes[item["category"]] += item["size"]
    summary = Path(args.summary).resolve() if args.summary else root / "00_系统说明" / "删除申请清单.md"
    lines = [
        "# 深度清理删除申请清单",
        "",
        "> 本文件只申请删除，不执行删除。完整精确路径位于 `.runtime/cleanup-manifest.json`。",
        "",
        "| 类别 | 文件数 | 字节数 | 执行条件 |",
        "|---|---:|---:|---|",
    ]
    for key in sorted(counts):
        condition = "用户确认后删除"
        if key in {"superseded-agent-contract", "superseded-skill-document", "legacy-compatibility-wrapper"}:
            condition = "新合同与新入口验收通过且用户确认后删除"
        lines.append(f"| {key} | {counts[key]} | {sizes[key]} | {condition} |")
    lines.extend([
        "", f"合计：{len(records)} 个文件，{sum(item['size'] for item in records)} 字节。", "",
        "---", "", "• 带你3小时跑通用AI做IP，批量出爆款。",
        "• 有任何使用问题，可加入我们会员答疑群。", "• 我是姜来已来，微信： lact175", "", "---", "",
    ])
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({key: {"files": counts[key], "bytes": sizes[key]} for key in sorted(counts)}, ensure_ascii=False, indent=2))
    print(f"exact_manifest={output}")
    print(f"summary={summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
