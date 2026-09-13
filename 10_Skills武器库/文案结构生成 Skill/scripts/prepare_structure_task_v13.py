#!/usr/bin/env python3
"""Prepare a V13 copy-structure handoff without a topic-table binding."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from structure_v13 import build_handoff_v13, load_topic_analysis_v13


def main() -> int:
    parser = argparse.ArgumentParser(description="准备不经选题表的 V13 文案结构 handoff")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--topic-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build_handoff_v13(
        topic=args.topic.strip(), benchmark_id=args.benchmark_id.strip(),
        topic_analysis=load_topic_analysis_v13(args.topic_analysis), topic_analysis_path=args.topic_analysis,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "prepared", "schema": payload["schema"], "topic": payload["topic"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
