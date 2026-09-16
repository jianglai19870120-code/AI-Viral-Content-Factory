"""Candidate-scoped approvals for dictionary-external big-framework names."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "independent-benchmark-big-framework-temporary-naming-review-v1"
FORMAL_MODULES = {"观点", "痛点", "误区", "解决方案", "案例", "推荐理由"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty(value: object) -> bool:
    return bool(str(value or "").strip())


def load_approved_temporary_names(
    path: Path | None, *, source: Path, candidate: Path, dictionary_sha256: str,
) -> dict[str, dict[str, Any]]:
    """Return FNN-scoped metadata, or reject stale/incomplete temporary approval.

    A temporary approval is intentionally not a dictionary fallback: its hashes
    bind it to one source and one three-column candidate only.
    """
    if path is None:
        return {}
    review_path = path.resolve()
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"临时大框架命名审核不可读取：{exc}") from exc
    expected = {
        "source_sha256": digest(source.resolve()),
        "candidate_sha256": digest(candidate.resolve()),
        "naming_dictionary_sha256": dictionary_sha256,
    }
    if review.get("schema") != SCHEMA or review.get("status") != "completed":
        raise ValueError("临时大框架命名审核未完成或 schema 不正确")
    if review.get("temporary_scope") != "this-candidate-only":
        raise ValueError("临时大框架命名审核必须限定为本次候选")
    if any(review.get(key) != value for key, value in expected.items()):
        raise ValueError("临时大框架命名审核与当前源稿、候选或命名词典不一致")
    reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), dict) else {}
    if reviewer.get("role") != "xiaoshen-audit" or not _nonempty(reviewer.get("reviewer_id")) or not _nonempty(reviewer.get("independence_attestation")):
        raise ValueError("临时大框架命名审核身份或独立性声明不完整")
    checks = {str(item.get("id") or ""): item for item in review.get("checks", []) if isinstance(item, dict)}
    expected_checks = {"dictionary-external-name", "definition-and-match-features", "candidate-only-scope"}
    if set(checks) != expected_checks or any(item.get("status") != "passed" or not _nonempty(item.get("summary")) or not item.get("evidence") for item in checks.values()):
        raise ValueError("临时大框架命名审核检查项不完整")
    items = review.get("temporary_name_reviews")
    if not isinstance(items, list) or not items:
        raise ValueError("临时大框架命名审核缺少逐 FNN 结论")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("临时大框架命名审核条目非法")
        block_id, label = str(item.get("block_id") or ""), str(item.get("suggested_name") or "").strip()
        role, module = item.get("role"), item.get("processing_module")
        if not block_id or not label or block_id in result:
            raise ValueError("临时大框架命名审核的 FNN 或名称不唯一")
        if item.get("verdict") != "passed" or not _nonempty(item.get("definition")) or not _nonempty(item.get("reasoning")):
            raise ValueError("临时大框架命名审核未逐项通过或缺少定义、理由")
        features = item.get("match_features")
        if not isinstance(features, list) or not any(_nonempty(value) for value in features):
            raise ValueError("临时大框架命名审核缺少原文匹配特征")
        if role not in {"processing-module", "structure-support"}:
            raise ValueError("临时大框架命名角色非法")
        if role == "processing-module" and module not in FORMAL_MODULES:
            raise ValueError("临时处理库大框架必须映射正式模块")
        if role == "structure-support" and module is not None:
            raise ValueError("临时结构支撑大框架不得映射处理库模块")
        result[block_id] = {
            "dictionaryEntryId": f"temporary:{block_id}",
            "canonicalName": label,
            "role": role,
            "processingModule": module,
            "definition": str(item["definition"]).strip(),
            "matchFeatures": [str(value).strip() for value in features if _nonempty(value)],
            "temporary": True,
        }
    return result
