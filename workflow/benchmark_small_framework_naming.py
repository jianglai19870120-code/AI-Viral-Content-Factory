"""Mechanical safeguards for functional, human-readable small-framework names."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable, Mapping

_RAW_STAGE = re.compile(r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十]+)\s*(?:版本|\.0\s*方法论|方法论)")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\\|", "|"))


def validate_small_framework_names(rows: Iterable[Mapping[str, str]]) -> None:
    """Reject objective anti-patterns; semantic fit remains an independent review duty."""
    seen: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        block_id = str(row.get("编号") or "")
        label = str(row.get("小框架") or "").strip()
        content = str(row.get("小框架原文内容") or "")
        if not label:
            raise ValueError("小框架名称不能为空")
        if any(token in label.lower() for token in ("<br", "|", "\n", "\r")):
            raise ValueError("小框架名称不得包含表格或换行标记")
        if label in seen[block_id]:
            raise ValueError("同一 FNN 内的小框架名称不得重复")
        seen[block_id].add(label)
        compact_label = _normalize(label)
        compact_content = _normalize(content)
        if len(compact_label) >= 5 and compact_label in compact_content:
            raise ValueError("小框架名称不得直接照搬本段原文主题或标题")
        if _RAW_STAGE.search(label):
            raise ValueError("小框架名称不得使用原文的方法版本或方法论标题")
