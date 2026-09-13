#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


TEXT_SUFFIXES = {".md", ".txt", ".py", ".json", ".jsonl", ".yaml", ".yml", ".ps1"}
MEMBER_EXCLUSIVE_SUFFIX = "（会员专享）"
ROOT_FILES = {
    "AGENTS.md", "README.md", "LICENSE", "CONTRIBUTING.md", "requirements.txt", "run.py",
    "requirements-dev.txt", "pyproject.toml", "CHANGELOG.md", ".gitignore", ".gitattributes",
    "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md", "CONTENT-RIGHTS.md", ".env.example",
}


def product_name(registry: dict) -> str:
    return registry["release"].get("publicName") or registry["system"]["displayName"]


def parse_description(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip().strip('"')
    return f"使用{path.parent.name}执行其正式业务合同。"

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.release.build_asset_manifest import build_manifest
from tools.platform.skill_contract import normalized_skill


def release_manifest(root: Path) -> tuple[Path, dict]:
    path = root / ".runtime" / "public-assets-manifest.json"
    try:
        return path, build_manifest(root, path)
    except PermissionError:
        fallback = Path(tempfile.gettempdir()) / "ai-traffic-factory-release" / root.name / "public-assets-manifest.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback, build_manifest(root, fallback)


def windows_path(path: Path) -> str:
    """Use the extended path namespace so deep Chinese asset paths can be packaged."""
    resolved = str(path.resolve())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved
    return resolved


def copy_file(root: Path, destination: Path, relative: str) -> None:
    source = root / relative
    target = destination / relative
    os.makedirs(windows_path(target.parent), exist_ok=True)
    try:
        shutil.copy2(windows_path(source), windows_path(target))
    except OSError as exc:
        raise RuntimeError(f"无法复制发布文件：{relative} -> {target} ({exc})") from exc


def is_member_exclusive(path: Path | str) -> bool:
    return any(MEMBER_EXCLUSIVE_SUFFIX in part for part in Path(path).parts)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(destination: Path) -> Path:
    target = destination / "release-checksums.json"
    files = []
    for path in sorted(destination.rglob("*")):
        if path.is_file() and path != target:
            files.append({"path": path.relative_to(destination).as_posix(), "sha256": file_sha256(path), "bytes": path.stat().st_size})
    target.write_text(json.dumps({"schema": "ai-traffic-release-checksums-v1", "files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def create_member_asset_placeholders(root: Path, destination: Path) -> None:
    asset_root = root / "02_资产中心"
    if not asset_root.is_dir():
        return
    for source_dir in sorted(path for path in asset_root.rglob("*") if path.is_dir()):
        relative = source_dir.relative_to(root)
        if not is_member_exclusive(relative):
            continue
        target_dir = destination / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        placeholder = target_dir / ".gitkeep"
        if not placeholder.exists():
            placeholder.write_text("", encoding="utf-8")


def github_package(root: Path, destination: Path) -> None:
    registry = json.loads((root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
    registered_source_dirs = {str(skill["sourceDir"]) for skill in registry["skills"]}
    registered_skill_ids = {str(skill["id"]) for skill in registry["skills"]}
    _, manifest = release_manifest(root)
    records = manifest["records"]
    for item in records:
        relative = item["path"]
        path = Path(relative)
        parts = path.parts
        canonical_skill_file = (
            len(parts) >= 3
            and parts[0] == "10_Skills武器库"
            and parts[1] in registered_source_dirs
            and (len(parts) == 3 and path.name == "SKILL.md" or len(parts) >= 4 and parts[2] in {"scripts", "references", "assets"})
        )
        obsolete_release_file = path.name in {
            "test_dry_copy_generation_stages.py", "test_dry_copy_mainline_rules.py", "audit_final_drafts.py"
        }
        allowed_core = (
            relative in ROOT_FILES
            or relative.startswith("00_系统说明/")
            or relative.startswith("schemas/")
            or relative.startswith(".github/workflows/")
            or (relative.startswith("01_Agent系统/") and (path.name == "AGENT.md" or "/scripts/" in relative or "/references/" in relative))
            or canonical_skill_file
            or relative.startswith("workflow/")
            or relative.startswith("tools/dispatch/")
            or relative.startswith("tools/quality/")
            or relative.startswith("tools/platform/")
            or relative.startswith("tools/release/")
            or relative.startswith("tools/dashboard/")
            or relative.startswith("tools/tests/")
            or (relative.startswith(".agents/skills/") and len(parts) >= 3 and parts[1] == "skills" and parts[2] in registered_skill_ids)
        )
        allowed_asset = (
            (relative.startswith("02_资产中心/") or relative.startswith("03_工作台/"))
            and item["status"] == "public"
        )
        member_placeholder = is_member_exclusive(path) and path.name == ".gitkeep"
        if is_member_exclusive(path) and not member_placeholder:
            continue
        if item["status"] == "public" and (allowed_core or allowed_asset or member_placeholder) and not obsolete_release_file and (root / relative).is_file():
            copy_file(root, destination, relative)
    create_member_asset_placeholders(root, destination)
    for raw_skill in registry["skills"]:
        skill = normalized_skill(root, registry, raw_skill)
        if skill.get("releaseStatus") != "member-exclusive" and not is_member_exclusive(skill["sourceDir"]):
            continue
        target_root = destination / "10_Skills武器库" / skill["sourceDir"]
        source_skill = root / "10_Skills武器库" / skill["sourceDir"] / "SKILL.md"
        description = parse_description(source_skill) if source_skill.is_file() else f"{skill['displayName']}会员专享入口。"
        target_root.mkdir(parents=True, exist_ok=True)
        (target_root / ".gitkeep").write_text("", encoding="utf-8")
        (target_root / "SKILL.md").write_text(
            "---\n"
            f"name: {skill['id']}\n"
            f"description: {description}\n"
            "---\n\n"
            f"# {skill['displayName']}\n\n"
            "该 Skill 属于会员专享能力，GitHub v1 基线只保留占位入口，不包含具体执行内容。\n",
            encoding="utf-8",
        )
    (destination / "PUBLIC_ASSETS_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def skillhub_package(root: Path, destination: Path) -> None:
    registry = json.loads((root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
    display_name = product_name(registry)
    destination.mkdir(parents=True, exist_ok=False)
    skill_md = f"""---
name: ai-traffic-team
description: {display_name}整套专家入口。用于在WorkBuddy中接收内容生产需求，按小姜调度、专业Agent执行、小审审核的正式链路调用书籍、播客、今日复盘、爆款选题、爆款开头、干货文案和IP视觉能力。
license: LICENSE
---

# {display_name}

先读取 `references/system-registry.json`，再根据任务读取对应 `references/skills/<id>.md`。任何产出都必须经过小审审核；缺少正式Skill的预留岗位必须退回。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
"""
    (destination / "SKILL.md").write_text(skill_md, encoding="utf-8")
    shutil.copy2(root / "LICENSE", destination / "LICENSE")
    ref_root = destination / "references"
    (ref_root / "skills").mkdir(parents=True)
    (ref_root / "schemas").mkdir(parents=True)
    shutil.copy2(root / "00_系统说明" / "system-registry.json", ref_root / "system-registry.json")
    shutil.copy2(root / "00_系统说明" / "schemas.md", ref_root / "schemas.md")
    for schema in (root / "schemas").glob("*.schema.json"):
        shutil.copy2(schema, ref_root / "schemas" / schema.name)
    for raw_skill in registry["skills"]:
        skill = normalized_skill(root, registry, raw_skill)
        if "skillhub" not in skill["platforms"]:
            continue
        source = root / "10_Skills武器库" / skill["sourceDir"] / "SKILL.md"
        target = ref_root / "skills" / f"{skill['id']}.md"
        if skill.get("releaseStatus") == "member-exclusive" or is_member_exclusive(skill["sourceDir"]):
            target.write_text(
                f"# {skill['displayName']}\n\n该 Skill 属于会员专享能力，公开包只保留入口占位，不包含具体执行内容。\n",
                encoding="utf-8",
            )
        else:
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    write_checksums(destination)
    files = [path for path in destination.rglob("*") if path.is_file()]
    unsupported = [path for path in files if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "LICENSE"]
    size = sum(path.stat().st_size for path in files)
    if unsupported:
        raise RuntimeError(f"SkillHub包包含非文本文件：{unsupported}")
    if len(files) > 300 or size > 10 * 1024 * 1024:
        raise RuntimeError(f"SkillHub包超限：files={len(files)}, size={size}")


def workbuddy_expert_package(root: Path, destination: Path) -> None:
    """构建 WorkBuddy Enterprise 企业专家插件包。"""
    registry = json.loads((root / "00_系统说明/system-registry.json").read_text(encoding="utf-8"))
    display_name = product_name(registry)
    _, manifest_data = release_manifest(root)
    rights = manifest_data["records"]
    public = {item["path"] for item in rights if item["status"] == "public"}
    destination.mkdir(parents=True, exist_ok=False)
    (destination / ".codebuddy-plugin").mkdir()
    (destination / "agents").mkdir()
    (destination / "skills").mkdir()
    manifest = {
        "name": "ai-traffic-team",
        "version": registry["system"]["version"],
        "description": f"{display_name}：小姜总控、专业Agent执行、小审审核的内容生产专家系统。",
        "author": {"name": "姜来已来"},
        "agents": ["./agents/ai-traffic-team.md"],
        "expertType": "agent",
        "agentName": "ai-traffic-team",
        "displayName": {"en": "AI Traffic Team", "zh": "姜来已来小助理"},
        "profession": {"en": "AI Content Team Orchestrator", "zh": "爆款内容工厂总控"},
        "displayDescription": {
            "en": "Routes content tasks to specialized roles and enforces quality review before delivery.",
            "zh": "统一接收内容生产需求，按小姜调度、专业岗位执行、小审审核完成交付。",
        },
        "categoryId": "06-ContentCreative",
        "defaultInitPrompt": {
            "zh": "嗨，我是姜来已来小助理。请告诉我你要处理的内容任务。",
            "en": "Tell me which content-production task you want the AI Traffic Team to handle.",
        },
        "tags": [
            {"en": "Content Workflow", "zh": "内容工作流"},
            {"en": "Multi-Agent", "zh": "多岗位协作"},
            {"en": "Quality Gate", "zh": "质量审核"},
        ],
        "quickPrompts": [
            {"en": "Turn a selected topic into a dry-goods script", "zh": "从已选选题生成干货型文案"},
            {"en": "Break down a book into reusable modules", "zh": "把一本书拆成可复用内容模块"},
            {"en": "Refresh work-journal case cards", "zh": "刷新今日复盘案例卡"},
        ],
    }
    (destination / ".codebuddy-plugin/plugin.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    agent_source = (root / "01_Agent系统/01_小姜-CEO助理Agent/AGENT.md").read_text(encoding="utf-8")
    agent_prompt = f"""---
name: ai-traffic-team
description: {display_name}总控专家。接收正式内容生产需求，读取中央注册表，路由到专业Skill，并确保任何产出经小审放行后交付。
displayName:
  en: AI Traffic Team
  zh: 姜来已来小助理
profession:
  en: AI Content Team Orchestrator
  zh: 爆款内容工厂总控
maxTurns: 80
---

""" + agent_source
    (destination / "agents/ai-traffic-team.md").write_text(agent_prompt, encoding="utf-8")
    shutil.copy2(root / "LICENSE", destination / "LICENSE")
    shutil.copy2(root / "00_系统说明/system-registry.json", destination / "system-registry.json")
    shutil.copy2(root / "00_系统说明/schemas.md", destination / "schemas.md")
    shutil.copytree(root / "schemas", destination / "schemas")
    for raw_skill in registry["skills"]:
        skill = normalized_skill(root, registry, raw_skill)
        source_root = root / "10_Skills武器库" / skill["sourceDir"]
        target_root = destination / "skills" / skill["sourceDir"]
        if skill.get("releaseStatus") == "member-exclusive" or is_member_exclusive(skill["sourceDir"]):
            target_root.mkdir(parents=True, exist_ok=True)
            (target_root / "SKILL.md").write_text(
                f"# {skill['displayName']}\n\n该 Skill 属于会员专享能力，专家包只保留入口占位，不包含具体执行内容。\n",
                encoding="utf-8",
            )
            continue
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            relative_source = source.relative_to(root).as_posix()
            canonical = source.name == "SKILL.md" or any(part in {"scripts", "references", "assets"} for part in source.relative_to(source_root).parts)
            if canonical and relative_source in public:
                target = target_root / source.relative_to(source_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)



def main() -> int:
    parser = argparse.ArgumentParser(description="构建GitHub、SkillHub或WorkBuddy专家发布包")
    parser.add_argument("target", choices=["github", "skillhub", "workbuddy-expert"])
    parser.add_argument("--root")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = Path(args.output).resolve() if args.output else root / "dist" / f"{args.target}-{stamp}"
    if destination.exists():
        raise RuntimeError(f"输出目录已存在，拒绝覆盖：{destination}")
    if args.target == "github":
        destination.mkdir(parents=True)
        github_package(root, destination)
    elif args.target == "skillhub":
        skillhub_package(root, destination)
    else:
        workbuddy_expert_package(root, destination)
    files = [path for path in destination.rglob("*") if path.is_file()]
    result = {"target": args.target, "output": str(destination), "files": len(files), "bytes": sum(p.stat().st_size for p in files)}
    write_checksums(destination)
    archive = Path(shutil.make_archive(str(destination), "zip", root_dir=destination))
    result["archive"] = str(archive)
    result["archive_bytes"] = archive.stat().st_size
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{file_sha256(archive)}  {archive.name}\n", encoding="ascii")
    result["archive_sha256"] = file_sha256(archive)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
