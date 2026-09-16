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


VERSION = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def state_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "AI-Viral-Content-Factory" / "publish"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(root: Path, *command: str) -> None:
    result = subprocess.run([sys.executable, *command], cwd=root, env={**os.environ, "PYTHONUTF8": "1"})
    if result.returncode:
        raise RuntimeError("发布门禁失败：" + " ".join(command))


def git(root: Path, *command: str) -> str:
    result = subprocess.run(["git", *command], cwd=root, text=True, encoding="utf-8", errors="replace", capture_output=True)
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


def push_public_projection(root: Path, stage: Path, version: str, branch: str) -> dict[str, str]:
    remote = git(root, "remote", "get-url", "origin")
    with tempfile.TemporaryDirectory(prefix="ai-viral-public-git-") as temporary:
        checkout = Path(temporary) / "public"
        clone = subprocess.run(["git", "clone", "--branch", branch, "--single-branch", remote, str(checkout)], text=True, encoding="utf-8", errors="replace", capture_output=True)
        if clone.returncode:
            raise RuntimeError("无法创建 GitHub 公开投影仓：" + clone.stderr.strip())
        for child in checkout.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
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
        existing = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{version}"], cwd=checkout, text=True, encoding="utf-8", capture_output=True)
        if existing.returncode == 0 and existing.stdout.strip() != commit:
            raise RuntimeError(f"标签 {version} 已存在且指向不同提交，拒绝覆盖")
        if existing.returncode:
            git(checkout, "tag", "-a", version, "-m", f"Release {version}")
            git(checkout, "push", "origin", version)
    return {"commit": commit, "url": remote.removesuffix(".git") + "/releases/tag/" + version}


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
    parser.add_argument("--skip-gates", action="store_true", help="仅用于本地调试，正式发布禁止使用")
    parser.add_argument("--state")
    args = parser.parse_args()
    root = PROJECT_ROOT
    state = Path(args.state).resolve() if args.state else state_root() / f"{args.version}.json"
    try:
        result = execute(root, args.version, dry_run=args.dry_run, skip_gates=args.skip_gates, branch=args.branch, state_path=state)
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "failed", "version": args.version, "error": str(exc), "state_path": str(state)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
