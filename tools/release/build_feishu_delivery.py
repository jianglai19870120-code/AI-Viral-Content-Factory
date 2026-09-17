#!/usr/bin/env python3
"""Build a full, member-inclusive Feishu delivery archive from a working tree.

Unlike the public GitHub package, this delivery package retains every member-only
asset.  It is still deliberately free of local runtime data, caches, audit and
dispatch records, recovered history, generated evidence, credentials, and build
artifacts.  The source tree is never changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOTS = {
    ".agents", ".github", "00_系统说明", "01_Agent系统", "02_资产中心",
    "03_工作台", "04_数据中心", "10_Skills武器库", "schemas", "tools", "workflow",
}
ROOT_FILES = {
    "AGENTS.md", "README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md",
    "COMMERCIAL-LICENSE.md", "THIRD_PARTY_NOTICES.md", "CONTENT-RIGHTS.md",
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "run.py",
    ".gitignore", ".gitattributes", ".env.example",
}
EXCLUDED_PARTS = {
    ".git", ".runtime", ".workbuddy", ".obsidian", ".codex", "dist", "_TEMP",
    "outputs", "node_modules", "__pycache__", ".venv", "venv", "env", "__MACOSX",
}
RECORD_OR_HISTORY_PARTS = {
    "99_运行记录", "99_执行记录", "99_审核记录", "99_本地运行记录", "99_历史处理记录",
    "99_历史恢复材料", "99_归档", "99_备份", "调度记录", "人工确认回执", "00_正式审核回执",
}
LOCAL_FILENAMES = {".env", ".sync-state.json", "ima_sync_state.json", ".processed_registry.jsonl", "skip_list.jsonl", "nul"}
SENSITIVE_NAME_RE = re.compile(r"(?:credential|secret|token|password|private.?key|apikey|api.?key)", re.IGNORECASE)
SENSITIVE_VALUE_RE = re.compile(r"(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})")
TOOL_JUNK_RE = re.compile(r"^tools/(?:_backup_chunk|_migrate_|_verify_|_batch|patch_|rewrites_|tmp_|recover\.py$|migrate\.py$|migrate_11to10\.py$|transform_11to10\.py$|acc\.py$|check_audit\.py$|validate\.py$)", re.IGNORECASE)
MEMBER_CASE_REGISTRY = Path("00_系统说明/benchmark-case-registry.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def excluded(relative: Path) -> tuple[bool, str]:
    parts = relative.parts
    posix = relative.as_posix()
    if not parts:
        return True, "empty-path"
    if parts[0] not in PROJECT_ROOTS and len(parts) > 1:
        return True, "outside-project-contract"
    if len(parts) == 1 and parts[0] not in ROOT_FILES:
        return True, "unlisted-root-file"
    if any(part in EXCLUDED_PARTS for part in parts):
        return True, "runtime-cache-or-build-output"
    if any(part in RECORD_OR_HISTORY_PARTS for part in parts):
        return True, "runtime-record-or-history"
    name = relative.name
    if name in LOCAL_FILENAMES or name.endswith(".pyc") or name.endswith(".pending.json"):
        return True, "local-state"
    if name.startswith(".env") and name != ".env.example":
        return True, "environment-config"
    if name.endswith(".local"):
        return True, "local-config"
    if TOOL_JUNK_RE.match(posix):
        return True, "one-off-tooling"
    if posix.startswith("02_资产中心/06_配图库/") and (
        "evidence" in parts or "prompts" in parts or "prompt" in name.casefold() or name == "codex-workflow.txt"
    ):
        return True, "image-generation-evidence"
    if posix.startswith("04_数据中心/02_事件流水/by-date/"):
        return True, "runtime-event-log"
    if SENSITIVE_NAME_RE.search(name):
        return True, "sensitive-filename"
    return False, ""


def included_files(root: Path, *, allow_extra_root_files: bool = False) -> tuple[list[Path], dict[str, int]]:
    files: list[Path] = []
    excluded_counts: dict[str, int] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        skip, reason = excluded(relative)
        if allow_extra_root_files and len(relative.parts) == 1 and reason == "unlisted-root-file":
            skip, reason = False, ""
        if skip:
            excluded_counts[reason] = excluded_counts.get(reason, 0) + 1
        else:
            files.append(path)
    return sorted(files), dict(sorted(excluded_counts.items()))


def scan_sensitive(files: list[Path], root: Path) -> list[str]:
    findings: list[str] = []
    text_suffixes = {".md", ".txt", ".py", ".json", ".jsonl", ".yaml", ".yml", ".ps1", ".toml", ".env", ".ini", ".cfg"}
    for path in files:
        if path.suffix.lower() not in text_suffixes:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if SENSITIVE_VALUE_RE.search(content):
            findings.append(path.relative_to(root).as_posix())
    return findings


def delivery_readme(version: str, created_at: str, file_count: int, source_bytes: int, baseline: str) -> str:
    return f"""# AI爆款内容工厂 VIP 完整交付包

