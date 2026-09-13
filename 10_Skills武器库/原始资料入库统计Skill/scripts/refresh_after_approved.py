#!/usr/bin/env python3
"""Refresh derived inventories only after an approved formal release."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workflow.input_inventory import TYPES
from workflow.inventory_refresh import refresh_after_approved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", action="append", choices=tuple(TYPES), default=[])
    parser.add_argument("--benchmark-cases", action="store_true")
    parser.add_argument("--producer", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    if not args.type and not args.benchmark_cases:
        raise SystemExit("至少指定一个 --type 或 --benchmark-cases")
    print(json.dumps(refresh_after_approved(project_root=ROOT, source_types=args.type, include_benchmarks=args.benchmark_cases, producer=args.producer, reason=args.reason), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
