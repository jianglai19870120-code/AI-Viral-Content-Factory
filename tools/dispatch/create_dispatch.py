#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from workflow.common import create_dispatch_record


def main() -> int:
    parser = argparse.ArgumentParser(description="创建小姜正式调度记录")
    parser.add_argument("--task-name", required=True)
    parser.add_argument("--task-type", required=True)
    parser.add_argument("--target-agent", required=True)
    parser.add_argument("--input-source", required=True)
    parser.add_argument("--requires-audit", choices=["是", "否"], default="是")
    args = parser.parse_args()
    record = create_dispatch_record(args.task_name, args.task_type, args.target_agent, args.input_source, args.requires_audit)
    print(record.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
