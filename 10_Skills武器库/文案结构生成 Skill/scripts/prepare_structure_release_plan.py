#!/usr/bin/env python3
"""Create an auditable runtime release plan; it never writes a formal output."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.topic_structure_releases import handoff_binding, resolve_selected_topic
from render_structure_markdown import CST, release_directory, release_path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="为选题表直连文案结构生成小审发布包计划")
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    binding = handoff.get("topic_table_binding")
    allowed = {("copy-structure-handoff-v16", "copy-structure-v16")}
    if (handoff.get("schema"), candidate.get("schema")) not in allowed or not isinstance(binding, dict):
        raise SystemExit("发布计划只接受绑定选题表的同版本 V11/V12/V13 handoff 与候选")
    row = resolve_selected_topic(str(handoff.get("topic") or ""), benchmark_case_id=str(handoff.get("benchmark_case_id") or ""))
    if handoff_binding(row) != binding or candidate.get("topic_table_binding") != binding:
        raise SystemExit("选题表目标行或候选绑定已漂移")
    if candidate.get("topic") != handoff.get("topic") or candidate.get("benchmark_case_id") != handoff.get("benchmark_case_id"):
        raise SystemExit("候选未锁定 handoff 的选题或对标编号")
    try:
        target = release_path(candidate, release_directory(candidate), datetime.now(CST))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    plan = {
        "schema": "copy-structure-release-plan-v1",
        "topic_table_binding": binding,
        "topic": handoff["topic"],
        "benchmark_case_id": handoff["benchmark_case_id"],
        "candidate_path": str(args.candidate.resolve()),
        "candidate_sha256": digest(args.candidate),
        "handoff_path": str(args.handoff.resolve()),
        "handoff_sha256": digest(args.handoff),
        "planned_output_path": str(target.resolve()),
        "planned_output_name": target.name,
        "requested_status": "已生成结构",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "planned", "output": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
