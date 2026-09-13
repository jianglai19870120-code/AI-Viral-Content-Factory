#!/usr/bin/env python3
"""统一测试入口：跳过测试同样视为验收失败。"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    returncode = 0
    with tempfile.TemporaryDirectory(prefix="ai-traffic-factory-tests-") as temporary:
        runtime = Path(temporary) / "runtime"
        workbench_runtime = Path(temporary) / "workbench"
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        # Tests must never read or write state owned by a desktop watchdog service.
        env["AI_TRAFFIC_RUNTIME_ROOT"] = str(runtime)
        env["AI_VIRAL_WORKBENCH_RUNTIME"] = str(workbench_runtime)
        for suite in ("tools/tests", "03_工作台/tests"):
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", suite, "-p", "test*.py", "-v"],
                cwd=root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
            )
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            if "skipped=" in result.stderr or "skipped=" in result.stdout:
                print(f"[FAIL] {suite} 验收测试不允许存在跳过项。", file=sys.stderr)
                returncode = 1
            returncode = max(returncode, result.returncode)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
