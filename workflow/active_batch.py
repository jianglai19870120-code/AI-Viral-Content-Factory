from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow.common import PROJECT_ROOT, append_brand_footer_text
from workflow.runtime import runtime_root


ACTIVE_BATCH_STATE = runtime_root() / "state" / "active_batch_state.json"
DEFAULT_RESUME_TOKENS = ["继续任务", "下一步", "继续"]
STRUCTURE_REAUDIT_BATCH_TYPE = "dry-goods-structure-reaudit"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_valid_state(data: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema",
        "batch_id",
        "batch_type",
        "batch_size",
        "source_review_batch",
        "queue",
        "cursor",
        "completed_items",
        "approved_items",
        "skipped_items",
        "failed_items",
        "repair_queue",
        "status",
        "last_run_at",
        "resume_token_phrases",
    }
    missing = sorted(required - set(data))
    if missing:
        raise ValueError(f"活跃批次状态缺少字段：{missing}")
    if data["schema"] != "active-batch-state-v1":
        raise ValueError(f"活跃批次状态 schema 非法：{data['schema']}")
    if data["status"] not in {"active", "completed", "blocked"}:
        raise ValueError(f"活跃批次状态非法：{data['status']}")
    return data


def load_active_batch(*, required: bool = False) -> dict[str, Any] | None:
    if not ACTIVE_BATCH_STATE.is_file():
        if required:
            raise FileNotFoundError(f"当前没有活跃批次状态文件：{ACTIVE_BATCH_STATE}")
        return None
    data = json.loads(ACTIVE_BATCH_STATE.read_text(encoding="utf-8"))
    return _ensure_valid_state(data)


def save_active_batch(data: dict[str, Any]) -> Path:
    data["last_run_at"] = _now()
    _rebuild_rollups(data)
    _ensure_valid_state(data)
    _write_json(ACTIVE_BATCH_STATE, data)
    return ACTIVE_BATCH_STATE


def create_structure_reaudit_batch(
    *,
    batch_id: str,
    source_review_batch: str,
    queue_titles: list[str],
    batch_size: int = 10,
) -> dict[str, Any]:
    state = {
        "schema": "active-batch-state-v1",
        "batch_id": batch_id,
        "batch_type": STRUCTURE_REAUDIT_BATCH_TYPE,
        "batch_size": batch_size,
        "source_review_batch": source_review_batch,
        "queue": [
            {
                "title": title,
                "queue_index": index,
                "status": "pending",
            }
            for index, title in enumerate(queue_titles, start=1)
        ],
        "cursor": -1,
        "completed_items": [],
        "approved_items": [],
        "skipped_items": [],
        "failed_items": [],
        "repair_queue": [],
        "status": "active",
        "last_run_at": _now(),
        "resume_token_phrases": list(DEFAULT_RESUME_TOKENS),
    }
    return state


def next_pending_index(state: dict[str, Any]) -> int | None:
    queue = state.get("queue") or []
    cursor = int(state.get("cursor", -1))
    for index in range(cursor + 1, len(queue)):
        if queue[index].get("status") == "pending":
            return index
    for index, item in enumerate(queue):
        if item.get("status") == "pending":
            return index
    return None


def record_item_result(state: dict[str, Any], *, queue_index: int, result: dict[str, Any]) -> dict[str, Any]:
    if queue_index < 1 or queue_index > len(state.get("queue") or []):
        raise IndexError(f"queue_index 越界：{queue_index}")
    item = state["queue"][queue_index - 1]
    item.update(result)
    item["queue_index"] = queue_index
    if not item.get("completed_at"):
        item["completed_at"] = _now()
    state["cursor"] = max(int(state.get("cursor", -1)), queue_index - 1)
    _rebuild_rollups(state)
    return state


def _rebuild_rollups(state: dict[str, Any]) -> None:
    completed: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    repair_queue: list[dict[str, Any]] = []

    for item in state.get("queue") or []:
        status = item.get("status", "pending")
        if status == "pending":
            continue
        completed.append(dict(item))
        if status == "approved":
            approved.append(dict(item))
        elif status == "skipped_frozen_incompatible":
            skipped.append(dict(item))
            failed.append(dict(item))
            repair_queue.append(dict(item))
        elif status == "rejected_queued_for_repair":
            failed.append(dict(item))
            repair_queue.append(dict(item))

    state["completed_items"] = completed
    state["approved_items"] = approved
    state["skipped_items"] = skipped
    state["failed_items"] = failed
    state["repair_queue"] = repair_queue
    if all(item.get("status") != "pending" for item in state.get("queue") or []):
        state["status"] = "completed"
    elif state.get("status") != "blocked":
        state["status"] = "active"


def summarize_active_batch(state: dict[str, Any]) -> dict[str, Any]:
    queue = state.get("queue") or []
    return {
        "batch_id": state.get("batch_id", ""),
        "batch_type": state.get("batch_type", ""),
        "batch_size": state.get("batch_size", 0),
        "total": len(queue),
        "cursor": state.get("cursor", -1),
        "approved_count": len(state.get("approved_items") or []),
        "rejected_count": len(state.get("failed_items") or []),
        "skipped_count": len(state.get("skipped_items") or []),
        "repair_queue_count": len(state.get("repair_queue") or []),
        "pending_count": sum(1 for item in queue if item.get("status") == "pending"),
        "status": state.get("status", ""),
    }


def render_batch_summary_markdown(state: dict[str, Any]) -> str:
    summary = summarize_active_batch(state)
    lines = [
        f"# 干货型结构活跃批次摘要：{summary['batch_id']}",
        "",
        f"- 批次类型：{summary['batch_type']}",
        f"- 总条数：{summary['total']}",
        f"- approved：{summary['approved_count']}",
        f"- rejected：{summary['rejected_count']}",
        f"- skipped：{summary['skipped_count']}",
        f"- repair_queue：{summary['repair_queue_count']}",
        f"- 状态：{summary['status']}",
        "",
        "## 批次明细",
        "",
        "| 序号 | 题目 | 结果 |",
        "|---|---|---|",
    ]
    for item in state.get("queue") or []:
        lines.append(f"| {item.get('queue_index', '')} | {item.get('title', '')} | {item.get('status', 'pending')} |")
    return append_brand_footer_text("\n".join(lines).rstrip() + "\n")
