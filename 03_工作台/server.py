#!/usr/bin/env python3
"""AI爆款内容工厂本机工作台服务。

所有资产读取受白名单限制；正文生产由 Codex 桌面可见任务执行。
前端不能直接调用专业 Skill，也不能绕过小审审核门禁。
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
import ctypes
import hashlib
import itertools
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from collections import Counter
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

WORKBENCH_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WORKBENCH_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))
from workflow.asset_paths import relative as asset_relative, resolve as asset_resolve  # noqa: E402
FRONTEND_ROOT = WORKBENCH_ROOT / "frontend"
BRAND_SYSTEM_ROOT = WORKBENCH_ROOT / "01_品牌设计系统"
# Runtime state must not live in the repository. Codex can recreate the
# workspace under a different sandbox identity after restart, which makes
# repository-local SQLite files and redirected logs inaccessible.
RUNTIME_ROOT = Path(
    os.environ.get(
        "AI_VIRAL_WORKBENCH_RUNTIME",
        str(Path(os.environ.get("LOCALAPPDATA", str(WORKBENCH_ROOT))) / "AI-Viral-Content-Factory" / "workbench"),
    )
).resolve()
UPLOAD_ROOT = RUNTIME_ROOT / "uploads"
TODAY_TASK_RUNTIME_ROOT = RUNTIME_ROOT / "today-tasks"
DB_PATH = RUNTIME_ROOT / "workbench.db"
STORE_INITIALIZATION_LOCK = threading.RLock()
STORE_INITIALIZED_PATH: Path | None = None
INPUT_INVENTORY_LOCK = threading.RLock()
INPUT_INVENTORY_CACHE: tuple[float, dict[str, Any]] | None = None
FOLDER_SYNC_LOCK = threading.RLock()
PROMPT_ROOT = WORKBENCH_ROOT / "config" / "prompts"
TODAY_TASK_PROMPT_ROOT = PROMPT_ROOT / "today-tasks"
TODAY_MODULES_CONFIG = WORKBENCH_ROOT / "config" / "today-work-modules.json"
TODAY_CANDIDATE_ROOT = RUNTIME_ROOT / "asset-edit-candidates"
DESKTOP_BRIDGE_SCRIPT = WORKBENCH_ROOT / "scripts" / "codex_desktop_bridge.py"
DESKTOP_BRIDGE_AGENT_SCRIPT = WORKBENCH_ROOT / "scripts" / "codex_desktop_bridge_agent.py"
DESKTOP_BRIDGE_AGENT_PROCESS: subprocess.Popen[str] | None = None
ASSET_ROOT = PROJECT_ROOT / "02_资产中心"
# ``member-capabilities.json`` is retained only for legacy asset rows that do
# not have a registered content type. Registered member types unlock from their
# own formal output library instead of from a manually edited capability flag.
MEMBER_MANIFEST = WORKBENCH_ROOT / "config" / "member-capabilities.json"
CONTENT_TYPE_REGISTRY = WORKBENCH_ROOT / "config" / "content-types.json"
TOPIC_ROOT = asset_resolve(PROJECT_ROOT, "topics.tables")
STRUCTURE_ROOT = asset_resolve(PROJECT_ROOT, "output.structures")
COPY_ROOT = asset_resolve(PROJECT_ROOT, "output.copies")
GALLERY_ROOT = asset_resolve(PROJECT_ROOT, "gallery.dry_goods")
CASE_CARD_ROOT = asset_resolve(PROJECT_ROOT, "process.cases") / "01_案例卡"
BOOK_MODULE_INDEX = asset_resolve(PROJECT_ROOT, "process.views") / "01_推荐好书" / "05_模块索引" / "模块索引.jsonl"
SYSTEM_REGISTRY = PROJECT_ROOT / "00_系统说明" / "system-registry.json"
CANONICAL_SKILL_ROOT = PROJECT_ROOT / "10_Skills武器库"
CODEX_SKILL_ROOT = PROJECT_ROOT / ".agents" / "skills"
AGENT_AVATAR_ROOT = PROJECT_ROOT / "01_Agent系统" / "09_Agent头像资产" / "像素头像" / "raw_no_text"
FORMAL_AUDIT_ROOT = PROJECT_ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "00_正式审核回执"
AUDIT_RECEIPT_ROOT = FORMAL_AUDIT_ROOT / "dry-goods-copy" / "receipts"
LOCAL_CODEX_CLI = WORKBENCH_ROOT / "vendor" / "codex-cli" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"

BRAND_FONT_FILES = {
    "OPPOSans-Variable.ttf",
    "OPPOSans-Regular.ttf",
    "OPPOSans-Medium.ttf",
    "OPPOSans-Bold.ttf",
    "OPPOSans-Heavy.ttf",
}
BRAND_STATUS_FILES = {
    "available.svg",
    "running.svg",
    "needs-user.svg",
    "auditing.svg",
    "completed.svg",
    "planned.svg",
}
BRAND_COMMUNITY_FILES = {
    "community-intro-01.png",
    "community-intro-02.png",
    "community-intro-03.png",
    "community-wechat-qr.jpg",
    "vip-crown.png",
}

sys.path.insert(0, str(PROJECT_ROOT))
from workflow.common import BRAND_FOOTER  # noqa: E402
from workflow.data_center import (  # noqa: E402
    append_data_event,
    data_entities,
    data_events,
    load_snapshot,
    record_today_refresh_completion,
    refresh_data_center,
    verified_final_copy_bindings,
)
from workflow.topic_structure_releases import (  # noqa: E402
    parse_benchmark_case_ids,
    record_owner_frozen_structure,
    verified_release_bindings,
)
from workflow.benchmark_cases import (  # noqa: E402
    record_owner_approved_case_edit,
    validate_owner_approved_case_edit,
)
from workflow.benchmark_structure_v3 import normalize_portable_case_markdown, repair_table_divider  # noqa: E402
from workflow.input_inventory import rebuild_inventory, inventory_summary, video_active_batch, video_correction_batch, video_refresh_batch  # noqa: E402

IGNORED_FILE_NAMES = {".gitkeep", ".DS_Store", "Thumbs.db"}
IGNORED_DIR_NAMES = {"__pycache__", ".git"}
ALLOWED_ATTACHMENT_SUFFIXES = {".txt", ".md", ".pdf", ".doc", ".docx", ".xlsx", ".csv", ".mp3", ".m4a", ".wav", ".mp4", ".mov", ".png", ".jpg", ".jpeg", ".webp"}
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENTS_TOTAL_BYTES = 15 * 1024 * 1024
# ``submitted`` means only that the Desktop bridge has attempted the visible
# task submission.  It stays visible until Codex reports ``started`` or the
# confirmation deadline expires; it must never be silently treated as running.
ACTIVE_SESSION_STATUSES = {"creating-desktop-task", "submitted", "running", "repairing", "reconnecting", "needs-user", "waiting-audit"}
TERMINAL_SESSION_STATUSES = {"completed", "released", "rejected", "failed", "interrupted", "cancelled", "blocked", "expired"}
VISIBLE_TASK_EVENT_STATUS = {
    "started": "running",
    "repairing": "repairing",
    "reconnecting": "reconnecting",
    "waiting-user": "needs-user",
    "waiting-audit": "waiting-audit",
    "released": "released",
    "rejected": "rejected",
    "blocked": "blocked",
}
WORKBENCH_PORT = 8766
WORKBENCH_INSTANCE_ID = uuid.uuid4().hex[:12]
WORKBENCH_STARTED_AT = datetime.now().astimezone().isoformat(timespec="seconds")
WORKBENCH_BUILD = "workbench-v1.0.0"
# Legacy worker helpers below are retained only to inspect historical sessions.
# New copy tasks never route through an App Server or background worker.
COPY_PRODUCTION_SKILL_IDS = (
    "xiaojiang-dispatch",
    "copy-structure-generation",
    "final-copy-generation",
    "xiaoshen-audit",
)


def source(label: str, path: str, member: str | None = None, count_mode: str | None = None) -> dict[str, Any]:
    """Describe one visible asset source and, when needed, its business count."""
    return {"label": label, "path": path, "member": member, "countMode": count_mode}


ASSET_GROUPS: list[dict[str, Any]] = [
    {"stage": "input", "stageLabel": "输入库", "eyebrow": "找", "id": "benchmark", "title": "对标内容", "description": "现役对标账号资料", "sources": [source("对标账号", asset_relative("topics.accounts"))]},
    {"stage": "input", "stageLabel": "输入库", "eyebrow": "说", "id": "daily-review", "title": "每日复盘", "description": "今日复盘录音与真实经历", "sources": [source("今日复盘录音", asset_relative("input.journals"), "daily-review")]},
    {"stage": "input", "stageLabel": "输入库", "eyebrow": "学", "id": "learning", "title": "好书 · 播客 · 热点 · 视频", "description": "高密度知识与新鲜事件", "sources": [source("推荐好书", asset_relative("input.books")), source("热门播客", asset_relative("input.podcasts"), "podcast"), source("热点事件", asset_relative("input.events"), "hot-events"), source("视频文案", asset_relative("input.videos"), "video")]},
    {"stage": "process", "stageLabel": "处理库", "eyebrow": "筛选出", "id": "topics", "title": "爆款选题", "description": "九列爆款选题表", "sources": [source("爆款选题库", asset_relative("topics.tables"), count_mode="topic-rows-except-no")]},
    {"stage": "process", "stageLabel": "处理库", "eyebrow": "拆解出", "id": "modules", "title": "内容模块", "description": "现役观点、痛点、误区、方案、案例与推荐理由", "sources": [source("观点", asset_relative("process.views")), source("痛点", asset_relative("process.pains"), "video"), source("误区", asset_relative("process.misconceptions")), source("解决方案", asset_relative("process.solutions")), source("案例", asset_relative("process.cases"), "daily-review", count_mode="case-cards"), source("推荐理由", asset_relative("process.recommendations"))]},
    {"stage": "process", "stageLabel": "处理库", "eyebrow": "生成出", "id": "structures", "title": "文案结构", "description": "现役文案结构库", "sources": [source("干货型结构", asset_relative("output.structures.dry_goods")), source("推荐型结构", asset_relative("output.structures.recommend"), "recommend"), source("获客型结构", asset_relative("output.structures.acquisition"), "acquisition")]},
    {"stage": "output", "stageLabel": "输出库", "eyebrow": "正式输出", "id": "final-copy", "title": "短视频爆款成稿", "description": "小审放行后的正式内容", "sources": [source("干货型成稿", asset_relative("output.copies.dry_goods"), count_mode="copy-topics")]},
]
GROUP_BY_ID = {item["id"]: item for item in ASSET_GROUPS}

# Asset-center directory map.  This is deliberately a finite allow-list:
# browsers receive labels and ids only, never arbitrary local paths.
def catalog_item(item_id: str, label: str, relative_path: str, *, member_only: bool = False, kind: str = "asset") -> dict[str, Any]:
    return {"id": item_id, "label": label, "relativePath": relative_path, "memberOnly": member_only, "kind": kind}


ASSET_CATALOG: list[dict[str, Any]] = [
    {"id": "input", "label": "输入库", "icon": "inbox", "kind": "flow", "items": [
        catalog_item("input-books", "推荐好书", asset_relative("input.books")),
        catalog_item("input-podcasts", "热门播客", asset_relative("input.podcasts"), member_only=True),
        catalog_item("input-events", "热点事件", asset_relative("input.events"), member_only=True),
        catalog_item("input-videos", "视频文案", asset_relative("input.videos"), member_only=True),
        catalog_item("input-journals", "今日复盘", asset_relative("input.journals"), member_only=True),
    ]},
    {"id": "process", "label": "处理库", "icon": "layers", "kind": "flow", "items": [
        catalog_item("process-views", "观点内容模块", asset_relative("process.views")),
        catalog_item("process-pains", "痛点内容模块", asset_relative("process.pains"), member_only=True),
        catalog_item("process-misconceptions", "误区内容模块", asset_relative("process.misconceptions")),
        catalog_item("process-solutions", "解决方案内容模块", asset_relative("process.solutions")),
        catalog_item("process-cases", "案例内容模块", asset_relative("process.cases"), member_only=True),
        catalog_item("process-recommendations", "推荐理由内容模块", asset_relative("process.recommendations")),
    ]},
    {"id": "output", "label": "输出库", "icon": "output", "kind": "flow", "items": [
        catalog_item("output-structures", "文案结构", asset_relative("output.structures")),
        catalog_item("output-copies", "正文成稿", asset_relative("output.copies")),
    ]},
    {"id": "topics", "label": "选题库", "icon": "target", "kind": "asset", "items": [
        catalog_item("topic-accounts", "对标账号", asset_relative("topics.accounts")),
        catalog_item("topic-tables", "选题分类", asset_relative("topics.tables")),
    ]},
    {"id": "cases", "label": "案例库", "icon": "layers", "kind": "asset", "items": [
        catalog_item("case-sources", "对标视频原文", asset_relative("cases.source")),
        catalog_item("case-breakdowns", "案例结构拆解", asset_relative("cases.breakdowns")),
    ]},
    {"id": "gallery", "label": "配图库", "icon": "gallery", "kind": "asset", "items": [
        catalog_item("gallery-dry-goods", "干货型配图", asset_relative("gallery.dry_goods")),
        catalog_item("gallery-recommend", "推荐型配图", asset_relative("gallery.recommend"), member_only=True),
        catalog_item("gallery-acquisition", "获客型配图", asset_relative("gallery.acquisition"), member_only=True),
        catalog_item("gallery-podcast", "播客解读型配图", asset_relative("gallery.podcast"), member_only=True),
        catalog_item("gallery-events", "热点事件型配图", asset_relative("gallery.events"), member_only=True),
    ]},
    {"id": "skills", "label": "Skills 武器库", "icon": "puzzle", "kind": "skills", "items": [
        catalog_item("skill-books", "好书解读-内容模块拆解Skill", "10_Skills武器库/好书解读-内容模块拆解Skill", kind="skill"),
        catalog_item("skill-podcasts", "播客解读-内容模块拆解Skill（会员专享）", "10_Skills武器库/播客解读-内容模块拆解Skill（会员专享）", member_only=True, kind="skill"),
        catalog_item("skill-videos", "视频文案-痛点卡拆解Skill（会员专享）", "10_Skills武器库/视频文案-痛点卡拆解Skill（会员专享）", member_only=True, kind="skill"),
        catalog_item("skill-journals", "今日复盘-案例卡拆解Skill（会员专享）", "10_Skills武器库/今日复盘-案例卡拆解Skill（会员专享）", member_only=True, kind="skill"),
        catalog_item("skill-topics", "爆款选题分类Skill", "10_Skills武器库/爆款选题分类Skill", kind="skill"),
        catalog_item("skill-cases", "对标视频-结构拆解Skill（会员专享）", "10_Skills武器库/对标视频-结构拆解Skill（会员专享）", member_only=True, kind="skill"),
        catalog_item("skill-structures", "文案结构生成 Skill", "10_Skills武器库/文案结构生成 Skill", kind="skill"),
        catalog_item("skill-copies", "正文成稿生成 Skill", "10_Skills武器库/正文成稿生成 Skill", kind="skill"),
        catalog_item("skill-inventory", "原始资料入库统计Skill", "10_Skills武器库/原始资料入库统计Skill", kind="skill"),
        catalog_item("skill-gallery", "IP视觉PPT生成Skill", "10_Skills武器库/IP视觉PPT生成Skill", kind="skill"),
    ]},
]
CATALOG_BY_ID = {item["id"]: item for item in ASSET_CATALOG}
CATALOG_ITEM_BY_ID = {item["id"]: item for section in ASSET_CATALOG for item in section["items"]}
# Today's file-open actions use explicit keys instead of accepting a browser
# supplied path.  This keeps the workbench constrained to formal asset roots.
TODAY_FOLDER_TARGETS = {
    "dry-goods-copy": COPY_ROOT,
    "dry-goods-structure": STRUCTURE_ROOT,
    "topics": TOPIC_ROOT,
}
TODAY_FOLDER_LABELS = {
    "dry-goods-copy": "干货型成稿库",
    "dry-goods-structure": "干货型结构4",
    "topics": "爆款选题表",
}
CHECKMARK_PREFIXES = ("√", "✓")
TODAY_EDITOR_SURFACES = {
    "copy": {"label": "干货型正文", "root": COPY_ROOT, "kind": "markdown"},
    "structure": {"label": "干货型爆款结构4", "root": STRUCTURE_ROOT, "kind": "markdown"},
    "topics": {"label": "爆款选题表", "root": TOPIC_ROOT, "kind": "topic-table"},
    "cases": {"label": "对标复刻拆解", "root": ASSET_ROOT / "05_案例库" / "02_对标复刻拆解", "kind": "markdown"},
}
BRAND_STYLESHEET_FILES = {"tokens.css"}
# 网页内由工作区所有者手动编辑的正文、爆款选题表与爆款结构，修改本身就是最终确认。
# 这三类编辑直接更新正式资产，不创建候选，也不进入小审队列。
OWNER_DIRECT_EDIT_SURFACES = {"copy", "topics", "structure"}
MAX_EDITOR_FILE_BYTES = 8 * 1024 * 1024
def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_asset_path(relative: str) -> Path:
    path = (ASSET_ROOT / relative).resolve()
    if not path.is_relative_to(ASSET_ROOT.resolve()):
        raise ValueError("资产路径不在允许范围内")
    return path


def _launch_folder(path: Path, *, label: str) -> dict[str, Any]:
    """Open a verified local directory through the interactive desktop bridge."""
    if sys.platform == "win32":
        return queue_desktop_folder(path, label=label)
    failure: list[OSError] = []
    finished = threading.Event()

    def launch() -> None:
        try:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as exc:
            failure.append(exc)
        finally:
            finished.set()

    threading.Thread(target=launch, daemon=True, name="workbench-open-folder").start()
    finished.wait(0.35)
    if failure:
        raise RuntimeError(f"无法打开{label}：{failure[0]}") from failure[0]
    return {"opened": True, "status": "launch-requested", "launchMode": "system-opener"}


class EditorConflictError(RuntimeError):
    """The browser attempted to save an asset that changed after it was read."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _today_editor_surface(surface: str) -> dict[str, Any]:
    item = TODAY_EDITOR_SURFACES.get(surface)
    if item is None:
        raise ValueError("未知今日工作编辑入口")
    root = Path(item["root"]).resolve()
    if not root.is_relative_to(ASSET_ROOT.resolve()) or not root.is_dir():
        raise FileNotFoundError("今日工作编辑目录不存在")
    return {**item, "root": root}


def _today_editor_file_id(surface: str, path: Path) -> str:
    digest = hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]
    return f"{surface}_{digest}"


def _project_relative_path(path: Path) -> str:
    """Display a project-relative path without relying on Windows 8.3 aliases."""
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _today_editor_paths(surface: str) -> list[Path]:
    config = _today_editor_surface(surface)
    root = config["root"]
    paths: list[Path] = []
    for path in sorted(root.rglob("*.md"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
        if path.name in IGNORED_FILE_NAMES or path.name == "README.md":
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > MAX_EDITOR_FILE_BYTES:
            continue
        paths.append(path)
    return paths


def _case_editor_type_from_title(path: Path) -> str:
    """Keep manually added legacy cases discoverable when not yet registered."""
    title = path.stem.lstrip("√✓").strip()
    candidate = title.split("_", 1)[0].strip() if "_" in title else ""
    return candidate or "未归类"


def _case_editor_registry_type_index() -> tuple[dict[Path, str], list[str]]:
    """Map present formal paths to their registered type without hard-coded UI types."""
    paths: dict[Path, str] = {}
    ordered_types: list[str] = []
    for entry in _case_registry_entries():
        case_type = str(entry.get("type") or "").strip()
        if case_type and case_type not in ordered_types:
            ordered_types.append(case_type)
        breakdown = _case_breakdown_path(str(entry.get("breakdownPath") or ""))
        if breakdown and case_type:
            paths[breakdown.resolve()] = case_type
    return paths, ordered_types


def _case_editor_type_catalog(files: list[dict[str, Any]], ordered_types: list[str]) -> list[str]:
    present = {str(item.get("caseType") or "").strip() for item in files}
    present.discard("")
    ranked = [case_type for case_type in ordered_types if case_type in present]
    remaining = sorted(present.difference(ranked).difference({"未归类"}))
    return ranked + remaining + (["未归类"] if "未归类" in present else [])


def _structure_four_has_content(path: Path) -> bool:
    """Return whether every visible Structure 4 row has user content.

    A manually completed structure can predate the freeze index.  In that case
    the filename has no check mark and there is no release binding, but the
    Structure 4 table itself is already filled.  The editor must recognize
    that state instead of showing a false ``待冻结`` result.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return False
    in_section = False
    table_started = False
    rows: list[list[str]] = []
    for raw in lines:
        line = raw.strip()
        if re.match(r"^##\s+结构四\s*$", line):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not table_started:
            # Skip the header and its Markdown divider.
            table_started = True
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    # A valid structure-four table has data rows and no empty core-content cell.
    return bool(rows) and all(len(row) >= 3 and row[2] for row in rows)


def _structure_four_editor_state(path: Path) -> dict[str, Any]:
    """Use freeze binding when present, otherwise inspect Structure 4 content."""
    content_filled = _structure_four_has_content(path)
    owner_checked = _is_checked_filename(path)
    try:
        current_hash = _sha256_file(path)
        for binding in verified_release_bindings().values():
            output_path = Path(str(binding.get("output_path") or ""))
            if output_path.resolve() == path.resolve():
                frozen = bool(binding.get("structure_four_frozen")) and str(binding.get("output_sha256") or "") == current_hash
                return {
                    "structureFourFilled": owner_checked or frozen or content_filled,
                    "structureFourStatus": "已填写结构四" if owner_checked else ("已冻结结构四" if frozen else ("已填写结构四" if content_filled else "待冻结结构四")),
                    "structureFourReason": "" if (owner_checked or frozen or content_filled) else "结构四尚未填写完整。",
                }
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return {
        "structureFourFilled": owner_checked or content_filled,
        "structureFourStatus": "已填写结构四" if (owner_checked or content_filled) else "待冻结结构四",
        "structureFourReason": "" if (owner_checked or content_filled) else "未找到已冻结绑定，且结构四表格尚未填写完整。",
    }


def _today_editor_files(surface: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    case_type_index, case_type_order = _case_editor_registry_type_index() if surface == "cases" else ({}, [])
    for source_path in _today_editor_paths(surface):
        path = _promote_owner_marked_structure_candidate(source_path) if surface == "structure" else source_path
        item = {
            "id": _today_editor_file_id(surface, path),
            "label": path.stem,
            "relativePath": _project_relative_path(path),
            "pending": not _is_checked_filename(path),
            "modifiedAt": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
        }
        item.update(_candidate_state(surface, path))
        if item.get("candidateFilename"):
            item["label"] = str(item["candidateFilename"])
        if surface == "copy":
            item.update(_copy_editor_check_state(path, item))
        if surface == "structure":
            item.update(_structure_four_editor_state(path))
            item["pending"] = not item["structureFourFilled"]
        if surface == "cases":
            item["caseType"] = case_type_index.get(path.resolve()) or _case_editor_type_from_title(path)
        files.append(item)
    return files


def _today_editor_resolve_file(surface: str, file_id: str) -> Path:
    config = _today_editor_surface(surface)
    for path in _today_editor_paths(surface):
        if secrets.compare_digest(_today_editor_file_id(surface, path), file_id):
            resolved = path.resolve()
            if resolved.is_relative_to(config["root"]) and resolved.is_file():
                return resolved
    raise FileNotFoundError("编辑文件不存在或已不在允许列表中")


def _today_editor_filename(path: Path, value: Any) -> Path:
    """Validate an in-page Markdown filename change before renaming the file."""
    name = str(value or "").strip()
    if name.lower().endswith(".md"):
        name = name[:-3].rstrip()
    if not name or name in {".", ".."}:
        raise ValueError("文件名不能为空")
    if len(name) > 180 or any(character in name for character in '<>:"/\\|?*'):
        raise ValueError("文件名包含不允许的字符")
    target = path.with_name(f"{name}.md").resolve()
    if not target.is_relative_to(path.parent.resolve()):
        raise ValueError("文件名不允许包含目录")
    if target != path.resolve() and target.exists():
        raise ValueError("同名文件已存在，请换一个名称")
    return target


TOPIC_TABLE_COLUMNS = ["核心关键词", "选题", "原爆款元素", "博主名", "点赞数", "链接", "是否选中", "对标复刻拆解编号", "状态"]


def today_topic_benchmark_cases() -> dict[str, Any]:
    """Return only registered, present benchmark breakdowns for topic-table selection."""
    registry_path = PROJECT_ROOT / "00_系统说明" / "benchmark-case-registry.json"
    breakdown_root = asset_resolve(PROJECT_ROOT, "cases.breakdowns").resolve()
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取对标案例注册表：{exc}") from exc
    cases: list[dict[str, Any]] = []
    for item in registry.get("cases", []):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id") or "").strip()
        relative_path = str(item.get("breakdownPath") or "").strip()
        candidate = (PROJECT_ROOT / relative_path).resolve()
        if not re.fullmatch(r"[A-Z]+-\d{3}", case_id) or not candidate.is_relative_to(breakdown_root) or not candidate.is_file() or candidate.suffix.lower() != ".md":
            continue
        cases.append({
            "id": case_id,
            "title": str(item.get("breakdownTitle") or candidate.stem),
            "type": str(item.get("type") or ""),
            "memberOnly": "（会员专享）" in candidate.relative_to(breakdown_root).as_posix(),
        })
    return {"cases": sorted(cases, key=lambda item: item["id"])}


def _validate_changed_topic_case_bindings(original_rows: list[list[str]], rows: list[Any]) -> None:
    """Reject a newly typed fake case code without blocking untouched legacy rows."""
    allowed = {item["id"] for item in today_topic_benchmark_cases()["cases"]}
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(TOPIC_TABLE_COLUMNS):
            continue
        original = original_rows[index] if index < len(original_rows) else []
        value = str(row[7]).strip()
        previous = str(original[7]).strip() if len(original) > 7 else ""
        if value != previous and value and value not in allowed:
            raise ValueError("对标复刻拆解编号必须通过选择器选择现役已登记案例")


def _parse_markdown_table(path: Path) -> dict[str, Any]:
    """Read the active nine-column topic-table contract without schema drift."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header_index = next((index for index in range(len(lines) - 1) if lines[index].strip().startswith("|") and lines[index + 1].strip().startswith("|")), None)
    if header_index is None:
        raise ValueError("选题表缺少 Markdown 表头")
    columns = [cell.strip() for cell in lines[header_index].strip().strip("|").split("|")]
    divider = [cell.strip() for cell in lines[header_index + 1].strip().strip("|").split("|")]
    if columns != TOPIC_TABLE_COLUMNS or len(divider) != len(TOPIC_TABLE_COLUMNS):
        raise ValueError("选题表必须保持现役九列结构")
    rows: list[list[str]] = []
    row_lines: list[int] = []
    for line_number, line in enumerate(lines[header_index + 2:], start=header_index + 3):
        if not line.strip().startswith("|"):
            break
        values = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(values) != len(TOPIC_TABLE_COLUMNS):
            raise ValueError("选题表存在非九列数据行，不能在网页中编辑")
        rows.append(values)
        row_lines.append(line_number)
    return {
        "lines": lines,
        "headerIndex": header_index,
        "columns": columns,
        "divider": divider,
        "rows": rows,
        "rowLines": row_lines,
    }


def _render_markdown_table(parsed: dict[str, Any], rows: list[Any]) -> str:
    columns = parsed["columns"]
    if not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise ValueError("选题表保存内容必须保持现役九列")
    sanitized = [[str(cell).replace("\n", " ").replace("|", "\\|").strip() for cell in row] for row in rows]
    header_index = int(parsed["headerIndex"])
    row_count = len(parsed["rows"])
    lines = list(parsed["lines"])
    table_lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(parsed["divider"]) + " |",
        *["| " + " | ".join(row) + " |" for row in sanitized],
    ]
    return "\n".join(lines[:header_index] + table_lines + lines[header_index + 2 + row_count:]).rstrip() + "\n"


def today_editor_catalog(surface: str) -> dict[str, Any]:
    config = _today_editor_surface(surface)
    files = _today_editor_files(surface)
    result = {"surface": surface, "label": config["label"], "kind": config["kind"], "files": files}
    if surface == "cases":
        _, ordered_types = _case_editor_registry_type_index()
        result["caseTypes"] = _case_editor_type_catalog(files, ordered_types)
    return result


def today_editor_file(surface: str, file_id: str) -> dict[str, Any]:
    config = _today_editor_surface(surface)
    path = _today_editor_resolve_file(surface, file_id)
    if path.stat().st_size > MAX_EDITOR_FILE_BYTES:
        raise ValueError("编辑文件超过大小限制")
    text = path.read_bytes().decode("utf-8")
    payload: dict[str, Any] = {
        "surface": surface,
        "kind": config["kind"],
        "id": file_id,
        "label": path.stem,
        "relativePath": _project_relative_path(path),
        "pending": not _is_checked_filename(path),
        "sha256": _sha256_file(path),
        "modifiedAt": datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds"),
    }
    payload.update(_candidate_state(surface, path, payload["sha256"]))
    if payload.get("candidateFilename"):
        payload["label"] = str(payload["candidateFilename"])
    if surface == "copy":
        payload.update(_copy_editor_check_state(path, payload))
    if config["kind"] == "markdown":
        payload["content"] = text
        if surface == "structure":
            payload.update(_structure_four_editor_state(path))
            payload["pending"] = not payload["structureFourFilled"]
    else:
        parsed = _parse_markdown_table(path)
        payload["table"] = {"columns": parsed["columns"], "rows": parsed["rows"]}
    return payload


def _atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)


