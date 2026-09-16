#!/usr/bin/env python3
"""AI爆款内容工厂的 Windows 安装、验证和正式业务入口。"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CODEX_CLI_ROOT = ROOT / "03_工作台" / "vendor" / "codex-cli"
LOCAL_CODEX_CLI = CODEX_CLI_ROOT / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"


def run_python(path: Path, *args: str) -> int:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return subprocess.call([sys.executable, str(path), *args], cwd=ROOT, env=env)


def run_command(command: list[str]) -> int:
    return subprocess.call(command, cwd=ROOT, env={**os.environ, "PYTHONUTF8": "1"})


def run_in(directory: Path, command: list[str]) -> int:
    return subprocess.call(command, cwd=directory, env={**os.environ, "PYTHONUTF8": "1"})


def node_major_version() -> int | None:
    node = shutil.which("node")
    if not node:
        return None
    try:
        version = subprocess.check_output([node, "--version"], text=True, encoding="utf-8", stderr=subprocess.STDOUT).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.fullmatch(r"v?(\d+)\.\d+\.\d+", version)
    return int(match.group(1)) if match else None


def doctor() -> int:
    failures: list[str] = []
    if not (sys.version_info.major == 3 and 11 <= sys.version_info.minor <= 13):
        failures.append(f"需要 Python 3.11–3.13，当前为 {sys.version.split()[0]}")
    for package in ("openpyxl", "requests", "PIL", "jsonschema", "yaml"):
        if importlib.util.find_spec(package) is None:
            failures.append(f"缺少 Python 依赖：{package}")
    required = [ROOT / "00_系统说明" / "system-registry.json", ROOT / "03_工作台" / "server.py", ROOT / "03_工作台" / "start-workbench.ps1", ROOT / "tools" / "platform" / "sync_skills.py"]
    for path in required:
        if not path.is_file():
            failures.append(f"缺少必要文件：{path.relative_to(ROOT).as_posix()}")
    try:
        registry = json.loads((ROOT / "00_系统说明" / "system-registry.json").read_text(encoding="utf-8"))
        for skill in registry.get("skills", []):
            source = ROOT / "10_Skills武器库" / str(skill.get("sourceDir", "")) / "SKILL.md"
            if not source.is_file():
                failures.append(f"Skill 真源缺失：{skill.get('id')}")
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"无法读取系统注册表：{exc}")
    if os.name != "nt":
        failures.append("本发布包当前仅支持 Windows；macOS 版本尚未发布。")
    else:
        shell = Path(os.environ.get("SystemRoot", r"C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if not shell.is_file():
            failures.append("未找到 Windows PowerShell，无法启动工作台。")
    node_major = node_major_version()
    if node_major is None:
        failures.append("未找到 Node.js 20 LTS。请安装 Node.js 20 LTS 后重新运行 python run.py install --dev。")
    elif node_major < 20:
        failures.append(f"需要 Node.js 20 或更高版本，当前为 Node.js {node_major}。请升级到 Node.js 20 LTS 后重新运行 python run.py install --dev。")
    if not (CODEX_CLI_ROOT / "package-lock.json").is_file():
        failures.append("缺少锁定的 Codex CLI package-lock.json。")
    if not LOCAL_CODEX_CLI.is_file():
        failures.append("锁定的 Codex CLI 尚未安装。请运行 python run.py install --dev（会执行 npm ci）。")
    print(json.dumps({"status": "passed" if not failures else "failed", "python": sys.version.split()[0], "node": node_major, "root": str(ROOT), "failures": failures}, ensure_ascii=False))
    return 0 if not failures else 1


def sync_platform(target: str, apply: bool) -> int:
    command = ["--target", target]
    if apply:
        command.append("--apply")
    result = run_python(ROOT / "tools" / "platform" / "sync_skills.py", *command)
    if result == 0 and apply:
        return run_python(ROOT / "tools" / "platform" / "render_skill_catalog.py", "--write")
    return result


def workbench(mode: str) -> int:
    if os.name != "nt":
        print(json.dumps({"status": "unsupported", "message": "工作台当前仅支持 Windows；macOS 版本尚未发布。"}, ensure_ascii=False))
        return 1
    shell = str(Path(os.environ.get("SystemRoot", r"C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    scripts = {"start": ROOT / "03_工作台" / "start-workbench.ps1", "status": ROOT / "03_工作台" / "workbench-control.ps1", "stop": ROOT / "03_工作台" / "workbench-control.ps1", "install": ROOT / "03_工作台" / "install-workbench-watchdog.ps1", "uninstall": ROOT / "03_工作台" / "install-workbench-watchdog.ps1"}
    arguments = [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts[mode])]
    if mode in {"status", "stop"}:
        arguments.extend(["-Mode", mode])
    elif mode == "uninstall":
        arguments.append("-Uninstall")
    result = run_command(arguments)
    if result == 0 and mode == "start":
        subprocess.run([shell, "-NoProfile", "-Command", "Start-Process 'http://127.0.0.1:8766'"], check=False)
    return result


def install(dev: bool, install_workbench: bool) -> int:
    result = run_command([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    if result:
        return result
    if dev:
        result = run_command([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"])
        if result:
            return result
    node_major = node_major_version()
    if node_major is None or node_major < 20:
        print("需要 Node.js 20 LTS 或更高版本；请安装后重新执行 python run.py install --dev。", file=sys.stderr)
        return 1
    npm = shutil.which("npm")
    if not npm:
        print("未找到 npm；请重新安装 Node.js 20 LTS 后重新执行 python run.py install --dev。", file=sys.stderr)
        return 1
    if not (CODEX_CLI_ROOT / "package-lock.json").is_file():
        print("缺少 Codex CLI 锁文件：03_工作台/vendor/codex-cli/package-lock.json", file=sys.stderr)
        return 1
    result = run_in(CODEX_CLI_ROOT, [npm, "ci", "--no-audit", "--no-fund"])
    if result:
        print("Codex CLI 依赖安装失败。请检查网络后在 03_工作台/vendor/codex-cli 运行 npm ci --no-audit --no-fund。", file=sys.stderr)
        return result
    result = sync_platform("codex", True)
    return workbench("install") if result == 0 and install_workbench else (result or doctor())


def test_all() -> int:
    for command in ([sys.executable, "-m", "unittest", "discover", "-s", "tools/tests", "-p", "test_*.py"], [sys.executable, "-m", "unittest", "discover", "-s", "03_工作台/tests", "-p", "test_*.py"]):
        code = run_command(command)
        if code:
            return code
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="AI爆款内容工厂统一入口")
    sub = parser.add_subparsers(dest="command", required=True)
    structure = sub.add_parser("copy-structure")
    for name in ("topic", "benchmark-id", "output"):
        structure.add_argument(f"--{name}", required=True)
    copy = sub.add_parser("final-copy-plan")
    for name in ("structure-four", "output"):
        copy.add_argument(f"--{name}", required=True)
    review = sub.add_parser("prepare-copy-semantic-review")
    review.add_argument("--kind", choices=["copy-structure", "final-copy"], required=True)
    review.add_argument("--plan", required=True); review.add_argument("--candidate", required=True); review.add_argument("--output", required=True)
    refresh = sub.add_parser("refresh-data-center"); refresh.add_argument("--reason", default="manual-refresh")
    video_search = sub.add_parser("search-video-modules")
    video_search.add_argument("query", nargs="?", default=""); video_search.add_argument("--module-type", choices=["pain", "viewpoint", "misconception"]); video_search.add_argument("--classification", default=""); video_search.add_argument("--audience", default=""); video_search.add_argument("--scene", default=""); video_search.add_argument("--limit", type=int, default=20); video_search.add_argument("--index")
    for name in ("validate", "doctor", "test", "audit-baseline"):
        sub.add_parser(name)
    sync = sub.add_parser("sync-platform"); sync.add_argument("--target", choices=["codex", "workbuddy"], required=True); sync.add_argument("--apply", action="store_true")
    install_parser = sub.add_parser("install"); install_parser.add_argument("--dev", action="store_true"); install_parser.add_argument("--workbench-service", action="store_true")
    workbench_parser = sub.add_parser("workbench"); workbench_parser.add_argument("mode", choices=["start", "status", "stop", "install", "uninstall"], default="start", nargs="?")
    release = sub.add_parser("release-check"); release.add_argument("--output")
    package = sub.add_parser("package", help="构建单一发布包")
    package.add_argument("target", choices=["github", "skillhub", "workbuddy-expert"])
    package.add_argument("--output")
    publish = sub.add_parser("publish", help="发布 GitHub 免费版和飞书会员版")
    publish.add_argument("--version", required=True)
    publish.add_argument("--branch", default="main")
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--preflight", action="store_true", help="只读检查 GitHub 免费投影与飞书会员 ZIP")
    publish.add_argument("--skip-gates", action="store_true")
    publish.add_argument("--state")
    args = parser.parse_args()
    if args.command == "copy-structure": return run_python(ROOT / "10_Skills武器库" / "文案结构生成 Skill" / "scripts" / "prepare_structure_task.py", "--topic", args.topic, "--benchmark-id", args.benchmark_id, "--output", args.output)
    if args.command == "final-copy-plan": return run_python(ROOT / "10_Skills武器库" / "正文成稿生成 Skill" / "scripts" / "prepare_copy_task.py", "--structure-four", args.structure_four, "--output", args.output)
    if args.command == "prepare-copy-semantic-review": return run_python(ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "independent_copy_semantic_review.py", "--kind", args.kind, "--plan", args.plan, "--candidate", args.candidate, "--target", args.output)
    if args.command == "refresh-data-center": return run_python(ROOT / "workflow" / "data_center.py", "--reason", args.reason)
    if args.command == "search-video-modules":
        command = [args.query, "--classification", args.classification, "--audience", args.audience, "--scene", args.scene, "--limit", str(args.limit)]
        if args.module_type: command.extend(["--module-type", args.module_type])
        if args.index: command.extend(["--index", args.index])
        return run_python(ROOT / "tools" / "query" / "search_video_modules.py", *command)
    if args.command == "validate": return run_python(ROOT / "tools" / "quality" / "validate_system.py", "--root", str(ROOT))
    if args.command == "doctor": return doctor()
    if args.command == "test": return test_all()
    if args.command == "sync-platform": return sync_platform(args.target, args.apply)
    if args.command == "install": return install(args.dev, args.workbench_service)
    if args.command == "workbench": return workbench(args.mode)
    if args.command == "audit-baseline": return run_python(ROOT / "tools" / "quality" / "audit_github_baseline.py")
    if args.command == "release-check": return run_command([sys.executable, "tools/quality/release_check.py", *( ["--output", args.output] if args.output else [])])
    if args.command == "package":
        command = ["tools/release/build_release.py", args.target]
        if args.output: command.extend(["--output", args.output])
        return run_command([sys.executable, *command])
    if args.command == "publish":
        command = ["tools/release/publish_release.py", "--version", args.version, "--branch", args.branch]
        if args.dry_run: command.append("--dry-run")
        if args.preflight: command.append("--preflight")
        if args.skip_gates: command.append("--skip-gates")
        if args.state: command.extend(["--state", args.state])
        return run_command([sys.executable, *command])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
