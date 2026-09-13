"""只为现役通用文案链路建立可再生查询索引。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
import uuid
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_IMPORT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_IMPORT_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(PROJECT_IMPORT_ROOT))
from workflow.module_function_index import build_rows, write_index, _case_card_rows
from workflow.benchmark_cases import get_case, load_registry
from workflow.universal_copy_contract import digest as contract_digest, parse_breakdown, valid_function
from workflow.asset_paths import ASSET_PATHS, relative as asset_relative, resolve as asset_resolve
from workflow.input_inventory import build_inventory, inventory_summary
from workflow.topic_structure_releases import load_release_index, verified_final_copy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "02_资产中心"
DATA_ROOT = PROJECT_ROOT / "04_数据中心"
MASTER_ROOT = DATA_ROOT / "01_主数据"
EVENT_ROOT = DATA_ROOT / "02_事件流水"
INDEX_ROOT = DATA_ROOT / "03_查询索引"
SNAPSHOT_ROOT = DATA_ROOT / "04_快照"
EXPORT_ROOT = DATA_ROOT / "05_导出"
MIGRATION_ROOT = DATA_ROOT / "06_迁移报告"
TOPIC_ROOT = asset_resolve(PROJECT_ROOT, "topics.tables")
STRUCTURE_ROOT = asset_resolve(PROJECT_ROOT, "output.structures")
COPY_ROOT = asset_resolve(PROJECT_ROOT, "output.copies")
BENCHMARK_VIDEO_SOURCE_ROOT = asset_resolve(PROJECT_ROOT, "cases.source")
BENCHMARK_VIDEO_BREAKDOWN_ROOT = asset_resolve(PROJECT_ROOT, "cases.breakdowns")
FORMAL_AUDIT_ROOT = PROJECT_ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "00_正式审核回执"
OWNER_APPROVAL_ROOT = PROJECT_ROOT / "01_Agent系统" / "01_小姜-CEO助理Agent" / "人工确认回执" / "benchmark-video-structure"
REGISTRY_FILE = MASTER_ROOT / "content-registry.json"
EVENT_FILE = EVENT_ROOT / "events.jsonl"
SNAPSHOT_FILE = SNAPSHOT_ROOT / "latest.json"
DATABASE_FILE = INDEX_ROOT / "factory-data.db"

def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def _relative(path: Path) -> str:
    try: return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError: return str(path.resolve())

def _walk(root: Path, suffix: str | None = None) -> list[Path]:
    if not root.is_dir(): return []
    return sorted(
        p for p in root.rglob("*")
        if p.is_file()
        and not any(part == "__pycache__" for part in p.parts)
        # `_private` is neither an asset type nor an archive location.  It is
        # a legacy recovery scratch name and must never become an active data
        # center entity if an interrupted job leaves one behind.
        and "_private" not in p.parts
        and p.name not in {"README.md", ".gitkeep", ".DS_Store", "Thumbs.db"}
        and not p.name.startswith(".")
        and (suffix is None or p.suffix.lower() == suffix)
    )

def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: PermissionError | None = None
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for attempt in range(8):
        temporary_root = PROJECT_ROOT / ".runtime" / "data-center-tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temp = temporary_root / f"{path.name}.{uuid.uuid4().hex}.tmp"
        try:
            temp.write_text(rendered, encoding="utf-8")
            os.replace(temp, path)
            return
        except PermissionError as exc:
            last_error = exc
            temp.unlink(missing_ok=True)
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"数据中心文件被外部程序锁定，已重试 8 次：{path}") from last_error

def normalize_title(value: str) -> str:
    return " ".join(re.sub(r"【[A-Z]{3}-\d{3}】", "", value).replace("（复刻拆解）", "").replace("（视频原文）", "").split()).strip()

def _topic_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file in _walk(TOPIC_ROOT):
        if file.suffix.lower() == ".csv":
            import csv
            with file.open(encoding="utf-8-sig", newline="") as handle:
                rows.extend({**row, "_source": _relative(file)} for row in csv.DictReader(handle))
        elif file.suffix.lower() == ".xlsx":
            try:
                from openpyxl import load_workbook
                sheet = load_workbook(file, read_only=True, data_only=True).active
                values = list(sheet.iter_rows(values_only=True))
                if values:
                    headers = [str(value or "").strip() for value in values[0]]
                    rows.extend({**{headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}, "_source": _relative(file)} for row in values[1:] if any(value not in (None, "") for value in row))
            except Exception:
                continue
        elif file.suffix.lower() == ".md":
            lines = file.read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines[:-1]):
                if not line.strip().startswith("|") or not lines[index + 1].strip().startswith("|"):
                    continue
                headers = [item.strip() for item in line.strip().strip("|").split("|")]
                if "选题" not in headers:
                    continue
                for body in lines[index + 2:]:
                    if not body.strip().startswith("|"):
                        break
                    values = [item.strip() for item in body.strip().strip("|").split("|")]
                    if len(values) == len(headers):
                        rows.append({**dict(zip(headers, values)), "_source": _relative(file)})
    return rows

def _approved_receipts() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for receipt in (FORMAL_AUDIT_ROOT / "benchmark-video-structure").glob("*_审核回执.json"):
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            case_id = str(data.get("benchmark_case_id") or "")
            if data.get("status") == "approved" and case_id:
                result[case_id] = receipt
        except (OSError, json.JSONDecodeError): pass
    for receipt in OWNER_APPROVAL_ROOT.glob("*_人工确认回执.json"):
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            case_id = str(data.get("benchmark_case_id") or "")
            if data.get("status") == "approved" and case_id:
                result[case_id] = receipt
        except (OSError, json.JSONDecodeError): pass
    return result

def _entities() -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for path in _walk(BENCHMARK_VIDEO_SOURCE_ROOT, ".md"):
        entities.append({"kind":"benchmark-video-source","title":normalize_title(path.stem),"path":_relative(path),"sha256":_sha256(path)})
    receipts = _approved_receipts()
    cases = {str(case["id"]): case for case in load_registry()["cases"]}
    for case_id, case in cases.items():
        resolved = get_case(case_id)
        path = Path(resolved["breakdownPath"])
        source = Path(resolved["sourcePath"])
        receipt = Path(resolved["auditPath"]) if Path(resolved["auditPath"]).is_file() else receipts.get(case_id)
        receipt_data = json.loads(receipt.read_text(encoding="utf-8")) if receipt else {}
        receipt_matches_current = bool(
            receipt and path.is_file() and source.is_file()
            and receipt_data.get("output_sha256") == _sha256(path)
            and receipt_data.get("source_sha256") == _sha256(source)
        )
        status = "approved" if receipt_matches_current else "unverified"
        if path.is_file():
            try:
                from workflow.benchmark_structure_v2 import framework_payload, parse_markdown
                blocks = framework_payload(parse_markdown(path))
                blueprint_hash = hashlib.sha256(json.dumps(blocks, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
                usable = status == "approved" and bool(blocks)
            except ValueError:
                blueprint_hash, usable = "", False
            entities.append({
                "kind":"benchmark-video-breakdown",
                "benchmark_case_id":case_id,
                "type":str(case.get("type") or ""),
                "title":normalize_title(path.stem),
                "path":_relative(path),
                "sourcePath":_relative(source),
                "sourceSha256":_sha256(source) if source.is_file() else "",
                "sha256":_sha256(path),
                "frameworkSha256":blueprint_hash,
                "auditStatus":status,
                "auditReceiptPath":_relative(receipt) if receipt else "",
                "caseListPath":"02_资产中心/05_案例库/清单/对标案例清单.jsonl",
                "statusReason":"当前三列表与源稿哈希均已获小审 approved" if status == "approved" else "当前正式文件未取得匹配哈希的 approved 小审回执",
                "frameworkBlocks":receipt_data.get("framework_blocks", []),
                "bigFrameworkUsable":usable,
            })
    for row in _topic_rows():
        title = str(row.get("选题") or "").strip()
        if title: entities.append({"kind":"topic","title":title,"path":str(row["_source"]),"selected":str(row.get("是否选中") or ""),"benchmark_case_id":str(row.get("对标复刻拆解编号") or "")})
    for path in _walk(STRUCTURE_ROOT, ".md"):
        entities.append({"kind":"copy-structure","title":normalize_title(path.stem),"path":_relative(path),"sha256":_sha256(path)})
    for path in _walk(COPY_ROOT, ".md"):
        entities.append({"kind":"final-copy","title":normalize_title(path.stem),"path":_relative(path),"sha256":_sha256(path)})
    for row in _case_card_rows():
        entities.append({
            "kind": "case-card-v12",
            "caseId": row.get("caseId"),
            "title": str(row.get("title") or ""),
            "path": str(row.get("path") or ""),
            "sourcePath": str(row.get("sourcePath") or ""),
            "sourceSha256": str(row.get("sourceSha256") or ""),
            "auditReceiptPath": str(row.get("auditReceiptPath") or ""),
            "sha256": str(row.get("contentSha256") or ""),
        })
    return entities

def _active_asset_counts() -> tuple[dict[str, int], dict[str, int], dict[str, Any]]:
    """Build one read-only snapshot from the active path registry only."""
    source_counts = {path: len(_walk(asset_resolve(PROJECT_ROOT, key))) for key, path in ASSET_PATHS.items()}
    formal_case_cards = list(_case_card_rows())
    # 案例目录还包含转写、索引与后台记录；它们不是可调用内容模块。
    source_counts[asset_relative("process.cases")] = len(formal_case_cards)
    inventory = inventory_summary(build_inventory(PROJECT_ROOT))
    input_total = sum(int(item["total"]) for item in inventory.values())
    process_total = sum(source_counts[asset_relative(key)] for key in ASSET_PATHS if key.startswith("process."))
    # V1 treats structures and copies as the output library.  Counting a
    # structure a second time as a process module created inconsistent totals
    # between the data center, asset map, and six-stage pipeline.
    output_total = (
        source_counts[asset_relative("output.structures")]
        + source_counts[asset_relative("output.copies")]
    )
    published_copy_total = _published_final_copy_count()
    metrics = {
        "inputSources": input_total,
        "inputCompleted": sum(int(item["completed"]) for item in inventory.values()),
        "inputPending": sum(int(item["pending"]) for item in inventory.values()),
        "inputNoCase": sum(int(item.get("noCase", 0)) for item in inventory.values()),
        "inputInventory": inventory,
        "contentModules": process_total,
        "caseCards": len(formal_case_cards),
        "benchmarkBreakdowns": len(_walk(BENCHMARK_VIDEO_BREAKDOWN_ROOT, ".md")),
        "structures": source_counts[asset_relative("output.structures")],
        # A raw Markdown file is not a formal output.  Only the hash-verified
        # structure-release index with an approved final-copy receipt counts.
        "outputCopies": published_copy_total,
        "galleryTopics": _gallery_topic_folder_count(),
    }
    metrics["assetUpdates"] = _asset_update_history(90)
    metrics["weeklyUpdates"] = metrics["assetUpdates"][-7:]
    return source_counts, {"input": input_total, "process": process_total, "output": output_total}, metrics


def _published_final_copy_count() -> int:
    """Count legacy publications and current hash-verified final-copy bindings."""
    paths: set[Path] = set()
    audit_root = FORMAL_AUDIT_ROOT / "final-copy"
    for publication_path in audit_root.glob("*.json") if audit_root.is_dir() else []:
        try:
            publication = json.loads(publication_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if publication.get("schema") != "final-copy-publication-v1" or publication.get("status") != "published":
            continue
        formal = Path(str(publication.get("formalPath") or "")).resolve()
        receipt = Path(str(publication.get("auditReceipt") or "")).resolve()
        if not formal.is_relative_to(COPY_ROOT.resolve()) or not formal.is_file() or not receipt.is_file() or publication.get("formalSha256") != _sha256(formal):
            continue
        try:
            audit = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if audit.get("artifactType") in {"final-copy-v2", "final-copy-v3"} and audit.get("status") == "approved":
            paths.add(formal)
    try:
        for entry in load_release_index().get("entries", []):
            if not isinstance(entry, dict) or not verified_final_copy(entry):
                continue
            formal = Path(str((entry.get("final_copy") or {}).get("output_path") or "")).resolve()
            if formal.is_relative_to(COPY_ROOT.resolve()):
                paths.add(formal)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return len(paths)


def _asset_update_history(days: int = 90) -> list[dict[str, Any]]:
    """Count real active-asset file modifications by local calendar day."""
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=days - 1)
    counts = {start + timedelta(days=offset): 0 for offset in range(days)}
    seen: set[Path] = set()
    for key in ASSET_PATHS:
        for path in _walk(asset_resolve(PROJECT_ROOT, key)):
            resolved = path.resolve()
            if resolved in seen or path.name in {".gitkeep", "README.md", "readme.md"}:
                continue
            if "99_归档" in path.parts:
                continue
            seen.add(resolved)
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone().date()
            except OSError:
                continue
            if modified in counts:
                counts[modified] += 1
    return [{"date": item.isoformat(), "count": counts[item]} for item in sorted(counts)]


def _source_counts() -> dict[str, int]:
    """Compatibility metrics retained for external read-only consumers."""
    _source_counts_by_path, _totals, metrics = _active_asset_counts()
    return {"输入库": metrics["inputSources"], "处理库": metrics["contentModules"], "对标案例": metrics["benchmarkBreakdowns"], "配图库": metrics["galleryTopics"]}

def _gallery_topic_folder_count() -> int:
    root = ASSET_ROOT / "06_配图库"
    return len([p for p in root.iterdir() if p.is_dir()]) if root.is_dir() else 0

def build_snapshot() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    entities = _entities()
    source_counts, asset_totals, metrics = _active_asset_counts()
    snapshot = {
        "schema":"factory-data-v4", "generatedAt":_now(), "pipeline":"active-six-module",
        "metrics": {**_source_counts(), **metrics}, "assetSourceCounts": source_counts,
        "assetTotals": asset_totals, "entities":len(entities), "legacyCompatibility":False,
        "operations": {"source":"active-asset-path-registry", "mode":"read-only-reconciliation"},
        "migration": {"activePathRegistry":"workflow/asset_paths.py", "archivedPathsExcluded":True},
    }
    return snapshot, entities, {"indexed":len(entities),"pipeline":"universal-copy-v1"}

def _write_database(entities: list[dict[str, Any]]) -> None:
    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_FILE) as conn:
        conn.execute("DROP TABLE IF EXISTS entities")
        conn.execute("CREATE TABLE entities (entity_id TEXT PRIMARY KEY, kind TEXT, title TEXT, path TEXT, payload TEXT)")
        conn.executemany("INSERT INTO entities VALUES (?, ?, ?, ?, ?)", [(f"{e.get('kind','')}:{index}",str(e.get("kind","")),str(e.get("title","")),str(e.get("path","")),json.dumps(e,ensure_ascii=False)) for index, e in enumerate(entities)])

def refresh_data_center(*, reason: str = "manual-refresh", producer: str = "system") -> dict[str, Any]:
    for directory in (MASTER_ROOT, EVENT_ROOT, INDEX_ROOT, SNAPSHOT_ROOT, EXPORT_ROOT, MIGRATION_ROOT): directory.mkdir(parents=True, exist_ok=True)
    index_error = ""
    try:
        write_index(build_rows())
    except RuntimeError as exc:
        index_error = str(exc)
    snapshot, entities, report = build_snapshot()
    snapshot["reason"] = reason; snapshot["producer"] = producer
    snapshot["moduleFunctionIndex"] = {"status": "stale", "reason": index_error} if index_error else {"status": "current"}
    _atomic_json(REGISTRY_FILE, {"schema":"content-registry-v3","generatedAt":snapshot["generatedAt"],"entities":entities})
    _atomic_json(SNAPSHOT_FILE, snapshot)
    _atomic_json(MIGRATION_ROOT / "latest.json", report)
    _write_database(entities)
    append_data_event("data-center-refreshed", {"reason":reason,"entities":len(entities),"moduleFunctionIndex":"stale" if index_error else "current"}, producer=producer)
    return snapshot

def load_snapshot() -> dict[str, Any] | None:
    try: return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return None

def append_data_event(event_type: str, payload: dict[str, Any], *, producer: str) -> None:
    EVENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with EVENT_FILE.open("a", encoding="utf-8") as handle: handle.write(json.dumps({"occurredAt":_now(),"eventType":event_type,"producer":producer,"payload":payload},ensure_ascii=False)+"\n")

def data_entities(limit: int = 500) -> list[dict[str, Any]]:
    try: return json.loads(REGISTRY_FILE.read_text(encoding="utf-8")).get("entities", [])[:limit]
    except (OSError, json.JSONDecodeError): return []

def data_events(limit: int = 300) -> list[dict[str, Any]]:
    try: return [json.loads(line) for line in EVENT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()][-limit:]
    except (OSError, json.JSONDecodeError): return []

def verified_final_copy_bindings(project_root: Path, copy_root: Path, receipt_root: Path) -> dict[tuple[str, str], dict[str, str]]:
    return {}

def record_today_refresh_completion(
    source_type: str,
    *,
    task_id: str = "",
    skill: str = "",
    completion_basis: str = "",
    audit_receipt_path: str = "",
    producer: str = "system",
) -> None:
    """Write the proven terminal result of one today-work visible task.

    The event is deliberately a small audit reference rather than a copy of
    its prompt or source contents, so the data center can correlate a refresh
    with the actual visible Codex task without turning historical task text
    into a second source of truth.
    """
    append_data_event(
        "source-refresh-completed",
        {
            "sourceType": source_type,
            "taskId": task_id,
            "skill": skill,
            "completionBasis": completion_basis,
            "auditReceiptPath": audit_receipt_path,
        },
        producer=producer,
    )

def _main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--reason", default="manual-refresh"); args = parser.parse_args()
    print(json.dumps(refresh_data_center(reason=args.reason), ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(_main())
