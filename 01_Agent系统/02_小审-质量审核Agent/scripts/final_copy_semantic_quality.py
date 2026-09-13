"""Shared human-review gates for final-copy-v3 semantic quality."""
from __future__ import annotations


REQUIRED_CHECK_IDS = (
    "冻结内容覆盖",
    "非核心功能完成",
    "FNN推进连贯",
    "写作手法适配",
    "口播与事实边界",
    "逻辑不自相矛盾",
    "抽象表达可落地",
    "段落不跑题",
    "方案可执行可验证",
    "开头具备停留理由",
    "段落有新增推进",
    "口播完整连贯",
    "收束降低行动门槛",
)
