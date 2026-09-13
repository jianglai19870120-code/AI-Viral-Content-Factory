"""小审：视频痛点卡 v2 分类发现门禁（只审不改）。"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN = ("、", "/", "-", "_", " ")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根必须为对象：{path}")
    return value


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def audit(discovery_path: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    discovery = read(discovery_path)
    issues: list[str] = []
    if discovery.get("schema") != "video-pain-taxonomy-discovery-v2" or discovery.get("status") != "awaiting_audit":
        issues.append("分类发现清单 schema 或状态不正确")
    taxonomy_path = Path(str(discovery.get("taxonomy_path") or ""))
    if not taxonomy_path.is_file() or sha(taxonomy_path) != discovery.get("taxonomy_sha256"):
        issues.append("冻结分类注册表不存在或哈希漂移")
        taxonomy: dict[str, Any] = {}
    else:
        taxonomy = read(taxonomy_path)
    if taxonomy.get("schema") != "video-pain-taxonomy-v2" or taxonomy.get("status") != "frozen":
        issues.append("分类注册表不是已冻结的 v2")
    seen_secondary: set[str] = set()
    taxonomy_pairs: set[tuple[str, str]] = set()
    for primary in taxonomy.get("primary_categories", []) if isinstance(taxonomy.get("primary_categories"), list) else []:
        name = str(primary.get("name") or "").strip()
        boundary = str(primary.get("boundary") or "").strip()
        children = primary.get("secondary_keywords") if isinstance(primary.get("secondary_keywords"), list) else []
        if not name or not boundary or any(token in name for token in FORBIDDEN) or len(children) < 2:
            issues.append(f"一级分类不合规：{name or '空'}")
        for child in children:
            secondary = str(child.get("name") or "").strip()
            if not secondary or not str(child.get("boundary") or "").strip() or any(token in secondary for token in FORBIDDEN):
                issues.append(f"二级分类不是单一问题词：{name}/{secondary or '空'}")
            if secondary in seen_secondary:
                issues.append(f"二级词不能同时归属多个一级：{secondary}")
            seen_secondary.add(secondary)
            taxonomy_pairs.add((name, secondary))
    manifest = discovery.get("source_manifest") if isinstance(discovery.get("source_manifest"), list) else []
    coverage = discovery.get("coverage") if isinstance(discovery.get("coverage"), list) else []
    source_ids = {str(row.get("source_id") or "") for row in manifest if isinstance(row, dict)}
    coverage_ids = {str(row.get("source_id") or "") for row in coverage if isinstance(row, dict)}
    if len(manifest) != discovery.get("expected_count") or not source_ids or source_ids != coverage_ids or len(coverage_ids) != len(coverage):
        issues.append("分类发现未对全部来源无漏重覆盖")
    evidence = discovery.get("classification_evidence") if isinstance(discovery.get("classification_evidence"), list) else []
    pain_ids = {str(row.get("source_id") or "") for row in coverage if isinstance(row, dict) and row.get("outcome") == "pain"}
    evidence_ids = {str(row.get("source_id") or "") for row in evidence if isinstance(row, dict)}
    if pain_ids != evidence_ids:
        issues.append("标为 pain 的来源缺少或多出分类依据")
    for row in evidence:
        if not isinstance(row, dict):
            issues.append("分类原文依据含非对象")
            continue
        pair = (str(row.get("primary_category") or ""), str(row.get("secondary_keyword") or ""))
        if pair not in taxonomy_pairs:
            issues.append(f"分类依据未命中冻结注册表：{pair[0]}/{pair[1]}")
    checks = [{"id": "taxonomy-v2-discovery-and-freeze", "status": "passed" if not issues else "failed", "detail": "；".join(issues) or "547 篇覆盖、一级边界、二级单词与冻结注册表均通过"}]
    return checks, {"taxonomy_discovery": rel(discovery_path), "taxonomy": rel(taxonomy_path) if taxonomy_path else ""}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discovery", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--task-id", default="")
    args = parser.parse_args()
    discovery = Path(args.discovery).resolve(); checks, subject = audit(discovery)
    status = "approved" if all(row["status"] == "passed" for row in checks) else "rejected"
    receipt = {"schema": "audit-receipt-v3", "status": status, "taskId": args.task_id or hashlib.sha256(rel(discovery).encode()).hexdigest()[:16], "artifactType": "video-pain-taxonomy-v2", "subject": {**subject, "manifest": rel(discovery), "candidateSha256": sha(discovery)}, "checks": checks, "required_check_ids": [row["id"] for row in checks], "audited_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
    target = Path(args.receipt).resolve(); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "checks": checks}, ensure_ascii=False))
    return 0 if status == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
