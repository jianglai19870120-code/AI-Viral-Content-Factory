"""Mechanical safeguards for transferable small-framework role names."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Iterable, Mapping

_RAW_STAGE = re.compile(r"(?:\d+(?:\.\d+)?|[一二三四五六七八九十]+)\s*(?:版本|\.0\s*方法论|方法论)")
_STEP_ROLE = re.compile(r"^步骤(?:\d+|[一二三四五六七八九十]+)执行$")
DISPLAY_SEPARATOR = "－"

# Labels express how a segment advances its major framework, never the source
# topic, tool, product, example, or conclusion being discussed.
COMMON_ROLES = frozenset({
    "议题引入", "价值承诺", "范围预告", "成果主张", "量化举证", "成果归因",
    "身份背书", "反向背书", "能力举证", "判断抛出", "判断展开", "例证支撑",
    "原则收束", "方案提出", "步骤总领", "阶段过渡", "步骤校验", "价值收束",
    "行动条件", "行动指令", "后续行动引导", "痛点主张", "场景呈现",
    "认知冲突", "误区呈现", "原因诊断", "纠偏判断", "案例引入", "过程举证",
    "案例回扣", "推荐判断", "内容价值解释", "经历引入", "经历举证", "经历回扣",
})
ROLE_BY_MAJOR = {
    "我的成就": frozenset({"成果主张", "量化举证", "成果归因"}),
    "我的背书": frozenset({"身份背书", "反向背书", "能力举证"}),
    "提出选题": frozenset({"议题引入", "价值承诺", "范围预告"}),
    "价值承诺": frozenset({"承诺展开", "收益说明", "范围预告"}),
    "全文概述": frozenset({"议题引入", "价值承诺", "范围预告"}),
    "观点": frozenset({"判断抛出", "判断展开", "例证支撑", "原则收束"}),
    "解决方案": frozenset({"方案提出", "步骤总领", "阶段过渡", "步骤校验"}),
    "行动引导": frozenset({"行动条件", "行动指令", "后续行动引导"}),
    "痛点": frozenset({"痛点主张", "场景呈现", "认知冲突"}),
    "误区": frozenset({"误区呈现", "原因诊断", "纠偏判断"}),
    "案例": frozenset({"案例引入", "过程举证", "案例回扣"}),
    "推荐理由": frozenset({"推荐判断", "内容价值解释", "例证支撑"}),
    "我的经历": frozenset({"经历引入", "经历举证", "经历回扣"}),
    "总结": frozenset({"价值收束", "原则收束"}),
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\\|", "|"))


def _role_allowed(major: str, label: str) -> bool:
    allowed = ROLE_BY_MAJOR.get(major, COMMON_ROLES)
    return label in allowed or (major == "解决方案" and bool(_STEP_ROLE.fullmatch(label)))


def small_framework_role(major: str, label: str, group_size: int) -> str:
    """Return the role hidden inside a user-facing small-framework label.

    A single-row FNN must stand on its own in the four-column table, while a
    multi-row FNN already has its shared major context in the rows around it.
    """
    major, label = major.strip(), label.strip()
    if group_size == 1:
        prefix = f"{major}{DISPLAY_SEPARATOR}"
        if not label.startswith(prefix) or not label[len(prefix):].strip():
            raise ValueError("单行 FNN 的小框架必须使用“大框架－结构作用”格式")
        return label[len(prefix):].strip()
    if DISPLAY_SEPARATOR in label:
        raise ValueError("多行 FNN 的小框架不得重复大框架前缀，只能写结构作用")
    return label


def validate_small_framework_names(rows: Iterable[Mapping[str, str]], *, strict: bool = False) -> None:
    """Reject non-transferable labels; strict mode is required for new candidates.

    Historical owner-approved cases remain readable with ``strict=False``.
    New candidate receipts always use strict mode, so a content summary cannot
    enter the audited pipeline.
    """
    values = list(rows)
    group_sizes = Counter(str(row.get("编号") or "") for row in values)
    seen: dict[str, set[str]] = defaultdict(set)
    for row in values:
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
        major = str(row.get("大框架") or "").strip()
        role = small_framework_role(major, label, group_sizes[block_id]) if strict else label
        if strict and not _role_allowed(major, role):
            raise ValueError(
                "小框架必须使用所属大框架允许的结构作用词；"
                "不得以工具、产品、选题、案例或原文结论概述该段内容"
            )
