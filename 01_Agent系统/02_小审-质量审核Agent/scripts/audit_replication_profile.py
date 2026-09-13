#!/usr/bin/env python3
"""Write a profile-specific 小审 receipt after independently checking its GHX binding."""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from workflow.universal_copy_contract import digest, parse_breakdown

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--profile", type=Path, required=True); parser.add_argument("--benchmark", type=Path, required=True); parser.add_argument("--receipt", type=Path, required=True); parser.add_argument("--review-note", required=True, help="小审独立比对画像与 GHX 后的人工结论"); args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8")); parsed = parse_breakdown(args.benchmark); rows = {str(row.get("unit_no") or ""):row for row in profile.get("units", []) if isinstance(row, dict)}; errors=[]
    if profile.get("schema") != "benchmark-replication-profile-v2": errors.append("画像 schema 错误")
    if profile.get("benchmark_sha256") != digest(args.benchmark): errors.append("画像未绑定当前 GHX 哈希")
    if len(rows) != len(parsed["units"]): errors.append("画像未完整覆盖 GHX 复刻单元")
    for unit in parsed["units"]:
        row=rows.get(str(unit["unit_no"]) or "")
        if not row or row.get("source_text_sha256") != unit.get("source_text_sha256") or row.get("required_punctuation") != unit.get("source_punctuation") or row.get("word_range") != unit.get("word_range") or not row.get("sentence_shape") or not row.get("clause_roles"):
            errors.append(f"复刻单元 {unit['unit_no']} 的来源绑定或句式骨架不完整")
    if len(args.review_note.strip()) < 16: errors.append("小审复刻画像人工复核结论不足")
    receipt={"schema":"audit-receipt-v3","artifactType":"benchmark-replication-profile-v1","status":"approved" if not errors else "rejected","auditor":"xiaoshen","generatedAt":datetime.now(timezone.utc).isoformat(),"subject":{"profile":str(args.profile.resolve()),"benchmark":str(args.benchmark.resolve()),"profileSha256":digest(args.profile),"benchmarkSha256":digest(args.benchmark)},"independentReview":args.review_note,"issues":errors}
    args.receipt.parent.mkdir(parents=True, exist_ok=True); args.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n"); print(json.dumps(receipt,ensure_ascii=False)); return 0 if not errors else 1
if __name__ == "__main__": raise SystemExit(main())
