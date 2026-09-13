#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from tools.platform import skill_contract
except ModuleNotFoundError:
    import skill_contract


# Contract activation existed in the former registry.  V3 has no activation
# metadata, so ordinary registered Skills stay synchronizable without it.
activation_metadata = getattr(skill_contract, "activation_metadata", lambda root, registry, skill: {})


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "00_系统说明" / "system-registry.json"
SKIP_DIRS = {"__pycache__", ".pytest_cache", "outputs", "work", "smoke-pages", "smoke-test-work"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步AI爆款内容工厂 Skill 到Codex或WorkBuddy")
    parser.add_argument("--target", choices=["codex", "workbuddy"], required=True)
    parser.add_argument("--root", default=os.environ.get("AI_TRAFFIC_FACTORY_ROOT"))
    parser.add_argument("--install-root")
    parser.add_argument("--apply", action="store_true", help="执行同步；默认只检查")
    parser.add_argument("--skill", action="append", default=[])
    return parser.parse_args()


def load_registry(root: Path) -> dict:
    return json.loads((root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))


def parse_description(skill_md: Path) -> str:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if match:
        for line in match.group(1).splitlines():
            if line.startswith("description:"):
                return line.split(":", 1)[1].strip().strip('"')
    return f"使用{skill_md.parent.name}执行其正式业务合同。"


def product_name(registry: dict) -> str:
    # V3 registry keeps public identity on system; retain compatibility with
    # earlier registries that still expose a release block.
    return (registry.get("release") or {}).get("publicName") or registry["system"]["displayName"]


def skill_version(registry: dict, skill: dict) -> str:
    """Use explicit legacy contract versions when present, otherwise V3."""
    return str(skill.get("contractVersion") or registry["system"].get("version") or "1.0.0")


def skill_platforms(skill: dict) -> list[str]:
    """V3 skills are repository Codex skills unless a legacy list says otherwise."""
    return list(skill.get("platforms") or ["codex"])


def codex_files(root: Path, registry: dict, skill: dict) -> dict[str, bytes]:
    source = root / "10_Skills武器库" / skill["sourceDir"] / "SKILL.md"
    member_placeholder = "（会员专享）" in str(skill["sourceDir"]) and not source.is_file()
    if not source.is_file() and not member_placeholder:
        raise FileNotFoundError(f"注册 Skill 缺少 SKILL.md：{source}")
    description = (
        f"{skill['displayName']}为会员专享能力；公开包只提供安装识别入口，不包含执行内容。"
        if member_placeholder
        else parse_description(source)
    )
    canonical = f"10_Skills武器库/{skill['sourceDir']}/SKILL.md"
    display_name = product_name(registry)
    activation = activation_metadata(root, registry, skill)
    activation_step = ""
    if activation.get("required"):
        activation_step = (
            f"0. 正式执行前必须运行 `python run.py activate-skill {skill['id']} --repair --target codex`；"
            "只有合同激活结果为 approved 才能创建调度、生成 runtime 或发布正式文件。\n"
        )
    if member_placeholder:
        body = f"""---
name: {skill['id']}
description: {description}
---

# {skill['displayName']}

这是{display_name}的会员专享 Skill 公开安装入口。

当前合同版本：`{skill_version(registry, skill)}`。

该公开仓不含该 Skill 的执行内容；配置会员内容后再进行实际同步与调用。
"""
    else:
        body = f"""---
name: {skill['id']}
description: {description}
---

# {skill['displayName']}

这是{display_name}的 Codex 仓库级适配入口。

当前合同版本：`{skill_version(registry, skill)}`。

{activation_step}
1. 从当前工作区根目录完整读取 `{canonical}`。
2. 按中央注册表 `00_系统说明/system-registry.json` 校验版本、归属和状态。
3. 正式业务任务必须先经过小姜调度记录，再由所属Agent执行。
4. 所有产出写盘后必须取得小审审核回执，未放行不得交付。
5. 需要详细规则或脚本时，只读取源Skill直接引用的资源。
"""
    yaml = f"""interface:
  display_name: \"{skill['displayName']}\"
  short_description: \"{description[:100].replace(chr(34), chr(39))}\"
  default_prompt: \"使用 ${skill['id']} 按{display_name}正式调度和审核链执行任务。\"
"""
    summary_data = {
        "schema": "ai-traffic-installed-skill-v2",
        "id": skill["id"],
        "displayName": skill["displayName"],
        "version": skill_version(registry, skill),
        "sourceDir": skill["sourceDir"],
        "adapterPayloadSha256": digest({"SKILL.md": body.encode("utf-8"), "agents/openai.yaml": yaml.encode("utf-8")}),
    }
    if activation:
        summary_data["activation"] = activation
    summary = json.dumps(summary_data, ensure_ascii=False, indent=2) + "\n"
    return {"SKILL.md": body.encode("utf-8"), "agents/openai.yaml": yaml.encode("utf-8"), ".generated-manifest.json": summary.encode("utf-8")}


def iter_source_files(source: Path):
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if any(part in SKIP_DIRS for part in rel.parts) or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield rel, path.read_bytes()


def digest(files: dict[str, bytes]) -> str:
    h = hashlib.sha256()
    for name, content in sorted(files.items()):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(content)
    return h.hexdigest()


def directory_files(path: Path) -> dict[str, bytes]:
    if not path.is_dir():
        return {}
    return {rel.as_posix(): data for rel, data in iter_source_files(path)}


def expected_install_files(root: Path, registry: dict, skill: dict, target: str) -> dict[str, bytes]:
    if target == "codex":
        return codex_files(root, registry, skill)
    source = root / "10_Skills武器库" / skill["sourceDir"]
    files = {rel.as_posix(): data for rel, data in iter_source_files(source)}
    manifest = {
        "schema": "ai-traffic-installed-skill-v2",
        "id": skill["id"],
        "displayName": skill["displayName"],
        "version": skill_version(registry, skill),
        "sourceDir": skill["sourceDir"],
    }
    activation = activation_metadata(root, registry, skill)
    if activation:
        manifest["activation"] = activation
    files[".generated-manifest.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return files


def apply_files(target: Path, files: dict[str, bytes]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    # 安装副本必须与当前合同完全一致。只覆盖会留下旧 schema、脚本或参考资料，
    # 下一次运行仍可能被错误读取，因此同步时清掉参与合同摘要的残留文件。
    current = directory_files(target)
    for relative in sorted(set(current) - set(files), reverse=True):
        stale = target / relative
        if stale.is_file():
            stale.unlink()
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve() if args.root else PROJECT_ROOT
    registry = load_registry(root)
    selected = set(args.skill)
    if args.install_root:
        install_root = Path(args.install_root).expanduser().resolve()
    elif args.target == "codex":
        install_root = root / ".agents" / "skills"
    else:
        install_root = Path.home() / ".workbuddy" / "skills"

    failures = 0
    for raw_skill in registry["skills"]:
        skill = skill_contract.normalized_skill(root, registry, raw_skill)
        if args.target not in skill_platforms(skill):
            continue
        if args.target == "codex" and skill.get("codexDistribution") == "global-portable":
            if not selected or skill["id"] in selected or skill["displayName"] in selected:
                print(f"[PORTABLE] {skill['id']} -> 使用源码 scripts/install_to_codex.py 安装到用户级 Codex")
            continue
        if selected and skill["id"] not in selected and skill["displayName"] not in selected:
            continue
        files = expected_install_files(root, registry, skill, args.target)
        target = install_root / (skill["id"] if args.target == "codex" else skill["displayName"])
        current = directory_files(target)
        if digest(current) == digest(files):
            print(f"[OK] {skill['id']} -> {target}")
            continue
        if not args.apply:
            failures += 1
            print(f"[DRIFT] {skill['id']} -> {target}")
            continue
        apply_files(target, files)
        if digest(directory_files(target)) != digest(files):
            failures += 1
            print(f"[FAIL] {skill['id']} -> {target}")
        else:
            print(f"[SYNCED] {skill['id']} -> {target}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
