#!/usr/bin/env python3
"""Prepare a copy-structure handoff from one selected v4.2 topic-table row."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.topic_structure_releases import handoff_binding, resolve_selected_topic
from prepare_structure_task import build_handoff, load_topic_analysis
from structure_v13 import build_handoff_v13, load_topic_analysis_v13


def main() -> int:
    parser = argparse.ArgumentParser(description="从选题表中锁定选题和已审核对标复刻拆解编号，准备文案结构 handoff")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--benchmark-id", help="该选题行绑定多个对标编号时，显式锁定其中一个")
    parser.add_argument("--topic-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-v12", action="store_true", help="仅用于历史兼容；新任务默认生成 V13")
    args = parser.parse_args()
    row = resolve_selected_topic(args.topic, benchmark_case_id=args.benchmark_id)
    if args.legacy_v12:
        analysis = load_topic_analysis(args.topic_analysis)
        payload = build_handoff(topic=str(row["选题"]).strip(), benchmark_id=str(row["selected_benchmark_case_id"]), topic_analysis=analysis, topic_analysis_path=args.topic_analysis, topic_table_binding=handoff_binding(row))
    else:
        analysis = load_topic_analysis_v13(args.topic_analysis)
        payload = build_handoff_v13(topic=str(row["选题"]).strip(), benchmark_id=str(row["selected_benchmark_case_id"]), topic_analysis=analysis, topic_analysis_path=args.topic_analysis, topic_table_binding=handoff_binding(row))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "prepared", "topic": payload["topic"], "benchmark": payload["benchmark_case_id"], "topicTable": payload["topic_table_binding"]["topic_table_relative_path"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
