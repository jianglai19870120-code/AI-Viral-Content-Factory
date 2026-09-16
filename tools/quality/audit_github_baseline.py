#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = Path("dist/github-baseline-audit")
MEMBER_EXCLUSIVE_SUFFIX = "（会员专享）"
FORBIDDEN_MARKERS = ("AI流量团队2.0", "E:" + chr(92) + "AI流量团队2.0")
TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".jsonl", ".yaml", ".yml", ".ps1", ".toml"}
ACTIVE_SCAN_ROOTS = (
    "run.py",
    "README.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "00_系统说明",
    "01_Agent系统",
    "10_Skills武器库",
    ".agents/skills",
    "workflow",
    "tools",
    "schemas",
)

import sys

sys.path.insert(0, str(PROJECT_ROOT))

from tools.platform.sync_skills import codex_files, digest, directory_files, load_registry
from tools.platform.skill_contract import normalized_skill
from tools.platform.render_skill_catalog import render_mapping, render_matrix
from tools.release.build_asset_manifest import build_manifest
from tools.release.public_policy import HOST_PATH_PATTERN, is_member_exclusive, release_violations
from tools.release.build_release import github_package
from workflow.common import append_brand_footer_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计 GitHub v1 基线的 Skill 同步、边界和旧名残留")
    parser.add_argument("--root")
    parser.add_argument("--output-dir")
    return parser.parse_args()


def collect_non_registry_dirs(root: Path, registry: dict) -> list[str]:
    registered = {skill["sourceDir"] for skill in registry["skills"]}
    extra = []
    for path in sorted((root / "10_Skills武器库").iterdir()):
        if not path.is_dir() or path.name in registered:
            continue
        if is_member_exclusive(path, directory=True):
            continue
        if path.name.startswith("__"):
            continue
        extra.append(path.name)
    return extra


def scan_old_name_markers(root: Path) -> list[dict]:
    matches: list[dict] = []
    for relative in ACTIVE_SCAN_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        files = [base] if base.is_file() else [p for p in base.rglob("*") if p.is_file()]
        for path in files:
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if path.name == "audit_github_baseline.py":
                continue
            for marker in FORBIDDEN_MARKERS:
                if marker in text:
                    matches.append({"path": path.relative_to(root).as_posix(), "marker": marker})
    return matches


def boundary_decisions(root: Path) -> list[dict]:
    decisions = []
    root_names = {entry.name.lower() for entry in os.scandir(root)}
    decisions.append({
        "path": "_TEMP/",
        "decision": "local-only",
        "reason": "人工清理记录目录，不属于运行主链，已按本地留痕处理。",
    })
    decisions.append({
        "path": "dist/",
        "decision": "local-only",
        "reason": "发布产物目录，不作为源码真源，基线仓不提交。",
    })
    decisions.append({
        "path": "schemas/",
        "decision": "include",
        "reason": "现役 JSON Schema 合同层，必须进入基线仓。",
    })
    decisions.append({
        "path": "CHANGELOG.md",
        "decision": "include",
        "reason": "版本变更说明，保留进基线仓。",
    })
    decisions.append({
        "path": "10_Skills武器库/ima-skills-1.1.9（会员专享）/",
        "decision": "local-only",
        "reason": "未注册会员目录，含 __MACOSX 和 .DS_Store，不进入 GitHub v1 基线仓。",
    })
    decisions.append({
        "path": "nul",
        "decision": "exclude",
        "reason": "Windows 保留设备名幽灵项，不作为真实文件处理。",
        "present_in_listing": "nul" in root_names,
    })
    return decisions


def audit_staged_package(root: Path) -> list[str]:
    """Validate the tree that will actually become the new public baseline."""
    failures: list[str] = []
    forbidden_parts = {"99_历史恢复材料", "调度记录", "人工确认回执", "00_正式审核回执", "__pycache__", "evidence"}
    with tempfile.TemporaryDirectory(prefix="ai-traffic-public-stage-") as temporary:
        stage = Path(temporary) / "github"
        stage.mkdir(parents=True)
        github_package(root, stage)
        for path in stage.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(stage)
            if any(part in forbidden_parts for part in relative.parts):
                failures.append(f"公开暂存包包含禁止路径：{relative.as_posix()}")
            if is_member_exclusive(relative) and path.name not in {".gitkeep", "SKILL.md"}:
                failures.append(f"公开暂存包泄露会员文件：{relative.as_posix()}")
            if path.suffix.lower() not in TEXT_SUFFIXES or path.name == "audit_github_baseline.py":
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_MARKERS):
                failures.append(f"公开暂存包包含旧项目路径：{relative.as_posix()}")
            if HOST_PATH_PATTERN.search(text):
                failures.append(f"公开暂存包包含本机绝对路径：{relative.as_posix()}")
    return failures


