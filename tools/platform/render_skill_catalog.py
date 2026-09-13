#!/usr/bin/env python3
"""Render public Skill catalogues from the V3 registry; never hand-edit them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from tools.platform.skill_contract import normalized_skill
except ModuleNotFoundError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.platform.skill_contract import normalized_skill


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_registry(root: Path) -> dict:
    return json.loads((root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))


def footer(text: str) -> str:
    return text.rstrip() + "\n\n---\n\n• 带你3小时跑通用AI做IP，批量出爆款。\n• 有任何使用问题，可加入我们会员答疑群。\n• 我是姜来已来，微信： lact175\n\n---\n"


def render_matrix(root: Path, registry: dict) -> str:
    agents = {item["id"]: item["displayName"] for item in registry["agents"]}
    rows = ["# Skill 公开状态矩阵", "", "> 自动生成；真源为 `00_系统说明/system-registry.json`。", "", "| Skill ID | 中文名称 | 归属 | 合同版本 | 执行类型 | 平台 | 发布状态 |", "|---|---|---|---|---|---|---|"]
    for raw in registry["skills"]:
        skill = normalized_skill(root, registry, raw)
        rows.append(f"| {skill['id']} | {skill['displayName']} | {agents[skill['owner']]} | {skill['contractVersion']} | {skill['executorType']} | {', '.join(skill['platforms'])} | {skill['releaseStatus']} |")
    return footer("\n".join(rows))


def render_mapping(root: Path, registry: dict) -> str:
    agents = {item["id"]: item["displayName"] for item in registry["agents"]}
    rows = ["# Skill 来源映射表", "", "> 自动生成；真源为 `00_系统说明/system-registry.json`。", "", "| Skill ID | 中文名称 | 当前归属 Agent | 唯一源码目录 | Codex 适配目录 |", "|---|---|---|---|---|"]
    for raw in registry["skills"]:
        skill = normalized_skill(root, registry, raw)
        rows.append(f"| {skill['id']} | {skill['displayName']} | {agents[skill['owner']]} | `10_Skills武器库/{skill['sourceDir']}/SKILL.md` | `.agents/skills/{skill['id']}/SKILL.md` |")
    return footer("\n".join(rows))


def targets(root: Path) -> dict[Path, str]:
    registry = load_registry(root)
    base = root / "00_系统说明"
    return {base / "Skill公开状态矩阵.md": render_matrix(root, registry), base / "Skill来源映射表.md": render_mapping(root, registry)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else PROJECT_ROOT
    values = targets(root)
    drift = []
    for path, content in values.items():
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != content:
            drift.append(path.relative_to(root).as_posix())
            if args.write:
                path.write_text(content, encoding="utf-8")
    print(json.dumps({"status": "synced" if args.write else ("drift" if drift else "ok"), "files": drift}, ensure_ascii=False))
    return 0 if args.write or not drift else 1


if __name__ == "__main__":
    raise SystemExit(main())
