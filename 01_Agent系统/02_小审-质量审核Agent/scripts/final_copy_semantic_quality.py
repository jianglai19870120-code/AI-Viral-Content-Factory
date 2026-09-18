"""Shared human-review gates for final-copy semantic quality."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workflow.writing_contract import rule_ids


def required_check_ids(binding: dict | None = None) -> tuple[str, ...]:
    """The V5 review checklist is the V3 contract's final-copy rule set."""
    if not isinstance(binding, dict):
        raise ValueError("V5 正文审核必须携带写作文案表达合同绑定")
    return tuple(rule_ids(binding, "final-copy"))
