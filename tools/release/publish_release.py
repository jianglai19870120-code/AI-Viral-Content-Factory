"""One local, resumable release transaction for public GitHub and private Feishu."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.release.build_feishu_delivery import build_from_public_stage
from tools.release.build_release import github_package
from tools.release.feishu_publish import FeishuConfig, FeishuPublisher
from tools.quality.audit_github_baseline import audit_staged_package


VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def state_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "AI-Viral-Content-Factory" / "publish"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def asset_inventory(root: Path) -> dict[str, str]:
    """Return the active deliverable asset snapshot for mirror reporting.

    The public projection is intentionally a complete replacement.  Keeping a
    path-to-hash snapshot makes deletions visible before the temporary checkout
    is cleared and gives the release state an auditable answer to “what was
    taken down”.
    """
    asset_root = root / "02_资产中心"
    if not asset_root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(asset_root.rglob("*"))
        if path.is_file() and path.name != ".gitkeep"
    }


def asset_change_summary(previous_root: Path, current_root: Path) -> dict[str, list[str] | int]:
    return asset_change_summary_from_inventories(asset_inventory(previous_root), asset_inventory(current_root))


def asset_change_summary_from_inventories(previous: dict[str, str], current: dict[str, str]) -> dict[str, list[str] | int]:
    added = sorted(set(current) - set(previous))
    deleted = sorted(set(previous) - set(current))
    modified = sorted(path for path in set(previous) & set(current) if previous[path] != current[path])
    return {
        "scope": "02_资产中心 active-delivery mirror",
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "addedCount": len(added),
        "modifiedCount": len(modified),
        "deletedCount": len(deleted),
    }


def asset_inventory_from_public_manifest(payload: str) -> dict[str, str]:
    """Read the previous asset snapshot without checking out every old blob."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub 当前公开资产清单不可解析，拒绝执行镜像删除") from exc
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        raise RuntimeError("GitHub 当前公开资产清单缺少 records，拒绝执行镜像删除")
    return {
        str(item["path"]): str(item["sha256"])
        for item in records
        if isinstance(item, dict)
        and str(item.get("path") or "").startswith("02_资产中心/")
        and str(item.get("path") or "").split("/")[-1] != ".gitkeep"
        and str(item.get("status") or "") == "public"
        and str(item.get("sha256") or "")
    }


def run(root: Path, *command: str) -> None:
    result = subprocess.run([sys.executable, *command], cwd=root, env={**os.environ, "PYTHONUTF8": "1"})
    if result.returncode:
        raise RuntimeError("发布门禁失败：" + " ".join(command))


