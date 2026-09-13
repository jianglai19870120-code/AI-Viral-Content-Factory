#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from workflow.common import append_brand_footer_text


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(append_brand_footer_text(text.rstrip() + "\n"), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="从中央注册表生成系统派生状态与Skill文档")
    parser.add_argument("--root")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    registry = json.loads((root / "00_系统说明/system-registry.json").read_text(encoding="utf-8"))
    agent_names = {item["id"]: item["displayName"] for item in registry["agents"]}

    matrix = [
        "# Skill 公开状态矩阵", "",
        "> 自动生成文件。请勿手工编辑；唯一真源为 `00_系统说明/system-registry.json`。", "",
        "| Skill ID | 中文名称 | 归属 | 合同版本 | 执行类型 | 平台 | 发布状态 |",
        "|---|---|---|---|---|---|---|",
    ]
    mapping = [
        "# Skill 来源映射表", "",
        "> 自动生成文件。请勿手工编辑；唯一真源为 `00_系统说明/system-registry.json`。", "",
        "| Skill ID | 中文名称 | 当前归属 Agent | 唯一源码目录 | Codex适配目录 | WorkBuddy安装目录 |",
        "|---|---|---|---|---|---|",
    ]
    for skill in registry["skills"]:
        matrix.append(f"| {skill['id']} | {skill['displayName']} | {agent_names[skill['owner']]} | {skill['contractVersion']} | {skill['executorType']} | {', '.join(skill['platforms'])} | {skill['releaseStatus']} |")
        codex_location = (
            f"用户级 `.codex/skills/{skill['id']}/SKILL.md`（便携安装包）"
            if skill.get("codexDistribution") == "global-portable"
            else f"`.agents/skills/{skill['id']}/SKILL.md`"
        )
        mapping.append(
            f"| {skill['id']} | {skill['displayName']} | {agent_names[skill['owner']]} | "
            f"`10_Skills武器库/{skill['sourceDir']}/SKILL.md` | {codex_location} | "
            f"`$HOME/.workbuddy/skills/{skill['displayName']}/SKILL.md` |"
        )
    _write(root / "10_Skills武器库/Skill公开状态矩阵.md", "\n".join(matrix))
    _write(root / "10_Skills武器库/Skill来源映射表.md", "\n".join(mapping))

    validation_path = root / ".runtime/validation-result.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8")) if validation_path.is_file() else {"status": "not-run"}
    cleanup_path = root / ".runtime/cleanup-manifest.json"
    cleanup = json.loads(cleanup_path.read_text(encoding="utf-8")) if cleanup_path.is_file() else {"records": []}
    state = {
        "schema": "ai-traffic-system-state-v2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "contractSource": "00_系统说明/system-registry.json",
        "system": registry["system"],
        "release": registry["release"],
        "agents": {"total": len(registry["agents"]), "active": sum(a["status"] == "active" for a in registry["agents"]), "reserved": sum(a["status"] == "reserved" for a in registry["agents"])},
        "skills": {"total": len(registry["skills"]), "active": sum(s["status"] == "active" for s in registry["skills"])},
        "validation": validation,
        "cleanup": {"remainingCandidates": len(cleanup.get("records", [])), "manifest": ".runtime/cleanup-manifest.json"},
    }
    state_path = root / "00_系统说明/system-state.json"
    try:
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except PermissionError:
        fallback = root / "dist" / "_local_checks" / "system-state.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"warning": f"无法写入 {state_path}", "fallback": str(fallback)}, ensure_ascii=False))
    print(json.dumps({"generated": 3, "skills": len(registry["skills"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