- 版本：v{version}
- 打包时间：{created_at}
- 非会员基线：{baseline}
- 内容文件：{file_count} 个，源文件合计：{source_bytes:,} bytes
- 适用：Windows 10/11、Python 3.11–3.13、Node.js 20 LTS、Codex Desktop

这是当前工作副本制作的会员完整包，已保留目录名带“（会员专享）”的实际内容。

未包含：本机运行态、缓存、node_modules、虚拟环境、审核/调度记录、历史归档/备份、图像生成证据、临时文件、构建产物、环境变量与疑似凭证文件。原始工作区不会因打包而被删除或修改。

安装说明见 `00_系统说明/跨电脑安装与发布.md`。解压后建议先执行：

```powershell
py -3.12 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python run.py install --dev
python run.py doctor
python run.py sync-platform --target codex --apply
```

包内 `DELIVERY_MANIFEST.json` 列出全部文件、大小与 SHA-256；`DELIVERY_ARCHIVE.sha256` 可校验压缩包本身。

---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
"""


def write_archive(source_root: Path, output: Path, *, baseline: str, member_assets_included: bool, allow_extra_root_files: bool) -> dict:
    if output.exists():
        raise RuntimeError(f"输出压缩包已存在，拒绝覆盖：{output}")
    registry = json.loads((source_root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
    version = str(registry["system"]["version"])
    files, excluded_counts = included_files(source_root, allow_extra_root_files=allow_extra_root_files)
    sensitive = scan_sensitive(files, source_root)
    if sensitive:
        raise RuntimeError("候选交付包发现疑似真实凭证，已停止打包：" + ", ".join(sensitive))
    created_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    source_bytes = sum(path.stat().st_size for path in files)
    prefix = f"AI爆款内容工厂-VIP-v{version}/"
    records = [
        {"path": path.relative_to(source_root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in files
    ]
    manifest = {
        "schema": "ai-viral-content-factory-feishu-delivery-v1",
        "product": registry["system"]["displayName"],
        "version": version,
        "createdAt": created_at,
        "baseline": baseline,
        "memberAssetsIncluded": member_assets_included,
        "sourceRoot": ".",
        "files": records,
        "excludedFileCounts": excluded_counts,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in files:
            archive.write(path, prefix + path.relative_to(source_root).as_posix())
        archive.writestr(prefix + "DELIVERY_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        archive.writestr(prefix + "README_交付说明.md", delivery_readme(version, created_at, len(files), source_bytes, baseline))
    archive_sha = sha256(output)
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{archive_sha}  {output.name}\n", encoding="utf-8")
    return {
        "archive": str(output), "archiveBytes": output.stat().st_size, "archiveSha256": archive_sha,
        "checksum": str(checksum), "version": version, "files": len(files), "sourceBytes": source_bytes,
        "baseline": baseline, "memberAssetsIncluded": member_assets_included, "excludedFileCounts": excluded_counts,
    }


def build(root: Path, output: Path) -> dict:
    return write_archive(root, output, baseline="current-working-tree", member_assets_included=True, allow_extra_root_files=False)


def is_member_asset(relative: Path) -> bool:
    return any("（会员专享）" in part for part in relative.parts)


def is_member_delivery_asset(relative: Path) -> bool:
    """Member delivery also needs the private case index outside member folders."""
    return is_member_asset(relative) or relative == MEMBER_CASE_REGISTRY


def git_ref(root: Path, ref: str) -> str:
    result = subprocess.run(["git", "rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=root, text=True, encoding="utf-8", capture_output=True)
    if result.returncode:
        raise RuntimeError(f"无法解析 Git 基线 {ref}: {result.stderr.strip()}")
    return result.stdout.strip()


def safe_extract_archive(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:") as archive:
        for item in archive.getmembers():
            target = (destination / item.name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError(f"Git 归档包含越界路径：{item.name}")
        archive.extractall(destination, filter="data")


def build_github_synced(root: Path, ref: str, output: Path) -> dict:
    commit = git_ref(root, ref)
    copied_member_files = 0
    member_excluded: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="ai-viral-feishu-github-") as temp:
        stage = Path(temp)
        archive_path = stage / "github-baseline.tar"
        with archive_path.open("wb") as stream:
            archived = subprocess.run(["git", "archive", "--format=tar", commit], cwd=root, stdout=stream, stderr=subprocess.PIPE)
        if archived.returncode:
            raise RuntimeError(f"无法导出 GitHub 基线 {commit}: {archived.stderr.decode('utf-8', errors='replace').strip()}")
        safe_extract_archive(archive_path, stage)
        archive_path.unlink()
        for source in root.rglob("*"):
            if not source.is_file():
                continue
            relative = source.relative_to(root)
            if not is_member_delivery_asset(relative):
                continue
            skip, reason = excluded(relative)
            if skip:
                member_excluded[reason] = member_excluded.get(reason, 0) + 1
                continue
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_member_files += 1
        result = write_archive(
            stage,
            output,
            baseline=f"GitHub origin/main @ {commit}",
            member_assets_included=True,
            allow_extra_root_files=True,
        )
    result["githubCommit"] = commit
    result["localMemberFilesOverlaid"] = copied_member_files
    result["excludedLocalMemberFileCounts"] = dict(sorted(member_excluded.items()))
    return result


def build_from_public_stage(root: Path, public_stage: Path, output: Path, *, baseline: str) -> dict:
    """Create a VIP delivery from the exact already-validated public projection.

    This avoids assuming that the private workspace itself is a Git checkout of
    the just-pushed public commit.  Only member directories are overlaid from
    the workspace; every non-member file comes from ``public_stage``.
    """
    if not public_stage.is_dir() or not (public_stage / "00_系统说明" / "system-registry.json").is_file():
        raise RuntimeError("公开投影目录不完整，不能构建飞书会员交付包")
    copied_member_files = 0
    member_excluded: dict[str, int] = {}
    for source in root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(root)
        if not is_member_delivery_asset(relative):
            continue
        skip, reason = excluded(relative)
        if skip:
            member_excluded[reason] = member_excluded.get(reason, 0) + 1
            continue
        target = public_stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_member_files += 1
    result = write_archive(
        public_stage,
        output,
        baseline=baseline,
        member_assets_included=True,
        allow_extra_root_files=True,
    )
    result["localMemberFilesOverlaid"] = copied_member_files
    result["excludedLocalMemberFileCounts"] = dict(sorted(member_excluded.items()))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="构建飞书用 VIP 完整交付压缩包")
    parser.add_argument("--root", default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", required=True)
    parser.add_argument("--github-ref", help="以指定 Git 提交作为非会员基线，并仅叠加本机会员专享目录内容")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    result = build_github_synced(root, args.github_ref, Path(args.output).resolve()) if args.github_ref else build(root, Path(args.output).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
