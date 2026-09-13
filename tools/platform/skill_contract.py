"""Current platform contract identifiers and V3 release metadata adapters."""
from __future__ import annotations

from pathlib import Path


STRUCTURE_SKILL_ID="copy-structure-generation"
COPY_SKILL_ID="final-copy-generation"
ACTIVE_SKILLS={STRUCTURE_SKILL_ID,COPY_SKILL_ID,"benchmark-video-structure-breakdown"}
MEMBER_EXCLUSIVE_SUFFIX = "（会员专享）"


def is_member_exclusive(skill: dict) -> bool:
    """Directory suffix is the canonical entitlement marker in registry V3."""
    return MEMBER_EXCLUSIVE_SUFFIX in str(skill.get("sourceDir") or "")


def normalized_skill(root: Path, registry: dict, skill: dict) -> dict:
    """Supply legacy release fields without bloating the V3 source registry."""
    source_root = root / "10_Skills武器库" / str(skill["sourceDir"])
    platforms = skill.get("platforms") or ["codex"]
    executor = skill.get("executorType")
    if not executor:
        executor = "script" if (source_root / "scripts").is_dir() else "instruction"
    return {
        **skill,
        "contractVersion": str(skill.get("contractVersion") or registry.get("system", {}).get("version") or "1.0.0"),
        "platforms": list(platforms),
        "executorType": executor,
        "releaseStatus": "member-exclusive" if is_member_exclusive(skill) else str(skill.get("releaseStatus") or "public"),
    }
