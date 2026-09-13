#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    registry = json.loads((root / "00_系统说明/system-registry.json").read_text(encoding="utf-8"))
    handoffs = []
    for path in sorted((root / ".runtime/handoffs").glob("*.json")):
        handoffs.append(json.loads(path.read_text(encoding="utf-8")))
    result = {
        "system": registry["system"]["id"],
        "version": registry["system"]["version"],
        "release_status": registry["release"]["status"],
        "agents": {state: sum(a["status"] == state for a in registry["agents"]) for state in ("active", "reserved")},
        "skills": len(registry["skills"]),
        "tasks": {state: sum(t.get("status") == state for t in handoffs) for state in ("needs-agent", "needs-user", "completed", "rejected", "blocked")},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
