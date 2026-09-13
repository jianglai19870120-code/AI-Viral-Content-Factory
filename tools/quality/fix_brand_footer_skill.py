# -*- coding: utf-8 -*-
"""修复今日复盘-案例卡拆解Skill 下遗漏的旧"30天"品牌尾注 -> "3小时"。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workflow"))
from common import append_brand_footer_to_dir  # noqa: E402

skill_dir = ROOT / "10_Skills武器库" / "今日复盘-案例卡拆解Skill（会员专享）"
n = append_brand_footer_to_dir(skill_dir, "*.md", recursive=True)
print("已规范化（旧30天->新3小时）文件数:", n)
