#!/usr/bin/env python3
"""Create the V3-contract review template for an independent V5 final-copy audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

from final_copy_semantic_quality import required_check_ids
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from workflow.writing_contract import guidance_snapshot, rules_for, validate_guidance_snapshot


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="创建完整 FNN 正文独立语义审稿模板")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    rows = candidate.get("framework_mappings") if isinstance(candidate.get("framework_mappings"), list) else []
    if candidate.get("schema") != "final-copy-v5" or plan.get("schema") != "final-copy-plan-v5":
        raise SystemExit("独立正文审稿只接受 final-copy-plan-v5/final-copy-v5")
    binding=plan.get("writing_contract") if isinstance(plan.get("writing_contract"),dict) else {}
    validate_guidance_snapshot(plan.get("writing_contract_guidance_snapshot"),binding,"final-copy")
    validate_guidance_snapshot(candidate.get("writing_contract_guidance_snapshot"),binding,"final-copy")
    snapshot=guidance_snapshot(binding,"final-copy"); by_id={rule["id"]:rule for rule in snapshot["rules"]}
    payload = {
        "schema": "independent-framework-final-copy-semantic-review-v5",
        "status": "needs-review",
        "reviewer": {"reviewer_id": "", "independence_attestation": ""},
        "plan_path": str(args.plan.resolve()),
        "candidate_path": str(args.candidate.resolve()),
        "annotations_path": str(args.annotations.resolve()),
        "plan_sha256": digest(args.plan),
        "candidate_sha256": digest(args.candidate),
        "annotations_sha256": digest(args.annotations),
        "writing_contract": binding,
        "writing_contract_guidance_snapshot": snapshot,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checks": [
            {"id": key, "source_anchors":by_id[key]["source_anchors"], "rule_text":by_id[key]["directive"], "original_guidance":by_id[key]["original_guidance"], "status": "needs-review", "summary": "", "evidence": [{"item_id":"","candidate_quote":"","reasoning":""}]}
            for key in required_check_ids(plan.get("writing_contract") if isinstance(plan.get("writing_contract"), dict) else None)
        ],
        "item_reviews": [
            {"id": str(row.get("framework_id") or ""), "verdict": "needs-review", "reasoning": "", "candidate_quote": "", "specificness_evidence": "", "evidence": []}
            for row in rows if isinstance(row, dict)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "needs-review", "review": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
