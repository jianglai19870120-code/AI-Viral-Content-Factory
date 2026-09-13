#!/usr/bin/env python3
"""Create a human-review template for an independent V3 final-copy audit."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from final_copy_semantic_quality import REQUIRED_CHECK_IDS


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
    rows = candidate.get("framework_mappings") if isinstance(candidate.get("framework_mappings"), list) else []
    payload = {
        "schema": "independent-framework-final-copy-semantic-review-v3",
        "status": "needs-review",
        "reviewer": {"reviewer_id": "", "independence_attestation": ""},
        "plan_path": str(args.plan.resolve()),
        "candidate_path": str(args.candidate.resolve()),
        "annotations_path": str(args.annotations.resolve()),
        "plan_sha256": digest(args.plan),
        "candidate_sha256": digest(args.candidate),
        "annotations_sha256": digest(args.annotations),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checks": [
            {"id": key, "status": "needs-review", "summary": "", "evidence": []}
            for key in REQUIRED_CHECK_IDS
        ],
        "item_reviews": [
            {"id": str(row.get("framework_id") or ""), "verdict": "needs-review", "reasoning": "", "evidence": []}
            for row in rows if isinstance(row, dict)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "needs-review", "review": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
