#!/usr/bin/env python3
"""Mechanical validation entry point for the single V19 structure chain."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from structure_v19 import validate_v19

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--handoff",type=Path,required=True);parser.add_argument("--candidate",type=Path,required=True);args=parser.parse_args()
    handoff=json.loads(args.handoff.read_text(encoding="utf-8"));candidate=json.loads(args.candidate.read_text(encoding="utf-8"))
    errors=validate_v19(handoff,candidate)
    if errors: print("FAIL\n"+"\n".join("- "+item for item in errors));return 1
    print(f"PASS V19: {len(handoff.get('big_frameworks',[]))} 个完整大框架逐卡锁定原要点、V3 合同和结构三来源证据");return 0
if __name__=="__main__":raise SystemExit(main())
