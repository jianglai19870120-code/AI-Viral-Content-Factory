"""Canonical public-release boundary for the Source Available repository."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


MEMBER_EXCLUSIVE_SUFFIX = "（会员专享）"
LOCAL_ONLY_PARTS = {".git", ".runtime", ".workbuddy", ".obsidian", ".codex", "dist", "_TEMP", "__pycache__", "__MACOSX", "node_modules"}
LOCAL_ONLY_WORKBENCH_PARTS = {"runtime", "__pycache__"}
LOCAL_ONLY_FILENAMES = {".env", ".sync-state.json", "ima_sync_state.json", ".processed_registry.jsonl", "skip_list.jsonl"}
PROCESS_DIRECTORY_MARKERS = {"99_历史处理记录", "99_运行记录", "99_执行记录", "99_审核记录", "99_本地运行记录", "99_历史恢复材料", "调度记录", "人工确认回执", "00_正式审核回执"}
ALLOWED_ROOTS = {"00_系统说明", "01_Agent系统", "02_资产中心", "03_工作台", "04_数据中心", "10_Skills武器库", "schemas", "tools", "workflow", ".agents", ".github"}
ALLOWED_ROOT_FILES = {"AGENTS.md", "README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md", "CONTENT-RIGHTS.md", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "run.py", ".gitignore", ".gitattributes", ".env.example"}
PROJECT_DIRECTORY_NAME = "AI" + "爆款内容工厂"
POSIX_HOME_PREFIX = "/" + "home" + "/"
HOST_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/](?:Users[\\/](?:Administrator|ADMINI~1)|"
    + re.escape(PROJECT_DIRECTORY_NAME)
    + r"|AI流量团队2\.0)|"
    + re.escape(POSIX_HOME_PREFIX)
    + r"[^/]+/)",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")


def load_policy(root: Path) -> dict:
    registry = json.loads((root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
    policy = registry.get("release", {}).get("publicAssetPolicy")
    if not isinstance(policy, dict):
        raise ValueError("system-registry.json 缺少 release.publicAssetPolicy")
    return policy


def is_member_exclusive(path: Path | str, *, directory: bool = False) -> bool:
    """A member boundary is a directory suffix, never a file name or type flag."""
    relative = Path(path)
    parts = relative.parts if directory else relative.parent.parts
    return any(MEMBER_EXCLUSIVE_SUFFIX in part for part in parts)


def classify(relative: Path) -> tuple[str, str]:
    """Return (public|private, stable reason) for a repository-relative file."""
    parts = relative.parts
    text = relative.as_posix()
    if any(part in LOCAL_ONLY_PARTS for part in parts) or relative.suffix.lower() == ".pyc":
        return "private", "local-runtime-or-cache"
    if text.startswith("03_工作台/") and any(part in LOCAL_ONLY_WORKBENCH_PARTS for part in parts[1:]):
        return "private", "workbench-runtime"
    if text.startswith("04_数据中心/02_事件流水/by-date/"):
        return "private", "data-center-runtime-event"
    if is_member_exclusive(relative):
        return ("public", "member-placeholder") if relative.name == ".gitkeep" else ("private", "member-exclusive-content")
    if text.startswith("tools/tmp_"):
        return "private", "temporary-tooling"
    if text.startswith("02_资产中心/06_配图库/") and ("evidence" in parts or "prompts" in parts or "prompt" in relative.name.casefold() or relative.name == "codex-workflow.txt"):
        return "private", "local-gallery-evidence"
    is_asset_data = bool(parts) and parts[0] in {"02_资产中心", "04_数据中心"}
    if relative.name in LOCAL_ONLY_FILENAMES:
        return "private", "local-process-record"
    if is_asset_data and (relative.name.endswith(".pending.json") or "candidate" in relative.name.lower()):
        return "private", "local-process-record"
    if any(part in PROCESS_DIRECTORY_MARKERS for part in parts):
        return "private", "local-process-record"
    return "public", "formal-source-or-asset"


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True)
    return [Path(item) for item in result.stdout.decode("utf-8", errors="strict").split("\0") if item]


def release_violations(root: Path, *, check_index: bool = False) -> list[str]:
    load_policy(root)
    failures: list[str] = []
    if not check_index:
        return failures
    for relative in tracked_files(root):
        if len(relative.parts) == 1:
            if relative.name not in ALLOWED_ROOT_FILES:
                failures.append(f"未分类根文件进入发布索引：{relative.as_posix()}")
        elif relative.parts[0] not in ALLOWED_ROOTS:
            failures.append(f"未分类根目录进入发布索引：{relative.as_posix()}")
        status, reason = classify(relative)
        if status != "public":
            failures.append(f"私有或运行态文件进入发布索引：{relative.as_posix()} ({reason})")
            continue
        path = root / relative
        if not path.is_file():
            failures.append(f"Git 索引引用的发布文件在工作区不存在：{relative.as_posix()}")
            continue
        if path.suffix.lower() not in {".py", ".ps1", ".cmd", ".bat", ".json", ".toml", ".yaml", ".yml", ".env", ".txt", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if TOKEN_PATTERN.search(text):
            failures.append(f"疑似真实凭证进入发布索引：{relative.as_posix()}")
        if relative.parts[0] in {"workflow", "tools", "03_工作台"} and HOST_PATH_PATTERN.search(text):
            failures.append(f"源码包含当前机器绝对路径：{relative.as_posix()}")
    return failures
