#!/usr/bin/env python3
"""Run the reproducible v2 release gate without using checkout runtime state."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def run_check(root: Path, env: dict[str, str], name: str, command: list[str]) -> dict:
    result = subprocess.run(command, cwd=root, text=True, encoding="utf-8", errors="replace", env=env, capture_output=True)
    print(f"\n=== {name} ===")
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return {"name": name, "command": command, "returncode": result.returncode, "passed": result.returncode == 0}


def package_check(root: Path, env: dict[str, str], target: str, destination: Path) -> dict:
    result = run_check(
        root,
        env,
        f"package-{target}",
        [sys.executable, "tools/release/build_release.py", target, "--root", str(root), "--output", str(destination)],
    )
    archive = destination.with_suffix(".zip")
    checksum = archive.with_suffix(".zip.sha256")
    required = [destination / "release-checksums.json", archive, checksum]
    if target == "github":
        required.extend([destination / "03_工作台" / "server.py", destination / "README.md"])
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        result["passed"] = False
        result["missing"] = missing
    return result


def execute(root: Path, output: Path) -> int:
    if output.exists():
        raise RuntimeError(f"发布验收输出目录已存在，拒绝覆盖：{output}")
    output.mkdir(parents=True)
    runtime = output / "runtime"
    env = os.environ.copy()
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "AI_TRAFFIC_RUNTIME_ROOT": str(runtime / "workflow"),
        "AI_VIRAL_WORKBENCH_RUNTIME": str(runtime / "workbench"),
    })
    checks = [
        run_check(root, env, "doctor", [sys.executable, "run.py", "doctor"]),
        run_check(root, env, "validate", [sys.executable, "run.py", "validate"]),
        run_check(root, env, "tests", [sys.executable, "run.py", "test"]),
        run_check(root, env, "sync-platform-codex", [sys.executable, "run.py", "sync-platform", "--target", "codex"]),
        run_check(root, env, "audit-baseline", [sys.executable, "run.py", "audit-baseline"]),
    ]
    for target in ("github", "skillhub", "workbuddy-expert"):
        checks.append(package_check(root, env, target, output / target))
    result = {
        "schema": "ai-traffic-release-check-v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "checks": checks,
        "output": str(output),
    }
    (output / "release-check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="执行 v2 发布前完整门禁")
    parser.add_argument("--root")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    if args.output:
        return execute(root, Path(args.output).resolve())
    with tempfile.TemporaryDirectory(prefix="ai-traffic-release-check-") as temporary:
        return execute(root, Path(temporary) / "release")


if __name__ == "__main__":
    raise SystemExit(main())
