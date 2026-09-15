"""Source-level input inventory and processing-status reconciliation.

The workbench must count source documents, not downstream cards.  This module
keeps one row per canonical input source and links it to formal processing
evidence where that evidence can be traced safely.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


TYPES = {
    "books": ("书籍", "01_推荐好书-源文件"),
    "podcasts": ("播客", "02_热门播客-源文件（会员专享）"),
    "video-sources": ("视频文案", "04_视频文案-源文件（会员专享）"),
    "work-journals": ("复盘", "99_今日复盘-源文件（会员专享）"),
    "events": ("事件", "03_热点事件-源文件（会员专享）"),
}
EXTENSIONS = {".md", ".txt", ".pdf", ".epub", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".mp3", ".m4a", ".wav"}
VIDEO_DISCOVERY_EXTENSIONS = EXTENSIONS | {".mp4", ".mov"}
SKIP = {".gitkeep", "README.md"}


def _norm(value: str) -> str:
    value = str(value or "").lower()
    value = re.sub(r"[\s_\-（）()\[\]【】《》:：,，。.!！?？、]+", "", value)
    return value


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _files(root: Path, suffixes: set[str] | None = None) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.name not in SKIP and not p.name.startswith(".")
        and "__pycache__" not in p.parts and "_private" not in p.parts
        and (suffixes is None or p.suffix.lower() in suffixes)
    )


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _source_id(kind: str, rel: str, digest: str) -> str:
    return f"{kind}-{hashlib.sha256(f'{rel}|{digest}'.encode()).hexdigest()[:16]}"


_BOOK_EVIDENCE_CACHE: dict[str, list[tuple[str, str]]] = {}


def _book_evidence(root: Path, title: str) -> tuple[str, int, str]:
    needle = _norm(title)
    key = str(root.resolve())
    evidence = _BOOK_EVIDENCE_CACHE.get(key)
    if evidence is None:
        evidence = [(_norm(p.name), _norm(_read(p)[:4000])) for p in _files(root, {".md"})]
        _BOOK_EVIDENCE_CACHE[key] = evidence
    hits = []
    for name, text in evidence:
        if name.startswith(needle) or needle in text:
            hits.append(name)
    return ("已拆解", len(hits), "已找到推荐好书正式模块来源") if hits else ("未拆解", 0, "未找到可回溯的正式模块来源")


def _podcast_evidence(root: Path, title: str) -> tuple[str, int, str]:
    needle = _norm(title)
    hits = []
    for p in _files(root, {".md"}):
        if needle in _norm(p.name) or needle in _norm(_read(p)[:5000]):
            hits.append(p)
    return ("已拆解", len(hits), "已找到播客正式模块来源") if hits else ("未拆解", 0, "未找到可回溯的正式播客模块来源")


def _video_manifest(root: Path) -> list[dict[str, Any]]:
    path = root / "00_标准化源文档" / "manifest.jsonl"
    rows = []
    for line in _read(path).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("source_id"):
            rows.append(row)
    return rows


def _raw_video_sources(root: Path) -> list[tuple[Path, str, dict[str, Any]]]:
    """Expose user-confirmed video files in the same refresh queue as inputs."""
    manifest_rows = _video_manifest(root)
    standardized_hashes = {
        str(item.get("source_file_sha256") or "")
        for item in manifest_rows
        if str(item.get("source_file_sha256") or "")
    }
    result: list[tuple[Path, str, dict[str, Any]]] = []
    for path in _files(root, VIDEO_DISCOVERY_EXTENSIONS):
        try:
            path.relative_to(root / "00_标准化源文档")
            continue
        except ValueError:
            pass
        # Once a source workbook has a matching manifest hash it is already
        # represented by its generated source documents, not a second raw row.
        if _sha(path) in standardized_hashes:
            continue
        result.append((path, path.stem, {"manual_input": True}))
    return result


_VIDEO_EVIDENCE_CACHE: dict[str, dict[str, Any]] = {}


def _json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _project_path(project_root: Path, value: str) -> Path:
    """Resolve a receipt path without allowing a receipt to escape its project."""
    candidate = Path(value)
    resolved = candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return Path()
    return resolved


def _video_batch_state(project_root: Path) -> dict[str, Any]:
    """Read the formal, sequential video-pain ledger and source-audit proof.

    A pain card is not enough evidence by itself: the batch ledger records the
    source-level release decision.  Conversely, a raw manifest source may only
    become *ready* for the pain Skill after its corrected candidate has an
    approved small-audit receipt.  This keeps the dashboard from sending a
    known-ineligible next batch to Codex.
    """
    cache_key = str(project_root.resolve())
    runtime_root = project_root / ".runtime" / "video-pain-cards"
    correction_root = runtime_root / "five-source-batches"
    # v2 is the active rebuild contract.  Keep the older state readable only
    # for historical workspaces that have not migrated, never as a competing
    # source of truth once the v2 ledger exists.
    v2_ledger = runtime_root / "rebuild-547-v2" / "state" / "coverage-ledger.json"
    legacy_ledger = correction_root / "rebuild-547-state" / "coverage-ledger.json"
    ledger_path = v2_ledger if v2_ledger.is_file() else legacy_ledger
    receipt_paths = tuple(correction_root.glob("batch-*/小审回执/*.json"))
    marker = (
        ledger_path.stat().st_mtime_ns if ledger_path.is_file() else 0,
        max((path.stat().st_mtime_ns for path in receipt_paths), default=0),
        len(receipt_paths),
    )
    cached = _VIDEO_EVIDENCE_CACHE.get(cache_key)
    if cached and cached.get("marker") == marker:
        return dict(cached["state"])

    ledger = _json_object(ledger_path)
    sources = ledger.get("sources") if isinstance(ledger.get("sources"), list) else []
    source_rows = {
        str(item.get("source_id")): item
        for item in sources
        if isinstance(item, dict) and item.get("source_id")
    }
    released: set[str] = set()
    for batch in ledger.get("completed_batches", []):
        if not isinstance(batch, dict) or batch.get("release_status") != "released":
            continue
        released.update(str(value) for value in batch.get("source_ids", []) if value)

    corrected: dict[str, dict[str, str]] = {}
    for receipt_path in receipt_paths:
        receipt = _json_object(receipt_path)
        subject = receipt.get("subject") if isinstance(receipt.get("subject"), dict) else {}
        source_id = str(subject.get("source_id") or "")
        candidate = _project_path(project_root, str(subject.get("candidate") or ""))
        if (
            receipt.get("schema") != "audit-receipt-v3"
            or receipt.get("artifactType") != "video-source-correction-v1"
            or receipt.get("status") != "approved"
            or not source_id
            or not candidate.is_file()
            or str(subject.get("candidateSha256") or "") != _sha(candidate)
        ):
            continue
        corrected[source_id] = {
            "candidate_path": candidate.relative_to(project_root.resolve()).as_posix(),
            "audit_receipt": receipt_path.resolve().relative_to(project_root.resolve()).as_posix(),
        }

    next_sources: list[dict[str, Any]] = []
    if not ledger.get("active_batch") and ledger.get("next_batch_ready") is True:
        batch_size = int(ledger.get("batch_size") or 5)
        next_sources = [item for item in sources if isinstance(item, dict) and item.get("status") == "pending"][:batch_size]
    next_ids = [str(item.get("source_id")) for item in next_sources if item.get("source_id")]
    ready_ids: set[str] = set(next_ids) if next_ids and all(source_id in corrected for source_id in next_ids) else set()

    state = {
        "ledger_available": ledger.get("schema") == "video-pain-batch-ledger-v1",
        "ledger_path": ledger_path,
        "ledger": ledger,
        "contract_version": "v2" if ledger_path == v2_ledger else "legacy",
        "sources": source_rows,
        "released": released,
        "corrected": corrected,
        "next_ids": next_ids,
        "ready_ids": ready_ids,
    }
    _VIDEO_EVIDENCE_CACHE[cache_key] = {"marker": marker, "state": state}
    return state


def _video_evidence(project_root: Path, row: dict[str, Any], source_path: Path) -> tuple[str, int, str]:
    source_id = str(row.get("source_id") or "")
    if not source_id:
        return "来源不明确", 0, "标准化视频 manifest 缺少 source_id，不能建立来源绑定"
    state = _video_batch_state(project_root)
    source = state["sources"].get(source_id, {})
    if not state["ledger_available"] or not source:
        return "来源不明确", 0, "未找到视频痛点批次台账来源，不能判定为已拆解"
    if str(source.get("source_sha256") or "") != _sha(source_path):
        return "来源不明确", 0, "标准化源文件哈希与视频痛点批次台账不一致"
    if source_id in state["released"]:
        return "已拆解", 1, "已在视频痛点连续批次中获小审批准并正式发布"
    if source_id in state["ready_ids"]:
        return "未拆解", 0, "下一连续批校对源已获小审 approved，可启动痛点卡拆解"
    next_ids = state["next_ids"]
    if source_id in next_ids:
        return "待审核", 0, "下一连续批尚缺小息校对候选及小审 approved 回执"
    return "待审核", 0, "尚未进入已校对并经小审 approved 的下一连续批，不能启动痛点卡拆解"


def video_refresh_batch(project_root: Path) -> list[dict[str, str]]:
    """Return only the verified next batch accepted by the pain-card contract."""
    state = _video_batch_state(project_root)
    result: list[dict[str, str]] = []
    for source_id in state["next_ids"]:
        if source_id not in state["ready_ids"]:
            return []
        source = state["sources"].get(source_id, {})
        source_path = _project_path(project_root, str(source.get("source_path") or ""))
        correction = state["corrected"].get(source_id, {})
        if not source_path.is_file() or not correction:
            return []
        result.append({
            "source_id": source_id,
            "source_path": source_path.relative_to(project_root.resolve()).as_posix(),
            "candidate_path": str(correction["candidate_path"]),
            "audit_receipt": str(correction["audit_receipt"]),
        })
    return result


def video_active_batch(project_root: Path) -> dict[str, Any]:
    """Return the single v2 batch that must be resumed before a new refresh.

    The dashboard must never call it a missing batch: an active batch is a
    valid, resumable work item whose next action is determined by its existing
    receipts and runtime artifacts.
    """
    state = _video_batch_state(project_root)
    active = state["ledger"].get("active_batch")
    if not isinstance(active, dict) or not active.get("batch_number"):
        return {}
    source_ids = active.get("source_ids") if isinstance(active.get("source_ids"), list) else []
    return {
        "batch_number": int(active["batch_number"]),
        "source_ids": [str(item) for item in source_ids if str(item)],
        "run_dir": str(active.get("run_dir") or ""),
        "phase": str(active.get("phase") or "machine_evidence"),
        "source_manifest": str(active.get("source_manifest") or ""),
        "contract_version": str(state["contract_version"]),
    }


def video_correction_batch(project_root: Path) -> dict[str, Any]:
    """Return the next source-correction batch before it can enter pain routing."""
    state = _video_batch_state(project_root)
    if not state["ledger_available"] or not state["next_ids"]:
        return {}
    sources: list[dict[str, str]] = []
    for source_id in state["next_ids"]:
        source = state["sources"].get(source_id, {})
        source_path = _project_path(project_root, str(source.get("source_path") or ""))
        if not source_path.is_file() or str(source.get("source_sha256") or "") != _sha(source_path):
            return {}
        sources.append({"source_id": source_id, "source_path": source_path.relative_to(project_root.resolve()).as_posix()})
    completed = [int(item.get("batch_number") or 0) for item in state["ledger"].get("completed_batches", []) if isinstance(item, dict)]
    return {"batch_number": max(completed, default=0) + 1, "sources": sources}


_JOURNAL_INDEX_CACHE: dict[str, tuple[int, int, list[dict[str, Any]]]] = {}


def _journal_evidence(project_root: Path, title: str, source_path: Path) -> tuple[str, int, str, list[dict[str, str]]]:
    index = project_root / "02_资产中心" / "02_处理库" / "05_案例_内容模块（会员专享）" / "02_案例卡索引" / "案例卡索引.jsonl"
    key = str(index.resolve())
    stat = index.stat() if index.exists() else None
    signature = (stat.st_mtime_ns, stat.st_size) if stat else (-1, -1)
    cached = _JOURNAL_INDEX_CACHE.get(key)
    indexed = cached[2] if cached and cached[:2] == signature else None
    if indexed is None:
        indexed = []
        for line in _read(index).splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and str(row.get("schema_version") or "") == "work-journal-case-card-v12":
                indexed.append(row)
        _JOURNAL_INDEX_CACHE[key] = (*signature, indexed)
    source_hash = _sha(source_path)
    hits = []
    for row in indexed:
        indexed_path = str(row.get("source_path") or "")
        indexed_title = str(row.get("source_title") or "")
        same_source = (indexed_path and _norm(Path(indexed_path).name) == _norm(source_path.name)) or (_norm(title) and _norm(title) == _norm(indexed_title))
        if same_source and str(row.get("source_sha256") or "") == source_hash:
            hits.append(row)
    if hits:
        cards = [
            {
                "case_id": str(row.get("case_id") or ""),
                "title": str(row.get("title") or ""),
                "card_path": str(row.get("card_path") or ""),
            }
            for row in hits
        ]
        return "已拆解", len(cards), "案例卡索引已回溯到源笔记", cards
    no_case_ledger = project_root / "02_资产中心" / "02_处理库" / "05_案例_内容模块（会员专享）" / "05_案例卡跳过记录" / "no_case_list.jsonl"
    for line in _read(no_case_ledger).splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        indexed_path = str(row.get("source_path") or "")
        if (
            isinstance(row, dict)
            and str(row.get("schema_version") or "") == "work-journal-case-card-v12"
            and str(row.get("release_disposition") or "") == "no_case"
            and str(row.get("source_sha256") or "") == source_hash
            and indexed_path
            and _norm(Path(indexed_path).name) == _norm(source_path.name)
        ):
            return "已处理", 0, "小审已确认本条复盘不生成案例卡", []
    stale_same_source = any(
        ((str(row.get("source_path") or "") and _norm(Path(str(row.get("source_path") or "")).name) == _norm(source_path.name))
         or (_norm(title) and _norm(title) == _norm(str(row.get("source_title") or ""))))
        for row in indexed
    )
    if stale_same_source:
        return "未拆解", 0, "源文件已变更，旧案例卡不能继续作为现役证据", []
    return "未拆解", 0, "未找到对应案例卡", []


def build_inventory(project_root: Path) -> list[dict[str, Any]]:
    input_root = project_root / "02_资产中心" / "01_输入库"
    rows: list[dict[str, Any]] = []
    video_rows = _video_manifest(input_root / TYPES["video-sources"][1])
    for kind, (label, dirname) in TYPES.items():
        root = input_root / dirname
        if kind == "video-sources":
            sources = []
            for item in video_rows:
                rel = str(item.get("relative_path") or "")
                path = root / "00_标准化源文档" / rel
                if path.is_file():
                    sources.append((path, str(item.get("title") or ""), item))
            sources.extend(_raw_video_sources(root))
        else:
            sources = [(p, p.stem, {}) for p in _files(root, EXTENSIONS)]
            # 展示样板只说明录入格式，不是可拆解的复盘源。它必须与今日复盘
            # Skill 的入口闸门保持同一口径，不能把仪表盘长期卡在“待处理 1”。
            if kind == "work-journals":
                sources = [item for item in sources if not item[0].name.startswith("样板-")]
        seen: set[str] = set()
        for path, raw_title, meta in sources:
            digest = _sha(path)
            # Podcast exports occasionally contain the same source twice.
            dedupe = _norm(raw_title) + "|" + digest if kind == "podcasts" else str(path.resolve())
            if dedupe in seen:
                continue
            seen.add(dedupe)
            title = re.sub(r"^《(.+?)》$", r"\1", raw_title).strip() or path.stem
            rel = path.relative_to(project_root).as_posix()
            if kind == "books":
                status, output_count, reason = _book_evidence(project_root / "02_资产中心" / "02_处理库", title)
            elif kind == "podcasts":
                status, output_count, reason = _podcast_evidence(project_root / "02_资产中心" / "02_处理库" / "06_推荐理由_内容模块" / "02_热门播客（会员专享）", title)
            elif kind == "video-sources":
                if meta.get("manual_input"):
                    status, output_count, reason = "未拆解", 0, "用户已确认的输入文件，等待点击视频文案刷新"
                else:
                    status, output_count, reason = _video_evidence(project_root, meta, path)
            elif kind == "work-journals":
                status, output_count, reason, case_cards = _journal_evidence(project_root, title, path)
            else:
                status, output_count, reason = "未拆解", 0, "该输入类型尚未接入处理 Skill"
            # Video manifests already provide the stable source_id consumed by
            # the sequential pain-card ledger.  Re-hashing it here made the
            # workbench unable to prove a source belonged to an approved batch.
            canonical_id = str(meta.get("source_id") or "").strip() if kind == "video-sources" and not meta.get("manual_input") else ""
            row = {"source_id": canonical_id or _source_id(kind, rel, digest), "source_type": kind, "source_label": label, "title": title, "source_path": rel, "source_sha256": digest, "processing_output_count": output_count, "status": status, "status_reason": reason, "checked_at": datetime.now().astimezone().isoformat(timespec="seconds")}
            if kind == "video-sources":
                row["source_origin"] = "manual-file" if meta.get("manual_input") else "standardized"
            if kind == "work-journals":
                row["case_cards"] = case_cards
            rows.append(row)
    return rows


def rebuild_inventory(connection: Any, project_root: Path) -> list[dict[str, Any]]:
    rows = build_inventory(project_root)
    connection.execute("DELETE FROM input_inventory")
    connection.executemany("INSERT INTO input_inventory (source_id, source_type, source_label, title, source_path, source_sha256, processing_output_count, status, status_reason, checked_at) VALUES (:source_id,:source_type,:source_label,:title,:source_path,:source_sha256,:processing_output_count,:status,:status_reason,:checked_at)", rows)
    return rows


def inventory_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for kind, (label, _) in TYPES.items():
        subset = [r for r in rows if r["source_type"] == kind]
        no_case = sum(r["status"] == "已处理" for r in subset)
        result[kind] = {"label": label, "total": len(subset), "completed": sum(r["status"] in {"已拆解", "已处理"} for r in subset), "pending": sum(r["status"] == "未拆解" for r in subset), "review": sum(r["status"] == "待审核" for r in subset), "uncertain": sum(r["status"] == "来源不明确" for r in subset), "noCase": no_case}
    return result
