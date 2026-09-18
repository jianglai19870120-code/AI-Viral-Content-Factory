#!/usr/bin/env python3
"""Bind authored structure content to the only supported V19 handoff."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from structure_v19 import build_candidate_v19

def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--handoff",type=Path,required=True);parser.add_argument("--authoring",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    handoff=json.loads(args.handoff.read_text(encoding="utf-8"))
    if handoff.get("schema")!="copy-structure-handoff-v19":raise SystemExit("新结构只接受 copy-structure-handoff-v19")
    build_candidate_v19(args.handoff,args.authoring,args.output);print(json.dumps({"status":"built","schema":"copy-structure-v19"},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