def _candidate_path(surface: str, source_path: Path) -> Path:
    digest = hashlib.sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()[:24]
    target = (TODAY_CANDIDATE_ROOT / f"{surface}_{digest}.json").resolve()
    if not target.is_relative_to(TODAY_CANDIDATE_ROOT.resolve()):
        raise ValueError("编辑候选路径无效")
    return target


def _candidate_state(surface: str, source_path: Path, source_sha256: str | None = None) -> dict[str, Any]:
    target = _candidate_path(surface, source_path)
    try:
        candidate = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"candidateStatus": "none", "candidateId": "", "candidateUpdatedAt": "", "candidateFilename": ""}
    current_sha256 = source_sha256 or _sha256_file(source_path)
    if candidate.get("sourceSha256") != current_sha256:
        return {"candidateStatus": "stale", "candidateId": target.stem, "candidateUpdatedAt": str(candidate.get("updatedAt") or ""), "candidateFilename": ""}
    requested_filename = str(candidate.get("requestedFilename") or "").replace("\r", " ").replace("\n", " ").strip()
    return {"candidateStatus": str(candidate.get("status") or "draft"), "candidateId": target.stem, "candidateUpdatedAt": str(candidate.get("updatedAt") or ""), "candidateFilename": requested_filename}


def _write_edit_candidate(surface: str, path: Path, source_sha256: str, content: str, filename: str = "") -> dict[str, Any]:
    target = _candidate_path(surface, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    requested_filename = filename.replace("\r", " ").replace("\n", " ").strip()
    if len(requested_filename) > 200:
        raise ValueError("候选文件名不能超过 200 个字符")
    payload = {
        "schema": "workbench-asset-edit-candidate-v1",
        "candidateId": target.stem,
        "surface": surface,
        "sourcePath": _project_relative_path(path),
        "sourceSha256": source_sha256,
        "candidateContent": content,
        "requestedFilename": requested_filename,
        "status": "draft",
        "updatedAt": now(),
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return _candidate_state(surface, path, source_sha256)


def _promote_owner_marked_structure_candidate(path: Path) -> Path:
    """Promote a pre-direct-save owner checkmark candidate once, if still current.

    Earlier workbench versions saved structure edits as candidates.  A candidate
    whose requested filename begins with ``√`` is an explicit owner confirmation
    under the current policy, so migrate only that exact, hash-matched candidate
    into the formal structure file and remove the obsolete candidate record.
    """
    candidate_path = _candidate_path("structure", path)
    try:
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        requested_filename = str(candidate.get("requestedFilename") or "").strip()
        candidate_content = candidate.get("candidateContent")
        source_hash = str(candidate.get("sourceSha256") or "")
    except (OSError, json.JSONDecodeError):
        return path
    if (
        not _has_checkmark(requested_filename)
        or not isinstance(candidate_content, str)
        or not source_hash
        or not secrets.compare_digest(source_hash, _sha256_file(path))
    ):
        return path
    target = _today_editor_filename(path, requested_filename)
    _atomic_text(path, candidate_content)
    if target != path:
        path.replace(target)
    candidate_path.unlink(missing_ok=True)
    append_data_event("workbench-owner-structure-saved", {
        "surface": "structure",
        "relativePath": _project_relative_path(target),
        "ownerConfirmed": True,
        "migratedLegacyCandidate": True,
    }, producer="workbench")
    return target


def save_today_editor_file(surface: str, file_id: str, expected_sha256: str, payload: dict[str, Any]) -> dict[str, Any]:
    config = _today_editor_surface(surface)
    path = _today_editor_resolve_file(surface, file_id)
    before_sha256 = _sha256_file(path)
    if not expected_sha256 or not secrets.compare_digest(before_sha256, expected_sha256):
        raise EditorConflictError("文件已被其他操作更新，请重新加载后再编辑")
    if config["kind"] == "markdown":
        content = payload.get("content")
        if not isinstance(content, str):
            raise ValueError("正文或结构内容格式不正确")
        if len(content.encode("utf-8")) > MAX_EDITOR_FILE_BYTES:
            raise ValueError("编辑内容超过大小限制")
        if surface == "cases":
            content = normalize_portable_case_markdown(repair_table_divider(content))
    else:
        parsed = _parse_markdown_table(path)
        if surface == "topics":
            _validate_changed_topic_case_bindings(parsed["rows"], payload.get("rows"))
        content = _render_markdown_table(parsed, payload.get("rows"))

    requested_filename = str(payload.get("filename") or "").strip()
    target = _today_editor_filename(path, requested_filename) if requested_filename else path
    # The workbench confirmation is the workspace owner's explicit approval.
    # Every registered case edited through this surface therefore bypasses the
    # candidate/小审 route.  Keep the visible √ convention by adding it at the
    # same atomic save, rather than requiring an easy-to-miss filename edit
    # before the user can exercise that authority.
    owner_confirms_case = surface == "cases"
    if owner_confirms_case and not _is_checked_filename(target):
        target = _today_editor_filename(path, f"√{target.name}")
    if surface in OWNER_DIRECT_EDIT_SURFACES or owner_confirms_case:
        if owner_confirms_case:
            validate_owner_approved_case_edit(
                previous_breakdown=path,
                breakdown_markdown=target,
                content=content,
            )
        candidate_path = _candidate_path(surface, path)
        # Write the content before renaming, then move within the same directory.
        # This keeps the previous formal file intact until the replacement exists.
        _atomic_text(path, content)
        if target != path:
            path.replace(target)
        # Candidate keys use the original formal path.  Retain that key here
        # so an owner rename (including a leading √) cannot leave stale state.
        candidate_path.unlink(missing_ok=True)
        final_sha256 = _sha256_file(target)
        result = {
            "saved": True,
            "formalUpdated": True,
            "id": _today_editor_file_id(surface, target),
            "label": target.stem,
            "sha256": final_sha256,
            "savedAt": now(),
            "relativePath": _project_relative_path(target),
            "candidateStatus": "none",
            "candidateId": "",
            "candidateUpdatedAt": "",
            "candidateFilename": "",
        }
        if surface == "copy":
            result.update(_copy_editor_check_state(target, result))
        else:
            result["pending"] = not _is_checked_filename(target)
        if surface == "structure":
            if _is_checked_filename(target) and _structure_four_has_content(target):
                # A checked, complete Structure 4 is the owner's highest-authority
                # input for final-copy generation.  It inherits only the audited
                # FNN/framework skeleton; it is not sent back through 小审.
                record_owner_frozen_structure(structure_markdown=target)
                result["structureFourFreezeStatus"] = "owner-frozen"
            result.update(_structure_four_editor_state(target))
            result["pending"] = not result["structureFourFilled"]
        if owner_confirms_case:
            approval = record_owner_approved_case_edit(previous_breakdown=path, breakdown_markdown=target)
            result["caseOwnerApprovalStatus"] = "owner-approved"
            result["caseOwnerApprovalReceipt"] = str(approval["receipt_path"])
        append_data_event(f"workbench-owner-{surface}-saved", {
            "surface": surface,
            "relativePath": result["relativePath"],
            "beforeSha256": before_sha256,
            "afterSha256": final_sha256,
            "ownerConfirmed": True,
            "ownerApprovalMode": "owner-approved" if owner_confirms_case else "direct-save",
        }, producer="workbench")
        return result

    candidate = _write_edit_candidate(surface, path, before_sha256, content, str(payload.get("filename") or ""))
    append_data_event("workbench-asset-edit-candidate-saved", {
        "surface": surface,
        "relativePath": _project_relative_path(path),
        "beforeSha256": before_sha256,
        "candidateId": candidate["candidateId"],
    }, producer="workbench")
    result = {
        "saved": True, "formalUpdated": False,
        "id": file_id,
        # 编辑候选可暂存重命名；只有小审放行后的发布动作才会实际改动正式文件名。
        "label": str(candidate.get("candidateFilename") or path.stem),
        "pending": not _is_checked_filename(path),
        "sha256": before_sha256,
        "savedAt": now(),
        "relativePath": _project_relative_path(path),
        **candidate,
    }
    if surface == "copy":
        result.update(_copy_editor_check_state(path, result))
    if surface == "structure":
        result.update(_structure_four_editor_state(path))
        result["pending"] = not result["structureFourFilled"]
    return result


def _today_module_groups() -> list[dict[str, Any]]:
    try:
        payload = json.loads(TODAY_MODULES_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取今日工作模块配置：{exc}") from exc
    groups = payload.get("groups")
    if not isinstance(groups, list):
        raise RuntimeError("今日工作模块配置缺少 groups")
    return [item for item in groups if isinstance(item, dict)]


def _today_module_index() -> dict[str, dict[str, Any]]:
    modules: dict[str, dict[str, Any]] = {}
    for group in _today_module_groups():
        if group.get("id") == "input":
            for item in group.get("modules", []):
                if isinstance(item, dict) and item.get("id"):
                    modules[str(item["id"])] = {**item, "group": "input"}
        elif group.get("id"):
            modules[str(group["id"])] = {**group, "group": str(group["id"])}
    return modules


def _skill_status(module: dict[str, Any]) -> dict[str, Any]:
    """Resolve the configured Skill from the project's current weapon store."""
    if str(module.get("refreshMode") or "") == "waiting-integration":
        return {"skillAvailable": False, "refreshMode": "waiting-integration", "unlockReason": "该模块尚未接入 Skill"}
    skill_id = str(module.get("skill") or "").strip()
    if not skill_id:
        return {"skillAvailable": False, "refreshMode": "waiting-integration", "unlockReason": "该模块尚未接入 Skill"}
    candidates = [
        CODEX_SKILL_ROOT / skill_id / "SKILL.md",
        CANONICAL_SKILL_ROOT / skill_id / "SKILL.md",
    ]
    # Canonical weapon-store folders use the human-facing name rather than the
    # route ID; match their front matter/name when the ID folder is absent.
    if not any(path.is_file() for path in candidates):
        for skill_dir in CANONICAL_SKILL_ROOT.iterdir() if CANONICAL_SKILL_ROOT.is_dir() else []:
            skill_file = skill_dir / "SKILL.md"
            try:
                text = skill_file.read_text(encoding="utf-8") if skill_file.is_file() else ""
            except OSError:
                continue
            if skill_id in text or str(module.get("skillLabel") or "").replace("（会员专享）", "") in text:
                candidates.append(skill_file)
                break
    for skill_file in candidates:
        try:
            text = skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        body = re.sub(r"^---.*?---\s*", "", text, count=1, flags=re.DOTALL).strip()
        if body:
            return {"skillAvailable": True, "refreshMode": "available", "unlockReason": ""}
    return {"skillAvailable": False, "refreshMode": "locked", "unlockReason": "会员专享 Skill 尚未解锁或内容为空"}


def _module_root(module: dict[str, Any], key: str = "root") -> Path:
    value = str(module.get(key) or "")
    path = _safe_asset_path(value)
    if not path.is_dir():
        raise FileNotFoundError(f"模块目录不存在：{value}")
    return path


def _catalog_path(item: dict[str, Any]) -> Path:
    """Resolve a catalog allow-list entry without exposing arbitrary paths."""
    relative = str(item["relativePath"])
    if item.get("kind") == "skill":
        path = (PROJECT_ROOT / relative).resolve()
        if not path.is_relative_to(CANONICAL_SKILL_ROOT.resolve()):
            raise ValueError("Skill 路径不在武器库范围内")
        return path
    return _safe_asset_path(relative)


def _catalog_file_count(path: Path) -> int:
    return sum(
        file.name.lower() not in {"readme.md", "readme.txt", "index.md"}
        for file in _walk_files(path)
    ) if path.is_dir() else 0


def _catalog_has_content(path: Path, item: dict[str, Any]) -> bool:
    """Treat placeholders and README files as empty, but retain real assets/Skills."""
    if not path.is_dir():
        return False
    if item.get("kind") == "skill":
        skill_file = path / "SKILL.md"
        try:
            return skill_file.is_file() and bool(skill_file.read_text(encoding="utf-8").strip())
        except (OSError, UnicodeError):
            return False
    return any(file.name.lower() not in {"readme.md", "readme.txt", "index.md"} for file in _walk_files(path))


def _asset_catalog_snapshot() -> list[dict[str, Any]]:
    """Return only the active, two-level directory map for the asset page."""
    inventory_summary = _input_inventory_payload().get("summary", {})
    input_source_types = {
        "input-books": "books",
        "input-podcasts": "podcasts",
        "input-events": "events",
        "input-videos": "video-sources",
        "input-journals": "work-journals",
    }
    result = []
    for section in ASSET_CATALOG:
        children = []
        for item in section["items"]:
            path = _catalog_path(item)
            has_content = _catalog_has_content(path, item)
            # Skills are capabilities, not a file inventory. Their total is the
            # number of supported professional Skills, not internal file count.
            if section["kind"] == "skills":
                item_count = 0
            elif section["id"] == "input" and item["id"] in input_source_types:
                # Input-library totals are sources, not index/manifest files.
                # This is the same audited source ledger used by 今日工作 and
                # 源知识库, so one source cannot be counted twice here.
                source_type = input_source_types[item["id"]]
                summary = inventory_summary.get(source_type, {})
                item_count = int(summary.get("total", 0)) if isinstance(summary, dict) else 0
            elif item["id"] == "process-cases":
                # 录音总览、整理转写、索引和处理记录不是案例内容模块。
                item_count = _case_card_count()
            else:
                item_count = _catalog_file_count(path)
            children.append({
                "id": item["id"], "label": item["label"], "memberOnly": bool(item.get("memberOnly")),
                "locked": bool(item.get("memberOnly")) and not has_content, "exists": path.is_dir(),
                "count": item_count, "relativePath": item["relativePath"],
            })
        result.append({
            "id": section["id"], "label": section["label"], "icon": section["icon"], "kind": section["kind"],
            "count": len(children) if section["kind"] == "skills" else sum(int(child["count"]) for child in children),
            "items": children,
        })
    return result


def _case_breakdown_items() -> list[dict[str, Any]]:
    root = asset_resolve(PROJECT_ROOT, "cases.breakdowns")
    items = []
    for path in _walk_files(root):
        if path.suffix.lower() != ".md" or path.name.lower() in {"readme.md", "index.md"}:
            continue
        relative = path.relative_to(root).as_posix()
        member_only = "（会员专享）" in relative
        items.append({
            "id": relative, "title": path.stem, "memberOnly": member_only,
            "locked": False, "relativePath": _project_relative_path(path),
        })
    return items


def _case_breakdown_content(item_id: str) -> dict[str, Any]:
    root = asset_resolve(PROJECT_ROOT, "cases.breakdowns").resolve()
    candidate = (root / item_id).resolve()
    if not candidate.is_relative_to(root) or candidate.suffix.lower() != ".md" or not candidate.is_file():
        raise FileNotFoundError("对标复刻拆解不存在")
    if candidate.stat().st_size > MAX_EDITOR_FILE_BYTES:
        raise ValueError("拆解文件过大，无法在工作台预览")
    return {"title": candidate.stem, "relativePath": _project_relative_path(candidate), "content": candidate.read_text(encoding="utf-8")}


def _module_files(root: Path, suffixes: set[str] | None = None) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        if path.name in IGNORED_FILE_NAMES or path.name == "README.md" or path.name.startswith("."):
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        files.append(path)
    return files


def _topic_module_counts(root: Path) -> tuple[int, int]:
    """Count topic rows and rows awaiting a selection decision.

    ``是否选中`` is deliberately different from the downstream structure
    status: a blank selection means the row has not been judged yet, so it is
    the Today page's pending topic work.
    """
    count = pending = 0
    for path in _module_files(root, {".md"}):
        try:
            table = _parse_markdown_table(path)
        except (OSError, ValueError):
            continue
        count += len(table["rows"])
        pending += sum(len(row) > 6 and row[6].strip() == "" for row in table["rows"])
    return count, pending


def _topic_source_key(value: str) -> str:
    """Normalize account names without treating a category-table filename as its source."""
    return re.sub(r"[\s_\-—－()（）【】\[\]{}]+", "", str(value or "")).casefold()


def today_topic_candidates() -> dict[str, Any]:
    """List benchmark-account files by actual topic-table completion state.

    Topic tables are grouped by subject, not by account filename. Comparing
    filenames made each source look unprocessed even when its rows were
    already present in a newer generated topic table.
    """
    module = _today_module_index().get("topics")
    if module is None:
        raise RuntimeError("选题库模块未登记")
    source_root = _module_root(module, "sourceRoot")
    topic_root = _module_root(module)
    by_account: dict[str, list[Path]] = {}
    for table in _module_files(topic_root, {".md"}):
        try:
            parsed = _parse_markdown_table(table)
        except (OSError, ValueError):
            continue
        for row in parsed["rows"]:
            if len(row) <= 3:
                continue
            account_key = _topic_source_key(row[3])
            if account_key:
                by_account.setdefault(account_key, []).append(table)
    candidates: list[dict[str, Any]] = []
    for source in _module_files(source_root, {".xlsx"}):
        source_mtime = _file_mtime_ns(source)
        tables = by_account.get(_topic_source_key(source.stem), [])
        newest_table = max(tables, key=_file_mtime_ns, default=None)
        generated = bool(newest_table and _file_mtime_ns(newest_table) >= source_mtime)
        current = newest_table if generated else source
        candidates.append({
            "id": _project_relative_path(source),
            "title": source.name,
            "generated": generated,
            "generationMode": "regenerate" if generated else "initial",
            "generationLabel": "重新刷新（保留当前选题表）" if generated else "首次刷新",
            "updatedAt": _file_updated_at(current),
            "sourcePath": _project_relative_path(source),
            "currentTopicTables": [_project_relative_path(table) for table in sorted(set(tables), key=_file_mtime_ns, reverse=True)],
            "_sortMtime": _file_mtime_ns(current),
        })
    candidates.sort(key=lambda item: (int(item.pop("_sortMtime", 0)), str(item["title"])), reverse=True)
    return {"label": "选题库", "candidates": candidates}


def _formal_case_file_count() -> int:
    """A dissected case is one formal breakdown Markdown, not an audit hash.

    Audit receipts are a release gate, but the Today overview must not report
    six already-created breakdown cards as zero merely because an old receipt
    uses a different schema or source hash.
    """
    return len(_module_files(ASSET_ROOT / "05_案例库" / "02_对标复刻拆解", {".md"}))


def _structure_pending_count() -> int:
    """Count only executable topic rows that genuinely lack a structure.

    A plain ``是否选中=是`` is a human-selection result, not a structure task.
    The row must also have a currently approved benchmark-case binding, and a matching
    formal structure must not already exist.  This prevents legacy selected
    rows without a benchmark number from inflating Today's pending count.
    """
    structure_titles = _output_structure_titles()
    approved_ids = _approved_case_ids()
    return sum(
        bool(row.get("selected"))
        and str(row.get("benchmarkCaseId") or "").strip() in approved_ids
        and str(row.get("title") or "").strip() not in structure_titles
        for row in _topic_rows()
    )


def _output_structure_titles() -> set[str]:
    """Return unique business structures, collapsing timestamped revisions."""
    titles: set[str] = set()
    for path in _module_files(STRUCTURE_ROOT, {".md"}):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        value = match.group(1) if match else path.stem
        # Existing V1 structures use both ``文案结构：标题`` and
        # ``文案结构｜标题`` headings.  Normalize either form to the topic
        # title before comparing it with the selected-topic table.
        value = re.sub(r"^文案结构(?:[：:｜|]\s*)?", "", value).strip()
        if value:
            titles.add(value)
    return titles


def _gallery_completed_titles() -> set[str]:
    """Each gallery topic folder is one completed topic package."""
    if not GALLERY_ROOT.is_dir():
        return set()
    return {
        item.name.strip()
        for item in GALLERY_ROOT.iterdir()
        if item.is_dir() and item.name not in IGNORED_DIR_NAMES and not item.name.startswith(".")
    }


def _gallery_completed_directories() -> dict[str, Path]:
    """Keep the newest gallery folder for each normalized topic key."""
    if not GALLERY_ROOT.is_dir():
        return {}
    directories: dict[str, Path] = {}
    for item in GALLERY_ROOT.iterdir():
        if not item.is_dir() or item.name in IGNORED_DIR_NAMES or item.name.startswith("."):
            continue
        key = _gallery_topic_key(item.name)
        prior = directories.get(key)
        if prior is None or item.stat().st_mtime_ns > prior.stat().st_mtime_ns:
            directories[key] = item
    return directories


def _gallery_topic_key(value: str) -> str:
    return re.sub(r"[\\s_：:，,。.!！?？、（）()【】\[\]「」《》]", "", str(value)).lower()


def _gallery_pending_count(copy_titles: set[str]) -> int:
    completed = {_gallery_topic_key(value) for value in _gallery_completed_titles()}
    return sum(_gallery_topic_key(title) not in completed for title in copy_titles)


def _latest_copy_revision_key(path: Path, root: Path) -> str:
    """Collapse timestamped final-copy revisions without merging case branches."""
    stem = path.stem.lstrip("√✓").strip()
    stem = re.sub(r"_\d{8}(?:-|_)\d{6}(?:（[^）]+）)?$", "", stem)
    try:
        parent = path.parent.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        parent = str(path.parent.resolve())
    return f"{parent}/{stem}".lower()


def _latest_copy_pending_count(root: Path) -> int:
    """Count only unconfirmed current final-copy revisions, never history."""
    latest: dict[str, Path] = {}
    for path in _module_files(root, {".md"}):
        key = _latest_copy_revision_key(path, root)
        previous = latest.get(key)
        if previous is None or path.stat().st_mtime_ns > previous.stat().st_mtime_ns:
            latest[key] = path
    return sum(not _is_checked_filename(path) for path in latest.values())


def _generated_refresh_count(module_id: str) -> int:
    """Use the selectable refresh catalog as the single source of missing work."""
    return sum(
        bool(item.get("eligible")) and not bool(item.get("generated"))
        for item in generation_candidates(module_id).get("candidates", [])
    )


def _module_work_counts(module: dict[str, Any]) -> dict[str, int]:
    """Return explicit dashboard counts instead of one overloaded pending value."""
    root = _module_root(module)
    module_id = str(module.get("id"))
    if module_id in {"books", "podcasts", "video-sources", "work-journals", "events"}:
        inventory = _input_inventory_payload()
        summary = inventory["summary"].get(module_id, {})
        completed = int(summary.get("completed", 0))
        # "待刷新" is deliberately every source not formally completed.  This
        # includes staged review/correction rows rather than hiding them behind
        # a second user-facing backlog label.
        refresh = max(0, int(summary.get("total", 0)) - completed)
        return {"currentCount": completed, "refreshCount": refresh, "editCount": 0, "pictureCount": 0}
    if module_id == "topics":
        current, edit = _topic_module_counts(root)
        refresh = sum(not bool(item.get("generated")) for item in today_topic_candidates().get("candidates", []))
        return {"currentCount": current, "refreshCount": refresh, "editCount": edit, "pictureCount": 0}
    if module_id == "cases":
        candidates = today_case_candidates().get("candidates", [])
        refresh = sum(not bool(item.get("generated")) for item in candidates)
        edit = sum(not _is_checked_filename(path) for path in _module_files(root, {".md"}))
        return {"currentCount": len(_module_files(root, {".md"})), "refreshCount": refresh, "editCount": edit, "pictureCount": 0}
    if module_id == "gallery":
        # One topic package counts once; individual PNG/page files are
        # implementation details and never leak into the dashboard.
        return {
            "currentCount": len(_gallery_completed_titles()),
            "refreshCount": 0,
            "editCount": 0,
            "pictureCount": _gallery_pending_count(_owner_confirmed_copy_titles()),
        }
    if module_id == "structures":
        return {
            "currentCount": _markdown_count(root),
            "refreshCount": _generated_refresh_count("structures"),
            "editCount": _latest_structure_pending_count(root),
            "pictureCount": 0,
        }
    if module_id == "copies":
        return {
            "currentCount": _markdown_count(root),
            "refreshCount": _generated_refresh_count("copies"),
            "editCount": _latest_copy_pending_count(root),
            "pictureCount": 0,
        }
    return {"currentCount": len(_module_files(root)), "refreshCount": 0, "editCount": 0, "pictureCount": 0}


def _module_counts(module: dict[str, Any]) -> tuple[int, int]:
    """Compatibility tuple for old consumers; new UI uses explicit fields."""
    counts = _module_work_counts(module)
    pending = counts["pictureCount"] or counts["refreshCount"] + counts["editCount"]
    return counts["currentCount"], pending


def _input_module_display_state(module: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Add source-gate information without redefining an input module's count."""
    module_id = str(module.get("id") or "")
    summary = payload.get("summary", {}).get(module_id, {}) if isinstance(payload, dict) else {}
    state = {"reviewCount": int(summary.get("review", 0)), "uncertainCount": int(summary.get("uncertain", 0))}
    # The video pain Skill only accepts the ledger's next continuous batch when
    # every corrected source has a small-audit approved receipt.  A raw source
    # is therefore "待校对", never a task that may be sent to Codex.
    if module_id == "video-sources" and int(summary.get("pending", 0)) == 0 and state["reviewCount"]:
        waiting = [
            row for row in payload.get("rows", [])
            if row.get("source_type") == module_id and row.get("status") == "待审核"
        ][:5]
        batch = "、".join(str(row.get("source_id") or "") for row in waiting if row.get("source_id"))
        state.update({
            "refreshPreflight": "video-source-correction",
            "refreshNotice": f"下一连续批 {batch or '视频源'} 将先由小息校对并交小审，再进入痛点卡拆解。",
        })
    return state


def _input_inventory_payload() -> dict[str, Any]:
    """Reconcile source-level status and return rows plus typed summaries."""
    global INPUT_INVENTORY_CACHE
    # Requests for /api/today/modules arrive in parallel from the browser.
    # Serialize the SQLite refresh and reuse a short-lived snapshot so they do
    # not queue behind one another on the database write lock.
    with INPUT_INVENTORY_LOCK:
        if INPUT_INVENTORY_CACHE and time.monotonic() - INPUT_INVENTORY_CACHE[0] < 10:
            return INPUT_INVENTORY_CACHE[1]
        initialize_store()
        with _connection() as connection:
            rows = rebuild_inventory(connection, PROJECT_ROOT)
        payload = {"generatedAt": now(), "summary": inventory_summary(rows), "rows": rows}
        INPUT_INVENTORY_CACHE = (time.monotonic(), payload)
        return payload


def _invalidate_input_inventory_cache() -> None:
    """Make an explicit folder sync observe filesystem changes immediately."""
    global INPUT_INVENTORY_CACHE
    with INPUT_INVENTORY_LOCK:
        INPUT_INVENTORY_CACHE = None


def _folder_sync_state_path() -> Path:
    return RUNTIME_ROOT / "folder-sync-state.json"


def _folder_sync_files() -> dict[str, dict[str, str]]:
    """Return the visible source files that an explicit sync is allowed to track.

    This is discovery only.  The inventory rows do not start any Skill and the
    topic/case source scans deliberately stop before their respective refresh
    tasks are created.
    """
    inventory = _input_inventory_payload()
    files: dict[str, dict[str, str]] = {
        "books": {}, "podcasts": {}, "events": {}, "video-sources": {}, "work-journals": {},
        "topics": {}, "cases": {},
    }
    for row in inventory.get("rows", []):
        source_type = str(row.get("source_type") or "")
        source_path = str(row.get("source_path") or "")
        fingerprint = str(row.get("source_sha256") or "")
        if source_type in files and source_path and fingerprint:
            files[source_type][source_path] = fingerprint
    modules = _today_module_index()
    for section, module_id in (("topics", "topics"), ("cases", "cases")):
        module = modules.get(module_id)
        if module is None:
            continue
        root = _module_root(module, "sourceRoot")
        for path in _module_files(root):
            relative = _project_relative_path(path)
            try:
                files[section][relative] = _sha256_file(path)
            except OSError:
                # A file being copied while the scan runs is retried by the
                # next explicit click instead of making the full sync fail.
                continue
    return files


def _load_folder_sync_state() -> dict[str, Any]:
    try:
        payload = json.loads(_folder_sync_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": "workbench-folder-sync-v1", "files": {}}
    return payload if isinstance(payload, dict) else {"schema": "workbench-folder-sync-v1", "files": {}}


def sync_workbench_folders(page: str) -> dict[str, Any]:
    """Discover manually copied source files and refresh derived workbench data."""
    with FOLDER_SYNC_LOCK:
        _invalidate_input_inventory_cache()
        current = _folder_sync_files()
        previous = _load_folder_sync_state().get("files", {})
        changes: dict[str, dict[str, int]] = {}
        for section, entries in current.items():
            before = previous.get(section, {}) if isinstance(previous, dict) else {}
            before = before if isinstance(before, dict) else {}
            changes[section] = {
                "added": len(set(entries) - set(before)),
                "changed": sum(entries[key] != before[key] for key in set(entries) & set(before)),
                "removed": len(set(before) - set(entries)),
                "current": len(entries),
            }
        snapshot = refresh_data_center(reason="folder-sync", producer="workbench")
        dashboard = dashboard_page(page)
        # Do not acknowledge the scan until every user-visible refresh result
        # is ready.  If either operation fails, keeping the former baseline
        # makes the same new/changed files visible again on the next click.
        state_path = _folder_sync_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_text(state_path, json.dumps({
            "schema": "workbench-folder-sync-v1",
            "syncedAt": now(),
            "files": current,
        }, ensure_ascii=False, indent=2) + "\n")
        return {
            "dataCenter": snapshot,
            "dashboard": dashboard,
            "sync": {"changes": changes, "syncedAt": now()},
        }


def _module_last_task(module_id: str) -> dict[str, str]:
    return _module_last_tasks({module_id})[module_id]


def _module_last_tasks(module_ids: set[str]) -> dict[str, dict[str, str]]:
    """Resolve all today-module task summaries from one ordered session scan.

    The old helper executed and decoded the same 200-session query once per
    tile. Today's dashboard has several tiles, so that made a page request
    needlessly proportional to the number of modules.
    """
    default = {
        "lastRefreshAt": "",
        "taskStatus": "尚未创建任务",
        "auditStatus": "尚无审核结果",
        "inputScope": "模块当前待处理范围",
    }
    result = {module_id: dict(default) for module_id in module_ids}
    unresolved = set(module_ids)
    for session in _rows("SELECT workflow_json,updated_at,status,approval_status FROM sessions ORDER BY updated_at DESC LIMIT 200"):
        workflow = _json_object(session.get("workflow_json"))
        module_id = str(workflow.get("todayModuleId") or "")
        if module_id not in unresolved:
            continue
        result[module_id] = {
            "lastRefreshAt": str(session.get("updated_at") or ""),
            "taskStatus": str(session.get("status") or ""),
            "auditStatus": str(session.get("approval_status") or "尚未审核"),
            "inputScope": str(workflow.get("inputScopeLabel") or "本次待处理清单"),
        }
        unresolved.remove(module_id)
        if not unresolved:
            break
    return result


def today_work_modules() -> dict[str, Any]:
    configured_groups = _today_module_groups()
    module_ids = {
        str(module.get("id"))
        for group in configured_groups
        for module in (group.get("modules", []) if group.get("id") == "input" else [group])
        if isinstance(module, dict) and module.get("id")
    }
    last_tasks = _module_last_tasks(module_ids)
    groups: list[dict[str, Any]] = []
    for group in configured_groups:
        if group.get("id") == "input":
            modules = []
            inventory_payload = _input_inventory_payload()
            for module in group.get("modules", []):
                if not isinstance(module, dict):
                    continue
                counts = _module_work_counts(module)
                pending = counts["pictureCount"] or counts["refreshCount"] + counts["editCount"]
                modules.append({**module, **_skill_status(module), **_input_module_display_state(module, inventory_payload), **counts, "pendingCount": pending, **last_tasks[str(module.get("id"))]})
            groups.append({"id": "input", "label": str(group.get("label")), "description": str(group.get("description")), "modules": modules})
            continue
        counts = _module_work_counts(group)
        pending = counts["pictureCount"] or counts["refreshCount"] + counts["editCount"]
        groups.append({"id": str(group.get("id")), "label": str(group.get("label")), "description": "", "modules": [{**group, **_skill_status(group), **counts, "pendingCount": pending, **last_tasks[str(group.get("id"))] }]})
    return {"generatedAt": now(), "groups": groups}


def _generation_selection_prompt(selected: list[Any]) -> str:
    """Render the user-confirmed generation manifest without trusting UI labels."""
    lines: list[str] = []
    for index, item in enumerate(selected, start=1):
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        mode = "重新生成（保留历史版本）" if item.get("generationMode") == "regenerate" else "首次生成"
        lines.append(
            f"{index}. [{mode}] {item.get('title') or '未命名选题'}\n"
            f"   - 来源选题表：{item.get('table') or '未记录'}\n"
            f"   - 对标复刻拆解编号：{item.get('benchmarkCaseId') or '未记录'}\n"
            f"   - 当前正式资产：{item.get('currentFormalPath') or '无'}"
        )
    return "\n".join(lines) if lines else "- 本次扫描未发现待处理对象。"


def _today_module_prompt(module: dict[str, Any], selected: list[Any], *, approved_source_manifest: str = "", video_correction: dict[str, Any] | None = None, video_continuation: dict[str, Any] | None = None, video_source_import: list[dict[str, str]] | None = None) -> str:
    root = _module_root(module)
    selected_text = _generation_selection_prompt(selected)
    manifest_note = f"\n已审核校对源批次清单（只可使用此清单）：{approved_source_manifest}\n" if approved_source_manifest else ""
    correction_note = ""
    gallery_note = ""
    workflow_chain = f"小姜分配 → {module['agent']}执行 → 小审审核 → 受控发布"
    if str(module.get("id") or "") == "gallery":
        gallery_note = """
配图业务运行硬约束：
1. 只消费当前正式 Skill 与由本次正文新建的工作包；不得编辑 Skill、生成程序或小审程序，不得复用旧工作包。
2. 只接受 `4.1.0` 新工作包。原生生图必须一次返回含标题、2–5 张主卡、每张 `evidence_nodes` 中的 1–3 条源自本页正文的内部证据短句、对应小场景/对象关系和 IP 人物的最终 PNG；禁止无文字候选、空白主卡/证据槽或任何后续叠字降级路径。遇到“第1个/第2个/第3个”并列结构，分支本身必须是主卡，装修、囤货等从属条件只能留在所属主卡的证据节点内。
3. 生图前必须真实挂载主脸锚点与 Skill 声明的合格成图品质参考；品质参考只约束图文一体、信息密度和手绘模块完成态，不得复制案例文字或语义对象。
4. 最终 PNG 必须先进入工作包 final-review/ 并经小审逐主卡、逐证据核对实际可见中文、图文语义、空白槽、跨页重复和案例完成态；未取得哈希绑定 approved 回执不得发布或展示为结果。
5. 配图门禁退回进入修复循环，不得把 `rejected` 当作任务终点：
   - 每次动作先读取工作包 `render-state.json`，并只按 `render_recovery_loop.py ... next` 的指令继续；`attempt-ledger.json` 是唯一可变事实源。通过控制器租约避免同一页并发重画。
   - 工作包预审退回：先回写 `repairing`，保留退回工作包作审计证据；从原正文和当前正式 Skill 新建 v4.1 工作包后重审。若新工作包复现同一蓝图规划缺陷，控制器会请求独立 Skill 修复任务；主任务保持 `repairing`，修复验证后重建续跑。不得写 `blocked`，也不得修改本次生产任务中的 Skill、生成程序或小审程序。
   - 成图审核退回：先回写 `repairing`，只按冻结蓝图重画被退回页，直到小审放行；不得降级为无字图、叠字或空白槽。
   - ImageGen、文件、桌面桥接或任务失联：使用 `record-external` 回写 `reconnecting`、当前页、失败原因和下次恢复时间；工作台将自动向原任务发送检查点恢复指令，原任务不可用时创建恢复任务。
   - 只有正式小审回执 `approved` 后才回写 `released`；配图任务不得以 `rejected` 结束。
"""
    if video_correction:
        workflow_chain = f"小姜分配 → 小息校对 → 小审审核 → {module['agent']}痛点拆解 → 小审审核 → 受控发布"
        correction_note = f"""
本次先执行视频源校对准入（连续第 {video_correction['batch_number']} 批，固定 5 篇）：
1. 小姜先分配小息执行 `$standardize-and-inventory-sources`，仅处理上方列出的 5 个 source_id；使用该 Skill 的 `process_video_correction_batch.py --batch-number {video_correction['batch_number']}`，不得开启下一批。
2. 小审逐篇审核校对候选；只有五篇全部 `video-source-correction-v1 / approved` 后，生成 `video-corrected-source-batch-v1` 清单。
3. 再分配小拆执行 `${module['skill']}`，只读取这份已审核校对源清单，并继续执行小审与受控发布。
不得把原识别版源文档直接交给痛点批处理，也不得把“待确认”文字自动改写进候选。
"""
    if video_continuation:
        workflow_chain = f"小姜续接第 {video_continuation['batch_number']} 批 → 按既有阶段交小拆/小审 → 受控发布"
        correction_note = f"""
本次不是新开批次，而是续接正在进行的第 {video_continuation['batch_number']} 批：
1. 固定来源：{'、'.join(video_continuation['source_ids'])}。
2. 运行目录：{video_continuation['run_dir']}；当前阶段：{video_continuation['phase']}。
3. 必须先读取该目录已有的校对清单、机器证据、审核回执和台账，再只完成缺失的下一步；不得重新校对、重建上一批或启动下一批。
4. 若机器证据尚未完成，由小拆调用 `${module['skill']}` 续跑；若已完成，则交小审审核、暂存发布复核与原子提交。任一环节未 `approved` 不得写正式库。
"""
    if video_source_import:
        workflow_chain = f"小姜分配 → 小息技术标准化 → {module['agent']}痛点拆解 → 小审审核 → 受控发布"
        correction_note = """
本次发现的是用户已手动放入视频文案输入目录的文件：
1. 这些文件已由用户确认，可直接进入本次刷新范围；不得创建额外确认界面或独立前置任务。
2. 小息调用 `$standardize-and-inventory-sources`，只为后续 Skill 做必要技术标准化：视频 Excel 生成稳定 source_id 与 manifest；不得改写、移动或删除原始文件。
3. 标准化完成后，按现有连续批次规则继续处理；若已有连续批次或校对批次，必须优先续接，不能跳批。
4. 小审只审核后续校对、拆解和正式发布产物，不把用户已确认的输入文件退回为未确认状态。
"""
    generation_note = ""
    if str(module.get("id") or "") in {"structures", "copies"} and any(isinstance(item, dict) for item in selected):
        generation_note = """
本次为用户明确选择的生成清单：
1. 只处理上方逐项清单，严格按顺序串行；每项都要先完成生成候选、再交小审、最后受控发布。
2. 标记“首次生成”的项目不得引用旧正式版本；标记“重新生成”的项目必须新建候选和新版本，保留全部历史正式资产与审核记录。
3. 不得因文件名未打 √ 而跳过“重新生成”项目；√ 仅是所有者人工确认标记，不是本次生成资格。
4. 每项完成后在任务回写中记录模式、正式产物路径和小审结论；任一项目未获 approved 不得发布为正式结果。
"""
    return f"""请作为小姜执行“今日工作”刷新任务。

模块：{module['label']}（{module['id']}）
正式目录：{_project_relative_path(root)}
本次刷新扫描清单（逐项执行，不得扩大范围）：
{selected_text}
执行 Skill：${module['skill']}
Skill 名称：{module.get('skillLabel') or module['skill']}
执行人：{module['agent']}
    {manifest_note}
    {correction_note}
    {gallery_note}
    {generation_note}

    请创建调度记录，并严格按：{workflow_chain}。
不得直接覆盖未审核正式资产；若没有可处理内容，明确记录“无新增”。案例、配图和本次多项结构/正文任务均须串行处理。完成后回写本任务的审核结论与正式产物路径。"""


def _queue_visible_task(session_id: str) -> dict[str, Any]:
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("工作台任务不存在")
    session = rows[0]
    prompt_file = (TODAY_TASK_RUNTIME_ROOT / f"{session_id}.prompt.md").resolve()
    if not prompt_file.is_relative_to(TODAY_TASK_RUNTIME_ROOT.resolve()):
        raise ValueError("任务提示词路径无效")
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(str(session["message"]).strip() + "\n", encoding="utf-8")
    # The visible Codex task receives only a command that reads this local
    # one-time signature.  Keeping the token out of the prompt prevents a
    # copied task message from impersonating the workbench on another machine.
    token = secrets.token_urlsafe(24)
    token_root = RUNTIME_ROOT / "bridge-tokens"
    token_root.mkdir(parents=True, exist_ok=True)
    (token_root / f"{session_id}.token").write_text(token, encoding="utf-8")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    deadline = (datetime.now().astimezone() + timedelta(minutes=15)).isoformat(timespec="seconds")
    workflow = _json_object(session.get("workflow_json"))
    workflow["promptFile"] = str(prompt_file)
    with _connection() as connection:
        connection.execute(
            "UPDATE sessions SET status='creating-desktop-task', approval_status='approved', bridge_status='desktop-bridge-queued', desktop_navigation_status='waiting-user-agent', delivery_token_hash=?, delivery_deadline_at=?, execution_authorized=1, workflow_json=?, updated_at=? WHERE id=?",
            (token_hash, deadline, json.dumps(workflow, ensure_ascii=False), now(), session_id),
        )
    _record_event(session_id, "info", "已创建独立 Codex 任务，等待桌面桥接打开。", kind="visible-task-request", detail={"promptFile": _project_relative_path(prompt_file)})
    return _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))[0]


def _approved_case_source_hashes() -> set[str]:
    approved_outputs = {_sha256_file(path) for path in _approved_case_paths()}
    values: set[str] = set()
    for receipt_path in (FORMAL_AUDIT_ROOT / "benchmark-video-structure").glob("*.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("schema") == "audit-receipt-v1" and receipt.get("status") == "approved" and isinstance(receipt.get("source_sha256"), str) and receipt.get("output_sha256") in approved_outputs:
            values.add(receipt["source_sha256"])
    return values


def _approved_case_paths() -> set[Path]:
    output_hashes: set[str] = set()
    for receipt_path in (FORMAL_AUDIT_ROOT / "benchmark-video-structure").glob("*.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("schema") == "benchmark-structure-audit-v2" and receipt.get("status") == "approved" and isinstance(receipt.get("output_sha256"), str):
            output_hashes.add(receipt["output_sha256"])
    return {path for path in _module_files(ASSET_ROOT / "05_案例库" / "02_对标复刻拆解", {".md"}) if _sha256_file(path) in output_hashes}


def _published_structure_paths() -> set[Path]:
    paths: set[Path] = set()
    for binding in verified_release_bindings().values():
        path = Path(str(binding.get("output_path") or "")).resolve()
        if path.is_relative_to(STRUCTURE_ROOT.resolve()) and path.is_file():
            paths.add(path)
    return paths


def _published_copy_paths() -> set[Path]:
    paths: set[Path] = set()
    audit_root = FORMAL_AUDIT_ROOT / "final-copy"
    for receipt_path in audit_root.glob("*.json"):
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if receipt.get("schema") != "final-copy-publication-v1" or receipt.get("status") != "published":
            continue
        path = Path(str(receipt.get("formalPath") or "")).resolve()
        audit_path = Path(str(receipt.get("auditReceipt") or "")).resolve()
        if not path.is_relative_to(COPY_ROOT.resolve()) or not path.is_file() or not audit_path.is_file() or receipt.get("formalSha256") != _sha256_file(path):
            continue
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if audit.get("artifactType") in {"final-copy-v2", "final-copy-v3"} and audit.get("status") == "approved":
            paths.add(path)
    return paths


def _heading_title(path: Path) -> str:
    """Read one formal artifact title for generation identity checks."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem
    match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else path.stem


def _structure_title_key(value: str) -> str:
    value = re.sub(r"^文案结构(?:[：:｜|]\s*)?", "", str(value or "")).strip()
    return _normalized_copy_title(value)


def _latest_structure_for_topic(title: str) -> Path | None:
    key = _normalized_copy_title(title)
    matches = [
        path for path in _module_files(STRUCTURE_ROOT, {".md"})
        if _structure_title_key(_heading_title(path)) == key
        or _normalized_copy_title(path.stem).startswith(key + "_")
    ]
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def _latest_published_copy_for_topic(title: str) -> Path | None:
    key = _normalized_copy_title(title)
    matches = [path for path in _published_copy_paths() if _normalized_copy_title(_heading_title(path)) == key]
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def _latest_structure_for_topic_case(title: str, case_id: str) -> Path | None:
    """Resolve a structure inside one explicit topic × benchmark branch."""
    key = _normalized_copy_title(title)
    marker = f"_{case_id}_"
    matches = [
        path for path in _module_files(STRUCTURE_ROOT, {".md"})
        if marker in path.name and _structure_title_key(_heading_title(path)) == key
    ]
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def _latest_copy_for_topic(title: str) -> Path | None:
    """Find the latest generated copy file for a topic, independent of √/audit.

    The refresh selector answers only whether a body draft was generated.  It
    must not call an existing draft “未生成” just because the owner has not
    checked its filename yet or an audit receipt has not been recorded.
    """
    key = _normalized_copy_title(title)
    matches = [
        path for path in _module_files(COPY_ROOT, {".md"})
        if _normalized_copy_title(_heading_title(path)) == key
    ]
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def _latest_copy_for_topic_case(title: str, case_id: str) -> Path | None:
    """Resolve one generated body draft inside an explicit benchmark branch."""
    key = _normalized_copy_title(title)
    marker = f"_{case_id}_"
    matches = [
        path for path in _module_files(COPY_ROOT, {".md"})
        if marker in path.name and _normalized_copy_title(_heading_title(path)) == key
    ]
    return max(matches, key=lambda path: path.stat().st_mtime_ns) if matches else None


def _file_updated_at(path: Path | None) -> str:
    """Return a displayable local timestamp for a file or generated folder."""
    if not path or not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def _file_mtime_ns(path: Path | None) -> int:
    return path.stat().st_mtime_ns if path and path.exists() else 0


def _generation_candidate_fingerprint(item: dict[str, Any]) -> str:
    """Bind a browser selection to the exact current generation preflight state."""
    payload = {
        key: item.get(key, "")
        for key in ("id", "moduleId", "benchmarkCaseId", "eligible", "generationMode", "currentFormalPath", "currentFormalSha256", "structurePath", "structureSha256")
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def generation_candidates(module_id: str) -> dict[str, Any]:
    """Return the common selectable catalog for structure and final-copy production.

    An ungenerated structure needs a selected topic plus a confirmed benchmark;
    an ungenerated final copy needs a structure explicitly checked by its owner.
    Existing assets remain selectable for controlled regeneration.
    """
    if module_id not in {"structures", "copies"}:
        raise ValueError("该模块不支持选择式生成")
    approved_cases = _approved_case_ids()
    items: list[dict[str, Any]] = []
    for row in _topic_rows():
        if not row.get("selected"):
            continue
        title = str(row.get("title") or "").strip()
        raw_case_ids = str(row.get("benchmarkCaseId") or "").strip()
        try:
            case_ids = parse_benchmark_case_ids(raw_case_ids)
        except ValueError:
            # Keep the bad row diagnosable in the API, but it will not enter a
            # visible selectable group until an actual case ID is chosen.
            case_ids = (raw_case_ids or "",)
        for case_id in case_ids:
            structure = _latest_structure_for_topic_case(title, case_id) if title and case_id else None
            structure_path = _project_relative_path(structure) if structure else ""
            structure_hash = _sha256_file(structure) if structure and structure.is_file() else ""
            current: Path | None = structure if module_id == "structures" else _latest_copy_for_topic_case(title, case_id)
            generated = current is not None
            eligible = True
            reason = ""
            if not title:
                eligible, reason = False, "选题标题为空"
            elif case_id not in approved_cases:
                eligible, reason = False, "尚未绑定已审核对标复刻拆解"
            elif module_id == "copies":
                if structure is None:
                    eligible, reason = False, "尚未生成对应编号的文案结构"
                elif not _is_checked_filename(structure):
                    eligible, reason = False, "文案结构尚未由所有者打 √ 确认"
            # A topic may branch into one or more benchmark cases, but every
            # generation selection must visibly identify its exact FNN source.
            # Omitting the ID for a single branch made two otherwise identical
            # rows impossible to distinguish in the selection dialog.
            display_title = f"{title} · {case_id}" if case_id else title
            current_path = _project_relative_path(current) if current else ""
            current_hash = _sha256_file(current) if current and current.is_file() else ""
            timestamp_path = current or structure
            item = {
                "id": f"{str(row.get('id') or '')}::{case_id}",
                "moduleId": module_id,
                "title": display_title,
                "topicTitle": title,
                "table": str(row.get("tableFile") or ""),
                "tablePath": str(row.get("tablePath") or ""),
                "benchmarkCaseId": case_id,
                "generated": generated,
                "generationMode": "regenerate" if generated else "initial",
                "generationLabel": "重新生成（保留历史版本）" if generated else "首次生成",
                "eligible": eligible,
                "reason": reason,
                "currentFormalPath": current_path,
                "currentFormalSha256": current_hash,
                "ownerConfirmed": bool(current and _is_checked_filename(current)),
                "structurePath": structure_path,
                "structureSha256": structure_hash,
                "structureFourStatus": _structure_four_editor_state(structure).get("structureFourStatus", "尚未生成结构") if structure else "尚未生成结构",
                "updatedAt": _file_updated_at(timestamp_path),
                "_sortMtime": _file_mtime_ns(timestamp_path),
            }
            item["fingerprint"] = _generation_candidate_fingerprint(item)
            items.append(item)
    items.sort(key=lambda item: (int(item.pop("_sortMtime", 0)), str(item.get("title") or "")), reverse=True)
    return {
        "generatedAt": now(),
        "moduleId": module_id,
        "label": "文案结构" if module_id == "structures" else "正文成稿",
        "skill": "copy-structure-generation" if module_id == "structures" else "final-copy-generation",
        "skillLabel": "文案结构生成Skill" if module_id == "structures" else "正文成稿生成Skill",
        "candidates": items,
    }


def _validated_generation_selection(module_id: str, selected: Any) -> list[dict[str, Any]]:
    """Rebuild and verify browser selections so stale or invented rows cannot run."""
    if not isinstance(selected, list) or not selected:
        raise ValueError("请至少选择一条要生成的内容")
    requested: list[tuple[str, str]] = []
    for item in selected:
        if not isinstance(item, dict):
            raise ValueError("生成选择格式无效")
        item_id = str(item.get("id") or "")
        fingerprint = str(item.get("fingerprint") or "")
        if not item_id or not fingerprint:
            raise ValueError("生成选择缺少当前候选凭据")
        requested.append((item_id, fingerprint))
    if len({item_id for item_id, _ in requested}) != len(requested):
        raise ValueError("同一选题不能重复选择")
    current = {item["id"]: item for item in generation_candidates(module_id)["candidates"]}
    resolved: list[dict[str, Any]] = []
    for item_id, fingerprint in requested:
        item = current.get(item_id)
        if not item or item.get("fingerprint") != fingerprint:
            raise ValueError("候选内容或前置资产已变化，请重新打开选择窗口")
        if not item.get("eligible"):
            raise ValueError(f"{item.get('title') or '该选题'}暂不可生成：{item.get('reason') or '前置条件未满足'}")
        resolved.append(item)
    return resolved


def _module_pending_items(module: dict[str, Any]) -> list[str]:
    module_id = str(module.get("id") or "")
    if module_id in {"books", "podcasts", "video-sources", "work-journals", "events"}:
        payload = _input_inventory_payload()
        return [str(row["source_path"]) for row in payload["rows"] if row["source_type"] == module_id and row["status"] == "未拆解"]
    if module_id == "gallery":
        return []
    if module_id == "cases":
        approved_sources = _approved_case_source_hashes()
        return [_project_relative_path(path) for path in _module_files(_module_root(module, "sourceRoot"), {".md", ".txt"}) if _sha256_file(path) not in approved_sources]
    if module_id == "topics":
        return [str(item["id"]) for item in today_topic_candidates().get("candidates", []) if not bool(item.get("generated"))]
    if module_id == "structures":
        titles = _output_structure_titles()
        approved_ids = _approved_case_ids()
        return [
            str(row.get("title") or "")
            for row in _topic_rows()
            if row.get("selected")
            and str(row.get("benchmarkCaseId") or "").strip() in approved_ids
            and str(row.get("title") or "").strip() not in titles
        ]
    if module_id == "copies":
        return [_project_relative_path(path) for path in sorted(_published_structure_paths()) if _structure_four_editor_state(path).get("structureFourFilled")]
    return [_project_relative_path(path) for path in _module_files(_module_root(module))]


def create_today_module_task(module_id: str, selected: Any = None) -> dict[str, Any]:
    module = _today_module_index().get(module_id)
    if module is None:
        raise ValueError("未知今日工作模块")
    skill_state = _skill_status(module)
    if skill_state["refreshMode"] == "waiting-integration":
        raise ValueError("该模块尚未接入 Skill，当前仅显示等待接入")
    if not skill_state["skillAvailable"]:
        raise PermissionError(skill_state["unlockReason"])
    selected_items = selected if isinstance(selected, list) and all(isinstance(item, str) for item in selected) else []
    generation_selections: list[dict[str, Any]] = []
    if module_id in {"structures", "copies"}:
        generation_selections = _validated_generation_selection(module_id, selected)
        selected_items = generation_selections
    if module_id == "cases":
        if not selected_items:
            raise ValueError("请至少选择一条要刷新的对标视频原文")
        allowed = {item["id"] for item in today_case_candidates()["candidates"]}
        if any(item not in allowed for item in selected_items):
            raise ValueError("案例库任务只能选择当前对标视频原文清单")
    elif module_id == "topics":
        if not selected_items:
            raise ValueError("请至少选择一个要刷新的对标账号文件")
        allowed = {item["id"] for item in today_topic_candidates().get("candidates", [])}
        if any(item not in allowed for item in selected_items):
            raise ValueError("选题库任务只能选择当前对标账号文件清单")
    elif module.get("selection") and not selected_items:
        raise ValueError("请先选择要生成配图的已确认正文")
    approved_video_batch: list[dict[str, str]] = []
    correction_batch: dict[str, Any] = {}
    continuation_batch: dict[str, Any] = {}
    video_source_import: list[dict[str, str]] = []
    if module_id == "cases":
        # The selected source-path manifest is already validated above.  Never
        # replace it with a whole-directory scan after the user has chosen a
        # subset in the refresh dialog.
        pass
    elif module.get("selection"):
        allowed = {item["id"] for item in today_gallery_candidates()["candidates"]}
        if any(item not in allowed for item in selected_items):
            raise ValueError("配图任务只能选择当前已确认正文")
    elif module_id == "video-sources":
        continuation_batch = video_active_batch(PROJECT_ROOT)
        if continuation_batch:
            selected_items = [
                f"{source_id}｜续接第 {continuation_batch['batch_number']} 批｜当前阶段：{continuation_batch['phase']}"
                for source_id in continuation_batch["source_ids"]
            ]
        else:
            approved_video_batch = video_refresh_batch(PROJECT_ROOT)
        if approved_video_batch:
            selected_items = [
                f"{item['source_id']}｜校对候选：{item['candidate_path']}｜小审回执：{item['audit_receipt']}"
                for item in approved_video_batch
            ]
        elif not continuation_batch:
            correction_batch = video_correction_batch(PROJECT_ROOT)
            selected_items = [
                f"{item['source_id']}｜标准化源：{item['source_path']}"
                for item in correction_batch.get("sources", [])
            ]
            if not selected_items:
                video_source_import = [
                    {"source_id": str(row.get("source_id") or ""), "source_path": str(row.get("source_path") or "")}
                    for row in _input_inventory_payload().get("rows", [])
                    if row.get("source_type") == "video-sources"
                    and row.get("source_origin") == "manual-file"
                    and row.get("status") == "未拆解"
                ]
                selected_items = [
                    f"{item['source_id']}｜用户确认输入：{item['source_path']}"
                    for item in video_source_import
                ]
    elif module_id not in {"structures", "copies"}:
        selected_items = _module_pending_items(module)
    if module_id == "video-sources" and not selected_items:
        raise ValueError("视频文案未找到可校验的下一连续批，未创建 Codex 任务")
    navigation = desktop_navigation_status()
    if not navigation["available"]:
        raise RuntimeError(str(navigation.get("message") or "当前 Codex 桌面桥接不可用，请先打开 Codex 桌面"))
    session_id = uuid.uuid4().hex[:12]
    approved_source_manifest = ""
    if approved_video_batch:
        manifest_path = (TODAY_TASK_RUNTIME_ROOT / "video-source-manifests" / f"{session_id}.json").resolve()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "schema": "video-corrected-source-batch-v1",
            "status": "approved",
            "source_count": len(approved_video_batch),
            "sources": approved_video_batch,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        approved_source_manifest = _project_relative_path(manifest_path)
    task_batch = [
        {
            "title": item["title"],
            "progress": "pending",
            "attempt": 1,
            "nextStep": item["generationLabel"] + "，等待小姜按清单串行分配。",
            "generationMode": item["generationMode"],
            "currentFormalPath": item["currentFormalPath"],
            "auditConclusion": "待小审",
        }
        for item in generation_selections
    ]
    session = create_session({
        "action": "today-refresh",
        "title": f"今日工作｜刷新{module['label']}",
        "message": _today_module_prompt(module, selected_items, approved_source_manifest=approved_source_manifest, video_correction=correction_batch, video_continuation=continuation_batch, video_source_import=video_source_import),
        "workflow": {"todayModuleId": module_id, "skill": module["skill"], "preflightSkill": "standardize-and-inventory-sources" if correction_batch or video_source_import else "", "selected": selected_items, "generationSelections": generation_selections, "videoContinuation": continuation_batch, "videoSourceImport": video_source_import, "inputScopeLabel": f"{len(selected_items)} 项待处理"},
        "batch": task_batch,
        "skipApproval": True,
    }, session_id=session_id)
    return _session_summary(_queue_visible_task(session["id"]), include_events=False)


def today_gallery_candidates() -> dict[str, Any]:
    """List checked final copies as initial or regenerate gallery work.

    A gallery folder is the only completion evidence.  This deliberately keeps
    a checked final copy with no matching folder in ``未生成`` and makes an
    existing folder a controlled ``已生成`` regeneration choice.
    """
    completed = _gallery_completed_directories()
    candidates: list[dict[str, Any]] = []
    for path in _owner_confirmed_copy_paths():
        title = _normalized_copy_title(_heading_title(path))
        gallery_directory = completed.get(_gallery_topic_key(title))
        generated = gallery_directory is not None
        candidates.append({
            "id": _project_relative_path(path),
            "title": title or path.stem.lstrip("√✓").strip(),
            "generated": generated,
            "generationMode": "regenerate" if generated else "initial",
            "generationLabel": "重新生成（保留历史版本）" if generated else "首次生成",
            "updatedAt": _file_updated_at(gallery_directory or path),
            "_sortMtime": _file_mtime_ns(gallery_directory or path),
        })
    candidates.sort(key=lambda item: (int(item.pop("_sortMtime", 0)), str(item["title"])), reverse=True)
    return {"label": "配图库", "candidates": candidates}


def _case_registry_entries() -> list[dict[str, Any]]:
    registry_path = PROJECT_ROOT / "00_系统说明" / "benchmark-case-registry.json"
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in payload.get("cases", []) if isinstance(item, dict)]


def _case_breakdown_path(value: str) -> Path | None:
    raw = Path(str(value or "").strip())
    if not str(raw):
        return None
    candidate = raw if raw.is_absolute() else PROJECT_ROOT / raw
    candidate = candidate.resolve()
    root = ASSET_ROOT / "05_案例库" / "02_对标复刻拆解"
    return candidate if candidate.is_relative_to(root.resolve()) else None


def today_case_candidates() -> dict[str, Any]:
    """List each benchmark source once, split by whether a breakdown exists.

    A formal Markdown on disk is the sole evidence for “已生成”; audit state
    is intentionally not used to hide an existing result from regeneration.
    """
    module = _today_module_index()["cases"]
    source_root = _module_root(module, "sourceRoot")
    registered = {
        str(item.get("sourceTitle") or "").strip(): item
        for item in _case_registry_entries()
        if str(item.get("sourceTitle") or "").strip()
    }
    candidates: list[dict[str, Any]] = []
    for source in _module_files(source_root, {".md", ".txt"}):
        source_title = source.stem.strip()
        registration = registered.get(source_title, {})
        breakdown = _case_breakdown_path(str(registration.get("breakdownPath") or ""))
        generated = bool(breakdown and breakdown.is_file())
        timestamp_path = breakdown if generated else source
        candidates.append({
            "id": _project_relative_path(source),
            "title": source_title,
            "caseId": str(registration.get("id") or ""),
            "generated": generated,
            "generationMode": "regenerate" if generated else "initial",
            "generationLabel": "重新生成（保留历史版本）" if generated else "首次生成",
            "currentFormalPath": _project_relative_path(breakdown) if generated and breakdown else "",
            "updatedAt": _file_updated_at(timestamp_path),
            "_sortMtime": _file_mtime_ns(timestamp_path),
        })
    candidates.sort(key=lambda item: (int(item.pop("_sortMtime", 0)), str(item["title"])), reverse=True)
    return {"label": "案例库", "candidates": candidates}


def submit_edit_candidate(candidate_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"(?:topics|cases|structure|copy)_[0-9a-f]{24}", candidate_id):
        raise ValueError("编辑候选编号无效")
    candidate_path = (TODAY_CANDIDATE_ROOT / f"{candidate_id}.json").resolve()
    if not candidate_path.is_relative_to(TODAY_CANDIDATE_ROOT.resolve()) or not candidate_path.is_file():
        raise FileNotFoundError("编辑候选不存在")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    source = (PROJECT_ROOT / str(candidate.get("sourcePath") or "")).resolve()
    if not source.is_relative_to(ASSET_ROOT.resolve()) or not source.is_file():
        raise FileNotFoundError("编辑候选的正式来源不存在")
    if candidate.get("sourceSha256") != _sha256_file(source):
        raise EditorConflictError("正式文件已变化，候选已失效；请重新读取后编辑")
    candidate["status"] = "submitted"
    candidate["submittedAt"] = now()
    candidate_path.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prompt = f"""请作为小姜处理网页资产编辑候选。

候选文件：{_project_relative_path(candidate_path)}
正式来源：{_project_relative_path(source)}
来源哈希：{candidate['sourceSha256']}

先由小审独立审核候选内容、来源哈希和编辑影响。只有 approved 后，才由受控发布步骤写回正式来源；若退回，不得修改正式文件。完成后写回正式审核回执和发布结果。"""
    session = create_session({
        "action": "asset-edit-audit", "title": f"今日工作｜审核编辑候选 {source.stem}", "message": prompt,
        "workflow": {"candidateId": candidate_id, "sourcePath": _project_relative_path(source)}, "skipApproval": True,
    })
    return _session_summary(_queue_visible_task(session["id"]), include_events=False)


def _brand_portrait_files() -> set[str]:
    """Expose only the currently approved portrait assets from the manifest."""
    manifest = BRAND_SYSTEM_ROOT / "人物头像" / "portrait-manifest.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    portraits = payload.get("portraits") if isinstance(payload.get("portraits"), dict) else {}
    return {Path(str(value)).name for value in portraits.values()}


def _brand_icon_files() -> set[str]:
    manifest = BRAND_SYSTEM_ROOT / "图标" / "manifest.json"
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    icons = payload.get("icons") if isinstance(payload.get("icons"), list) else []
    return {f"{item}.svg" for item in icons if isinstance(item, str) and re.fullmatch(r"[a-z0-9-]+", item)}


def _safe_brand_asset_path(relative: str) -> Path:
    """Map public brand URLs to a small explicit asset allowlist."""
    normalized = Path(unquote(relative).replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("品牌资源路径不允许越界")
    parts = normalized.parts
    if parts == ("logo.png",):
        # Keep the public URL stable while serving the approved large-wordmark logo.
        target = BRAND_SYSTEM_ROOT / "标志" / "logo2.png"
    elif len(parts) == 2 and parts[0] == "icons" and parts[1] in _brand_icon_files():
        target = BRAND_SYSTEM_ROOT / "图标" / parts[1]
    elif len(parts) == 2 and parts[0] == "portraits" and parts[1] in _brand_portrait_files():
        target = BRAND_SYSTEM_ROOT / "人物头像" / "正式头像" / parts[1]
    elif len(parts) == 2 and parts[0] == "status" and parts[1] in BRAND_STATUS_FILES:
        target = BRAND_SYSTEM_ROOT / "人物头像" / "状态徽标" / parts[1]
    elif len(parts) == 2 and parts[0] == "community" and parts[1] in BRAND_COMMUNITY_FILES:
        target = BRAND_SYSTEM_ROOT / "社群介绍" / parts[1]
    elif len(parts) == 2 and parts[0] == "fonts" and parts[1] in BRAND_FONT_FILES:
        target = BRAND_SYSTEM_ROOT / "字体" / "OPPOSans" / parts[1]
    elif len(parts) == 1 and parts[0] in BRAND_STYLESHEET_FILES:
        target = BRAND_SYSTEM_ROOT / "品牌规范" / parts[0]
    else:
        raise ValueError("品牌资源不在公开白名单中")
    resolved = target.resolve()
    if not resolved.is_relative_to(BRAND_SYSTEM_ROOT.resolve()) or not resolved.is_file():
        raise FileNotFoundError("品牌资源不存在")
    return resolved


def _load_member_capabilities() -> set[str]:
    if not MEMBER_MANIFEST.is_file():
        return set()
    try:
        payload = json.loads(MEMBER_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {value for value in payload.get("capabilities", []) if isinstance(value, str)}


def _walk_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    for current, dirs, names in os.walk(root, onerror=lambda _error: None):
        dirs[:] = [item for item in dirs if item not in IGNORED_DIR_NAMES]
        for name in names:
            if name in IGNORED_FILE_NAMES or name.startswith("~$"):
                continue
            path = Path(current) / name
            try:
                if path.is_file():
                    files.append(path)
            except OSError:
                continue
    return files


def _content_type_registry() -> list[dict[str, Any]]:
    """Load the user-editable, relative-path-only type registry."""
    try:
        payload = json.loads(CONTENT_TYPE_REGISTRY.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("内容类型注册表不存在") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("内容类型注册表格式不正确") from exc
    if payload.get("schema") != "ai-content-workbench-content-types-v1":
        raise RuntimeError("内容类型注册表版本不受支持")
    entries = payload.get("types")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("内容类型注册表未登记任何类型")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in entries:
        if not isinstance(raw, dict):
            raise RuntimeError("内容类型注册表包含无效条目")
        type_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        roots = raw.get("roots")
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,48}", type_id) or not name or type_id in seen:
            raise RuntimeError("内容类型注册表的标识或名称无效")
        if not isinstance(roots, dict) or set(roots) != {"input", "process", "output"}:
            raise RuntimeError(f"内容类型 {name} 的三库目录未完整登记")
        normalized_roots: dict[str, str | None] = {}
        for stage, relative in roots.items():
            if relative is None:
                normalized_roots[stage] = None
                continue
            if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
                raise RuntimeError(f"内容类型 {name} 的目录必须是相对路径")
            path = _safe_asset_path(relative)
            normalized_roots[stage] = path.relative_to(ASSET_ROOT.resolve()).as_posix()
        workflow_mode = str(raw.get("workflowMode") or "assets-plan")
        if workflow_mode not in {"full", "assets-plan"}:
            raise RuntimeError(f"内容类型 {name} 的工作台能力无效")
        deployment_status = str(raw.get("deploymentStatus") or "deployed")
        if deployment_status not in {"deployed", "not-deployed"}:
            raise RuntimeError(f"内容类型 {name} 的部署状态无效")
        if deployment_status == "deployed" and not normalized_roots["output"]:
            raise RuntimeError(f"内容类型 {name} 已部署但未登记正式正文目录")
        result.append({
            "id": type_id,
            "name": name,
            "memberOnly": bool(raw.get("memberOnly")),
            "icon": str(raw.get("icon") or "folder"),
            "workflowMode": workflow_mode,
            "deploymentStatus": deployment_status,
            "roots": normalized_roots,
        })
        seen.add(type_id)
    return result


def _meaningful_markdown_files(root: Path) -> list[Path]:
    """Return formal body files, excluding placeholders and documentation."""
    result: list[Path] = []
    for path in _walk_files(root):
        if path.suffix.lower() != ".md" or path.name.lower() in {"readme.md", "index.md"}:
            continue
        stem = path.stem.lower()
        if stem.startswith(("_", "template", "模板")):
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text.replace(BRAND_FOOTER, "").strip():
            result.append(path)
    return result


def _content_type_available(item: dict[str, Any]) -> tuple[bool, list[Path]]:
    output = item["roots"].get("output")
    if item.get("deploymentStatus") != "deployed" or not output:
        return False, []
    bodies = _meaningful_markdown_files(_safe_asset_path(output))
    return (not item["memberOnly"] or bool(bodies)), bodies


def _registered_content_type(type_id: str) -> dict[str, Any] | None:
    return next((item for item in _content_type_registry() if item["id"] == type_id), None)


def _format_time(timestamp: float | None) -> str | None:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds") if timestamp else None


def _topic_rows_except_no() -> int:
    """Count usable topic-table rows, excluding only rows explicitly marked no."""
    return sum(str(row.get("selectionValue") or "").strip() != "否" for row in _topic_rows())


def _gallery_topic_folder_count() -> int:
    """Each first-level gallery folder is one generated topic, not one image."""
    if not GALLERY_ROOT.is_dir():
        return 0
    total = 0
    for item in GALLERY_ROOT.iterdir():
        try:
            if item.is_dir() and item.name not in IGNORED_DIR_NAMES and not item.name.startswith("."):
                total += 1
        except OSError:
            continue
    return total


def gallery_output_count() -> int:
    """Return generated copy-gallery packages for the cumulative-output chart.

    A package is the first-level directory created for one copy, rather than
    each individual image file inside it.  This keeps the data-center metric
    aligned with the gallery card's existing business count.
    """
    return _gallery_topic_folder_count()


def _asset_source_count(item: dict[str, Any], files: list[Path]) -> int:
    """Apply the asset-center's business counting contract for named sources."""
    mode = item.get("countMode")
    if mode == "topic-rows-except-no":
        return _topic_rows_except_no()
    if mode == "markdown-files":
        return sum(path.suffix.lower() == ".md" for path in files)
    if mode == "copy-topics":
        return len(_output_copy_titles())
    if mode == "case-cards":
        return _case_card_count()
    return len(files)


def _source_snapshot(item: dict[str, Any], capabilities: set[str]) -> dict[str, Any]:
    path = _safe_asset_path(item["path"])
    files = _walk_files(path)
    member = item.get("member")
    registered = _registered_content_type(str(member)) if member else None
    unlocked = not member or (
        _content_type_available(registered)[0]
        if registered is not None
        else bool(member in capabilities and files)
    )
    visible = files if unlocked else []
    ordered = sorted(visible, key=lambda file: file.stat().st_mtime if file.exists() else 0, reverse=True)
    recent = []
    for file in ordered[:8]:
        try:
            stat = file.stat()
            recent.append({"name": file.name, "path": file.relative_to(PROJECT_ROOT).as_posix(), "updatedAt": _format_time(stat.st_mtime), "size": stat.st_size})
        except (OSError, ValueError):
            continue
    latest = ordered[0].stat().st_mtime if ordered else None
    count = _asset_source_count(item, visible) if unlocked else 0
    return {"label": item["label"], "relativePath": item["path"], "exists": path.is_dir(), "memberOnly": bool(member), "memberCapability": member, "unlocked": unlocked, "count": count, "latestAt": _format_time(latest), "recent": recent}


def _group_snapshot(group: dict[str, Any], capabilities: set[str]) -> dict[str, Any]:
    sources = [_source_snapshot(item, capabilities) for item in group["sources"]]
    members = [item for item in sources if item["memberOnly"]]
    public = [item for item in sources if not item["memberOnly"]]
    unlocked = [item for item in members if item["unlocked"]]
    access = "public" if not members else ("locked" if not public and not unlocked else "partial" if len(unlocked) < len(members) else "unlocked")
    latest = max((item["latestAt"] for item in sources if item["latestAt"]), default=None)
    return {**{key: group[key] for key in ("stage", "stageLabel", "eyebrow", "id", "title", "description")}, "access": access, "count": sum(item["count"] for item in sources), "latestAt": latest, "sources": sources}


def asset_overview() -> dict[str, Any]:
    capabilities = _load_member_capabilities()
    catalog = _asset_catalog_snapshot()
    catalog_by_id = {str(section.get("id") or ""): section for section in catalog}
    # The V1 data center and the V1 asset map share one visible source of
    # truth.  Legacy ASSET_GROUPS remains only for historical open-folder
    # compatibility and no longer drives displayed statistics.
    totals = {stage: int(catalog_by_id.get(stage, {}).get("count") or 0) for stage in ("input", "process", "output")}
    footer_lines = [line.strip("• ") for line in BRAND_FOOTER.splitlines() if line.strip() and line.strip() != "---"]
    match = re.search(r"微信：\s*([^\s]+)", BRAND_FOOTER)
    type_libraries = []
    for item in _content_type_registry():
        available, bodies = _content_type_available(item)
        roots = []
        for stage in ("input", "process", "output"):
            relative = item["roots"].get(stage)
            if not relative:
                roots.append({
                    "stage": stage,
                    "label": {"input": "输入库", "process": "处理库", "output": "输出库"}[stage],
                    "relativePath": "",
                    "exists": False,
                    "count": 0,
                    "deploymentStatus": "not-deployed",
                })
                continue
            path = _safe_asset_path(relative)
            roots.append({
                "stage": stage,
                "label": {"input": "输入库", "process": "处理库", "output": "输出库"}[stage],
                "relativePath": relative,
                "exists": path.is_dir(),
                "count": len(_meaningful_markdown_files(path)) if available else 0,
                "deploymentStatus": item["deploymentStatus"],
            })
        type_libraries.append({"id": item["id"], "name": item["name"], "available": available, "memberOnly": item["memberOnly"], "deploymentStatus": item["deploymentStatus"], "roots": roots, "bodyCount": len(bodies) if available else 0})
    return {"generatedAt": now(), "groups": [], "catalog": catalog, "typeLibraries": type_libraries, "stageTotals": totals, "memberManifestDetected": MEMBER_MANIFEST.is_file(), "memberCapabilities": sorted(capabilities), "brand": {"lines": footer_lines, "wechat": match.group(1) if match else ""}}


def _brand_info() -> dict[str, str | list[str]]:
    footer_lines = [line.strip("• ") for line in BRAND_FOOTER.splitlines() if line.strip() and line.strip() != "---"]
    match = re.search(r"微信：\s*([^\s]+)", BRAND_FOOTER)
    return {"lines": footer_lines, "wechat": match.group(1) if match else ""}


def _apply_snapshot_asset_counts(assets: dict[str, Any], snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """Keep page metadata from snapshots without overriding V1 live counts."""
    # Historical snapshots use the retired ASSET_GROUPS layout.  Overlaying
    # their totals onto the active catalog made the data page disagree with
    # 资产中心 and 今日工作 after a refresh.  Live catalog counts are now the
    # sole displayed source; the snapshot is retained for trend history only.
    return assets


def content_types() -> list[dict[str, Any]]:
    result = []
    for item in _content_type_registry():
        available, bodies = _content_type_available(item)
        result.append({
            "id": item["id"], "name": item["name"], "available": available,
            "memberOnly": item["memberOnly"], "workflowMode": item["workflowMode"],
            "icon": item["icon"], "bodyCount": len(bodies) if available else 0,
            "deploymentStatus": item["deploymentStatus"],
            "unlockReason": "正式正文已检测到" if available and item["memberOnly"] else "公开类型" if available else "目录尚未部署" if item["deploymentStatus"] == "not-deployed" else "等待本机正式正文",
        })
    return result


def cumulative_output_by_content_type() -> list[dict[str, Any]]:
    """Count current Markdown assets by the registered content-type order.

    A registered but not-yet-deployed type stays visible with a zero value so
    the data-center chart never invents a production capability or hides a
    planned content line.
    """
    result: list[dict[str, Any]] = []
    for item in _content_type_registry():
        output = item["roots"].get("output")
        count = len(_module_files(_safe_asset_path(output), {".md"})) if output and item.get("deploymentStatus") == "deployed" else 0
        result.append({
            "id": item["id"],
            "name": item["name"],
            "count": count,
            "deployed": item.get("deploymentStatus") == "deployed" and bool(output),
        })
    return result


def _topic_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not TOPIC_ROOT.is_dir():
        return rows
    for table in sorted(TOPIC_ROOT.glob("*.md")):
        try:
            parsed = _parse_markdown_table(table)
        except (OSError, ValueError):
            continue
        for row_index, cells in enumerate(parsed["rows"], start=1):
            try:
                likes = int(cells[4].replace(",", "") or 0)
            except ValueError:
                likes = 0
            rows.append({"id": f"{table.name}:{row_index}", "title": cells[1], "keyword": cells[0], "selected": cells[6] == "是", "selectionValue": cells[6], "benchmarkCaseId": cells[7], "status": cells[8] or "待生成结构", "likes": likes, "table": table.stem, "tableFile": table.name, "tablePath": table.relative_to(PROJECT_ROOT).as_posix(), "line": row_index, "pipelineRow": row_index - 1})
    return rows


def topic_overview() -> dict[str, Any]:
    selected = [row for row in _topic_rows() if row["selected"]]
    return {"generatedAt": now(), "topics": sorted(selected, key=lambda item: (-item["likes"], item["title"])), "states": dict(Counter(row["status"] for row in selected))}


def _is_checked_filename(path: Path) -> bool:
    return _has_checkmark(path.name)


def _has_checkmark(value: str) -> bool:
    """Recognize the owner-facing completion marker in a filename or candidate label."""
    return str(value or "").lstrip().startswith(CHECKMARK_PREFIXES)


def _copy_editor_check_state(path: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Expose a saved owner check mark before the formal audit publishes it.

    Browser edits are intentionally written as candidates first.  Previously a
    check mark in the candidate filename was rendered in the page heading but
    ignored by the sidebar filter, making a user-completed draft look pending.
    This is only a display/work-queue state: it never treats a candidate as an
    approved formal publication.
    """
    formal_checked = _is_checked_filename(path)
    candidate_checked = (
        str(candidate.get("candidateStatus") or "") in {"draft", "submitted"}
        and _has_checkmark(str(candidate.get("candidateFilename") or ""))
    )
    return {
        "pending": not (formal_checked or candidate_checked),
        "copyEditorStatus": "candidate-marked" if candidate_checked and not formal_checked else ("formal-marked" if formal_checked else "pending"),
    }


def _markdown_count(root: Path, *, checked: bool | None = None) -> int:
    files = [path for path in _walk_files(root) if path.suffix.lower() == ".md"]
    if checked is None:
        return len(files)
    return sum(_is_checked_filename(path) is checked for path in files)


def _structure_revision_key(path: Path, root: Path) -> str:
    """Collapse timestamped structure revisions without collapsing branches."""
    stem = path.stem.lstrip("√✓").strip()
    stem = re.sub(r"_\d{8}(?:-|_)\d{6}(?:（[^）]+）)?$", "", stem)
    try:
        parent = path.parent.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        parent = str(path.parent.resolve())
    return f"{parent}/{stem}".lower()


def _latest_structure_pending_count(root: Path) -> int:
    """Count only unconfirmed current revisions, never unconfirmed history."""
    latest: dict[str, Path] = {}
    for path in _module_files(root, {".md"}):
        key = _structure_revision_key(path, root)
        previous = latest.get(key)
        if previous is None or path.stat().st_mtime_ns > previous.stat().st_mtime_ns:
            latest[key] = path
    return sum(not _is_checked_filename(path) for path in latest.values())


def _checked_copy_count(root: Path) -> int:
    """Count the checked final-copy files shown by the Today正文 editor."""
    return sum(
        path.suffix.lower() == ".md" and _is_checked_filename(path)
        for path in _walk_files(root)
    )


def _today_tasks_for_type(
    type_id: str,
    queue_snapshot: dict[str, Any] | None = None,
    data_snapshot: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return the six Today cards for one registered content type.

    Only dry-goods has a complete public folder and Skill contract today.  Other
    types remain explicit locked cards until their paths and Skills are added to
    the registry, rather than leaking member counts or inventing mappings.
    """
    content_type = next((item for item in content_types() if item["id"] == type_id), None)
    if content_type is None:
        raise ValueError("未知内容类型")
    if type_id != "dry-goods" or not content_type["available"]:
        unlocked_but_not_installed = bool(content_type["available"])
        return [{
            "id": card_id,
            "tag": "待安装" if unlocked_but_not_installed else "会员专享",
            "title": content_type["name"],
            "count": None,
            "status": "目录已解锁，生产链路待安装" if unlocked_but_not_installed else "当前类型尚未解锁",
            "locked": True,
            "target": {"kind": "locked"},
        } for card_id in ("optimize-copy", "fill-structure-four", "generate-structure", "select-topic", "refresh-topics", "break-review")]

    refresh_state = data_snapshot.get("todayRefresh", {}) if isinstance(data_snapshot, dict) else {}
    benchmark_refresh = refresh_state.get("benchmark", {}) if isinstance(refresh_state, dict) else {}
    review_refresh = refresh_state.get("dailyReview", {}) if isinstance(refresh_state, dict) else {}
    snapshot_counts = (
        data_snapshot.get("todayWork", {}).get("dryGoods", {})
        if isinstance(data_snapshot, dict) and isinstance(data_snapshot.get("todayWork"), dict)
        else {}
    )

    def refresh_card(card_id: str, title: str, status: str, action: str, state: dict[str, Any]) -> dict[str, Any]:
        pending = max(0, int(state.get("pendingCount") or 0)) if isinstance(state, dict) else 0
        requested_display = str(state.get("displayMode") or "") if isinstance(state, dict) else ""
        display = "count" if pending > 0 else "zero" if requested_display == "zero" else "refresh"
        return {
            "id": card_id,
            "tag": "待刷新",
            "title": title,
            "count": pending if display == "count" else 0 if display == "zero" else None,
            "pendingCount": pending,
            "displayMode": display,
            "status": status,
            "updatedAt": state.get("updatedAt", "") if isinstance(state, dict) else "",
            "completedToday": bool(state.get("completedToday")) if isinstance(state, dict) else False,
            "completedAt": state.get("completedAt", "") if isinstance(state, dict) else "",
            "target": {"kind": "refresh", "action": action},
        }

    if snapshot_counts:
        # The copy editor is a live file surface. Its card must use the same
        # checked-file rule rather than a possibly stale data-center snapshot.
        optimize_count = _checked_copy_count(COPY_ROOT)
        unchecked_structures = int(snapshot_counts.get("fillStructureFour") or 0)
        pending_structures = int(snapshot_counts.get("generateStructure") or 0)
        untyped_count = int(snapshot_counts.get("selectTopic") or 0)
    else:
        rows = _topic_rows()
        typed_topics = [row for row in rows if row["contentType"] == content_type["name"]]
        selected_topics = [row for row in typed_topics if row["selected"]]
        optimize_count = _checked_copy_count(COPY_ROOT)
        unchecked_structures = _markdown_count(STRUCTURE_ROOT, checked=False)
        pending_structures = sum(row["status"] == "待生成结构" for row in selected_topics)
        untyped_count = sum(
            not str(row.get("contentType", "")).strip()
            and str(row.get("selectionValue", "是" if row.get("selected") else "")).strip() != "否"
            for row in rows
        )
    return [
        {"id": "optimize-copy", "tag": "已撰写", "title": "干货型正文", "count": optimize_count, "status": "已打勾的成稿", "target": {"kind": "editor", "surface": "copy"}},
        {"id": "fill-structure-four", "tag": "待填写", "title": "干货型爆款结构4", "count": unchecked_structures, "status": "待人工撰写", "target": {"kind": "editor", "surface": "structure"}},
        {"id": "generate-structure", "tag": "待生成", "title": "干货型结构123", "count": pending_structures, "status": "已选中，待生成", "target": {"kind": "refresh", "action": "generate-structure"}},
        {"id": "select-topic", "tag": "待筛选", "title": "干货型爆款选题", "count": untyped_count, "status": "待人工筛选", "target": {"kind": "editor", "surface": "topics"}},
        refresh_card("refresh-topics", "爆款选题", "对标账号可处理", "refresh-topics", benchmark_refresh),
        refresh_card("break-review", "今日复盘", "复盘资料可处理", "break-review", review_refresh),
    ]


def _structure_file_for_topic(topic: str) -> Path | None:
    """Resolve only the formal structure naming contract used by the copy pipeline."""
    candidates = [path for path in STRUCTURE_ROOT.glob("*.md") if path.name.startswith(topic + "_")]
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    # Historical formal structures can carry dates or status prefixes. Their
    # H1 remains the authoritative topic identity, not their filename.
    normalized = re.sub(r"\s+", "", topic).lstrip("√")
    matches: list[Path] = []
    for path in STRUCTURE_ROOT.glob("*.md"):
        try:
            if re.sub(r"\s+", "", structure_topic_title(path)).lstrip("√") == normalized:
                matches.append(path)
        except OSError:
            continue
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def _checked_structure_file_for_topic(topic: str) -> Path | None:
    """Resolve the latest structure explicitly marked as manually filled.

    The workbench treats a leading ``√`` or ``✓`` in the formal structure
    filename as the user's explicit confirmation that structure four is ready
    for copy production. Content parsing remains useful for diagnostics, but
    must not silently override that manual workflow marker.
    """
    normalized = _normalized_copy_title(topic)
    matches: list[Path] = []
    for path in STRUCTURE_ROOT.glob("*.md"):
        if not _is_checked_filename(path):
            continue
        filename = _normalized_copy_title(path.stem)
        if filename.startswith(normalized + "_"):
            matches.append(path)
            continue
        try:
            if _normalized_copy_title(structure_topic_title(path)) == normalized:
                matches.append(path)
        except OSError:
            continue
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _skill_frontmatter_name(text: str) -> str:
    match = re.search(r"\A---\s*\n.*?^name:\s*([^\s#]+)", text, flags=re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def copy_production_capabilities() -> dict[str, Any]:
    """Read the currently enabled formal Skills before creating a copy batch.

    This is an availability check, not a version-consistency gate. The body
    Skill is the authority for interpreting its current contract and references.
    Versions and hashes are retained only as a background audit snapshot.
    """
    errors: list[str] = []
    try:
        registry = json.loads(SYSTEM_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ready": False, "checkedAt": now(), "chain": [], "errors": [f"无法读取系统注册表：{exc}"], "summary": "当前正文 Skill 不可用"}
    skills = registry.get("skills") if isinstance(registry.get("skills"), list) else []
    registered = {str(item.get("id")): item for item in skills if isinstance(item, dict)}
    chain: list[dict[str, Any]] = []
    canonical_root = CANONICAL_SKILL_ROOT.resolve()
    adapter_root = CODEX_SKILL_ROOT.resolve()
    for skill_id in COPY_PRODUCTION_SKILL_IDS:
        item = registered.get(skill_id)
        if not item:
            errors.append(f"注册表缺少 {skill_id}")
            continue
        source_dir = str(item.get("sourceDir") or "").strip()
        version = str(item.get("contractVersion") or "").strip()
        status = str(item.get("status") or "")
        if status != "active":
            errors.append(f"{skill_id} 当前未启用")
        if not source_dir:
            errors.append(f"{skill_id} 缺少正式源目录")
            continue
        source_path = (canonical_root / source_dir / "SKILL.md").resolve()
        entry_path = (adapter_root / skill_id / "SKILL.md").resolve()
        source_text = ""
        entry_text = ""
        if not source_path.is_relative_to(canonical_root) or not source_path.is_file():
            errors.append(f"{skill_id} 的正式源 Skill 不存在")
        else:
            try:
                source_text = source_path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"无法读取 {skill_id} 的正式源 Skill：{exc}")
        if not entry_path.is_relative_to(adapter_root) or not entry_path.is_file():
            errors.append(f"{skill_id} 的 Codex 入口不存在")
        else:
            try:
                entry_text = entry_path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"无法读取 {skill_id} 的 Codex 入口：{exc}")
            else:
                if _skill_frontmatter_name(entry_text) != skill_id:
                    errors.append(f"{skill_id} 的 Codex 入口标识不一致")
        paths = [path for path in (source_path, entry_path) if path.is_file()]
        updated_at = max((path.stat().st_mtime for path in paths), default=0)
        chain.append({
            "id": skill_id,
            "displayName": str(item.get("displayName") or skill_id),
            "registryVersion": version,
            "status": status,
            "sourceDir": source_dir,
            "sourcePath": _relative_project_path(source_path),
            "entryPath": _relative_project_path(entry_path),
            "sourceSha256": _file_sha256(source_path) if source_path.is_file() else "",
            "entrySha256": _file_sha256(entry_path) if entry_path.is_file() else "",
            "updatedAt": _format_time(updated_at) if updated_at else "",
            "inputSchema": str(item.get("inputSchema") or ""),
            "outputSchema": str(item.get("outputSchema") or ""),
        })
    ready = not errors and len(chain) == len(COPY_PRODUCTION_SKILL_IDS)
    summary = "当前正文 Skill 可用" if ready else "当前正文 Skill 不可用"
    return {"ready": ready, "checkedAt": now(), "chain": chain, "errors": errors, "summary": summary}


def copy_production_capability_status() -> dict[str, Any]:
    """Return only the availability information that the UI is allowed to show."""
    capabilities = copy_production_capabilities()
    return {
        "ready": capabilities["ready"],
        "checkedAt": capabilities["checkedAt"],
        "summary": capabilities["summary"],
        "errors": capabilities["errors"],
    }


def _json_object(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _relative_project_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _today_task_file(session_id: str, suffix: str) -> Path:
    return (TODAY_TASK_RUNTIME_ROOT / f"{session_id}{suffix}").resolve()


def _today_task_template(definition: dict[str, str]) -> str:
    template_name = str(definition.get("promptTemplate") or "")
    target = (TODAY_TASK_PROMPT_ROOT / template_name).resolve()
    if not template_name or not target.is_relative_to(TODAY_TASK_PROMPT_ROOT.resolve()):
        raise ValueError("今日工作提示词模板无效")
    try:
        prompt = target.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"未找到今日工作提示词模板：{exc}") from exc
    if not prompt:
        raise RuntimeError("今日工作提示词模板为空")
    return prompt


def _write_today_task_artifacts(session_id: str, definition: dict[str, str], content_type: str) -> tuple[str, str, str]:
    """Persist a Today-task-only manifest and the exact prompt sent to Codex."""
    runtime_root = TODAY_TASK_RUNTIME_ROOT.resolve()
    manifest = _today_task_file(session_id, ".json")
    prompt_file = _today_task_file(session_id, ".prompt.md")
    if not manifest.is_relative_to(runtime_root) or not prompt_file.is_relative_to(runtime_root):
        raise ValueError("今日工作运行态路径无效")
    prompt = _today_task_template(definition)
    source_type = str(definition.get("sourceType") or "")
    rejection_instruction = (
        "3. 审核退回、取消、失败或需要用户确认时，不得使用 `released`；"
        "应回写对应的 `rejected`、`blocked` 或 `waiting-user` 状态。"
    )
    if str(definition.get("skill") or "") == "generate-ip-ppt":
        rejection_instruction = (
            "3. 配图预审或成图审核退回时，不得使用 `released` 或 `rejected` 结束任务；"
            "应先回写 `repairing`，再按当前 Skill 的修复循环处理。"
        )
    if source_type:
        prompt = f"""{prompt.rstrip()}

## 工作台状态回写

本次工作台任务 ID：`{session_id}`。这不是产出步骤，不能替代当前正式 Skill 的调度、审核或输出规则。

1. 开始执行后运行：
   `python 03_工作台/scripts/report_visible_task_event.py --session {session_id} --event started`
2. 只有完成当前正式 Skill 的全部检查后，才运行 `released` 回写：
   - 本次没有待处理资料：追加 `--completion-basis no-pending`。
   - 本次产生正式结果并取得小审放行：追加 `--completion-basis audit-approved --audit-receipt <正式小审回执项目相对路径>`。
{rejection_instruction}
"""
    prompt = prompt.strip()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "workbench-today-task-v2",
        "taskId": session_id,
        "action": definition["action"],
        "contentType": content_type,
        "skill": definition["skill"],
        "promptTemplate": definition["promptTemplate"],
        "createdAt": now(),
    }
    temporary_manifest = manifest.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary_manifest, manifest)
    temporary_prompt = prompt_file.with_suffix(".md.tmp")
    temporary_prompt.write_text(prompt, encoding="utf-8")
    os.replace(temporary_prompt, prompt_file)
    return _relative_project_path(manifest), _relative_project_path(prompt_file), prompt


def _verified_published_topic_ids(topics: list[dict[str, Any]]) -> set[str]:
    """Return topics with a final copy bound to the current structure version."""
    bindings = verified_final_copy_bindings(PROJECT_ROOT, COPY_ROOT, AUDIT_RECEIPT_ROOT)
    published: set[str] = set()
    for topic in topics:
        structure = _structure_file_for_topic(str(topic.get("title") or ""))
        if not structure:
            continue
        try:
            relative = structure.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
            if (relative, _file_sha256(structure)) in bindings:
                published.add(str(topic["id"]))
        except (OSError, ValueError):
            continue
    return published


def _copy_generation_evidence(topic: dict[str, Any], output_titles: set[str]) -> list[str]:
    """Return stable evidence that a topic already has a generated copy.

    A formal copy in the output library and the topic-table status are both
    valid user-facing generation records. Audit receipt/hash matching remains
    a release gate, but is deliberately not used to hide an already generated
    topic from the pending one-click queue.
    """
    evidence: list[str] = []
    if _normalized_copy_title(str(topic.get("title") or "")) in output_titles:
        evidence.append("正文成稿库")
    if str(topic.get("status") or "").strip().startswith("已生成正文"):
        evidence.append("选题表状态")
    return evidence


def _count_files(path: Path) -> int:
    return len(_walk_files(path))


def _latest_at(path: Path) -> str | None:
    """Return the most recent file timestamp beneath one approved pipeline source."""
    candidates = _walk_files(path) if path.is_dir() else ([path] if path.is_file() else [])
    latest = max((item.stat().st_mtime for item in candidates), default=None)
    return _format_time(latest)


def _case_card_count() -> int:
    """Count only active formal CASE cards, never historical thought cards or indexes."""
    return sum(1 for path in _walk_files(CASE_CARD_ROOT) if path.suffix.lower() == ".md" and path.name.startswith("CASE-"))


def _featured_book_count() -> int:
    titles: set[str] = set()
    try:
        lines = BOOK_MODULE_INDEX.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        title = str(item.get("source_title") or "").strip()
        if item.get("status") == "ready" and title:
            titles.add(title)
    return len(titles)


def _selected_structure_rows(topics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for topic in topics:
        structure = _structure_file_for_topic(topic["title"])
        if structure:
            rows.append({"topic": topic, "structure": structure})
    return rows


def _normalized_copy_title(value: str) -> str:
    """Normalize topic identity while ignoring the formal copy version suffix."""
    title = re.sub(r"\s+", "", value).lstrip("√✓").strip()
    return re.sub(r"_\d{8}_\d{6}(?:（正文(?:优化)?）)?$", "", title)


def _output_copy_titles() -> set[str]:
    """Read titles only from formally published, hash-verified final copies."""
    titles: set[str] = set()
    for path in _published_copy_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        title = _normalized_copy_title(match.group(1) if match else path.stem)
        if title:
            titles.add(title)
    return titles


def _owner_confirmed_copy_paths() -> list[Path]:
    """Return final-copy files explicitly confirmed by the workspace owner."""
    return [path for path in _module_files(COPY_ROOT, {".md"}) if _is_checked_filename(path)]


def _owner_confirmed_copy_titles() -> set[str]:
    """Titles available to owner-controlled downstream actions such as 配图."""
    titles: set[str] = set()
    for path in _owner_confirmed_copy_paths():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
        title = _normalized_copy_title(match.group(1) if match else path.stem)
        if title:
            titles.add(title)
    return titles


def _output_copy_topic_ids(topics: list[dict[str, Any]], output_titles: set[str] | None = None) -> set[str]:
    """Map output-library H1 titles back to currently selected dry-goods topics."""
    titles = output_titles if output_titles is not None else _output_copy_titles()
    return {
        topic["id"]
        for topic in topics
        if _normalized_copy_title(str(topic.get("title") or "")) in titles
    }


def _approved_copy_receipts() -> int:
    """Count only formal dry-goods V3 approvals, never output files as receipts."""
    total = 0
    for receipt in AUDIT_RECEIPT_ROOT.glob("*.json") if AUDIT_RECEIPT_ROOT.is_dir() else []:
        try:
            payload = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
        if (
            payload.get("schema") == "ai-traffic-audit-receipt-v3"
            and payload.get("status") == "approved"
            and artifact.get("type") == "dry-goods-copy-v6"
        ):
            total += 1
    return total


def _db() -> sqlite3.Connection:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def _connection() -> Any:
    connection = _db()
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_store() -> None:
    global STORE_INITIALIZED_PATH
    database_path = DB_PATH.resolve()
    with STORE_INITIALIZATION_LOCK:
        if STORE_INITIALIZED_PATH == database_path and database_path.exists():
            return
        with _connection() as connection:
            # The workbench is accessed by the browser, watchdog and desktop
            # bridge concurrently. WAL plus a bounded busy wait avoids
            # spurious lock failures without discarding task history.
            try:
                connection.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                # A diagnostic/read-only connection may be holding an older
                # local database open. Startup must remain available.
                pass
            connection.executescript("""
        CREATE TABLE IF NOT EXISTS plans (id TEXT PRIMARY KEY, content_type TEXT NOT NULL, plan_date TEXT, weekdays TEXT NOT NULL, repeat_rule TEXT NOT NULL, monthly_day INTEGER NOT NULL DEFAULT 0, ends_at TEXT, remind_time TEXT NOT NULL, target_count INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS plan_completions (plan_id TEXT NOT NULL, occurrence_date TEXT NOT NULL, content_type TEXT NOT NULL, target_count INTEGER NOT NULL, completed_at TEXT NOT NULL, PRIMARY KEY (plan_id, occurrence_date));
        CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT NOT NULL, message TEXT NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL, approval_status TEXT NOT NULL, bridge_status TEXT NOT NULL, codex_thread_id TEXT NOT NULL DEFAULT '', codex_turn_id TEXT NOT NULL DEFAULT '', codex_project_id TEXT NOT NULL DEFAULT '', codex_project_root TEXT NOT NULL DEFAULT '', desktop_navigation_status TEXT NOT NULL DEFAULT 'not-opened', delivery_token_hash TEXT NOT NULL DEFAULT '', delivery_deadline_at TEXT NOT NULL DEFAULT '', bridge_log_path TEXT NOT NULL DEFAULT '', batch_json TEXT NOT NULL DEFAULT '', workflow_json TEXT NOT NULL DEFAULT '{}', execution_authorized INTEGER NOT NULL DEFAULT 0, recovery_state_path TEXT NOT NULL DEFAULT '', recovery_next_at TEXT NOT NULL DEFAULT '', recovery_failure_class TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, level TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'system', message TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, request_id_json TEXT NOT NULL, method TEXT NOT NULL, params_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, resolved_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS idx_events_session_id_id ON events(session_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_status_updated_at ON sessions(status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_approvals_session_created_at ON approvals(session_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS input_inventory (source_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_label TEXT NOT NULL, title TEXT NOT NULL, source_path TEXT NOT NULL, source_sha256 TEXT NOT NULL, processing_output_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL, status_reason TEXT NOT NULL, checked_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_input_inventory_type_status ON input_inventory(source_type, status);
        CREATE TABLE IF NOT EXISTS desktop_folder_requests (id TEXT PRIMARY KEY, path TEXT NOT NULL, label TEXT NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL DEFAULT '', agent_id TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_desktop_folder_requests_status_created ON desktop_folder_requests(status, created_at);
        """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}
            if "codex_thread_id" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN codex_thread_id TEXT NOT NULL DEFAULT ''")
            if "codex_turn_id" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN codex_turn_id TEXT NOT NULL DEFAULT ''")
            if "batch_json" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN batch_json TEXT NOT NULL DEFAULT ''")
            if "codex_project_id" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN codex_project_id TEXT NOT NULL DEFAULT ''")
            if "codex_project_root" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN codex_project_root TEXT NOT NULL DEFAULT ''")
            if "desktop_navigation_status" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN desktop_navigation_status TEXT NOT NULL DEFAULT 'not-opened'")
            if "workflow_json" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN workflow_json TEXT NOT NULL DEFAULT '{}'")
            if "execution_authorized" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN execution_authorized INTEGER NOT NULL DEFAULT 0")
            if "delivery_token_hash" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN delivery_token_hash TEXT NOT NULL DEFAULT ''")
            if "delivery_deadline_at" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN delivery_deadline_at TEXT NOT NULL DEFAULT ''")
            if "bridge_log_path" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN bridge_log_path TEXT NOT NULL DEFAULT ''")
            if "recovery_state_path" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN recovery_state_path TEXT NOT NULL DEFAULT ''")
            if "recovery_next_at" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN recovery_next_at TEXT NOT NULL DEFAULT ''")
            if "recovery_failure_class" not in columns:
                connection.execute("ALTER TABLE sessions ADD COLUMN recovery_failure_class TEXT NOT NULL DEFAULT ''")
            event_columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)")}
            if "kind" not in event_columns:
                connection.execute("ALTER TABLE events ADD COLUMN kind TEXT NOT NULL DEFAULT 'system'")
            if "detail_json" not in event_columns:
                connection.execute("ALTER TABLE events ADD COLUMN detail_json TEXT NOT NULL DEFAULT '{}'")
            plan_columns = {row["name"] for row in connection.execute("PRAGMA table_info(plans)")}
            if "target_count" not in plan_columns:
                connection.execute("ALTER TABLE plans ADD COLUMN target_count INTEGER NOT NULL DEFAULT 1")
            if "updated_at" not in plan_columns:
                connection.execute("ALTER TABLE plans ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''")
            if "monthly_day" not in plan_columns:
                connection.execute("ALTER TABLE plans ADD COLUMN monthly_day INTEGER NOT NULL DEFAULT 0")
        STORE_INITIALIZED_PATH = database_path


def reconcile_interrupted_sessions() -> None:
    """Retire invisible App Server tasks rather than pretending they are desktop work."""
    with _connection() as connection:
        # Historical completed turns may have retained a transient reconnect flag
        # after the previous workbench process stopped. They never need recovery.
        connection.execute(
            "UPDATE sessions SET bridge_status='completed', updated_at=? WHERE status='completed' AND bridge_status='reconnect-required'",
            (now(),),
        )
        # Gallery work is allowed to recover indefinitely. A missing Desktop
        # turn is a transport event, never a reason to terminate its audit
        # loop. Queue a visible resume with a persisted next-recovery time.
        connection.execute(
            "UPDATE sessions SET status='reconnecting', approval_status='approved', bridge_status='desktop-bridge-recovery-queued', desktop_navigation_status='recovery-queued', execution_authorized=1, recovery_failure_class='desktop-bridge', recovery_next_at=?, updated_at=? WHERE action='today-refresh' AND workflow_json LIKE '%gallery%' AND status IN ('submitted','running','repairing','needs-user','waiting-audit') AND codex_thread_id != '' AND bridge_status IN ('connected','reconnect-required','awaiting-visible-task')",
            (now(), now()),
        )
        # Only non-gallery legacy App Server transport sessions are not
        # visible Desktop work. Their historical blocked behaviour remains.
        connection.execute(
            "UPDATE sessions SET status='blocked', approval_status='needs-desktop-task', bridge_status='background-thread-not-visible', desktop_navigation_status='not-visible', execution_authorized=0, updated_at=? WHERE (action!='today-refresh' OR workflow_json NOT LIKE '%gallery%') AND status IN ('submitted','running','repairing','needs-user','waiting-audit') AND codex_thread_id != '' AND bridge_status IN ('connected','reconnect-required','awaiting-visible-task')",
            (now(),),
        )
        # A desktop prompt being pasted is not evidence that a Codex task has
        # started. Retire stale deliveries so they cannot keep the UI polling.
        deadline = (datetime.now().astimezone() - timedelta(minutes=2)).isoformat(timespec="seconds")
        connection.execute(
            "UPDATE sessions SET status='reconnecting', approval_status='approved', bridge_status='desktop-bridge-recovery-queued', desktop_navigation_status='recovery-queued', execution_authorized=1, recovery_failure_class='desktop-bridge', recovery_next_at=?, updated_at=? WHERE action='today-refresh' AND workflow_json LIKE '%gallery%' AND status IN ('creating-desktop-task','submitted','needs-agent','needs-user') AND codex_thread_id='' AND updated_at < ?",
            (now(), now(), deadline),
        )
        connection.execute(
            "UPDATE sessions SET status='expired', bridge_status='desktop-task-unconfirmed', desktop_navigation_status='unconfirmed', execution_authorized=0, updated_at=? WHERE (action!='today-refresh' OR workflow_json NOT LIKE '%gallery%') AND status IN ('submitted','needs-agent','needs-user') AND codex_thread_id='' AND updated_at < ?",
            (now(), deadline),
        )
        # A helper process is intentionally short-lived. If the workbench
        # restarted before it reported a sent task, let the user create again
        # instead of leaving a permanent spinner.
        connection.execute(
            "UPDATE sessions SET status='failed', bridge_status='desktop-bridge-interrupted', desktop_navigation_status='failed', updated_at=? WHERE (action!='today-refresh' OR workflow_json NOT LIKE '%gallery%') AND status='creating-desktop-task' AND bridge_status LIKE 'desktop-bridge-%' AND updated_at < ?",
            (now(), deadline),
        )


def _rows(query: str, values: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with _connection() as connection:
        return [dict(row) for row in connection.execute(query, values).fetchall()]


PLAN_REPEAT_RULES = {"none", "daily", "weekly", "monthly"}


def _parse_plan_date(value: Any, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是 YYYY-MM-DD 日期") from exc


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    first_next = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last_day = (first_next - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def _plan_weekdays(value: Any) -> list[int]:
    raw = value
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = []
    days = sorted({int(item) for item in raw or [] if str(item).isdigit() and 0 <= int(item) <= 6})
    return days


def _plan_monthly_day(value: Any, start: date) -> int:
    raw = start.day if value is None or value == "" else value
    try:
        monthly_day = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("每月执行日必须是 1 到 31") from exc
    if not 1 <= monthly_day <= 31:
        raise ValueError("每月执行日必须是 1 到 31")
    return monthly_day


def _plan_payload(payload: dict[str, Any], *, plan_id: str | None = None, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    # Planning is organizational metadata and does not execute or unlock a
    # content pipeline. Allow every registered type here; generation and asset
    # access continue to enforce their existing membership/deployment gates.
    allowed_types = {item["id"] for item in content_types()}
    type_id = str(payload.get("contentType", existing.get("content_type") if existing else "dry-goods"))
    if type_id not in allowed_types:
        raise ValueError("未知内容类型，不能加入计划")
    start_raw = payload.get("startDate", payload.get("date", existing.get("plan_date") if existing else date.today().isoformat()))
    start = _parse_plan_date(start_raw or date.today().isoformat(), "开始日期")
    repeat_rule = str(payload.get("repeatRule", existing.get("repeat_rule") if existing else "none"))
    if repeat_rule not in PLAN_REPEAT_RULES:
        raise ValueError("重复规则不正确")
    # The original schema required a reminder time. Keep it only so historical
    # rows remain readable; plans no longer expose or schedule by this value.
    reminder = str(existing.get("remind_time") if existing else "00:00") or "00:00"
    try:
        target_count = int(payload.get("targetCount", existing.get("target_count", 1) if existing else 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("目标条数必须是整数") from exc
    if not 1 <= target_count <= 999:
        raise ValueError("目标条数需在 1 到 999 条之间")
    if repeat_rule == "weekly":
        if "weekdays" in payload:
            weekdays = _plan_weekdays(payload.get("weekdays"))
            if not weekdays:
                raise ValueError("每周重复至少选择一天")
        else:
            weekdays = _plan_weekdays(existing.get("weekdays") if existing else []) or [start.weekday()]
        monthly_day = 0
    elif repeat_rule == "monthly":
        weekdays = []
        monthly_value = payload.get("monthlyDay", existing.get("monthly_day") if existing else start.day)
        monthly_day = _plan_monthly_day(start.day if str(monthly_value) in {"", "0", "None"} else monthly_value, start)
    else:
        weekdays = []
        monthly_day = 0
    raw_end = payload.get("endsAt", existing.get("ends_at") if existing else "")
    if repeat_rule == "none":
        ends_at = start.isoformat()
    else:
        if not raw_end:
            raise ValueError("重复计划必须选择重复至日期")
        ends_at = str(raw_end)
        end = _parse_plan_date(ends_at, "重复结束日期")
        if end < start:
            raise ValueError("重复结束日期不能早于开始日期")
        ends_at = end.isoformat()
    created_at = existing.get("created_at") if existing else now()
    return {
        "id": plan_id or uuid.uuid4().hex[:12],
        "content_type": type_id,
        "plan_date": start.isoformat(),
        "weekdays": json.dumps(weekdays, ensure_ascii=False),
        "repeat_rule": repeat_rule,
        "monthly_day": monthly_day,
        "ends_at": ends_at,
        "remind_time": reminder,
        "target_count": target_count,
        "created_at": created_at,
        "updated_at": now(),
    }


def _normalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(plan)
    normalized["target_count"] = int(normalized.get("target_count") or 1)
    try:
        normalized["weekdays"] = json.loads(normalized.get("weekdays") or "[]")
    except json.JSONDecodeError:
        normalized["weekdays"] = []
    # Early workbench builds allowed a blank date and duration. Keep those
    # records editable instead of letting a legacy row break the calendar.
    fallback_start = str(normalized.get("created_at") or date.today().isoformat())[:10]
    normalized["plan_date"] = normalized.get("plan_date") or fallback_start
    normalized["repeat_rule"] = normalized.get("repeat_rule") or "none"
    if normalized["repeat_rule"] not in PLAN_REPEAT_RULES:
        normalized["repeat_rule"] = "none"
    start = _parse_plan_date(normalized["plan_date"], "开始日期")
    if not normalized.get("ends_at"):
        normalized["ends_at"] = (start if normalized["repeat_rule"] == "none" else _add_months(start, 1)).isoformat()
    if normalized["repeat_rule"] == "weekly":
        normalized["weekdays"] = _plan_weekdays(normalized.get("weekdays")) or [start.weekday()]
    else:
        normalized["weekdays"] = []
    if normalized["repeat_rule"] == "monthly":
        try:
            normalized["monthly_day"] = _plan_monthly_day(normalized.get("monthly_day"), start)
        except ValueError:
            normalized["monthly_day"] = start.day
    else:
        normalized["monthly_day"] = 0
    normalized["start_date"] = normalized["plan_date"]
    normalized["end_date"] = normalized["ends_at"]
    return normalized


def list_plans() -> list[dict[str, Any]]:
    return [_normalize_plan(row) for row in _rows("SELECT * FROM plans ORDER BY COALESCE(plan_date, created_at), id")]


def _plan_occurrence_dates(plan: dict[str, Any], year: int, month: int) -> list[date]:
    start = _parse_plan_date(plan["plan_date"], "开始日期")
    end = _parse_plan_date(plan.get("ends_at") or plan["plan_date"], "重复结束日期")
    month_start = date(year, month, 1)
    month_end = _add_months(month_start, 1) - timedelta(days=1)
    if end < month_start or start > month_end:
        return []
    repeat = plan.get("repeat_rule", "none")
    if repeat == "none":
        return [start] if month_start <= start <= month_end else []
    cursor = max(start, month_start)
    result: list[date] = []
    if repeat == "monthly":
        monthly_day = _plan_monthly_day(plan.get("monthly_day"), start)
        occurrence = date(year, month, min(monthly_day, month_end.day))
        return [occurrence] if start <= occurrence <= end else []
    weekdays = set(_plan_weekdays(plan.get("weekdays")))
    while cursor <= min(end, month_end):
        if repeat == "daily" or (repeat == "weekly" and cursor.weekday() in weekdays):
            result.append(cursor)
        cursor += timedelta(days=1)
    return result


def plans_for_month(month_key: str) -> dict[str, Any]:
    match = re.fullmatch(r"(\d{4})-(\d{2})", month_key)
    if not match:
        raise ValueError("月份必须是 YYYY-MM")
    year, month = map(int, match.groups())
    if not 1 <= month <= 12:
        raise ValueError("月份不正确")
    plans = list_plans()
    month_start = date(year, month, 1).isoformat()
    month_end = (_add_months(date(year, month, 1), 1) - timedelta(days=1)).isoformat()
    with _connection() as connection:
        completion_rows = connection.execute(
            "SELECT plan_id, occurrence_date, completed_at FROM plan_completions WHERE occurrence_date BETWEEN ? AND ?",
            (month_start, month_end),
        ).fetchall()
    completions = {(row["plan_id"], row["occurrence_date"]): row["completed_at"] for row in completion_rows}
    occurrences: list[dict[str, Any]] = []
    for plan in plans:
        for occurrence in _plan_occurrence_dates(plan, year, month):
            occurrence_date = occurrence.isoformat()
            completed_at = completions.get((plan["id"], occurrence_date), "")
            occurrences.append({
                "id": f"{plan['id']}:{occurrence_date}", "planId": plan["id"], "date": occurrence_date,
                "contentType": plan["content_type"], "targetCount": plan["target_count"],
                "repeatRule": plan["repeat_rule"], "weekdays": plan["weekdays"], "monthlyDay": plan["monthly_day"], "completed": bool(completed_at), "completedAt": completed_at,
            })
    occurrences.sort(key=lambda item: (item["date"], item["planId"]))
    return {"month": month_key, "plans": plans, "occurrences": occurrences, "summary": {"occurrenceCount": len(occurrences), "targetCount": sum(item["targetCount"] for item in occurrences)}}


def _record_plan_event(event_type: str, plan: dict[str, Any]) -> None:
    try:
        append_data_event(event_type, {"planId": plan["id"], "contentType": plan["content_type"], "targetCount": plan["target_count"], "startDate": plan["plan_date"], "repeatRule": plan["repeat_rule"], "endsAt": plan["ends_at"], "monthlyDay": plan["monthly_day"]}, producer="workbench")
    except OSError:
        pass


def create_plan(payload: dict[str, Any]) -> dict[str, Any]:
    plan = _plan_payload(payload)
    with _connection() as connection:
        connection.execute("INSERT INTO plans (id,content_type,plan_date,weekdays,repeat_rule,monthly_day,ends_at,remind_time,target_count,created_at,updated_at) VALUES (:id,:content_type,:plan_date,:weekdays,:repeat_rule,:monthly_day,:ends_at,:remind_time,:target_count,:created_at,:updated_at)", plan)
    normalized = _normalize_plan(plan)
    _record_plan_event("workbench-plan-created", normalized)
    return normalized


def update_plan(plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = next((plan for plan in list_plans() if plan["id"] == plan_id), None)
    if existing is None:
        raise FileNotFoundError("工作计划不存在或已删除")
    plan = _plan_payload(payload, plan_id=plan_id, existing=existing)
    with _connection() as connection:
        connection.execute("UPDATE plans SET content_type=:content_type, plan_date=:plan_date, weekdays=:weekdays, repeat_rule=:repeat_rule, monthly_day=:monthly_day, ends_at=:ends_at, remind_time=:remind_time, target_count=:target_count, updated_at=:updated_at WHERE id=:id", plan)
    normalized = _normalize_plan(plan)
    _record_plan_event("workbench-plan-updated", normalized)
    return normalized


def delete_plan(plan_id: str) -> None:
    existing = next((plan for plan in list_plans() if plan["id"] == plan_id), None)
    if existing is None:
        raise FileNotFoundError("工作计划不存在或已删除")
    with _connection() as connection:
        connection.execute("DELETE FROM plan_completions WHERE plan_id = ?", (plan_id,))
        connection.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    _record_plan_event("workbench-plan-deleted", existing)


def set_plan_occurrence_completion(plan_id: str, occurrence_date: str, completed: bool) -> dict[str, Any]:
    occurrence = _parse_plan_date(occurrence_date, "计划日期")
    plan = next((item for item in list_plans() if item["id"] == plan_id), None)
    if plan is None:
        raise FileNotFoundError("工作计划不存在或已删除")
    valid_dates = _plan_occurrence_dates(plan, occurrence.year, occurrence.month)
    if occurrence not in valid_dates:
        raise ValueError("该日期不属于此工作计划")
    if completed:
        completed_at = now()
        with _connection() as connection:
            connection.execute(
                "INSERT INTO plan_completions (plan_id,occurrence_date,content_type,target_count,completed_at) VALUES (?,?,?,?,?) ON CONFLICT(plan_id,occurrence_date) DO UPDATE SET content_type=excluded.content_type,target_count=excluded.target_count,completed_at=excluded.completed_at",
                (plan_id, occurrence.isoformat(), plan["content_type"], plan["target_count"], completed_at),
            )
        event_type = "workbench-plan-completed"
    else:
        with _connection() as connection:
            connection.execute("DELETE FROM plan_completions WHERE plan_id = ? AND occurrence_date = ?", (plan_id, occurrence.isoformat()))
        completed_at = ""
        event_type = "workbench-plan-reopened"
    try:
        append_data_event(event_type, {"planId": plan_id, "date": occurrence.isoformat(), "contentType": plan["content_type"], "targetCount": plan["target_count"], "completedAt": completed_at}, producer="workbench")
    except OSError:
        pass
    return {"planId": plan_id, "date": occurrence.isoformat(), "completed": completed, "completedAt": completed_at}


def plan_completion_overview(as_of: date | None = None) -> dict[str, int]:
    """Return one consistent, due-through-today view of plan completion."""
    cutoff = as_of or date.today()
    due_occurrences: set[tuple[str, str]] = set()
    for plan in list_plans():
        start = _parse_plan_date(plan["plan_date"], "开始日期")
        end = min(_parse_plan_date(plan.get("ends_at") or plan["plan_date"], "重复结束日期"), cutoff)
        month = date(start.year, start.month, 1)
        while month <= end:
            for occurrence in _plan_occurrence_dates(plan, month.year, month.month):
                if occurrence <= cutoff:
                    due_occurrences.add((str(plan["id"]), occurrence.isoformat()))
            month = _add_months(month, 1)
    with _connection() as connection:
        completed_rows = connection.execute(
            "SELECT plan_id, occurrence_date FROM plan_completions WHERE occurrence_date <= ?",
            (cutoff.isoformat(),),
        ).fetchall()
    completed = sum((str(row["plan_id"]), str(row["occurrence_date"])) in due_occurrences for row in completed_rows)
    total = len(due_occurrences)
    return {
        "totalDueOccurrences": total,
        "completedOccurrences": completed,
        "completionRatePercent": round(completed / total * 100) if total else 0,
    }


SENSITIVE_EVENT_KEY = re.compile(r"(?:token|secret|password|authorization|cookie|api[_-]?key)", re.IGNORECASE)
SENSITIVE_EVENT_VALUE = re.compile(r"(?:Bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|xoxb-[A-Za-z0-9-]{8,})", re.IGNORECASE)


def _safe_event_value(value: Any, *, key: str = "") -> Any:
    """Keep task telemetry useful without persisting credentials or file bodies."""
    if SENSITIVE_EVENT_KEY.search(key) or key.lower() in {"data", "content", "attachment", "attachments"}:
        return "[已脱敏]"
    if isinstance(value, dict):
        return {str(item_key): _safe_event_value(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_safe_event_value(item, key=key) for item in value[:100]]
    if isinstance(value, str):
        return SENSITIVE_EVENT_VALUE.sub("[已脱敏]", value)[:2000]
    return value


def _record_event(
    session_id: str | None,
    level: str,
    message: str,
    *,
    kind: str = "system",
    detail: dict[str, Any] | None = None,
) -> None:
    safe_message = str(_safe_event_value(message))[-2000:]
    safe_detail = _safe_event_value(detail or {})
    with _connection() as connection:
        connection.execute(
            "INSERT INTO events (session_id,level,kind,message,detail_json,created_at) VALUES (?,?,?,?,?,?)",
            (session_id, level, kind, safe_message, json.dumps(safe_detail, ensure_ascii=False), now()),
        )
    # Verbose UI transport logs stay in the workbench database. Only explicit
    # business milestones are written to 04_数据中心 by their owning workflow.


def _codex_command() -> list[str]:
    """Prefer the current desktop CLI, with the vendored CLI as fallback."""
    executable = shutil.which("codex")
    if executable:
        return [executable]
    node = shutil.which("node")
    if node and LOCAL_CODEX_CLI.is_file():
        return [node, str(LOCAL_CODEX_CLI)]
    return []


def _codex_command_label(command: list[str]) -> str:
    if len(command) == 2:
        return "工作台内置官方 Codex CLI"
    return "桌面 Codex CLI" if command else ""


DESKTOP_BRIDGE_AGENT_LOCK = threading.Lock()
DESKTOP_BRIDGE_AGENT_LAST_SEEN = 0.0
DESKTOP_BRIDGE_AGENT_DETAILS: dict[str, Any] = {}


def update_desktop_bridge_agent(payload: dict[str, Any]) -> dict[str, Any]:
    """Record an explicit heartbeat from one interactive desktop agent."""
    global DESKTOP_BRIDGE_AGENT_LAST_SEEN, DESKTOP_BRIDGE_AGENT_DETAILS
    session_id = int(payload.get("windowsSessionId") or 0)
    interactive = bool(payload.get("interactiveSession")) and session_id > 0
    details = {
        "agentId": str(payload.get("agentId") or "")[:80],
        "pid": int(payload.get("pid") or 0),
        "user": str(payload.get("user") or "")[:160],
        "windowsSessionId": session_id,
        "windowStation": str(payload.get("windowStation") or "")[:160],
        "desktop": str(payload.get("desktop") or "")[:160],
        "interactiveSession": interactive,
        "codexWindowDetected": bool(payload.get("codexWindowDetected")) and interactive,
        "codexWindowHandle": int(payload.get("codexWindowHandle") or 0),
        "nativeTaskCreateAvailable": bool(payload.get("nativeTaskCreateAvailable")) and interactive,
        "folderLaunchAvailable": bool(payload.get("folderLaunchAvailable")) and interactive,
        "lastError": str(payload.get("lastError") or "")[:500],
    }
    with DESKTOP_BRIDGE_AGENT_LOCK:
        # Window enumeration occasionally returns no top-level windows for one
        # heartbeat while the interactive Desktop app is changing foreground.
        # Do not replace a handle already verified for this same user agent
        # with zero; the next job still re-checks IsWindow/visibility before
        # focus, so this is a short-lived transport fallback rather than proof
        # of task delivery.
        previous = DESKTOP_BRIDGE_AGENT_DETAILS
        if (
            interactive
            and not details["codexWindowDetected"]
            and not details["codexWindowHandle"]
            and details["agentId"]
            and details["agentId"] == previous.get("agentId")
            and previous.get("codexWindowDetected")
            and previous.get("codexWindowHandle")
        ):
            details["codexWindowDetected"] = True
            details["codexWindowHandle"] = int(previous["codexWindowHandle"])
        DESKTOP_BRIDGE_AGENT_LAST_SEEN = time.monotonic()
        DESKTOP_BRIDGE_AGENT_DETAILS = details
    return desktop_bridge_agent_status()


def desktop_bridge_agent_status() -> dict[str, Any]:
    with DESKTOP_BRIDGE_AGENT_LOCK:
        age = time.monotonic() - DESKTOP_BRIDGE_AGENT_LAST_SEEN if DESKTOP_BRIDGE_AGENT_LAST_SEEN else None
        details = dict(DESKTOP_BRIDGE_AGENT_DETAILS)
    connected = age is not None and age <= 8
    if not connected:
        details.update({"interactiveSession": False, "codexWindowDetected": False, "nativeTaskCreateAvailable": False, "folderLaunchAvailable": False})
    return {
        "connected": connected,
        "agentConnected": connected,
        "lastSeenSecondsAgo": round(age, 1) if age is not None else None,
        **details,
    }


def queue_desktop_folder(path: Path, *, label: str) -> dict[str, Any]:
    """Queue a folder launch for the agent in the signed-in desktop session."""
    agent = desktop_bridge_agent_status()
    if not agent.get("folderLaunchAvailable"):
        raise RuntimeError("当前登录用户的桌面桥接未连接，无法在本机打开文件夹")
    request_id = str(uuid.uuid4())
    with _connection() as connection:
        connection.execute(
            "INSERT INTO desktop_folder_requests (id,path,label,status,message,agent_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (request_id, str(path.resolve()), label, "queued", "", "", now(), now()),
        )
    return {"opened": False, "status": "queued-for-desktop", "requestId": request_id, "launchMode": "interactive-user-bridge"}


def next_desktop_folder_job() -> dict[str, Any] | None:
    rows = _rows("SELECT * FROM desktop_folder_requests WHERE status='queued' ORDER BY created_at ASC LIMIT 1")
    if not rows:
        return None
    item = rows[0]
    return {"requestId": item["id"], "path": item["path"], "label": item["label"]}


def claim_desktop_folder_job(request_id: str) -> dict[str, Any]:
    agent = desktop_bridge_agent_status()
    if not agent.get("folderLaunchAvailable"):
        raise RuntimeError("当前桌面桥接不能打开本机文件夹")
    with _connection() as connection:
        updated = connection.execute(
            "UPDATE desktop_folder_requests SET status='claimed',agent_id=?,updated_at=? WHERE id=? AND status='queued'",
            (str(agent.get("agentId") or ""), now(), request_id),
        ).rowcount
    if updated != 1:
        raise ValueError("文件夹打开请求已被领取或不存在")
    item = _rows("SELECT * FROM desktop_folder_requests WHERE id=?", (request_id,))[0]
    return {"requestId": item["id"], "path": item["path"], "label": item["label"]}


def report_desktop_folder_event(request_id: str, status: str, message: str = "") -> dict[str, Any]:
    if status not in {"opened", "failed"}:
        raise ValueError("文件夹打开状态无效")
    if status == "opened" and not message.strip():
        # A bare success signal cannot prove which Explorer window (if any)
        # reached the requested white-listed directory.
        raise ValueError("文件夹打开缺少目标目录确认，不能标记为成功")
    with _connection() as connection:
        updated = connection.execute(
            "UPDATE desktop_folder_requests SET status=?,message=?,updated_at=? WHERE id=?",
            (status, message[:300], now(), request_id),
        ).rowcount
    if updated != 1:
        raise ValueError("文件夹打开请求不存在")
    return {"requestId": request_id, "status": status, "message": message[:300]}


def desktop_folder_status(request_id: str) -> dict[str, Any]:
    rows = _rows("SELECT * FROM desktop_folder_requests WHERE id=?", (request_id,))
    if not rows:
        raise FileNotFoundError("文件夹打开请求不存在或已过期")
    item = rows[0]
    return {"requestId": request_id, "status": item["status"], "message": item.get("message", "")}


def _is_gallery_session(session: dict[str, Any]) -> bool:
    workflow = _json_object(session.get("workflow_json"))
    return str(session.get("action") or "") == "today-refresh" and str(workflow.get("todayModuleId") or "") == "gallery"


def _recovery_prompt_file(session: dict[str, Any]) -> Path:
    """Write a bounded resume instruction; the work package remains canonical."""
    workflow = _json_object(session.get("workflow_json"))
    state_path = str(session.get("recovery_state_path") or workflow.get("renderRecoveryState") or "")
    selected = workflow.get("selected") if isinstance(workflow.get("selected"), list) else []
    prompt = TODAY_TASK_RUNTIME_ROOT / f"{session['id']}.recovery.md"
    prompt.write_text(
        "这是工作台自动恢复，不是新一轮自由生成。请从已有配图检查点继续。\n\n"
        f"原任务：{session['id']}\n"
        f"恢复状态文件：{state_path or '在本次工作包内定位 render-state.json'}\n"
        f"原正文锚点：{json.dumps(selected, ensure_ascii=False)}\n\n"
        "先读取 attempt-ledger.json 与 render-state.json，运行 `render_recovery_loop.py --workdir <工作包> claim --owner <当前任务ID>`，"
        "再运行 `next`，只执行返回的 next_action。审核 rejected 只能录入控制器并进入 repairing；外部异常只能进入 reconnecting 并保留 next_retry_at。"
        "不得写 blocked、不得跳过小审、不得编辑历史工作包或放宽审核。若原 Codex 任务可用则继续该任务；不可用时在本恢复任务完成同一检查点。\n",
        encoding="utf-8",
    )
    return prompt


def _repair_prompt_file(session: dict[str, Any], repair: dict[str, Any]) -> Path:
    state_path = str(session.get("recovery_state_path") or "")
    request_id = str(repair.get("request_id") or "")
    prompt = TODAY_TASK_RUNTIME_ROOT / f"{session['id']}.skill-repair.md"
    prompt.write_text(
        "这是配图恢复控制器自动创建的独立 Skill 修复任务。只修复已复现的蓝图构建缺陷，"
        "不得修改生产工作包、正文、小审规则或发布目录。修复后必须用同类正文验证，并保留验证证据。\n\n"
        f"主工作台会话：{session['id']}\n恢复状态：{state_path}\n修复请求：{request_id}\n\n"
        "验证通过后运行：\n"
        f"`python 10_Skills武器库/IP视觉PPT生成Skill/scripts/render_recovery_loop.py --workdir <工作包> mark-repair-verified --request-id {request_id}`\n"
        "然后使用 report_visible_task_event.py 对上述主会话回写 reconnecting，并附同一 render-state.json；主任务将自动重建 v4.1 工作包并续跑。\n",
        encoding="utf-8",
    )
    return prompt


def _desktop_bridge_job(session: dict[str, Any]) -> dict[str, Any]:
    workflow = _json_object(session.get("workflow_json"))
    recovering = str(session.get("status") or "") == "reconnecting" and _is_gallery_session(session)
    prompt = _recovery_prompt_file(session) if recovering else Path(str(workflow.get("promptFile") or ""))
    if not prompt.is_file():
        raise FileNotFoundError("本次 Codex 固定提示词不存在")
    repair: dict[str, Any] = {}
    state_path = Path(str(session.get("recovery_state_path") or workflow.get("renderRecoveryState") or ""))
    if not state_path.is_absolute():
        state_path = PROJECT_ROOT / state_path
    if recovering and state_path.is_file():
        try:
            state = _json_object(state_path.read_text(encoding="utf-8"))
            candidate = state.get("repair_task")
            if isinstance(candidate, dict) and candidate.get("required") and candidate.get("status") == "queued":
                repair = candidate
        except OSError:
            repair = {}
    repair_prompt = _repair_prompt_file(session, repair) if repair else None
    return {
        "sessionId": str(session["id"]),
        "title": str(session["title"]),
        "promptFile": str(prompt.resolve()),
        "projectRoot": str(PROJECT_ROOT),
        "port": WORKBENCH_PORT,
        "windowHandle": int(desktop_bridge_agent_status().get("codexWindowHandle") or 0),
        "jobKind": "resume" if recovering else "create",
        "codexThreadId": str(session.get("codex_thread_id") or ""),
        "recoveryStatePath": str(session.get("recovery_state_path") or workflow.get("renderRecoveryState") or ""),
        "repairTask": repair,
        "repairPromptFile": str(repair_prompt) if repair_prompt else "",
    }


def next_desktop_bridge_job() -> dict[str, Any] | None:
    """Return one queued visible-task job to the interactive-user bridge only."""
    agent = desktop_bridge_agent_status()
    if not agent.get("codexWindowDetected") or not agent.get("nativeTaskCreateAvailable"):
        return None
    rows = _rows(
        "SELECT * FROM sessions WHERE (status='creating-desktop-task' AND bridge_status='desktop-bridge-queued') OR (status='reconnecting' AND bridge_status='desktop-bridge-recovery-queued' AND (recovery_next_at='' OR recovery_next_at<=?)) ORDER BY created_at ASC LIMIT 1",
        (now(),),
    )
    return _desktop_bridge_job(rows[0]) if rows else None


def claim_desktop_bridge_job(session_id: str) -> dict[str, Any]:
    """Atomically hand one queued task to the current interactive-user agent."""
    if not session_id:
        raise ValueError("桌面桥接任务 ID 不能为空")
    agent = desktop_bridge_agent_status()
    if not agent.get("codexWindowDetected"):
        raise RuntimeError("当前桌面桥接未检测到 Codex 窗口")
    if not agent.get("nativeTaskCreateAvailable"):
        raise RuntimeError("当前 Codex 桌面原生任务桥接未连接")
    with _connection() as connection:
        updated = connection.execute(
            "UPDATE sessions SET bridge_status=CASE WHEN status='reconnecting' THEN 'desktop-bridge-recovery-claimed' ELSE 'desktop-bridge-user-agent' END, desktop_navigation_status=CASE WHEN status='reconnecting' THEN 'recovery-claimed' ELSE 'user-agent-claimed' END, updated_at=? WHERE id=? AND ((status='creating-desktop-task' AND bridge_status='desktop-bridge-queued') OR (status='reconnecting' AND bridge_status='desktop-bridge-recovery-queued'))",
            (now(), session_id),
        ).rowcount
    if updated != 1:
        raise ValueError("桌面桥接任务已被领取或已失效")
    session = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))[0]
    _record_event(session_id, "info", "当前登录用户的桌面桥接已领取恢复任务，正在从检查点续接。" if session.get("status") == "reconnecting" else "当前登录用户的桌面桥接已领取任务，正在打开 Codex。", kind="desktop-bridge")
    return _desktop_bridge_job(session)


def desktop_navigation_status() -> dict[str, Any]:
    """Expose the user-session bridge without treating App Server threads as visible."""
    agent = desktop_bridge_agent_status()
    return {
        "available": DESKTOP_BRIDGE_SCRIPT.is_file() and os.name == "nt" and bool(agent.get("codexWindowDetected")) and bool(agent.get("nativeTaskCreateAvailable")),
        "mode": "interactive-user-native-desktop-agent",
        "message": "当前登录用户的 Codex Desktop 原生桥接已连接；返回真实任务编号后才确认任务已创建。" if agent.get("nativeTaskCreateAvailable") else (agent.get("lastError") or "正在等待当前登录用户的 Codex Desktop 原生桥接连接。"),
        "agent": agent,
    }


def ensure_desktop_bridge_agent(port: int) -> None:
    """Start one hidden interactive-user bridge when running on Windows."""
    global DESKTOP_BRIDGE_AGENT_PROCESS
    if os.name != "nt" or not DESKTOP_BRIDGE_AGENT_SCRIPT.is_file():
        return
    session_id = ctypes.c_ulong()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id)):
        return
    if session_id.value == 0:
        # A SYSTEM/service process cannot display Explorer or Codex windows.
        # The user's Startup entry launches the interactive bridge at login.
        return
    if DESKTOP_BRIDGE_AGENT_PROCESS and DESKTOP_BRIDGE_AGENT_PROCESS.poll() is None:
        return
    DESKTOP_BRIDGE_AGENT_PROCESS = subprocess.Popen(
        [sys.executable, "-B", str(DESKTOP_BRIDGE_AGENT_SCRIPT), "--port", str(port)],
        cwd=str(PROJECT_ROOT), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        text=True,
    )


def stop_desktop_bridge_agent() -> None:
    global DESKTOP_BRIDGE_AGENT_PROCESS
    process, DESKTOP_BRIDGE_AGENT_PROCESS = DESKTOP_BRIDGE_AGENT_PROCESS, None
    if process and process.poll() is None:
        process.terminate()


def bridge_status() -> dict[str, Any]:
    """The retired background copy bridge is deliberately unavailable."""
    return {
        "available": False,
        "mode": "retired-background-copy-worker",
        "message": "工作台不再运行或恢复旧正文后台 worker。",
    }


class CodexBridge:
    """Minimal JSONL client for ``codex app-server`` over stdio.

    It intentionally starts only after a user approves a task. The App Server
    remains the authority for tool approval prompts; this workbench only stores
    the resulting thread and streams status back to the local task log.
    """

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._request_ids = itertools.count(1)
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._thread_sessions: dict[str, str] = {}
        self.last_error = ""

    @property
    def connected(self) -> bool:
        return bool(self.process and self.process.poll() is None)

    def _emit(self, session_id: str | None, level: str, message: str, *, kind: str = "codex-notification", detail: dict[str, Any] | None = None) -> None:
        if session_id:
            _record_event(session_id, level, message, kind=kind, detail=detail)

    def _start_reader(self, stream: Any, is_error: bool = False) -> None:
        def read() -> None:
            for raw in iter(stream.readline, ""):
                text = raw.strip()
                if not text:
                    continue
                if is_error:
                    self.last_error = text[-1000:]
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    self.last_error = f"Codex 返回了无法识别的数据：{text[-180:]}"
                    continue
                if "method" in payload and "id" in payload:
                    self._handle_server_request(payload)
                    continue
                response_id = payload.get("id")
                if isinstance(response_id, int):
                    waiting = self._pending.pop(response_id, None)
                    if waiting:
                        waiting.put(payload)
                    continue
                params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                thread_id = str(params.get("threadId", ""))
                session_id = self._thread_sessions.get(thread_id)
                method = str(payload.get("method", "Codex 事件"))
                if session_id:
                    error = params.get("error") if isinstance(params.get("error"), dict) else {}
                    summary = params.get("delta") or params.get("message") or error.get("message") or params.get("status") or params.get("reason") or "状态已更新"
                    self._emit(
                        session_id,
                        "info",
                        f"Codex {method}: {summary}",
                        detail={"method": method, "params": params},
                    )
                    if method == "error" and str(summary).startswith("Reconnecting"):
                        with _connection() as connection:
                            connection.execute("UPDATE sessions SET bridge_status='reconnect-required', updated_at=? WHERE id=?", (now(), session_id))
                    if method == "turn/completed":
                        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
                        status = str(turn.get("status", "completed"))
                        mapped = {"completed": "completed", "failed": "failed", "interrupted": "interrupted"}.get(status, "running")
                        with _connection() as connection:
                            current = connection.execute("SELECT status FROM sessions WHERE id=?", (session_id,)).fetchone()
                            # A user cancellation is an explicit business decision. Keep it even
                            # though Codex later reports the interrupted turn as its transport state.
                            if not current or current["status"] != "cancelled":
                                # A completed turn is no longer waiting for the bridge. Keeping a
                                # stale reconnect flag here made completed tasks look like they ran forever.
                                bridge_status = "completed" if mapped == "completed" else "connected"
                                connection.execute(
                                    "UPDATE sessions SET status=?, bridge_status=?, updated_at=? WHERE id=?",
                                    (mapped, bridge_status, now(), session_id),
                                )
                    elif method in {"turn/started", "turn/updated"}:
                        with _connection() as connection:
                            connection.execute("UPDATE sessions SET status='running', bridge_status='connected', updated_at=? WHERE id=?", (now(), session_id))

        threading.Thread(target=read, daemon=True, name="codex-app-server-reader").start()

    def _handle_server_request(self, payload: dict[str, Any]) -> None:
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        thread_id = str(params.get("threadId") or params.get("conversationId") or "")
        session_id = self._thread_sessions.get(thread_id)
        method = str(payload.get("method", ""))
        if not session_id:
            # A request from an unknown thread must never be implicitly approved.
            self._write({"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32601, "message": "This workbench does not own the requested Codex thread."}})
            return
        approval_id = _store_server_approval(session_id, payload.get("id"), method, params)
        if method == "item/tool/requestUserInput":
            summary = "Codex 正在等待你补充信息"
        else:
            summary = params.get("command") or params.get("reason") or "需要你的确认"
        self._emit(session_id, "warning", f"等待你确认：{summary}（请求 {approval_id}）", kind="approval", detail={"approvalId": approval_id, "method": method, "params": params})

    def connect(self) -> None:
        with self._lock:
            if self.connected:
                return
            command = _codex_command()
            if not command:
                raise RuntimeError("未找到可运行的 Codex 命令。")
            self.last_error = ""
            try:
                self.process = subprocess.Popen(
                    [*command, "app-server"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=PROJECT_ROOT,
                    bufsize=1,
                )
            except OSError as exc:
                self.process = None
                raise RuntimeError(f"Codex app-server 无法启动：{exc}") from exc
            if not self.process.stdin or not self.process.stdout or not self.process.stderr:
                self.stop()
                raise RuntimeError("Codex app-server 未提供标准输入输出通道。")
            self._start_reader(self.process.stdout)
            self._start_reader(self.process.stderr, is_error=True)
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "aip-workbench", "title": "AI爆款内容工厂", "version": "1.0"},
                # Project/thread APIs are explicitly gated by Codex App Server.
                # Declaring this does not grant file or command permissions.
                "capabilities": {"experimentalApi": True},
            },
        )
        self.notify("initialized", {})

    def _write(self, payload: dict[str, Any]) -> None:
        if not self.connected or not self.process or not self.process.stdin:
            detail = self.last_error or "Codex app-server 未保持运行。"
            raise RuntimeError(detail)
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except OSError as exc:
            raise RuntimeError(f"无法向 Codex app-server 发送请求：{exc}") from exc

    def request(self, method: str, params: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
        request_id = next(self._request_ids)
        waiting: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._pending[request_id] = waiting
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            response = waiting.get(timeout=timeout)
        except queue.Empty as exc:
            self._pending.pop(request_id, None)
            raise RuntimeError(f"Codex 未在 {timeout} 秒内响应 {method}。") from exc
        if "error" in response:
            error = response["error"]
            raise RuntimeError(str(error.get("message") if isinstance(error, dict) else error))
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Codex {method} 响应格式不正确。")
        return result

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def respond_to_server_request(self, request_id: Any, result: dict[str, Any]) -> None:
        self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _project_id(self) -> str:
        """Resolve the saved Codex project by its exact local root each time."""
        self.connect()
        cursor: str | None = None
        project_root = PROJECT_ROOT.resolve()
        while True:
            params: dict[str, Any] = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            result = self.request("project/list", params)
            projects = result.get("data") if isinstance(result.get("data"), list) else []
            for project in projects:
                if not isinstance(project, dict):
                    continue
                roots = project.get("roots") if isinstance(project.get("roots"), list) else []
                for root in roots:
                    path = root.get("path") if isinstance(root, dict) else ""
                    try:
                        if path and Path(str(path)).resolve() == project_root:
                            project_id = str(project.get("id", ""))
                            if project_id:
                                return project_id
                    except OSError:
                        continue
            cursor_value = result.get("nextCursor")
            cursor = str(cursor_value) if cursor_value else None
            if not cursor:
                break
        raise RuntimeError(f"未在 Codex 中找到根目录为 {PROJECT_ROOT} 的项目，任务没有启动。")

    def resume_thread(self, session_id: str, thread_id: str) -> None:
        self.connect()
        self.request("thread/resume", {"threadId": thread_id})
        self._thread_sessions[thread_id] = session_id

    def interrupt_task(self, session_id: str, thread_id: str, turn_id: str) -> None:
        self.connect()
        if thread_id not in self._thread_sessions:
            self.resume_thread(session_id, thread_id)
        self.request("turn/interrupt", {"threadId": thread_id, "turnId": turn_id})

    def start_task(self, session_id: str, prompt: str) -> tuple[str, str, str]:
        self.connect()
        thread = self.request(
            "thread/start",
            {
                "cwd": str(PROJECT_ROOT),
                "runtimeWorkspaceRoots": [str(PROJECT_ROOT)],
            },
        )
        thread_payload = thread.get("thread") if isinstance(thread.get("thread"), dict) else thread
        thread_id = str(thread_payload.get("id", "")) if isinstance(thread_payload, dict) else ""
        if not thread_id:
            raise RuntimeError("Codex 未返回线程编号。")
        self._thread_sessions[thread_id] = session_id
        instructions = (
            "你正在 AI爆款内容工厂中作为小姜处理来自本机工作台的正式任务。"
            "先加载并遵守 xiaojiang-dispatch；不得直接代替专业 Agent，也不得绕过小审 xiaoshen-audit。"
            "如任务需要文件变更、命令或网络访问，必须在 App Server 的审批机制中等待用户确认。"
            "用户任务如下：\n" + prompt
        )
        turn = self.request("turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": instructions}]})
        turn_payload = turn.get("turn") if isinstance(turn.get("turn"), dict) else turn
        turn_id = str(turn_payload.get("id", "")) if isinstance(turn_payload, dict) else ""
        # The App Server binds a thread to the supplied workspace directory.
        # Keep the root in the local session record as the project identifier.
        return thread_id, turn_id, str(PROJECT_ROOT)

    def stop(self) -> None:
        with self._lock:
            process, self.process = self.process, None
            self._pending.clear()
            self._thread_sessions.clear()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


CODEX_BRIDGE = CodexBridge()


class DesktopTaskBridge:
    """Launch the local helper that creates a user-visible Codex Desktop task.

    The helper controls only the installed Desktop app. It never falls back to
    ``app-server`` because that transport creates an invisible background thread.
    """

    def launch(self, session_id: str, title: str, prompt_file: Path) -> None:
        if not DESKTOP_BRIDGE_SCRIPT.is_file():
            raise RuntimeError("未找到 Codex 桌面桥接助手。")
        if not prompt_file.is_file():
            raise RuntimeError("未找到本次 Codex 固定提示词。")
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        log_root = RUNTIME_ROOT / "bridge-logs"
        token_root = RUNTIME_ROOT / "bridge-tokens"
        log_root.mkdir(parents=True, exist_ok=True)
        token_root.mkdir(parents=True, exist_ok=True)
        stdout_path = log_root / f"{session_id}.out.log"
        stderr_path = log_root / f"{session_id}.err.log"
        token_path = token_root / f"{session_id}.token"
        token_path.write_text(token, encoding="utf-8")
        deadline = (datetime.now().astimezone() + timedelta(minutes=2)).isoformat(timespec="seconds")
        with _connection() as connection:
            connection.execute(
                "UPDATE sessions SET delivery_token_hash=?, delivery_deadline_at=?, bridge_log_path=?, updated_at=? WHERE id=?",
                (token_hash, deadline, _relative_project_path(stdout_path), now(), session_id),
            )
        with _connection() as connection:
            connection.execute(
                "UPDATE sessions SET bridge_status='desktop-bridge-queued', desktop_navigation_status='waiting-user-agent', updated_at=? WHERE id=?",
                (now(), session_id),
            )
        _record_event(session_id, "info", "已加入当前登录用户的 Codex 桌面桥接队列。", kind="desktop-bridge")


DESKTOP_TASK_BRIDGE = DesktopTaskBridge()
_BATCH_RECONCILE_LOCK = threading.Lock()
_BATCH_RECONCILING: set[str] = set()
# Persistent model turns may stream slowly while producing a full article. The
# backend emits activity events; only a genuinely silent 15-minute turn is
# considered stalled.
COPY_WORKER_STALL_SECONDS = 900
COPY_WORKER_TRANSPORT_INITIAL_RETRY_SECONDS = 45
COPY_WORKER_TRANSPORT_MAX_RETRY_SECONDS = 300
COPY_WORKER_POLL_SECONDS = 10


def _stage_attachments(session_id: str, attachments: Any) -> list[Path]:
    """Persist browser-selected files only in runtime; never write them into factory assets."""
    if attachments is None:
        return []
    if not isinstance(attachments, list) or len(attachments) > MAX_ATTACHMENTS:
        raise ValueError(f"一次最多上传 {MAX_ATTACHMENTS} 个附件")
    target = (UPLOAD_ROOT / session_id).resolve()
    if not target.is_relative_to(UPLOAD_ROOT.resolve()):
        raise ValueError("附件暂存路径无效")
    target.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    total = 0
    for index, item in enumerate(attachments, start=1):
        if not isinstance(item, dict):
            raise ValueError("附件格式不正确")
        name = Path(str(item.get("name", ""))).name.strip()
        suffix = Path(name).suffix.lower()
        if not name or suffix not in ALLOWED_ATTACHMENT_SUFFIXES:
            raise ValueError("附件格式不支持")
        try:
            content = base64.b64decode(str(item.get("data", "")), validate=True)
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("附件内容无法读取") from exc
        if not content or len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError("单个附件必须小于 5MB")
        total += len(content)
        if total > MAX_ATTACHMENTS_TOTAL_BYTES:
            raise ValueError("附件总大小必须小于 15MB")
        safe_stem = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", Path(name).stem)[:80] or "attachment"
        destination = target / f"{index:02d}_{safe_stem}{suffix}"
        destination.write_bytes(content)
        staged.append(destination)
    return staged


def create_session(payload: dict[str, Any], *, session_id: str | None = None) -> dict[str, Any]:
    action = str(payload.get("action", "general"))
    defaults = {"generate-copy": "请小姜核验已填写结构四，并按现役正文链路分配小写与小审。", "generate-structure": "请小姜为已选中选题创建结构生成调度记录，交由小拆和小审处理。", "refresh-topics": "请小姜分配小策刷新对标账号的爆款选题表，并交小审审核。", "break-review": "请小姜分配小拆执行今日复盘“同步 IMA + 扫描待拆解 + 案例卡拆解 + 小审放行”的完整链路；同步无新增时也必须继续扫描待拆解资料，并显式回报 0 条结果。", "inventory-stats": "请小姜分配小息刷新原始资料入库统计，并交小审轻确认。", "today-refresh": "", "asset-edit-audit": "", "general": ""}
    if action not in defaults:
        raise ValueError("未知任务动作")
    message = str(payload.get("message", "")).strip() or defaults[action]
    if not message:
        raise ValueError("请填写要交给小姜的任务")
    session_id = session_id or uuid.uuid4().hex[:12]
    attachments = _stage_attachments(session_id, payload.get("attachments"))
    if attachments:
        attachment_paths = "\n".join(f"- {path}" for path in attachments)
        message += f"\n\n本次任务附件已暂存于工作台运行目录，仅供本次任务读取：\n{attachment_paths}"
    skip_approval = bool(payload.get("skipApproval", False))
    workflow = payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
    batch = payload.get("batch") if isinstance(payload.get("batch"), list) else []
    session = {
        "id": session_id, "title": str(payload.get("title") or "小姜任务"), "message": message,
        "action": action, "status": "pending", "approval_status": "approved" if skip_approval else "needs-approval",
        "bridge_status": "not-started", "codex_thread_id": "", "codex_turn_id": "",
        "codex_project_id": "", "codex_project_root": "", "desktop_navigation_status": "not-opened",
        "batch_json": json.dumps(batch, ensure_ascii=False), "workflow_json": json.dumps(workflow, ensure_ascii=False),
        "execution_authorized": 1 if skip_approval else 0, "created_at": now(), "updated_at": now(),
    }
    with _connection() as connection:
        connection.execute("""INSERT INTO sessions (id,title,message,action,status,approval_status,bridge_status,codex_thread_id,codex_turn_id,codex_project_id,codex_project_root,desktop_navigation_status,batch_json,workflow_json,execution_authorized,created_at,updated_at)
            VALUES (:id,:title,:message,:action,:status,:approval_status,:bridge_status,:codex_thread_id,:codex_turn_id,:codex_project_id,:codex_project_root,:desktop_navigation_status,:batch_json,:workflow_json,:execution_authorized,:created_at,:updated_at)""", session)
    initial_message = "小姜已接收任务，正在创建 Codex 对话。" if skip_approval else "小姜已接收任务，等待你批准启动 Codex。"
    _record_event(session["id"], "info", initial_message, kind="task-state", detail={"action": action, "status": "pending"})
    return session


def _session_summary(session: dict[str, Any], *, include_events: bool = False) -> dict[str, Any]:
    """Serialize a compact session summary; task history is loaded on demand."""
    session = dict(session)
    if not include_events:
        # The assistant drawer needs enough context to identify a task, but it
        # must not pull multi-page fixed prompts into every dashboard request.
        session["message"] = str(session.get("message") or "")[:280]
    try:
        batch = json.loads(session.pop("batch_json", "") or "[]")
    except json.JSONDecodeError:
        batch = []
    workflow = _json_object(session.pop("workflow_json", "{}"))
    session["workflow"] = workflow
    # Historical background-worker batches stay hidden. User-selected serial
    # manifests are a visible task record and are safe to expose read-only.
    session["batch"] = batch if workflow.get("generationSelections") else []
    session["business_status"] = session["status"]
    if include_events:
        events = _rows("SELECT level,kind,message,detail_json,created_at FROM events WHERE session_id = ? ORDER BY id DESC LIMIT 120", (session["id"],))
        for event in events:
            try:
                event["detail"] = json.loads(event.pop("detail_json") or "{}")
            except json.JSONDecodeError:
                event["detail"] = {}
        session["events"] = events
    return session


def list_sessions(*, limit: int = 30, active_only: bool = False, include_events: bool = True) -> list[dict[str, Any]]:
    # Keep the browser honest after the two-minute visible-task confirmation
    # window.  Without this check an attempted paste could remain "submitted"
    # forever until the service happened to restart.
    reconcile_interrupted_sessions()
    where = " WHERE status IN ({})".format(",".join("?" for _ in ACTIVE_SESSION_STATUSES)) if active_only else ""
    values: tuple[Any, ...] = tuple(ACTIVE_SESSION_STATUSES) + (max(1, min(limit, 100)),) if active_only else (max(1, min(limit, 100)),)
    sessions = _rows(f"SELECT * FROM sessions{where} ORDER BY updated_at DESC LIMIT ?", values)
    return [_session_summary(session, include_events=include_events) for session in sessions]


def session_detail(session_id: str) -> dict[str, Any]:
    reconcile_interrupted_sessions()
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("任务会话不存在")
    return _session_summary(rows[0], include_events=True)


def list_approvals() -> list[dict[str, Any]]:
    approvals = _rows("SELECT * FROM approvals ORDER BY created_at DESC LIMIT 50")
    for approval in approvals:
        try:
            approval["params"] = json.loads(approval.pop("params_json"))
        except json.JSONDecodeError:
            approval["params"] = {}
        approval.pop("request_id_json", None)
    return approvals


def _store_server_approval(session_id: str, request_id: Any, method: str, params: dict[str, Any]) -> str:
    approval_id = uuid.uuid4().hex[:16]
    safe_params = _safe_event_value(params)
    with _connection() as connection:
        connection.execute(
            "INSERT INTO approvals (id,session_id,request_id_json,method,params_json,status,created_at) VALUES (?,?,?,?,?,?,?)",
            (approval_id, session_id, json.dumps(request_id), method, json.dumps(safe_params, ensure_ascii=False), "pending", now()),
        )
        connection.execute(
            "UPDATE sessions SET status='needs-user', updated_at=? WHERE id=?",
            (now(), session_id),
        )
    _record_event(session_id, "warning", "Codex 正在等待你的确认或补充输入。", kind="approval", detail={"approvalId": approval_id, "method": method, "params": safe_params})
    return approval_id


def approve_session(session_id: str) -> dict[str, Any]:
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("任务会话不存在")
    session = rows[0]
    if str(session.get("status")) in ACTIVE_SESSION_STATUSES:
        return session
    if str(session.get("status")) in TERMINAL_SESSION_STATUSES:
        raise ValueError("已结束任务不能重新创建 Codex 任务")
    navigation = desktop_navigation_status()
    if not navigation["available"]:
        raise RuntimeError(str(navigation.get("message") or "当前 Codex 桌面桥接不可用，请先打开 Codex 桌面"))
    # Approval is the explicit gate for general conversations.  It must then
    # use the same visible-native-task route as refreshes and one-click copy;
    # retaining an "awaiting-desktop-task" state here would create a task that
    # can never be claimed by the desktop Agent.
    _record_event(session_id, "info", "已批准任务，正在创建独立 Codex 对话。", kind="visible-task-request", detail={"projectRoot": str(PROJECT_ROOT)})
    return _queue_visible_task(session_id)


def report_visible_task_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept a small, auditable milestone from the visible Codex task only."""
    session_id = str(payload.get("sessionId", "")).strip()
    event = str(payload.get("event", "")).strip()
    message = str(payload.get("message", "")).strip()
    completion_basis = str(payload.get("completionBasis", "")).strip()
    audit_receipt_path = str(payload.get("auditReceiptPath", "")).strip()
    recovery_state_path = str(payload.get("recoveryStatePath", "")).strip()
    recovery_next_at = str(payload.get("recoveryNextAt", "")).strip()
    recovery_failure_class = str(payload.get("recoveryFailureClass", "")).strip()
    report_token = str(payload.get("reportToken", "")).strip()
    if not session_id or event not in VISIBLE_TASK_EVENT_STATUS:
        raise ValueError("可见任务事件参数无效")
    if len(message) > 500:
        raise ValueError("可见任务事件说明过长")
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("任务会话不存在")
    session = rows[0]
    expected_token = str(session.get("delivery_token_hash") or "")
    # All Desktop-delivered tasks carry a local one-time signature. The empty
    # branch remains only for pre-bridge historical records, which are not
    # eligible for automatic desktop launch and are covered by reconciliation.
    if expected_token and not secrets.compare_digest(expected_token, hashlib.sha256(report_token.encode("utf-8")).hexdigest()):
        raise PermissionError("可见任务回写签名无效")
    if session["status"] in {"cancelled", "released", "completed", "failed"}:
        raise ValueError("该任务已经结束，不能写入新的执行事件")
    workflow = _json_object(session.get("workflow_json"))
    refresh_module_id = str(workflow.get("todayModuleId") or "")
    refresh_module = _today_module_index().get(refresh_module_id) if str(session.get("action") or "") == "today-refresh" else None
    # Gallery audit feedback must keep the serial repair loop alive. A visual
    # rejection is actionable page/blueprint feedback, not a terminal refresh
    # result. Older visible-task prompts may still send `rejected`, so enforce
    # the same rule here instead of trusting the task prompt alone.
    effective_event = event
    if refresh_module_id == "gallery" and event == "rejected":
        effective_event = "repairing"
        if not message:
            message = "配图小审退回，正在按回执重建工作包或重画对应页面。"
    if refresh_module_id != "gallery" and event == "reconnecting":
        raise ValueError("只有配图任务可以使用 reconnecting")

    if effective_event == "released" and refresh_module:
        if completion_basis not in {"audit-approved", "no-pending"}:
            raise ValueError("今日刷新任务完成时必须提供完成依据")
        if completion_basis == "audit-approved":
            receipt = Path(audit_receipt_path)
            receipt = receipt if receipt.is_absolute() else PROJECT_ROOT / receipt
            try:
                receipt.resolve().relative_to(FORMAL_AUDIT_ROOT.resolve())
            except ValueError as exc:
                raise ValueError("审核回执必须位于正式小审回执目录") from exc
            if not receipt.is_file():
                raise FileNotFoundError("正式小审回执不存在")
            if refresh_module_id == "gallery":
                receipt_payload = _json_object(receipt.read_text(encoding="utf-8"))
                if receipt_payload.get("status") != "approved":
                    raise ValueError("配图只能由正式小审 approved 回执发布")
            audit_receipt_path = _relative_project_path(receipt)
        elif refresh_module_id == "gallery":
            raise ValueError("配图发布必须提供 audit-approved 正式小审回执")
        record_today_refresh_completion(
            refresh_module_id,
            task_id=session_id,
            skill=str(refresh_module.get("skill") or ""),
            completion_basis=completion_basis,
            audit_receipt_path=audit_receipt_path,
            producer="workbench-visible-task",
        )
    status = VISIBLE_TASK_EVENT_STATUS[effective_event]
    if recovery_state_path:
        state_candidate = Path(recovery_state_path)
        state_candidate = state_candidate if state_candidate.is_absolute() else PROJECT_ROOT / state_candidate
        try:
            recovery_state_path = str(state_candidate.resolve().relative_to(PROJECT_ROOT.resolve()))
        except ValueError as exc:
            raise ValueError("恢复状态文件必须位于项目目录") from exc
    updated_batch_json = str(session.get("batch_json") or "[]")
    if workflow.get("generationSelections"):
        try:
            batch_items = json.loads(updated_batch_json)
        except json.JSONDecodeError:
            batch_items = []
        if isinstance(batch_items, list):
            progress = {
                "started": ("running", "正在按用户选择的顺序生成。", ""),
                "waiting-audit": ("waiting-audit", "已交小审，等待审核结论。", "待小审"),
                "released": ("released", "小审已放行，已受控发布。", "approved"),
                "rejected": ("rejected", "小审退回，未发布正式资产。", "rejected"),
                "blocked": ("blocked", "任务已阻塞，等待处理。", ""),
            }.get(effective_event)
            if progress:
                for item in batch_items:
                    if not isinstance(item, dict):
                        continue
                    item["progress"], item["nextStep"], conclusion = progress
                    if conclusion:
                        item["auditConclusion"] = conclusion
                    if effective_event == "released" and audit_receipt_path:
                        item["auditReceipt"] = audit_receipt_path
                updated_batch_json = json.dumps(batch_items, ensure_ascii=False)
    with _connection() as connection:
        connection.execute(
            "UPDATE sessions SET status=?, bridge_status=?, desktop_navigation_status='visible-task-reported', delivery_deadline_at='', batch_json=?, recovery_state_path=CASE WHEN ?!='' THEN ? ELSE recovery_state_path END, recovery_next_at=CASE WHEN ?!='' THEN ? ELSE recovery_next_at END, recovery_failure_class=CASE WHEN ?!='' THEN ? ELSE recovery_failure_class END, updated_at=? WHERE id=?",
            (status, 'desktop-bridge-recovery-queued' if effective_event == 'reconnecting' else 'visible-task-reported', updated_batch_json, recovery_state_path, recovery_state_path, recovery_next_at, recovery_next_at, recovery_failure_class, recovery_failure_class, now(), session_id),
        )
    labels = {
        "started": "Codex 桌面任务已开始执行。",
        "repairing": "Codex 桌面任务正在按小审意见修复。",
        "reconnecting": "外部连接异常，工作台将在下次恢复时间自动续接。",
        "waiting-user": "Codex 桌面任务正在等待用户确认。",
        "waiting-audit": "Codex 桌面任务已交小审审核。",
        "released": "小审已放行，本次任务已完成。",
        "rejected": "小审退回，本次任务未放行。",
        "blocked": "Codex 桌面任务已阻塞，等待处理。",
    }
    _record_event(
        session_id,
        "success" if effective_event in {"started", "released"} else "warning",
        message or labels[effective_event],
        kind="visible-codex-task",
        detail={"event": event, "effectiveEvent": effective_event, "status": status, "recoveryStatePath": recovery_state_path, "recoveryNextAt": recovery_next_at, "recoveryFailureClass": recovery_failure_class},
    )
    return _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))[0]


def report_desktop_bridge_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Record only local Desktop bridge lifecycle events, never production output."""
    session_id = str(payload.get("sessionId", "")).strip()
    stage = str(payload.get("stage", "")).strip()
    message = str(payload.get("message", "")).strip()
    allowed = {
        "focusing": ("creating-desktop-task", "desktop-bridge-focusing", "focusing"),
        "creating": ("creating-desktop-task", "desktop-bridge-creating", "creating"),
        "resuming": ("reconnecting", "desktop-bridge-resuming", "resuming"),
        "resumed": ("running", "desktop-bridge-resumed", "resumed"),
        "resume-failed": ("reconnecting", "desktop-bridge-recovery-queued", "recovery-retry"),
        "repair-task-created": ("repairing", "desktop-skill-repair-running", "skill-repair-created"),
        "native-created": ("submitted", "desktop-native-thread-created", "native-thread-created"),
        "sent": ("submitted", "desktop-task-delivered-unconfirmed", "sent"),
        "submitted-unverified": ("submitted", "desktop-task-input-unverified", "submitted-unverified"),
        "failed": ("failed", "desktop-bridge-failed", "failed"),
    }
    if not session_id or stage not in allowed or len(message) > 500:
        raise ValueError("桌面桥接事件参数无效")
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("工作台任务不存在")
    session = rows[0]
    # A Desktop bridge can fail before it locates the window even though an
    # operator subsequently creates the same visible Codex task through the
    # official task API. Permit that one accurate recovery event; completed or
    # cancelled production sessions remain immutable.
    recover_visible_task = (
        stage in {"sent", "submitted-unverified"}
        and session["status"] == "failed"
        and session.get("bridge_status") == "desktop-bridge-failed"
    )
    if session["status"] in TERMINAL_SESSION_STATUSES and not recover_visible_task:
        raise ValueError("已结束任务不能更新桌面桥接状态")
    status, bridge, navigation = allowed[stage]
    gallery_bridge_failure = stage == "failed" and _is_gallery_session(session)
    if stage == "failed" and _is_gallery_session(session):
        status, bridge, navigation = "reconnecting", "desktop-bridge-recovery-queued", "recovery-queued"
    native_thread_id = ""
    native_project_id = ""
    if stage == "native-created":
        try:
            native_payload = json.loads(message)
        except json.JSONDecodeError as exc:
            raise ValueError("Codex Desktop 原生任务返回格式无效") from exc
        if not isinstance(native_payload, dict):
            raise ValueError("Codex Desktop 原生任务返回格式无效")
        native_thread_id = str(native_payload.get("threadId") or "").strip()
        native_project_id = str(native_payload.get("projectId") or "").strip()
        if not re.fullmatch(r"[0-9a-fA-F-]{16,80}", native_thread_id) or not native_project_id:
            raise ValueError("Codex Desktop 未返回有效任务编号")
        message = f"Codex Desktop 已创建可见任务（{native_thread_id}），固定提示词已发送。"
    with _connection() as connection:
        if stage == "native-created":
            connection.execute(
                "UPDATE sessions SET status=?, bridge_status=?, codex_thread_id=?, codex_project_id=?, codex_project_root=?, desktop_navigation_status=?, updated_at=? WHERE id=?",
                (status, bridge, native_thread_id, native_project_id, str(PROJECT_ROOT), navigation, now(), session_id),
            )
        else:
            if gallery_bridge_failure:
                retry_at = (datetime.now().astimezone() + timedelta(seconds=30)).isoformat(timespec="seconds")
                connection.execute(
                    "UPDATE sessions SET status=?, bridge_status=?, desktop_navigation_status=?, recovery_failure_class='desktop-bridge', recovery_next_at=?, updated_at=? WHERE id=?",
                    (status, bridge, navigation, retry_at, now(), session_id),
                )
            else:
                connection.execute(
                    "UPDATE sessions SET status=?, bridge_status=?, desktop_navigation_status=?, updated_at=? WHERE id=?",
                    (status, bridge, navigation, now(), session_id),
                )
    defaults = {
        "focusing": "正在定位 Codex 桌面窗口。",
        "creating": "正在创建 Codex 项目任务。",
        "resuming": "正在向原 Codex 任务发送检查点恢复指令。",
        "resumed": "原 Codex 任务已收到恢复指令，正在继续。",
        "resume-failed": "原 Codex 任务暂不可恢复，正在创建独立恢复任务。",
        "repair-task-created": "已创建独立 Skill 修复任务，主配图任务保持修复中。",
        "native-created": "Codex Desktop 已创建可见任务，固定提示词已发送。",
        "sent": "固定提示词已发送，等待 Codex 任务回写启动状态。",
        "submitted-unverified": "已尝试在新任务中输入固定提示词，等待 Codex 任务回写启动状态。",
        "failed": "Codex 桌面连接失败；配图任务将自动恢复。" if _is_gallery_session(session) else "Codex 桌面任务创建失败。",
    }
    _record_event(
        session_id,
        "warning" if stage in {"failed", "resume-failed"} else "info",
        message or defaults[stage],
        kind="desktop-bridge",
        detail={"stage": stage, "status": status},
    )
    return _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))[0]


def respond_to_approval(approval_id: str, decision: str = "", answers: Any = None) -> dict[str, Any]:
    rows = _rows("SELECT * FROM approvals WHERE id = ?", (approval_id,))
    if not rows:
        raise FileNotFoundError("审批记录不存在")
    raise ValueError("工作台 V1 不再代理后台 App Server 审批；请在对应的可见 Codex 任务中完成确认。")


def recover_session(session_id: str) -> dict[str, Any]:
    raise ValueError("可见任务模式不恢复后台 App Server 线程；请在原 Codex 桌面任务中继续。")


def open_session_task(session_id: str) -> dict[str, Any]:
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("任务会话不存在")
    session = rows[0]
    return {"sessionId": session_id, "mode": "manual-visible-task", "prompt": session["message"], "manifest": _json_object(session.get("workflow_json")).get("manifest", "")}


def cancel_session(session_id: str) -> dict[str, Any]:
    rows = _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))
    if not rows:
        raise FileNotFoundError("任务会话不存在")
    session = rows[0]
    status = str(session.get("status") or "")
    thread_id = str(session.get("codex_thread_id") or "")
    turn_id = str(session.get("codex_turn_id") or "")
    if status in ACTIVE_SESSION_STATUSES and thread_id:
        # V1 tasks run in the user-visible native Codex task.  The retired
        # App Server cannot interrupt that task, so changing the database row
        # here would only fake a cancellation while Codex keeps working.
        raise ValueError("该任务已在 Codex 桌面中运行；请在对应 Codex 任务里终止后，再回到工作台查看状态。")
    with _connection() as connection:
        connection.execute(
            "UPDATE sessions SET status='cancelled', bridge_status='cancelled', desktop_navigation_status='cancelled', updated_at=? WHERE id=?",
            (now(), session_id),
        )
    _record_event(session_id, "warning", "未创建 Codex 任务的请求已取消并保留审计记录；不会自动恢复或重复生成。", kind="task-state", detail={"status": "cancelled", "threadId": thread_id, "turnId": turn_id})
    return _rows("SELECT * FROM sessions WHERE id = ?", (session_id,))[0]


def continue_session(session_id: str, message: str) -> dict[str, Any]:
    raise ValueError("请在已创建的 Codex 桌面任务中继续对话；工作台不会向后台线程发送补充输入。")


def _agent_avatar(agent_id: str) -> str:
    names = {"xiaojiang": "01_小姜-CEO助理Agent.png", "xiaoshen": "02_小审-质量审核Agent.png", "xiaoxi": "03_小息-信息采集Agent.png", "xiaochai": "04_小拆-内容拆解Agent.png", "xiaojing": "05_小镜-对标结构研究Agent.png", "xiaoce": "06_小策-选题策略Agent.png", "xiaoxie": "07_小写-文案生产Agent.png", "xiaotu": "08_小图-视觉生产Agent.png", "xiaoshu": "09_小数-内容复盘Agent.png", "xiaojian": "10_小剪-视频制作Agent.png", "xiaofa": "11_小发-发布运营Agent.png"}
    return f"/agent-avatar/{names.get(agent_id, '')}" if names.get(agent_id) else ""


def agent_overview() -> dict[str, Any]:
    try:
        registry = json.loads(SYSTEM_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        registry = {"agents": []}
    task_agent = {"generate-copy": "xiaoxie", "generate-structure": "xiaochai", "refresh-topics": "xiaoce", "break-review": "xiaochai", "inventory-stats": "xiaoxi"}
    # Waiting for the user to create a Desktop task is not AI execution.
    active = [session for session in list_sessions() if session["status"] in {"running", "repairing", "needs-user", "waiting-audit"}]
    agents = []
    for item in registry.get("agents", []):
        current = next((session for session in active if task_agent.get(session["action"]) == item["id"]), None)
        agents.append({"id": item["id"], "name": item["displayName"], "skill": item.get("skill"), "availability": item["status"], "status": current["status"] if current else ("available" if item["status"] == "active" else "planned"), "currentTask": current["title"] if current else "", "avatar": _agent_avatar(item["id"])})
    return {"generatedAt": now(), "agents": agents}


def _markdown_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [path for path in root.rglob("*.md") if path.is_file() and path.name not in IGNORED_FILE_NAMES]


def _approved_case_ids() -> set[str]:
    """Return the current approved benchmark IDs from the authoritative registry."""
    try:
        registry = json.loads((PROJECT_ROOT / "00_系统说明" / "benchmark-case-registry.json").read_text(encoding="utf-8"))
        return {str(item.get("id") or "").strip() for item in registry.get("cases", []) if isinstance(item, dict) and item.get("id")}
    except (OSError, json.JSONDecodeError):
        return set()


def _selected_topic_count() -> int:
    """Count executable selected-topic × approved-case branches.

    A table cell may hold several benchmark IDs separated by ``<br>``.  Each
    binding is its own downstream structure/copy branch, so treating the whole
    cell as one identifier silently drops valid multi-case selections.
    """
    approved_ids = _approved_case_ids()
    count = 0
    for row in _topic_rows():
        if not row.get("selected"):
            continue
        try:
            case_ids = parse_benchmark_case_ids(str(row.get("benchmarkCaseId") or ""))
        except ValueError:
            continue
        count += sum(case_id in approved_ids for case_id in case_ids)
    return count


def _count_audits(folder: str) -> int:
    return len(_markdown_files(FORMAL_AUDIT_ROOT / folder)) + len(list((FORMAL_AUDIT_ROOT / folder).glob("*.json"))) if (FORMAL_AUDIT_ROOT / folder).is_dir() else 0


def _structure_four_count() -> int:
    return sum(1 for path in _markdown_files(STRUCTURE_ROOT) if "结构四" in path.read_text(encoding="utf-8", errors="ignore"))


def _generated_copy_count() -> int:
    """Count every current Markdown asset in the final-copy directory.

    This is intentionally independent from historic publication receipts.
    Hash-bound publication remains the formal release gate, but a renamed or
    owner-edited Markdown must remain visible as an existing copy asset.
    """
    return len(_module_files(COPY_ROOT, {".md"}))


def _active_pipeline_snapshot() -> dict[str, Any]:
    """Return the six public milestones while keeping internal gates intact."""
    # These are display milestones, not replacements for the registry's
    # internal workflow steps.  The latter remain the source of truth for
    # one-click generation and audit gates.
    inventory = _input_inventory_payload().get("summary", {})
    source_total = sum(int(item.get("total", 0)) for item in inventory.values() if isinstance(item, dict))
    catalog = {str(section.get("id") or ""): section for section in _asset_catalog_snapshot()}
    module_total = int(catalog.get("process", {}).get("count") or 0)
    cases = json.loads((PROJECT_ROOT / "00_系统说明" / "benchmark-case-registry.json").read_text(encoding="utf-8")).get("cases", [])
    display = [
        {"id": "source-knowledge", "label": "源知识库", "count": source_total, "formula": "输入库来源资料总数", "location": "01_输入库"},
        {"id": "content-modules", "label": "爆款内容模块", "count": module_total, "formula": "现役处理库内容模块总数", "location": "02_处理库"},
        {"id": "topics", "label": "爆款选题", "count": _selected_topic_count(), "formula": "已选中且绑定有效对标编号的选题分支", "location": "04_选题库/02_选题分类"},
        {"id": "cases", "label": "对标爆款", "count": len(cases), "formula": "已审核对标复刻拆解数量", "location": "05_案例库/02_对标复刻拆解"},
        {"id": "filled-structures", "label": "爆款结构文案", "count": _structure_four_count(), "formula": "已填写并冻结结构四", "location": "03_输出库/01_文案结构"},
        {"id": "final-copy", "label": "爆款成稿", "count": _generated_copy_count(), "formula": "正文成稿目录已落盘 Markdown 总数", "location": "03_输出库/02_正文成稿"},
    ]
    stages = [
        {"id": item["id"], "label": item["label"], "count": int(item["count"]), "statusLabel": "现役", "formula": item["formula"], "location": item["location"]}
        for item in display
    ]
    missing: list[str] = []
    if display[2]["count"] <= 0:
        missing.append("暂无已选中选题")
    if display[4]["count"] <= 0:
        missing.append("暂无已填写结构四")
    return {"generatedAt": now(), "stages": stages, "steps": [item["label"] for item in display], "oneClick": {"enabled": not missing, "missing": missing}}


def active_today_workflow() -> dict[str, Any]:
    pipeline = _active_pipeline_snapshot()
    stages = {stage["id"]: stage for stage in pipeline["stages"]}
    structure_count = int(stages.get("filled-structures", {}).get("count", 0))
    topic_count = int(stages.get("topics", {}).get("count", 0))
    return {
        "generatedAt": pipeline["generatedAt"],
        "summary": "工作台只展示现役链路；结构四由用户确认，正式发布必须经过小审。",
        "cards": [
            {"title": "已选中选题", "count": topic_count, "next": "锁定唯一选题行与已审核对标复刻拆解"},
            {"title": "待冻结结构四", "count": max(0, topic_count - structure_count), "next": "用户填写并冻结结构四后，才可进入正文"},
            {"title": "已发布正文", "count": int(stages.get("final-copy", {}).get("count", 0)), "next": "仅统计小审放行后的正式输出"},
        ],
    }


def _pipeline_stage_paths() -> dict[str, Path]:
    """Explicit local folders allowed from the seven-stage read-only details."""
    return {
        "source-knowledge": ASSET_ROOT / "01_输入库",
        "content-modules": ASSET_ROOT / "02_处理库",
        "case-cards": CASE_CARD_ROOT,
        "featured-books": BOOK_MODULE_INDEX.parent,
        "selected-topics": TOPIC_ROOT,
        "topics": TOPIC_ROOT,
        "cases": ASSET_ROOT / "05_案例库" / "02_对标复刻拆解",
        "copy-structures": STRUCTURE_ROOT,
        "filled-structures": STRUCTURE_ROOT,
        "final-copies": COPY_ROOT,
    }


def _relative_pipeline_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def pipeline_snapshot() -> dict[str, Any]:
    """Return the current registry-backed universal pipeline."""
    return _active_pipeline_snapshot()


def one_click_pipeline_options() -> dict[str, Any]:
    """Compatibility view for the shared final-copy selection catalog."""
    catalog = generation_candidates("copies")
    # Keep ``options`` for diagnostics and older callers; new UI uses the more
    # explicit ``candidates`` field shared with Today's refresh controls.
    return {**catalog, "options": catalog["candidates"]}


def _one_click_pipeline_prompt(selected: dict[str, Any], regenerate: bool) -> str:
    """Build the fixed, auditable prompt for exactly one selected topic."""
    return f"""请作为小姜执行“爆款流水线”一键成稿任务。

唯一选题：{selected['title']}
来源选题表：{selected['table']}
对标复刻拆解编号：{selected['benchmarkCaseId']}
执行 Skill：$final-copy-generation
Skill 名称：正文成稿生成Skill
执行人：小写
本次模式：{'重新生成（保留历史版本）' if regenerate else '首次生成'}

请读取该选题对应的已冻结结构四，按连续 FNN 大框架扩写正文，交小审独立审核，通过后受控发布。不得读取对标逐句、小结构或复刻画像，也不得覆盖历史正式文件。"""


def _one_click_pipeline_batch_prompt(selected: list[dict[str, Any]]) -> str:
    return f"""请作为小姜执行“爆款流水线”正文成稿任务。

执行 Skill：$final-copy-generation
Skill 名称：正文成稿生成Skill
执行人：小写
本次已由工作区所有者明确选择以下清单（逐项执行，不得扩大范围）：
{_generation_selection_prompt(selected)}

请严格按：小姜分配 → 小写逐项串行生成 → 小审逐项独立审核 → 受控发布。
标记“首次生成”的项目按当前已冻结结构四首次生成；标记“重新生成”的项目必须保留历史正式版本，只新建候选和新版本。文件名是否带 √ 不得影响本次重生成资格；√ 只服务人工确认和配图下游。每项都必须回写模式、正式产物路径与审核结论，未获 approved 不得发布。"""


def create_one_click_pipeline_task(topic_id: str = "", regenerate: bool = False, selections: Any = None) -> dict[str, Any]:
    navigation = desktop_navigation_status()
    if not navigation["available"]:
        raise RuntimeError(str(navigation.get("message") or "当前 Codex 桌面桥接不可用，请先打开 Codex 桌面"))
    if selections is not None:
        selected_items = _validated_generation_selection("copies", selections)
        prompt = _one_click_pipeline_batch_prompt(selected_items)
    else:
        # Retain the old single-topic call for any saved deep link while the
        # browser switches to the common multi-select dialog.
        pipeline = _active_pipeline_snapshot()
        gate = pipeline.get("oneClick") or {}
        if not gate.get("enabled"):
            raise ValueError("一键生成暂不可用：" + "、".join(gate.get("missing") or ["前置条件未满足"]))
        selected = next((item for item in one_click_pipeline_options()["options"] if item["id"] == topic_id), None)
        if not selected or not selected.get("eligible"):
            raise ValueError("请选择一个已选中且已填写有效对标复刻拆解编号的选题")
        if selected["generated"] and not regenerate:
            raise ValueError("该选题已生成正文；如需再次生成，请通过选择窗口勾选该条")
        selected_items = [selected]
        prompt = _one_click_pipeline_prompt(selected, bool(regenerate))
    task_batch = [
        {
            "title": item["title"], "progress": "pending", "attempt": 1,
            "nextStep": item["generationLabel"] + "，等待小姜按清单串行分配。",
            "generationMode": item["generationMode"], "currentFormalPath": item["currentFormalPath"], "auditConclusion": "待小审",
        }
        for item in selected_items
    ]
    session = create_session({
        "action": "generate-copy",
        "title": "爆款流水线｜正文成稿｜" + (selected_items[0]["title"] if len(selected_items) == 1 else f"{len(selected_items)} 条"),
        "message": prompt,
        "skipApproval": True,
        "workflow": {"pipeline": "active-six-module", "visibleStages": ["source-knowledge", "content-modules", "topics", "cases", "filled-structures", "final-copy"], "internalSteps": [1, 2, 3, 6, 9], "generationSelections": selected_items, "topicId": selected_items[0]["id"] if len(selected_items) == 1 else "", "benchmarkCaseId": selected_items[0]["benchmarkCaseId"] if len(selected_items) == 1 else "", "regenerate": any(item["generationMode"] == "regenerate" for item in selected_items)},
        "batch": task_batch,
    })
    return _session_summary(_queue_visible_task(session["id"]), include_events=False)


def dashboard() -> dict[str, Any]:
    """Return only the shared workbench shell.

    Detailed page data belongs to ``/api/dashboard/page/<page>``.  Keeping
    this endpoint small prevents an old browser or diagnostic call from
    pulling task history, candidates, and asset inventories into the first
    screen response.
    """
    initialize_store()
    data_snapshot = load_snapshot() if PROJECT_ROOT == WORKBENCH_ROOT.parent else None
    snapshot_id = str(data_snapshot.get("snapshotId") or data_snapshot.get("generatedAt") or "") if isinstance(data_snapshot, dict) else ""
    return {
        "generatedAt": data_snapshot.get("generatedAt", now()) if isinstance(data_snapshot, dict) else now(),
        "snapshotId": snapshot_id,
        "types": content_types(),
        "bridge": bridge_status(),
        "desktopNavigation": desktop_navigation_status(),
        "assets": {"brand": _brand_info()},
        "dataCenter": {
            "generatedAt": data_snapshot.get("generatedAt", "") if isinstance(data_snapshot, dict) else "",
            "snapshotId": snapshot_id,
            "refreshMode": "manual",
        },
    }


def dashboard_page(page: str) -> dict[str, Any]:
    allowed = {"today", "pipeline", "assets", "team", "data"}
    if page not in allowed:
        raise ValueError("未知工作台页面")
    initialize_store()
    snapshot = load_snapshot() if PROJECT_ROOT == WORKBENCH_ROOT.parent else None
    snapshot_id = str(snapshot.get("snapshotId") or snapshot.get("generatedAt") or "") if isinstance(snapshot, dict) else ""
    view: dict[str, Any] = {
        "page": page,
        "generatedAt": snapshot.get("generatedAt", now()) if isinstance(snapshot, dict) else now(),
        "snapshotId": snapshot_id,
        "types": content_types(),
        # Task summaries and approvals are intentionally loaded by their
        # dialogs/poller on demand; they are unrelated to a page switch.
        "bridge": bridge_status(),
        "desktopNavigation": desktop_navigation_status(),
        "assets": {"brand": _brand_info()},
        "dataCenter": {"generatedAt": snapshot.get("generatedAt", "") if isinstance(snapshot, dict) else "", "snapshotId": snapshot_id, "refreshMode": "manual"},
    }
    if page == "today":
        view["todayModules"] = today_work_modules()
    elif page == "pipeline":
        view["pipeline"] = pipeline_snapshot()
        view["copyCapabilities"] = copy_production_capability_status()
    elif page == "assets":
        view["assets"] = _apply_snapshot_asset_counts(asset_overview(), snapshot)
        view["metrics"] = snapshot.get("metrics", {}) if isinstance(snapshot, dict) else {}
    elif page == "team":
        view["agents"] = agent_overview()["agents"]
    elif page == "data":
        view["pipeline"] = pipeline_snapshot()
        view["planStats"] = plan_completion_overview()
        view["assets"] = _apply_snapshot_asset_counts(asset_overview(), snapshot)
        view["metrics"] = snapshot.get("metrics", {}) if isinstance(snapshot, dict) else {}
        view["contentOutputStats"] = cumulative_output_by_content_type()
        view["galleryOutputCount"] = gallery_output_count()
    return view


def workbench_health() -> dict[str, Any]:
    initialize_store()
    snapshot = load_snapshot()
    return {
        "status": "ok",
        "service": "ai-viral-workbench",
        "port": WORKBENCH_PORT,
        "instanceId": WORKBENCH_INSTANCE_ID,
        "build": WORKBENCH_BUILD,
        "startedAt": WORKBENCH_STARTED_AT,
        "snapshotId": str(snapshot.get("snapshotId") or snapshot.get("generatedAt") or "") if isinstance(snapshot, dict) else "",
        "snapshotGeneratedAt": str(snapshot.get("generatedAt") or "") if isinstance(snapshot, dict) else "",
        "bridge": bridge_status(),
        "desktopNavigation": desktop_navigation_status(),
    }


def _open_folder(group_id: str, source_index: int) -> dict[str, Any]:
    group = GROUP_BY_ID.get(group_id)
    if group is None or not 0 <= source_index < len(group["sources"]):
        raise ValueError("未知资产节点")
    snapshot = _source_snapshot(group["sources"][source_index], _load_member_capabilities())
    if snapshot["memberOnly"] and not snapshot["unlocked"]:
        raise PermissionError("会员内容尚未解锁")
    path = _safe_asset_path(snapshot["relativePath"])
    if not path.is_dir():
        raise FileNotFoundError("资产目录不存在")
    launch = _launch_folder(path, label="资产目录")
    return {**launch, "path": snapshot["relativePath"]}


def _open_catalog_directory(directory_id: str) -> dict[str, Any]:
    item = CATALOG_ITEM_BY_ID.get(directory_id)
    if item is None:
        raise ValueError("未知资产目录")
    path = _catalog_path(item)
    if not path.is_dir():
        raise FileNotFoundError("资产目录不存在")
    if item.get("memberOnly") and not _catalog_has_content(path, item):
        raise PermissionError("会员专享目录尚未解锁")
    launch = _launch_folder(path, label="资产目录")
    return {**launch, "path": str(item["relativePath"])}


def _open_type_root(type_id: str, stage: str) -> dict[str, Any]:
    item = _registered_content_type(type_id)
    if item is None or stage not in {"input", "process", "output"}:
        raise ValueError("未知内容类型目录")
    available, _bodies = _content_type_available(item)
    if not available:
        if item.get("deploymentStatus") == "not-deployed":
            raise FileNotFoundError("该会员类型的正式输出目录尚未部署")
        raise PermissionError("会员内容尚未解锁")
    relative = item["roots"].get(stage)
    if not relative:
        raise FileNotFoundError("该内容类型的目录尚未部署")
    path = _safe_asset_path(relative)
    if not path.is_dir():
        raise FileNotFoundError("内容类型目录不存在")
    launch = _launch_folder(path, label="内容类型目录")
    return {**launch, "typeId": type_id, "stage": stage, "path": path.relative_to(PROJECT_ROOT).as_posix()}


def _open_today_folder(key: str) -> dict[str, Any]:
    path = TODAY_FOLDER_TARGETS.get(key)
    if path is None:
        raise ValueError("未知今日工作目录")
    resolved = path.resolve()
    if not resolved.is_relative_to(ASSET_ROOT.resolve()) or not resolved.is_dir():
        raise FileNotFoundError("今日工作目录不存在")
    launch = _launch_folder(resolved, label="今日工作目录")
    return {
        **launch,
        "label": TODAY_FOLDER_LABELS[key],
        "path": resolved.relative_to(PROJECT_ROOT).as_posix(),
    }


def _open_gallery() -> dict[str, Any]:
    path = GALLERY_ROOT.resolve()
    if not path.is_relative_to(ASSET_ROOT.resolve()) or not path.is_dir():
        raise FileNotFoundError("配图库目录不存在")
    launch = _launch_folder(path, label="配图库目录")
    return {**launch, "path": path.relative_to(PROJECT_ROOT).as_posix()}


def _open_pipeline_stage(stage_id: str) -> dict[str, Any]:
    path = _pipeline_stage_paths().get(stage_id)
    if path is None:
        raise ValueError("未知流水线节点")
    resolved = path.resolve()
    if not resolved.is_relative_to(PROJECT_ROOT.resolve()) or not resolved.is_dir():
        raise FileNotFoundError("流水线正式目录不存在")
    launch = _launch_folder(resolved, label="流水线正式目录")
    return {**launch, "path": _relative_pipeline_path(resolved)}


class WorkbenchHandler(SimpleHTTPRequestHandler):
    server_version = "AIPWorkbench/1.0"

    def log_message(self, format: str, *args: object) -> None:
        sys.stdout.write("[工作台] " + format % args + "\n")

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            # Browsers routinely cancel stale fetches while a page rerenders.
            # This is not a server failure and must not poison the error log.
            return

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > 22 * 1024 * 1024:
            raise ValueError("请求体超过工作台附件上限")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求格式不正确")
        return payload

    def _unexpected_error(self, method: str, exc: Exception) -> None:
        sys.stderr.write(f"[工作台] {method} failed: {type(exc).__name__}: {exc}\n")
        self._json({"error": "工作台服务处理失败，请重试或查看本机诊断"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_GET(self) -> None:
        try:
            self._do_get()
        except PermissionError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except FileNotFoundError as exc:
            self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return
        except Exception as exc:
            self._unexpected_error("GET", exc)

    def _do_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/health":
            self._json(workbench_health())
        elif path == "/api/dashboard":
            self._json(dashboard())
        elif path.startswith("/api/dashboard/page/"):
            self._json(dashboard_page(path.rsplit("/", 1)[-1]))
        elif path == "/api/data-center/summary":
            snapshot = load_snapshot()
            if snapshot is None:
                self._json({"error": "尚未执行数据刷新"}, HTTPStatus.NOT_FOUND)
            else:
                self._json(snapshot)
        elif path == "/api/data-center/entities":
            self._json({"entities": data_entities()})
        elif path == "/api/data-center/events":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["100"])[0])
            self._json({"events": data_events(limit=max(1, min(limit, 500)))})
        elif path == "/api/assets":
            self._json(asset_overview())
        elif path == "/api/assets/case-breakdowns":
            self._json({"items": _case_breakdown_items()})
        elif path == "/api/assets/case-breakdown":
            query = parse_qs(parsed.query)
            self._json(_case_breakdown_content(query.get("id", [""])[0]))
        elif path == "/api/topics":
            self._json(topic_overview())
        elif path == "/api/today/editor":
            surface = parse_qs(parsed.query).get("surface", [""])[0]
            self._json(today_editor_catalog(surface))
        elif path == "/api/today/editor/file":
            query = parse_qs(parsed.query)
            self._json(today_editor_file(query.get("surface", [""])[0], query.get("id", [""])[0]))
        elif path == "/api/today/editor/benchmark-cases":
            self._json(today_topic_benchmark_cases())
        elif path == "/api/today/modules":
            self._json(today_work_modules())
        elif path == "/api/today/input-inventory" or path.startswith("/api/today/input-inventory/"):
            payload = _input_inventory_payload()
            parts = [unquote(item) for item in path.split("/") if item]
            if len(parts) >= 4 and parts[3]:
                kind = parts[3]
                payload["rows"] = [row for row in payload["rows"] if row["source_type"] == kind]
                payload["summary"] = {kind: payload["summary"].get(kind, {})}
                if len(parts) >= 5 and parts[4]:
                    payload["rows"] = [row for row in payload["rows"] if row["source_id"] == parts[4]]
            self._json(payload)
        elif path == "/api/today/gallery-candidates":
            self._json(today_gallery_candidates())
        elif path == "/api/today/case-candidates":
            self._json(today_case_candidates())
        elif path == "/api/today/topic-candidates":
            self._json(today_topic_candidates())
        elif path == "/api/today/generation-candidates":
            module_id = parse_qs(parsed.query).get("moduleId", [""])[0]
            self._json(generation_candidates(module_id))
        elif path == "/api/pipeline/one-click-options":
            self._json(one_click_pipeline_options())
        elif path == "/api/desktop-bridge/pending":
            self._json({"job": next_desktop_bridge_job()})
        elif path == "/api/desktop-bridge/folder-pending":
            self._json({"job": next_desktop_folder_job()})
        elif path == "/api/desktop-bridge/folder-status":
            self._json(desktop_folder_status(parse_qs(parsed.query).get("requestId", [""])[0]))
        elif path == "/api/agents":
            self._json(agent_overview())
        elif path == "/api/plans":
            month = parse_qs(parsed.query).get("month", [""])[0]
            self._json(plans_for_month(month) if month else {"plans": list_plans()})
        elif path == "/api/sessions":
            query = parse_qs(parsed.query)
            active_only = query.get("scope", [""])[0] == "active"
            self._json({"sessions": list_sessions(limit=int(query.get("limit", ["30"])[0]), active_only=active_only, include_events=False)})
        elif path.startswith("/api/sessions/") and path.endswith("/events"):
            self._json({"events": session_detail(path.split("/")[-2]).get("events", [])})
        elif path.startswith("/api/sessions/"):
            self._json(session_detail(path.rsplit("/", 1)[-1]))
        elif path == "/api/approvals":
            self._json({"approvals": list_approvals()})
        elif path.startswith("/agent-avatar/"):
            self._serve_avatar(path.rsplit("/", 1)[-1])
        elif path.startswith("/brand-assets/"):
            self._serve_brand_asset(path.removeprefix("/brand-assets/"))
        elif path.startswith("/api/"):
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        else:
            self._serve_static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._payload()
            if path == "/api/workbench/folder-sync":
                page = str(payload.get("page") or "data")
                result = sync_workbench_folders(page)
            elif path == "/api/data-center/refresh":
                snapshot = refresh_data_center(reason="manual-refresh", producer="workbench")
                page = str(payload.get("page") or "data")
                result = {"dataCenter": snapshot, "dashboard": dashboard_page(page)}
            elif path == "/api/open-asset-directory":
                result = _open_catalog_directory(str(payload.get("directoryId", "")))
            elif path == "/api/open-type-root":
                result = _open_type_root(str(payload.get("typeId", "")), str(payload.get("stage", "")))
            elif path == "/api/today/open-folder":
                result = _open_today_folder(str(payload.get("key", "")))
            elif path == "/api/today/tasks":
                self._json({"error": "旧今日刷新任务接口已删除；请通过小姜调度现役 Skill。"}, HTTPStatus.GONE)
                return
            elif path == "/api/plans":
                result = create_plan(payload)
            elif path.startswith("/api/plans/") and path.endswith("/completion"):
                parts = path.split("/")
                if len(parts) != 7 or parts[4] != "occurrences":
                    raise ValueError("计划完成接口路径不正确")
                result = set_plan_occurrence_completion(parts[3], parts[5], bool(payload.get("completed")))
            elif path == "/api/sessions":
                result = create_session(payload)
            elif path == "/api/today/module-refresh":
                # Existing tabs can retain a pre-fix app.js in memory.  Accept
                # its former `selections` key as a compatibility alias so a
                # valid user click never becomes a silent no-op after deploy.
                selected = payload.get("selected") if "selected" in payload else payload.get("selections")
                result = create_today_module_task(str(payload.get("moduleId", "")), selected)
            elif path == "/api/pipeline/one-click":
                result = create_one_click_pipeline_task(str(payload.get("topicId") or ""), bool(payload.get("regenerate")), payload.get("selections") if "selections" in payload else None)
            elif path == "/api/today/edit-candidate/submit":
                result = submit_edit_candidate(str(payload.get("candidateId", "")))
            elif path == "/api/desktop-bridge-event":
                result = report_desktop_bridge_event(payload)
            elif path == "/api/desktop-bridge/heartbeat":
                result = update_desktop_bridge_agent(payload)
            elif path == "/api/desktop-bridge/claim":
                result = claim_desktop_bridge_job(str(payload.get("sessionId", "")))
            elif path == "/api/desktop-bridge/folder-claim":
                result = claim_desktop_folder_job(str(payload.get("requestId", "")))
            elif path == "/api/desktop-bridge/folder-event":
                result = report_desktop_folder_event(str(payload.get("requestId", "")), str(payload.get("status", "")), str(payload.get("message", "")))
            elif path == "/api/visible-task-event":
                result = report_visible_task_event(payload)
            elif path.startswith("/api/sessions/") and path.endswith("/approve"):
                result = approve_session(path.split("/")[-2])
            elif path.startswith("/api/sessions/") and path.endswith("/recover"):
                result = recover_session(path.split("/")[-2])
            elif path.startswith("/api/sessions/") and path.endswith("/open"):
                result = open_session_task(path.split("/")[-2])
            elif path.startswith("/api/sessions/") and path.endswith("/cancel"):
                result = cancel_session(path.split("/")[-2])
            elif path.startswith("/api/sessions/") and path.endswith("/continue"):
                result = continue_session(path.split("/")[-2], str(payload.get("message", "")))
            elif path.startswith("/api/approvals/") and path.endswith("/respond"):
                result = respond_to_approval(path.split("/")[-2], str(payload.get("decision", "")), payload.get("answers"))
            else:
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                return
            self._json(result, HTTPStatus.CREATED if path in {"/api/plans", "/api/sessions"} else HTTPStatus.OK)
        except PermissionError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._unexpected_error("POST", exc)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/plans/"):
                delete_plan(path.rsplit("/", 1)[-1])
                self._json({"deleted": True})
            else:
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except FileNotFoundError as exc:
            self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._unexpected_error("DELETE", exc)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/today/editor/file":
                payload = self._payload()
                self._json(save_today_editor_file(
                    str(payload.get("surface", "")),
                    str(payload.get("id", "")),
                    str(payload.get("expectedSha256", "")),
                    payload,
                ))
            elif not path.startswith("/api/plans/"):
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
                return
            else:
                self._json(update_plan(path.rsplit("/", 1)[-1], self._payload()))
        except PermissionError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except EditorConflictError as exc:
            self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except (ValueError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._unexpected_error("PUT", exc)

    def _serve_avatar(self, name: str) -> None:
        target = (AGENT_AVATAR_ROOT / unquote(name)).resolve()
        if not target.is_relative_to(AGENT_AVATAR_ROOT.resolve()) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_brand_asset(self, relative: str) -> None:
        try:
            target = _safe_brand_asset_path(relative)
            body = target.read_bytes()
        except (ValueError, FileNotFoundError):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        requested = unquote(path).lstrip("/")
        target = (FRONTEND_ROOT / (requested or "index.html")).resolve()
        if not target.is_relative_to(FRONTEND_ROOT.resolve()):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            # Only route-like paths fall back to the SPA shell. Missing assets
            # must be real 404s so a typo cannot become a silent JS/CSS error.
            if requested and Path(requested).suffix:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            target = FRONTEND_ROOT / "index.html"
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(body)))
        # Workbench JavaScript and styles must never remain stale after a local restart.
        self.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
        self.end_headers()
        self.wfile.write(body)


def _bind_server(port: int) -> ThreadingHTTPServer:
    try:
        return ThreadingHTTPServer(("127.0.0.1", port), WorkbenchHandler)
    except OSError as exc:
        raise OSError(f"工作台端口 {port} 已被占用。请先运行“工作台诊断/重启”处理冲突，工作台不会自动切换端口。") from exc


def main() -> int:
    global WORKBENCH_PORT
    parser = argparse.ArgumentParser(description="AI爆款内容工厂本机工作台")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    initialize_store()
    reconcile_interrupted_sessions()
    server = _bind_server(args.port)
    WORKBENCH_PORT = args.port
    ensure_desktop_bridge_agent(args.port)
    url = f"http://127.0.0.1:{args.port}"
    print(f"工作台已启动：{url} · 实例 {WORKBENCH_INSTANCE_ID}")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop_desktop_bridge_agent()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
