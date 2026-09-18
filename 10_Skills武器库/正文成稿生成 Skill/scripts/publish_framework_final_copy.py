#!/usr/bin/env python3
"""Publish a reviewed final-copy-v5 artifact with hash-bound release evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.topic_structure_releases import append_final_copy_binding
from workflow.case_output_directories import assert_case_output_path
from render_framework_copy import render, render_annotations


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label}不可读取：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label}必须是 JSON 对象：{path}")
    return payload


def validate_bundle(*, plan_path: Path, candidate_path: Path, preview_path: Path,
                    annotations_path: Path, audit_receipt_path: Path,
                    formal_path: Path) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Reject anything that is not exactly the reviewed V5 release bundle."""
    plan = load_json(plan_path, "正文计划")
    candidate = load_json(candidate_path, "正文候选")
    receipt = load_json(audit_receipt_path, "小审回执")
    subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
    if (plan.get("schema"), candidate.get("schema")) != ("final-copy-plan-v5", "final-copy-v5"):
        raise ValueError("发布仅接受 final-copy-plan-v5/final-copy-v5")
    if candidate.get("plan_sha256") != digest(plan_path):
        raise ValueError("正文候选未绑定当前正文计划")
    if receipt.get("schema") != "audit-receipt-v3" or receipt.get("artifactType") != candidate.get("schema") or receipt.get("status") != "approved":
        raise ValueError("正式发布需要当前正文版本的 approved 小审回执")
    expected_hashes = {"planSha256": digest(plan_path), "candidateSha256": digest(candidate_path), "previewSha256": digest(preview_path), "annotationsSha256": digest(annotations_path)}
    if any(subject.get(key) != value for key, value in expected_hashes.items()):
        raise ValueError("小审回执未完整绑定当前计划、候选、预览或段落注释")
    expected = render(plan, candidate)
    if not preview_path.is_file() or preview_path.read_text(encoding="utf-8") != expected:
        raise ValueError("正文预览不是当前 V5 计划与候选的精确渲染结果")
    if not annotations_path.is_file() or annotations_path.read_text(encoding="utf-8") != render_annotations(plan, candidate):
        raise ValueError("段落注释不是当前 V5 计划与候选的精确渲染结果")
    if formal_path.exists() and formal_path.read_text(encoding="utf-8") != expected:
        raise ValueError("既有正式正文与已审核预览不一致；拒绝补发发布回执")
    return plan, candidate, expected


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".pending")
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publication_payload(*, formal_path: Path, preview_path: Path, candidate_path: Path, audit_receipt_path: Path) -> dict[str, str]:
    formal = formal_path.read_text(encoding="utf-8")
    return {"schema": "final-copy-publication-v1", "status": "published", "formalPath": str(formal_path.resolve()), "formalSha256": digest(formal_path), "renderedBodySha256": hashlib.sha256(formal.encode("utf-8")).hexdigest(), "previewSha256": digest(preview_path), "candidateSha256": digest(candidate_path), "auditReceipt": str(audit_receipt_path.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description="受控发布或补发 final-copy-v5 正文")
    for name, help_text in (("plan", ""), ("candidate", ""), ("preview", ""), ("annotations", ""), ("audit-receipt", ""), ("formal", "新建正式正文，或待补发的既有正式正文"), ("publication-receipt", "")):
        parser.add_argument(f"--{name}", type=Path, required=True, help=help_text)
    args = parser.parse_args()
    plan, candidate, expected = validate_bundle(plan_path=args.plan, candidate_path=args.candidate, preview_path=args.preview, annotations_path=args.annotations, audit_receipt_path=args.audit_receipt, formal_path=args.formal)
    assert_case_output_path(str(plan.get("benchmark_case_id") or ""), "final_copy", args.formal, create=True)
    created_formal = not args.formal.exists()
    if created_formal:
        atomic_write(args.formal, expected)
    try:
        append_final_copy_binding(topic=str(plan.get("topic") or ""), benchmark_case_id=str(plan.get("benchmark_case_id") or ""), output_path=args.formal, candidate_path=args.candidate, audit_receipt_path=args.audit_receipt)
    except Exception:
        if created_formal:
            args.formal.unlink(missing_ok=True)
        raise
    atomic_write(args.publication_receipt, json.dumps(publication_payload(formal_path=args.formal, preview_path=args.preview, candidate_path=args.candidate, audit_receipt_path=args.audit_receipt), ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "published", "formal": str(args.formal.resolve()), "publicationReceipt": str(args.publication_receipt.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