def audit_skills(root: Path, registry: dict) -> tuple[list[dict], list[str]]:
    failures: list[str] = []
    results: list[dict] = []
    matrix_text = render_matrix(root, registry)
    mapping_text = render_mapping(root, registry)
    matrix_path = root / "00_系统说明/Skill公开状态矩阵.md"
    mapping_path = root / "00_系统说明/Skill来源映射表.md"
    current_matrix = matrix_path.read_text(encoding="utf-8") if matrix_path.is_file() else ""
    current_mapping = mapping_path.read_text(encoding="utf-8") if mapping_path.is_file() else ""
    if current_matrix != matrix_text:
        failures.append("Skill公开状态矩阵与 system-registry.json 不一致")
    if current_mapping != mapping_text:
        failures.append("Skill来源映射表与 system-registry.json 不一致")

    skill_ids = {skill["id"] for skill in registry["skills"]}
    for raw_skill in registry["skills"]:
        skill = normalized_skill(root, registry, raw_skill)
        issues: list[str] = []
        source_root = root / "10_Skills武器库" / skill["sourceDir"]
        source_skill = source_root / "SKILL.md"
        adapter_root = root / ".agents" / "skills" / skill["id"]
        adapter_skill = adapter_root / "SKILL.md"
        portable_codex = skill.get("codexDistribution") == "global-portable"
        if not source_skill.is_file():
            issues.append("真源 SKILL.md 缺失")
        if "codex" in skill["platforms"]:
            if portable_codex:
                required_portable_files = (
                    source_root / "agents" / "openai.yaml",
                    source_root / "scripts" / "install_to_codex.py",
                    source_root / "scripts" / "build_portable_package.py",
                )
                if any(not path.is_file() for path in required_portable_files):
                    issues.append("Codex便携安装包缺少必需文件")
            elif not adapter_skill.is_file():
                issues.append("Codex 适配 SKILL.md 缺失")
        if skill["auditor"] not in skill_ids:
            issues.append(f"审核器未注册: {skill['auditor']}")
        if skill["releaseStatus"] == "member-exclusive" and MEMBER_EXCLUSIVE_SUFFIX not in skill["sourceDir"]:
            issues.append("注册表标记为 member-exclusive，但源码目录未带会员后缀")
        if skill["releaseStatus"] != "member-exclusive" and MEMBER_EXCLUSIVE_SUFFIX in skill["sourceDir"]:
            issues.append("源码目录带会员后缀，但注册表不是 member-exclusive")
        for schema_name in (skill["inputSchema"], skill["outputSchema"]):
            if str(schema_name).endswith(".schema.json") and not (root / "schemas" / schema_name).is_file():
                issues.append(f"Schema 缺失: {schema_name}")
        if adapter_root.is_dir() and not portable_codex:
            expected = codex_files(root, registry, skill)
            current = directory_files(adapter_root)
            if digest(expected) != digest(current):
                issues.append("Codex 适配目录与 sync-platform 生成结果不一致")
        if source_root.is_dir():
            stale_markers = []
            for path in source_root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for marker in FORBIDDEN_MARKERS:
                    if marker in text:
                        stale_markers.append(f"{path.relative_to(root).as_posix()} -> {marker}")
            if stale_markers:
                issues.append("存在旧项目名/旧绝对路径残留")
        status = "ok" if not issues else "fail"
        if issues:
            failures.extend(f"{skill['id']}: {issue}" for issue in issues)
        results.append({
            "id": skill["id"],
            "displayName": skill["displayName"],
            "version": skill["contractVersion"],
            "platforms": skill["platforms"],
            "status": status,
            "issues": issues,
        })
    return results, failures


