#!/usr/bin/env python3
"""Validate a V13 handoff/candidate pair directly for local debugging."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from structure_v13 import validate_v13


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    errors = validate_v13(json.loads(args.handoff.read_text(encoding="utf-8")), json.loads(args.candidate.read_text(encoding="utf-8")))
    if errors:
        print("FAIL\n" + "\n".join(f"- {item}" for item in errors))
        return 1
    print("PASS V13")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
