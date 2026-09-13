"""以固定五篇批次生成、审核并准入视频文案校对候选。

本脚本只触碰 .runtime。它从标准化 manifest 固定顺序取一个连续批次，
为每篇生成保守校对候选（没有确定修改时使用空变更清单），调用小审的
独立校对审核，并且仅在五篇全部 approved 后写准入清单。脚本一次只跑一
批，绝不自动开启下一批。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.common import append_brand_footer

import proofread_video_source as proofreader


DEFAULT_SOURCE_ROOT = ROOT / "02_资产中心" / "01_输入库" / "04_视频文案-源文件（会员专享）" / "00_标准化源文档"
DEFAULT_RUNTIME_ROOT = ROOT / ".runtime" / "video-pain-cards" / "five-source-batches"
AUDIT_SCRIPT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "audit_video_source_correction.py"
BATCH_SIZE = 5
LEDGER_SCHEMA = "video-source-correction-batch-ledger-v1"
PREFLIGHT_SCHEMA = "video-source-correction-coverage-preflight-v1"
ADMISSION_SCHEMA = "video-source-correction-approved-batch-v1"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def project_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def load_manifest(source_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    manifest_path = source_root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "video-source-manifest-v1" or not isinstance(payload.get("records"), list):
        raise ValueError("标准化 manifest 必须是 video-source-manifest-v1 且含 records 数组")
    return manifest_path, payload["records"]


def coverage_preflight(source_root: Path) -> dict[str, Any]:
    """验证 547 条记录、唯一 source_id、逐文档路径、哈希和全文绑定。"""
    manifest_path, records = load_manifest(source_root)
    issues: list[str] = []
    source_ids: list[str] = []
    bindings: list[dict[str, str]] = []
    seen: set[str] = set()
    for position, record in enumerate(records, start=1):
        source_id = str(record.get("source_id") or "")
        rel_path = str(record.get("relative_path") or "")
        if not source_id or not rel_path:
            issues.append(f"manifest 第 {position} 条缺 source_id 或 relative_path")
            continue
        if source_id in seen:
            issues.append(f"manifest source_id 重复：{source_id}")
            continue
        seen.add(source_id)
        source_ids.append(source_id)
        source_path = source_root / rel_path
        if not source_path.is_file():
            issues.append(f"{source_id} 缺少标准化源文档：{rel_path}")
            continue
        try:
            _, metadata, full_text = proofreader.read_source(source_path)
        except (OSError, ValueError) as exc:
            issues.append(f"{source_id} 无法读取标准化源文档：{exc}")
            continue
        if metadata.get("source_id") != source_id:
            issues.append(f"{source_id} 的源文档 source_id 不一致")
        text_hash = proofreader.sha256_text(full_text)
        if text_hash != str(record.get("full_text_sha256") or ""):
            issues.append(f"{source_id} 的全文哈希与 manifest 不一致")
        bindings.append({
            "source_id": source_id,
            "relative_path": rel_path,
            "source_document_sha256": sha256_bytes(source_path.read_bytes()),
            "full_text_sha256": text_hash,
        })
    if len(records) != 547:
        issues.append(f"全覆盖预检要求 547 篇，manifest 实际为 {len(records)} 篇")
    return {
        "schema": PREFLIGHT_SCHEMA,
        "generated_at": now(),
        "status": "passed" if not issues else "failed",
        "manifest_path": project_rel(manifest_path),
        "manifest_sha256": sha256_bytes(manifest_path.read_bytes()),
        "source_count": len(records),
        "batch_size": BATCH_SIZE,
        "expected_batch_count": (len(records) + BATCH_SIZE - 1) // BATCH_SIZE,
        "ordered_source_ids_sha256": sha256_json(source_ids),
        "source_bindings_sha256": sha256_json(bindings),
        "source_bindings": bindings,
        "issues": issues,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def persist_preflight(preflight_path: Path, current: dict[str, Any]) -> dict[str, Any]:
    """来源未变时复用首份预检，避免恢复运行改变已准入批次的哈希绑定。"""
    binding_keys = ("status", "manifest_sha256", "ordered_source_ids_sha256", "source_bindings_sha256", "source_count", "batch_size")
    if preflight_path.is_file():
        try:
            previous = json.loads(preflight_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = {}
        if previous.get("schema") == PREFLIGHT_SCHEMA and all(previous.get(key) == current.get(key) for key in binding_keys):
            return previous
    write_json(preflight_path, current)
    return current


def ledger_path(runtime_root: Path) -> Path:
    return runtime_root / "校对批次台账.json"


def load_or_init_ledger(runtime_root: Path, preflight: dict[str, Any]) -> dict[str, Any]:
    path = ledger_path(runtime_root)
    if not path.exists():
        return {
            "schema": LEDGER_SCHEMA,
            "created_at": now(),
            "coverage_preflight_path": project_rel(runtime_root / "全547篇覆盖预检.json"),
            "coverage_preflight_sha256": "",
            "manifest_sha256": preflight["manifest_sha256"],
            "ordered_source_ids_sha256": preflight["ordered_source_ids_sha256"],
            "batch_size": BATCH_SIZE,
            "batches": {},
        }
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError("现有校对批次台账 schema 不匹配；拒绝覆盖")
    for key in ("manifest_sha256", "ordered_source_ids_sha256"):
        if ledger.get(key) != preflight.get(key):
            raise ValueError(f"来源 manifest 或顺序已漂移（{key}），拒绝在旧台账上继续")
    return ledger


def save_ledger(runtime_root: Path, ledger: dict[str, Any], preflight_path: Path) -> None:
    ledger["updated_at"] = now()
    ledger["coverage_preflight_sha256"] = sha256_bytes(preflight_path.read_bytes())
    write_json(ledger_path(runtime_root), ledger)


def select_batch(records: list[dict[str, Any]], batch_number: int) -> list[dict[str, Any]]:
    if batch_number < 1:
        raise ValueError("batch_number 必须从 1 开始")
    start = (batch_number - 1) * BATCH_SIZE
    selected = records[start:start + BATCH_SIZE]
    if len(selected) != BATCH_SIZE and start + len(selected) != len(records):
        raise ValueError("批次选择不连续或超出 manifest 覆盖范围")
    if not selected:
        raise ValueError(f"批次 {batch_number} 超出 manifest 范围")
    return selected


def expected_prior_batch(ledger: dict[str, Any], batch_number: int) -> None:
    """下一批必须以全部前批 approved 为准；本轮只允许显式执行一个批次。"""
    for prior in range(1, batch_number):
        state = ledger.get("batches", {}).get(f"batch-{prior:04d}", {})
        if state.get("status") != "approved":
            raise ValueError(f"第 {prior} 批尚未 approved，禁止启动第 {batch_number} 批")


def changes_for_source(changes_dir: Path | None, source_id: str) -> list[dict[str, Any]]:
    """没有人工确认的修改清单时返回空列表，保证零改动校对可审。"""
    if changes_dir is None:
        return []
    path = changes_dir / f"{source_id}.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "video-source-correction-changes-v1" or payload.get("source_id") != source_id:
        raise ValueError(f"{path} 的修改清单 schema 或 source_id 不匹配")
    return list(payload.get("changes") or [])


def audit_candidate(candidate_path: Path, receipt_path: Path) -> dict[str, Any]:
    task_id = hashlib.sha256(project_rel(candidate_path).encode("utf-8")).hexdigest()[:16]
    result = subprocess.run(
        [sys.executable, str(AUDIT_SCRIPT), "--candidate", str(candidate_path), "--receipt", str(receipt_path), "--task-id", task_id],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if not receipt_path.is_file():
        raise RuntimeError(f"小审未写出回执：{candidate_path.name}；退出码 {result.returncode}；{result.stderr[-400:]}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if result.returncode != 0 or receipt.get("status") != "approved":
        detail = receipt.get("checks", [])
        raise RuntimeError(f"小审退回：{candidate_path.name}；{json.dumps(detail, ensure_ascii=False)[:800]}")
    candidate_hash = sha256_bytes(candidate_path.read_bytes())
    if receipt.get("subject", {}).get("candidateSha256") != candidate_hash:
        raise RuntimeError(f"小审回执与候选哈希未绑定：{candidate_path.name}")
    return receipt


def admission_manifest(
    batch_id: str,
    preflight_path: Path,
    records: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": ADMISSION_SCHEMA,
        "status": "approved",
        "batch_id": batch_id,
        "batch_number": int(batch_id.rsplit("-", 1)[1]),
        "approved_at": now(),
        "coverage_preflight_path": project_rel(preflight_path),
        "coverage_preflight_sha256": sha256_bytes(preflight_path.read_bytes()),
        "source_count": len(records),
        "source_ids": [str(record["source_id"]) for record in records],
        "sources": candidates,
    }


def run_batch(source_root: Path, runtime_root: Path, batch_number: int, changes_dir: Path | None = None) -> dict[str, Any]:
    preflight = coverage_preflight(source_root)
    preflight_path = runtime_root / "全547篇覆盖预检.json"
    preflight = persist_preflight(preflight_path, preflight)
    if preflight["status"] != "passed":
        raise RuntimeError("全547篇覆盖预检失败：" + "；".join(preflight["issues"]))

    manifest_path, records = load_manifest(source_root)
    ledger = load_or_init_ledger(runtime_root, preflight)
    expected_prior_batch(ledger, batch_number)
    selected = select_batch(records, batch_number)
    batch_id = f"batch-{batch_number:04d}"
    batch_root = runtime_root / batch_id
    state = ledger.setdefault("batches", {}).setdefault(batch_id, {"status": "running", "source_ids": [str(item["source_id"]) for item in selected]})
    if state.get("source_ids") != [str(item["source_id"]) for item in selected]:
        raise ValueError(f"{batch_id} 的已记账 source_id 与 manifest 当前连续批次不一致")
    if state.get("status") == "approved":
        admission_path = batch_root / "已审核校对源批次清单.json"
        if not admission_path.is_file():
            raise RuntimeError(f"{batch_id} 标记 approved 但缺少准入清单，拒绝继续")
        save_ledger(runtime_root, ledger, preflight_path)
        return {"status": "already-approved", "batch_id": batch_id, "admission_path": project_rel(admission_path)}

    state.update({"status": "running", "started_at": state.get("started_at") or now(), "source_ids": [str(item["source_id"]) for item in selected]})
    save_ledger(runtime_root, ledger, preflight_path)
    candidates: list[dict[str, Any]] = []
    try:
        for record in selected:
            source_id = str(record["source_id"])
            source_path = source_root / str(record["relative_path"])
            source_candidate_dir = batch_root / "校对候选"
            changes = changes_for_source(changes_dir, source_id)
            changes_path = batch_root / "修改清单" / f"{source_id}.json"
            write_json(changes_path, {"schema": "video-source-correction-changes-v1", "source_id": source_id, "changes": changes})
            candidate_path = proofreader.write_candidate(source_path, changes, source_candidate_dir)
            receipt_path = batch_root / "小审回执" / f"{source_id}.json"
            receipt = audit_candidate(candidate_path, receipt_path)
            candidates.append({
                "source_id": source_id,
                "original_source_path": str(record["relative_path"]),
                "original_full_text_sha256": str(record["full_text_sha256"]),
                "correction_candidate_path": project_rel(candidate_path),
                "correction_candidate_sha256": sha256_bytes(candidate_path.read_bytes()),
                "correction_audit_receipt": project_rel(receipt_path),
                "correction_audit_sha256": sha256_bytes(receipt_path.read_bytes()),
                "status": receipt["status"],
            })
    except Exception as exc:
        state.update({"status": "returned", "stopped_at": now(), "reason": str(exc), "processed_source_ids": [item["source_id"] for item in candidates]})
        save_ledger(runtime_root, ledger, preflight_path)
        # No approved admission manifest is written on any failure.
        raise

    approved_path = batch_root / "已审核校对源批次清单.json"
    batch_source_ledger_path = batch_root / "batch-source-ledger.json"
    approved = admission_manifest(batch_id, preflight_path, selected, candidates)
    write_json(batch_source_ledger_path, approved)
    write_json(approved_path, approved)
    state.update({
        "status": "approved", "approved_at": approved["approved_at"],
        "admission_path": project_rel(approved_path), "admission_sha256": sha256_bytes(approved_path.read_bytes()),
        "batch_source_ledger_path": project_rel(batch_source_ledger_path), "batch_source_ledger_sha256": sha256_bytes(batch_source_ledger_path.read_bytes()),
        "source_count": len(selected),
    })
    save_ledger(runtime_root, ledger, preflight_path)
    return {"status": "approved", "batch_id": batch_id, "admission_path": project_rel(approved_path), "source_ids": approved["source_ids"]}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="每批五篇视频文案校对候选 + 逐篇小审 + 准入清单")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--batch-number", type=int, default=1, help="只执行此一个连续批次；不会自动进入下一批")
    parser.add_argument("--changes-dir", type=Path, help="可选人工确认修改清单目录；缺文件时按零改动校对")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_batch(args.source_root.resolve(), args.runtime_root.resolve(), args.batch_number, args.changes_dir.resolve() if args.changes_dir else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
