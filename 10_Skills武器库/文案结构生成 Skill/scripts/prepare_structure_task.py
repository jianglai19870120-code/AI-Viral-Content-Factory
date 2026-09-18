#!/usr/bin/env python3
"""Create the only supported structure handoff: V19 bound to contract V3."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from structure_v19 import build_handoff_v19
from workflow.topic_structure_releases import handoff_binding, resolve_selected_topic

def main() -> int:
    parser=argparse.ArgumentParser(description="创建 V19 文案结构交接包")
    parser.add_argument("--topic",required=True);parser.add_argument("--benchmark-id",required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    try:
        selected=resolve_selected_topic(args.topic,benchmark_case_id=args.benchmark_id)
        payload=build_handoff_v19(topic=args.topic,benchmark_id=args.benchmark_id,topic_table_binding=handoff_binding(selected))
    except ValueError as exc: raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"prepared","schema":payload["schema"],"frameworkBlocks":len(payload["big_frameworks"]),"output":str(args.output)},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
