#!/usr/bin/env python3
"""Durable, audit-gated recovery controller for IP visual PPT rendering.

The attempt ledger is the sole mutable source of truth.  ``render-state.json``
is a replaceable projection used by people, the workbench and the Desktop
bridge.  This process intentionally never generates an image or marks a
review approved: it only decides the next safe action after an auditable
receipt or an external failure has been recorded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import uuid
from typing import Any


LEDGER_NAME = "attempt-ledger.json"
STATE_NAME = "render-state.json"
EXTERNAL_FAILURES = {"image-service", "file-system", "desktop-bridge", "task-missing", "network", "unknown-external"}
TERMINAL_STATES = {"released", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须是对象: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        handle.write(encoded)
        temporary = Path(handle.name)
    temporary.replace(path)


def sha256_json(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def paths(workdir: Path) -> tuple[Path, Path]:
    return workdir / LEDGER_NAME, workdir / STATE_NAME


def controller(ledger: dict[str, Any]) -> dict[str, Any]:
    value = ledger.setdefault("controller", {})
    value.setdefault("schema", "ip-visual-render-controller-v1")
    value.setdefault("state", "preflight")
    value.setdefault("revision", 0)
    value.setdefault("current_asset", "")
    value.setdefault("next_retry_at", "")
    value.setdefault("failure", {})
    value.setdefault("preflight_attempts", [])
    value.setdefault("external_failures", [])
    value.setdefault("repair_task", {})
    value.setdefault("lease", {"owner": "", "expires_at": "", "revision": 0})
    value.setdefault("final_audit_receipt", "")
    return value


def initialize(workdir: Path) -> dict[str, Any]:
    ledger_path, _state_path = paths(workdir)
    ledger = read_json(ledger_path)
    if not isinstance(ledger.get("assets"), list):
        raise ValueError("attempt-ledger.json 缺少 assets")
    for asset in ledger["assets"]:
        asset.setdefault("attempts", [])
        asset.setdefault("status", "pending")
        asset.setdefault("input_hash", "")
        asset.setdefault("audit_receipt", "")
    control = controller(ledger)
    control.setdefault("created_at", utc_now())
    control["updated_at"] = utc_now()
    persist(workdir, ledger)
    return ledger


def projection(ledger: dict[str, Any]) -> dict[str, Any]:
    control = controller(ledger)
    return {
        "schema": "ip-visual-render-state-v1",
        "attempt_ledger": LEDGER_NAME,
        "attempt_ledger_sha256": sha256_json(ledger),
        "state_revision": int(control["revision"]),
        "state": control["state"],
        "current_asset": control["current_asset"],
        "next_retry_at": control["next_retry_at"],
        "failure": control["failure"],
        "repair_task": control["repair_task"],
        "lease": control["lease"],
        "assets": [{"asset_id": a.get("asset_id", ""), "status": a.get("status", "pending"), "attempt_count": len(a.get("attempts") or [])} for a in ledger.get("assets") or []],
        "updated_at": control.get("updated_at", ""),
    }


def persist(workdir: Path, ledger: dict[str, Any]) -> None:
    control = controller(ledger)
    control["updated_at"] = utc_now()
    ledger_path, state_path = paths(workdir)
    write_json(ledger_path, ledger)
    write_json(state_path, projection(ledger))


def mutate(ledger: dict[str, Any], state: str, *, current_asset: str | None = None, failure: dict[str, Any] | None = None, next_retry_at: str | None = None) -> dict[str, Any]:
    control = controller(ledger)
    if control["state"] in TERMINAL_STATES and state not in TERMINAL_STATES:
        raise ValueError(f"终态 {control['state']} 不允许自动恢复")
    control["state"] = state
    if current_asset is not None:
        control["current_asset"] = current_asset
    if failure is not None:
        control["failure"] = failure
    if next_retry_at is not None:
        control["next_retry_at"] = next_retry_at
    control["revision"] = int(control["revision"]) + 1
    return control


def next_pending_asset(ledger: dict[str, Any]) -> str:
    for asset in ledger.get("assets") or []:
        if asset.get("status") in {"pending", "retry-required"}:
            return str(asset.get("asset_id") or "")
    return ""


def receipt_status(path: Path) -> str:
    return str(read_json(path).get("status") or "rejected").strip().lower()


def issue_fingerprint(receipt: dict[str, Any]) -> str:
    issues = receipt.get("issues") or receipt.get("findings") or receipt.get("reason") or "unknown"
    return hashlib.sha256(json.dumps(issues, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def record_preflight(workdir: Path, receipt_path: Path) -> dict[str, Any]:
    ledger = initialize(workdir)
    receipt = read_json(receipt_path)
    status = str(receipt.get("status") or "rejected").lower()
    control = controller(ledger)
    record = {
        "at": utc_now(), "receipt": str(receipt_path), "status": status,
        "fingerprint": issue_fingerprint(receipt), "issues": receipt.get("issues") or receipt.get("findings") or [],
    }
    control["preflight_attempts"].append(record)
    if status == "approved":
        asset = next_pending_asset(ledger)
        mutate(ledger, "rendering" if asset else "waiting-output-audit", current_asset=asset, failure={}, next_retry_at="")
    else:
        repeats = sum(1 for attempt in control["preflight_attempts"] if attempt["status"] != "approved" and attempt["fingerprint"] == record["fingerprint"])
        failure = {"class": "blueprint", "reason": "; ".join(str(x) for x in record["issues"][:3]), "receipt": str(receipt_path), "fingerprint": record["fingerprint"], "repeat_count": repeats}
        if repeats >= 2:
            repair = {"required": True, "kind": "skill-repair", "request_id": str(uuid.uuid4()), "fingerprint": record["fingerprint"], "created_at": utc_now(), "status": "queued"}
            control["repair_task"] = repair
            mutate(ledger, "repairing-blueprint", failure=failure, next_retry_at="")
        else:
            mutate(ledger, "repairing-blueprint", failure=failure, next_retry_at=utc_now())
    persist(workdir, ledger)
    return projection(ledger)


def record_asset(workdir: Path, asset_id: str, status: str, *, reason: str, correction: str, input_hash: str, receipt: str) -> dict[str, Any]:
    ledger = initialize(workdir)
    asset = next((item for item in ledger.get("assets") or [] if item.get("asset_id") == asset_id), None)
    if not asset:
        raise ValueError(f"未找到配图资产: {asset_id}")
    status = status.lower()
    if status not in {"approved", "rejected"}:
        raise ValueError("单页审核状态只能是 approved 或 rejected")
    asset["attempts"].append({
        "attempt": len(asset["attempts"]) + 1, "at": utc_now(), "audit_status": status,
        "reason": reason, "correction_instruction": correction, "input_hash": input_hash,
        "visual_blueprint_hash": asset.get("visual_blueprint_hash", ""), "audit_receipt": receipt,
    })
    asset["input_hash"] = input_hash
    asset["audit_receipt"] = receipt
    if status == "approved":
        asset["status"] = "approved"
        following = next_pending_asset(ledger)
        mutate(ledger, "rendering" if following else "waiting-output-audit", current_asset=following, failure={}, next_retry_at="")
    else:
        asset["status"] = "retry-required"
        mutate(ledger, "repairing-page", current_asset=asset_id, failure={"class": "asset-audit", "reason": reason, "receipt": receipt}, next_retry_at=utc_now())
    persist(workdir, ledger)
    return projection(ledger)


def record_external(workdir: Path, failure_class: str, reason: str) -> dict[str, Any]:
    if failure_class not in EXTERNAL_FAILURES:
        raise ValueError(f"未知外部异常类别: {failure_class}")
    ledger = initialize(workdir)
    control = controller(ledger)
    failures = control["external_failures"]
    consecutive = 1 + sum(1 for item in reversed(failures) if item.get("class") == failure_class)
    delay = min(15 * 60, 30 * (2 ** min(consecutive - 1, 5)))
    retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(timespec="seconds")
    failures.append({"at": utc_now(), "class": failure_class, "reason": reason, "retry_at": retry_at, "delay_seconds": delay})
    mutate(ledger, "reconnecting", failure={"class": failure_class, "reason": reason, "consecutive": consecutive}, next_retry_at=retry_at)
    persist(workdir, ledger)
    return projection(ledger)


def record_final_audit(workdir: Path, receipt_path: Path) -> dict[str, Any]:
    ledger = initialize(workdir)
    status = receipt_status(receipt_path)
    if status == "approved":
        mutate(ledger, "release-ready", failure={}, next_retry_at="")
        controller(ledger)["final_audit_receipt"] = str(receipt_path)
    else:
        current = next_pending_asset(ledger) or controller(ledger).get("current_asset", "")
        mutate(ledger, "repairing-page" if current else "repairing-blueprint", current_asset=current, failure={"class": "output-audit", "receipt": str(receipt_path), "reason": "成图审核未通过"}, next_retry_at=utc_now())
    persist(workdir, ledger)
    return projection(ledger)


def mark_repair_dispatched(workdir: Path, request_id: str, task_id: str) -> dict[str, Any]:
    ledger = initialize(workdir)
    repair = controller(ledger)["repair_task"]
    if not repair.get("required") or repair.get("request_id") != request_id:
        raise ValueError("没有匹配的 Skill 修复请求")
    repair.update({"status": "dispatched", "task_id": task_id, "dispatched_at": utc_now()})
    mutate(ledger, "repairing-skill", failure=controller(ledger)["failure"], next_retry_at="")
    persist(workdir, ledger)
    return projection(ledger)


def mark_repair_verified(workdir: Path, request_id: str) -> dict[str, Any]:
    ledger = initialize(workdir)
    repair = controller(ledger)["repair_task"]
    if repair.get("request_id") != request_id or repair.get("status") != "dispatched":
        raise ValueError("Skill 修复请求未处于已派发状态")
    repair.update({"status": "verified", "verified_at": utc_now(), "required": False})
    mutate(ledger, "repairing-blueprint", failure={}, next_retry_at=utc_now())
    persist(workdir, ledger)
    return projection(ledger)


def claim(workdir: Path, owner: str, ttl_seconds: int, expected_revision: int | None = None) -> dict[str, Any]:
    """Atomically claim the next render checkpoint.

    File replacement alone is insufficient when the Desktop bridge wakes twice.
    The short-lived exclusive guard serializes the read-check-write lease; the
    revision check prevents a stale bridge response from stealing a newer page.
    """
    lock_path = workdir / ".render-recovery.claim.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        # A process crash must not permanently strand the task. A live lease
        # normally lasts minutes, so only a very old guard is recoverable.
        try:
            stale = (datetime.now(timezone.utc).timestamp() - lock_path.stat().st_mtime) > 20 * 60
            if stale:
                lock_path.unlink()
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            else:
                raise RuntimeError("恢复控制器正在被另一进程领取，请等待当前租约结果") from exc
        except FileNotFoundError:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, f"{owner}\n{utc_now()}".encode("utf-8"))
        ledger = initialize(workdir)
        control = controller(ledger)
        if expected_revision is not None and int(control["revision"]) != expected_revision:
            raise RuntimeError(f"恢复状态版本已变化：期望 {expected_revision}，当前 {control['revision']}")
        lease = control["lease"]
        expires = str(lease.get("expires_at") or "")
        if lease.get("owner") and lease.get("owner") != owner and expires > utc_now():
            raise RuntimeError(f"恢复租约正由 {lease['owner']} 持有，至 {expires}")
        lease.update({"owner": owner, "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=max(5, ttl_seconds))).isoformat(timespec="seconds"), "revision": int(control["revision"])})
        persist(workdir, ledger)
        return projection(ledger)
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except OSError:
            pass


def next_action(workdir: Path) -> dict[str, Any]:
    ledger = initialize(workdir)
    control = controller(ledger)
    state = str(control["state"])
    action = "wait"
    if state == "preflight": action = "run-preflight"
    elif state == "rendering": action = "render-asset" if control["current_asset"] else "run-output-audit"
    elif state == "repairing-page": action = "render-asset"
    elif state == "repairing-blueprint": action = "repair-skill" if controller(ledger)["repair_task"].get("required") else "rebuild-work-package"
    elif state == "repairing-skill": action = "wait-skill-repair"
    elif state == "reconnecting": action = "resume-task"
    elif state == "waiting-output-audit": action = "run-output-audit"
    elif state == "release-ready": action = "publish-approved-package"
    return {**projection(ledger), "next_action": action}


def mark_released(workdir: Path, receipt_path: Path) -> dict[str, Any]:
    ledger = initialize(workdir)
    control = controller(ledger)
    if control.get("state") != "release-ready" or not receipt_path.is_file() or receipt_status(receipt_path) != "approved":
        raise ValueError("只有正式小审 approved 回执且处于 release-ready 才能发布")
    mutate(ledger, "released", failure={}, next_retry_at="")
    control["final_audit_receipt"] = str(receipt_path)
    persist(workdir, ledger)
    return projection(ledger)


def main() -> int:
    parser = argparse.ArgumentParser(description="IP视觉PPT 持久化不断线恢复控制器")
    parser.add_argument("--workdir", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    preflight = commands.add_parser("record-preflight"); preflight.add_argument("--receipt", required=True, type=Path)
    asset = commands.add_parser("record-asset"); asset.add_argument("--asset", required=True); asset.add_argument("--status", required=True); asset.add_argument("--reason", default=""); asset.add_argument("--correction", default=""); asset.add_argument("--input-hash", default=""); asset.add_argument("--receipt", default="")
    external = commands.add_parser("record-external"); external.add_argument("--class", dest="failure_class", required=True); external.add_argument("--reason", required=True)
    final_audit = commands.add_parser("record-final-audit"); final_audit.add_argument("--receipt", required=True, type=Path)
    dispatched = commands.add_parser("mark-repair-dispatched"); dispatched.add_argument("--request-id", required=True); dispatched.add_argument("--task-id", required=True)
    verified = commands.add_parser("mark-repair-verified"); verified.add_argument("--request-id", required=True)
    lease = commands.add_parser("claim"); lease.add_argument("--owner", required=True); lease.add_argument("--ttl-seconds", type=int, default=300); lease.add_argument("--expected-revision", type=int)
    commands.add_parser("next")
    release = commands.add_parser("mark-released"); release.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    workdir = args.workdir.resolve()
    if args.command == "init": result = projection(initialize(workdir))
    elif args.command == "record-preflight": result = record_preflight(workdir, args.receipt)
    elif args.command == "record-asset": result = record_asset(workdir, args.asset, args.status, reason=args.reason, correction=args.correction, input_hash=args.input_hash, receipt=args.receipt)
    elif args.command == "record-external": result = record_external(workdir, args.failure_class, args.reason)
    elif args.command == "record-final-audit": result = record_final_audit(workdir, args.receipt)
    elif args.command == "mark-repair-dispatched": result = mark_repair_dispatched(workdir, args.request_id, args.task_id)
    elif args.command == "mark-repair-verified": result = mark_repair_verified(workdir, args.request_id)
    elif args.command == "claim": result = claim(workdir, args.owner, args.ttl_seconds, args.expected_revision)
    elif args.command == "next": result = next_action(workdir)
    else: result = mark_released(workdir, args.receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
