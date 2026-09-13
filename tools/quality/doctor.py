#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import locale
import subprocess
import sys
from pathlib import Path


REQUIRED_MODULES = {"openpyxl": "openpyxl", "requests": "requests", "Pillow": "PIL", "jsonschema": "jsonschema"}


def main() -> int:
    parser = argparse.ArgumentParser(description="AI爆款内容工厂环境诊断")
    parser.add_argument("--root")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    checks: list[dict[str, object]] = []

    version_ok = (3, 11) <= sys.version_info[:2] < (3, 14)
    checks.append({"name": "python-version", "ok": version_ok, "detail": sys.version.split()[0]})
    checks.append({"name": "stdout-utf8", "ok": (sys.stdout.encoding or "").lower().replace("-", "") == "utf8", "detail": sys.stdout.encoding})
    checks.append({"name": "locale", "ok": True, "detail": locale.getpreferredencoding(False)})
    for package, module in REQUIRED_MODULES.items():
        checks.append({"name": f"dependency:{package}", "ok": importlib.util.find_spec(module) is not None, "detail": module})
    for relative in ("00_系统说明/system-registry.json", "schemas/handoff-v2.schema.json", "workflow/handoff.py", "tools/quality/validate_system.py"):
        checks.append({"name": f"path:{relative}", "ok": (root / relative).is_file(), "detail": relative})
    git = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    checks.append({"name": "git-repository", "ok": git.returncode == 0, "detail": (git.stdout or git.stderr).strip()})
    result = {"schema": "ai-traffic-doctor-v1", "ok": all(bool(item["ok"]) for item in checks), "checks": checks}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