def git(root: Path, *command: str) -> str:
    try:
        result = subprocess.run(
            ["git", *command], cwd=root, text=True, encoding="utf-8", errors="replace", capture_output=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Git 命令超时 git {' '.join(command)}") from exc
    if result.returncode:
        raise RuntimeError(f"Git 命令失败 git {' '.join(command)}: {result.stderr.strip()}")
    return result.stdout.strip()


def load_state(path: Path, version: str) -> dict[str, Any]:
    if path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("version") != version:
            raise RuntimeError("发布状态版本不一致，拒绝混用断点状态")
        return state
    return {"schema": "ai-viral-content-factory-release-v1", "version": version, "stages": {}, "feishu": {"releases": {}}}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def configured_version(root: Path) -> str:
    registry = json.loads((root / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
    return "v" + str(registry["system"]["version"])


def preflight(root: Path, version: str) -> None:
    if not VERSION.fullmatch(version):
        raise ValueError("版本必须采用 v主版本.次版本.修订号，例如 v3.1.0")
    if configured_version(root) != version:
        raise ValueError(f"system-registry.json 当前为 {configured_version(root)}，与请求发布版本 {version} 不一致")


def inspect_preflight(root: Path, version: str, state_path: Path) -> dict[str, Any]:
    """Perform every release-readiness check without changing a remote or state file."""
    preflight(root, version)
    state = load_state(state_path, version)
    remote = git(root, "remote", "get-url", "origin")
    failures = audit_staged_package(root)
    if failures:
        raise RuntimeError("公开投影预检失败：" + "；".join(failures))
    publisher = FeishuPublisher(FeishuConfig.from_environment())
    wiki_root = publisher.resolve_root()
    zip_block = publisher._vip_file_block(wiki_root["document_id"])
    return {
        "status": "preflight-passed",
        "version": version,
        "branch": str(state.get("branch") or "main"),
        "state_path": str(state_path),
        "completed_stages": sorted(name for name, complete in state.get("stages", {}).items() if complete),
        "github_remote": remote,
        "public_projection": "passed",
        "feishu_page": {"document_id_present": bool(wiki_root["document_id"]), "zip_name": zip_block["name"]},
    }


def run_gates(root: Path) -> None:
    for command in (
        ("run.py", "doctor"), ("run.py", "validate"), ("run.py", "test"),
        ("run.py", "sync-platform", "--target", "codex", "--apply"),
        ("run.py", "audit-baseline"), ("run.py", "release-check"),
    ):
        run(root, *command)


def build_public_stage(root: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    github_package(root, destination)
    if not (destination / "PUBLIC_ASSETS_MANIFEST.json").is_file():
        raise RuntimeError("公开投影未生成 PUBLIC_ASSETS_MANIFEST.json")


def push_public_projection(root: Path, stage: Path, version: str, branch: str) -> dict[str, Any]:
    remote = git(root, "remote", "get-url", "origin")
    with tempfile.TemporaryDirectory(prefix="ai-viral-public-git-") as temporary:
        checkout = Path(temporary) / "public"
        checkout.mkdir()
        # A projection is a complete replacement.  Fetch the previous commit
        # and tree only, then rebuild the index from the current stage.  This
        # avoids downloading every obsolete asset before deleting it.
        git(checkout, "init")
        git(checkout, "remote", "add", "origin", remote)
        # GitHub occasionally resets the long-lived HTTP/2 ref negotiation on
        # this Windows host.  HTTP/1.1 keeps the shallow metadata fetch
        # resumable and remains fully non-interactive.
        git(checkout, "-c", "http.version=HTTP/1.1", "fetch", "--depth=1", "--filter=blob:none", "origin", branch)
        if git(checkout, "ls-remote", "--tags", "origin", f"refs/tags/{version}"):
            raise RuntimeError(f"标签 {version} 已存在，拒绝覆盖")
        try:
            previous_manifest = git(checkout, "show", "FETCH_HEAD:PUBLIC_ASSETS_MANIFEST.json")
        except RuntimeError as exc:
            raise RuntimeError("无法读取 GitHub 当前公开资产清单，拒绝执行镜像删除") from exc
        asset_changes = asset_change_summary_from_inventories(
            asset_inventory_from_public_manifest(previous_manifest), asset_inventory(stage),
        )
        git(checkout, "update-ref", f"refs/heads/{branch}", "FETCH_HEAD")
        git(checkout, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
        git(checkout, "read-tree", "--empty")
        for source in stage.rglob("*"):
            target = checkout / source.relative_to(stage)
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        git(checkout, "add", "-A")
        if not git(checkout, "status", "--porcelain"):
            commit = git(checkout, "rev-parse", "HEAD")
        else:
            git(checkout, "commit", "-m", f"release: publish {version} public projection")
            commit = git(checkout, "rev-parse", "HEAD")
            git(checkout, "push", "origin", f"HEAD:refs/heads/{branch}")
        git(checkout, "tag", "-a", version, "-m", f"Release {version}")
        git(checkout, "push", "origin", version)
    return {
        "commit": commit,
        "url": remote.removesuffix(".git") + "/releases/tag/" + version,
        "assetChanges": asset_changes,
    }


def execute(root: Path, version: str, *, dry_run: bool, skip_gates: bool, branch: str, state_path: Path) -> dict[str, Any]:
    preflight(root, version)
    if skip_gates and not dry_run:
        raise ValueError("--skip-gates 只能与 --dry-run 一起用于本地调试")
    state = load_state(state_path, version)
    state["branch"] = branch
    if dry_run:
        return {"status": "dry-run", "version": version, "state_path": str(state_path), "steps": ["gates", "public-projection", "github-push", "vip-package", "feishu-publish"]}
    if not skip_gates and not state["stages"].get("gates"):
        run_gates(root)
        state["stages"]["gates"] = True; save_state(state_path, state)
    with tempfile.TemporaryDirectory(prefix="ai-viral-release-") as temporary:
        stage = Path(temporary) / "github"
        build_public_stage(root, stage)
        state["stages"]["public_projection"] = True; save_state(state_path, state)
        if not state["stages"].get("github"):
            state["github"] = push_public_projection(root, stage, version, branch)
            state["stages"]["github"] = True; save_state(state_path, state)
        delivery = state_root() / "deliveries" / f"AI爆款内容工厂-VIP-{version}.zip"
        if not state["stages"].get("vip_package"):
            if delivery.exists():
                raise RuntimeError(f"发现未登记的同版本会员交付包，拒绝覆盖：{delivery}")
            result = build_from_public_stage(root, stage, delivery, baseline=f"GitHub {version} @ {state['github']['commit']}")
            state["vip_package"] = result
            state["stages"]["vip_package"] = True; save_state(state_path, state)
    if not state["stages"].get("feishu"):
        archive = Path(state["vip_package"]["archive"])
        config = FeishuConfig.from_environment()
        state["feishu_result"] = FeishuPublisher(config).publish_version(
            version=version, github_url=state["github"]["url"], archive=archive,
            archive_sha256=str(state["vip_package"]["archiveSha256"]), state=state,
        )
        state["stages"]["feishu"] = True; save_state(state_path, state)
    return {"status": "published", "version": version, "state_path": str(state_path), "github": state.get("github"), "feishu": state.get("feishu_result")}


def main() -> int:
    parser = argparse.ArgumentParser(description="发布 GitHub 免费版和飞书会员版")
    parser.add_argument("--version", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight", action="store_true", help="只读检查发布条件、公开投影和飞书固定 ZIP")
    parser.add_argument("--skip-gates", action="store_true", help="仅用于本地调试，正式发布禁止使用")
    parser.add_argument("--state")
    args = parser.parse_args()
    root = PROJECT_ROOT
    state = Path(args.state).resolve() if args.state else state_root() / f"{args.version}.json"
    try:
        if args.preflight:
            if args.dry_run or args.skip_gates:
                raise ValueError("--preflight 不可与 --dry-run 或 --skip-gates 同时使用")
            result = inspect_preflight(root, args.version, state)
        else:
            result = execute(root, args.version, dry_run=args.dry_run, skip_gates=args.skip_gates, branch=args.branch, state_path=state)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "failed", "version": args.version, "error": str(exc), "state_path": str(state)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
