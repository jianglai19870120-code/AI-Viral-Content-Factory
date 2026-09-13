from __future__ import annotations

from pathlib import Path

from workflow.common import verify_dispatch_record
from workflow.registry import agent_by_id, skill_by_id


def require_assignment(*, task_type: str, agent_id: str, skill_id: str, input_keyword: str):
    agent = agent_by_id(agent_id)
    skill = skill_by_id(skill_id)
    if agent["status"] != "active":
        raise RuntimeError(f"Agent未启用：{agent_id}")
    if skill["status"] != "active" or skill["owner"] != agent_id:
        raise RuntimeError(f"Skill未启用或归属不匹配：{skill_id}")
    source = Path(__file__).resolve().parents[2] / "10_Skills武器库" / skill["sourceDir"] / "SKILL.md"
    if not source.is_file():
        raise RuntimeError(f"Skill合同缺失：{source}")
    return verify_dispatch_record(task_type, agent["displayName"], input_keyword)