def markdown_report(
    registry: dict,
    skill_results: list[dict],
    failures: list[str],
    boundary: list[dict],
    extra_skill_dirs: list[str],
    old_name_hits: list[dict],
    manifest_counts: dict,
) -> str:
    lines = [
        "# GitHub v1 基线审计报告",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 系统名：`{registry['system']['displayName']}`",
        f"- 系统版本：`{registry['system']['version']}`",
        f"- 注册 Skill 数量：`{len(skill_results)}`",
        f"- 结论：`{'通过' if not failures else '失败'}`",
        "",
        "## Skill 审计汇总",
        "",
        "| Skill | 版本 | 平台 | 结论 | 备注 |",
        "|---|---|---|---|---|",
    ]
    for item in skill_results:
        note = "；".join(item["issues"]) if item["issues"] else "同步正常"
        lines.append(
            f"| `{item['id']}` | `{item['version']}` | `{', '.join(item['platforms'])}` | "
            f"`{item['status']}` | {note} |"
        )
    lines.extend([
        "",
        "## 基线边界裁定",
        "",
        "| 路径 | 裁定 | 说明 |",
        "|---|---|---|",
    ])
    for item in boundary:
        lines.append(f"| `{item['path']}` | `{item['decision']}` | {item['reason']} |")
    lines.extend([
        "",
        "## 额外目录与残留",
        "",
        f"- 非注册 Skill 目录：{', '.join(f'`{name}`' for name in extra_skill_dirs) if extra_skill_dirs else '无'}",
        f"- 主链旧名残留：{len(old_name_hits)} 处",
        f"- 公开资产清单统计：`public={manifest_counts.get('public', 0)}` / `private={manifest_counts.get('private', 0)}` / `review_required={manifest_counts.get('review_required', 0)}`",
        "",
    ])
    if old_name_hits:
        lines.append("## 主链旧名残留明细")
        lines.append("")
        for hit in old_name_hits[:50]:
            lines.append(f"- `{hit['path']}` -> `{hit['marker']}`")
        lines.append("")
    if failures:
        lines.append("## 失败项")
        lines.append("")
        for failure in failures:
            lines.append(f"- {failure}")
        lines.append("")
    return append_brand_footer_text("\n".join(lines).rstrip() + "\n")


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve() if args.root else PROJECT_ROOT
    registry = load_registry(root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    requested_dir = Path(args.output_dir).resolve() if args.output_dir else root / REPORT_ROOT / stamp
    fallback_dir = Path(tempfile.gettempdir()) / "ai-traffic-factory-audits" / root.name / stamp
    report_dir = requested_dir
    try:
        report_dir.mkdir(parents=True, exist_ok=False)
    except PermissionError:
        report_dir = fallback_dir
        report_dir.mkdir(parents=True, exist_ok=False)
        print(f"[WARN] 无法写入 {requested_dir}，已改写到 {report_dir}")

    skill_results, failures = audit_skills(root, registry)
    extra_skill_dirs = collect_non_registry_dirs(root, registry)
    old_name_hits = scan_old_name_markers(root)
    if old_name_hits:
        failures.append(f"主链仍有旧名残留：{len(old_name_hits)} 处")
    boundary = boundary_decisions(root)
    failures.extend(release_violations(root))
    failures.extend(audit_staged_package(root))
    manifest_path = report_dir / "public-assets-manifest.json"
    manifest = build_manifest(root, manifest_path)
    counts = {
        status: sum(1 for item in manifest["records"] if item["status"] == status)
        for status in ("public", "private", "review_required")
    }

    report = {
        "schema": "ai-traffic-github-baseline-audit-v1",
        "generatedAt": datetime.now().isoformat(),
        "root": str(root),
        "status": "failed" if failures else "passed",
        "skills": skill_results,
        "boundary": boundary,
        "extraSkillDirs": extra_skill_dirs,
        "oldNameHits": old_name_hits,
        "manifestCounts": counts,
        "failures": failures,
    }
    (report_dir / "audit-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (report_dir / "audit-report.md").write_text(
        markdown_report(registry, skill_results, failures, boundary, extra_skill_dirs, old_name_hits, counts),
        encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "report_dir": str(report_dir), "failures": len(failures)}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
