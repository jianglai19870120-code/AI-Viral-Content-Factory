"""Canonical active asset paths for the AI viral content factory.

Runtime code must import this module instead of embedding retired directory
names.  Historical records may retain their original paths, but are never
resolved through this registry.
"""
from __future__ import annotations

from pathlib import Path


ASSET_PATHS: dict[str, str] = {
    "input.books": "01_输入库/01_推荐好书-源文件",
    "input.podcasts": "01_输入库/02_热门播客-源文件（会员专享）",
    "input.events": "01_输入库/03_热点事件-源文件（会员专享）",
    "input.videos": "01_输入库/04_视频文案-源文件（会员专享）",
    "input.journals": "01_输入库/99_今日复盘-源文件（会员专享）",
    "process.views": "02_处理库/01_观点_内容模块",
    "process.pains": "02_处理库/02_痛点_内容模块（会员专享）",
    "process.misconceptions": "02_处理库/03_误区_内容模块",
    "process.solutions": "02_处理库/04_解决方案_内容模块",
    "process.cases": "02_处理库/05_案例_内容模块（会员专享）",
    "process.recommendations": "02_处理库/06_推荐理由_内容模块（会员专享）",
    "topics.accounts": "04_选题库/01_对标账号",
    "topics.tables": "04_选题库/02_选题分类",
    "cases.source": "05_案例库/01_对标视频原文",
    "cases.breakdowns": "05_案例库/02_对标复刻拆解",
    "output.structures": "03_输出库/01_文案结构",
    "output.structures.dry_goods": "03_输出库/01_文案结构/01_干货型文案结构",
    "output.structures.recommend": "03_输出库/01_文案结构/02_推荐型文案结构（会员专享）",
    "output.structures.acquisition": "03_输出库/01_文案结构/03_获客型文案结构（会员专享）",
    "output.copies": "03_输出库/02_正文成稿",
    "output.copies.dry_goods": "03_输出库/02_正文成稿/01_干货型",
    "gallery.dry_goods": "06_配图库/01_干货型配图",
    "gallery.recommend": "06_配图库/02_推荐型配图（会员专享）",
    "gallery.acquisition": "06_配图库/03_获客型配图（会员专享）",
    "gallery.podcast": "06_配图库/04_播客解读型配图（会员专享）",
    "gallery.events": "06_配图库/05_热点事件型配图（会员专享）",
}

MEMBER_ONLY_KEYS = {
    "input.podcasts", "input.events", "input.videos", "input.journals",
    "process.pains", "process.cases", "process.recommendations", "output.structures.recommend",
    "output.structures.acquisition", "gallery.recommend", "gallery.acquisition",
    "gallery.podcast", "gallery.events",
}


def relative(key: str) -> str:
    return ASSET_PATHS[key]


def resolve(project_root: Path, key: str) -> Path:
    return (project_root / "02_资产中心" / ASSET_PATHS[key]).resolve()


def active_paths(project_root: Path) -> dict[str, dict[str, object]]:
    return {
        key: {"relativePath": value, "exists": resolve(project_root, key).is_dir(), "memberOnly": key in MEMBER_ONLY_KEYS}
        for key, value in ASSET_PATHS.items()
    }
