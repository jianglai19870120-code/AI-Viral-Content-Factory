from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "00_系统说明" / "system-registry.json"


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("system", {}).get("id") not in {"ai-traffic-team", "ai-viral-content-factory"}:
        raise ValueError(f"无效系统注册表：{path}")
    return data


def skill_by_id(skill_id: str) -> dict[str, Any]:
    for skill in load_registry()["skills"]:
        if skill["id"] == skill_id:
            return skill
    raise KeyError(f"未登记Skill：{skill_id}")


def agent_by_id(agent_id: str) -> dict[str, Any]:
    for agent in load_registry()["agents"]:
        if agent["id"] == agent_id:
            return agent
    raise KeyError(f"未登记Agent：{agent_id}")
