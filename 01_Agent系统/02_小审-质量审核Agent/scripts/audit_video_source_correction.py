"""小审：单篇视频文案校对版源文档独立审核。

只审不改。校对候选必须保留原识别版的完整绑定，并以可重放的修改
清单证明：校对后全文只来自错别字、标点、断句或重复音节的显式变更。
候选仅能存放在运行区；本脚本不会写入输入库或处理库。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCHEMA = "video-source-correction-candidate-v1"
ARTIFACT_TYPE = "video-source-correction-v1"
# 允许执行人将两个允许的基础类型合写（例如 OCR 同时出现重复音节
# 和错误标点）。“明显错别字”只是“错别字”的证据强度说明，不是润色。
ALLOWED_CHANGE_TYPES = {"错别字", "标点", "断句", "重复音节"}
TYPE_ALIASES = {
    "明显错别字": {"错别字"},
    "重复音节/标点": {"重复音节", "标点"},
    "标点/重复音节": {"重复音节", "标点"},
}
REQUIRED_CHECK_IDS = [
    "candidate-schema-and-source-binding",
    "original-source-hash",
    "corrected-text-hash",
    "change-ledger-shape-and-types",
    "change-offset-and-original-slice",
    "replay-without-unrecorded-rewrite",
    "pending-isolation",
]


@dataclass(frozen=True)
class Check:
    id: str
    layer: str
    name: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "layer": self.layer, "name": self.name, "status": self.status, "detail": self.detail}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def project_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value.strip("\"'")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = re.search(r"^---\s*$", text[3:], re.M)
    if not end:
        return {}, text
    header = text[3:3 + end.start()].strip("\r\n")
    body = text[3 + end.end():].lstrip("\r\n")
    result: dict[str, Any] = {}
    for raw in header.splitlines():
        match = re.match(r"^([\w\-\u4e00-\u9fff]+)\s*:\s*(.*)$", raw.rstrip())
        if match:
            result[match.group(1)] = scalar(match.group(2))
    return result, body


def section(body: str, heading: str) -> str:
    match = re.search(rf"^##\s+{re.escape(heading)}\s*$\s*(.*?)(?=^##\s+|\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def parse_ledger(body: str) -> tuple[list[dict[str, Any]], list[str]]:
    ledger_section = section(body, "修改清单")
    if not ledger_section:
        return [], ["缺少 ## 修改清单"]
    fenced = re.search(r"```jsonl\s*\n(.*?)```", ledger_section, re.S | re.I)
    if not fenced:
        return [], ["修改清单必须是 ```jsonl 代码块"]
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for number, line in enumerate(fenced.group(1).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            issues.append(f"修改清单第 {number} 行不是 JSON")
            continue
        if not isinstance(item, dict):
            issues.append(f"修改清单第 {number} 行不是对象")
            continue
        records.append(item)
    return records, issues


def load_source(path: Path) -> tuple[dict[str, Any], str, list[str]]:
    if not path.is_file():
        return {}, "", [f"原识别源文档不存在：{path}"]
    frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="strict"))
    full_text = section(body, "全文")
    issues = [] if full_text else ["原识别源文档缺少 ## 全文 或全文为空"]
    return frontmatter, full_text, issues


def make_check(identifier: str, layer: str, name: str, issues: list[str]) -> Check:
    return Check(identifier, layer, name, "failed" if issues else "passed", "；".join(issues) if issues else "通过")


def allowed_change_type(value: str) -> bool:
    """Allow only the four frozen base types, including explicit two-type labels."""
    if value in ALLOWED_CHANGE_TYPES or value in TYPE_ALIASES:
        return True
    parts = {part.strip() for part in re.split(r"[/、]", value) if part.strip()}
    return bool(parts) and parts <= ALLOWED_CHANGE_TYPES


def resolve_original_path(candidate: Path, value: str) -> Path:
    raw = Path(value)
    return raw.resolve() if raw.is_absolute() else (ROOT / raw).resolve()


def audit_candidate(candidate: Path) -> tuple[list[Check], dict[str, Any]]:
    if not candidate.is_file():
        checks = [make_check(identifier, "mechanical", identifier, [f"校对候选不存在：{candidate}"]) for identifier in REQUIRED_CHECK_IDS]
        return checks, {"candidate": project_rel(candidate), "change_count": 0}
    candidate_bytes = candidate.read_bytes()
    try:
        text = candidate_bytes.decode("utf-8")
    except UnicodeDecodeError:
        checks = [make_check(identifier, "mechanical", identifier, ["候选不是 UTF-8 文本"]) for identifier in REQUIRED_CHECK_IDS]
        return checks, {"candidate": project_rel(candidate), "change_count": 0}

    frontmatter, body = parse_frontmatter(text)
    schema_issues: list[str] = []
    if str(frontmatter.get("schema") or "") != SCHEMA:
        schema_issues.append(f"schema 必须是 {SCHEMA}")
    source_id = str(frontmatter.get("source_id") or "").strip()
    original_path_value = str(frontmatter.get("original_source_path") or "").strip()
    for key in ("source_id", "original_source_path", "original_source_sha256", "original_full_text_sha256", "corrected_full_text_sha256"):
        if not str(frontmatter.get(key) or "").strip():
            schema_issues.append(f"缺 frontmatter 字段：{key}")
    source_path = resolve_original_path(candidate, original_path_value) if original_path_value else ROOT / "__missing__"
    source_frontmatter, original_text, source_load_issues = load_source(source_path)
    if source_id and str(source_frontmatter.get("source_id") or "") != source_id:
        schema_issues.append("候选 source_id 与原识别源文档不一致")
    checks: list[Check] = [make_check("candidate-schema-and-source-binding", "mechanical", "候选合同与来源绑定", schema_issues)]

    original_hash_issues = list(source_load_issues)
    if source_path.is_file() and str(frontmatter.get("original_source_sha256") or "") != sha256_bytes(source_path.read_bytes()):
        original_hash_issues.append("original_source_sha256 与原识别源文档文件哈希不一致")
    if original_text and str(frontmatter.get("original_full_text_sha256") or "") != sha256_text(original_text):
        original_hash_issues.append("original_full_text_sha256 与原识别全文哈希不一致")
    checks.append(make_check("original-source-hash", "mechanical", "原识别版文件与全文哈希", original_hash_issues))

    corrected_text = section(body, "校对后全文")
    corrected_hash_issues: list[str] = []
    if not corrected_text:
        corrected_hash_issues.append("缺少 ## 校对后全文 或全文为空")
    elif str(frontmatter.get("corrected_full_text_sha256") or "") != sha256_text(corrected_text):
        corrected_hash_issues.append("corrected_full_text_sha256 与校对后全文不一致")
    checks.append(make_check("corrected-text-hash", "mechanical", "校对后全文哈希", corrected_hash_issues))

    ledger, ledger_parse_issues = parse_ledger(body)
    ledger_shape_issues = list(ledger_parse_issues)
    ledger_ids: set[str] = set()
    for number, change in enumerate(ledger, start=1):
        prefix = f"修改清单第 {number} 项"
        for key in ("change_id", "type", "original_start", "original_end", "original_text", "corrected_text", "reason", "status"):
            if key not in change:
                ledger_shape_issues.append(f"{prefix} 缺字段：{key}")
        change_id = str(change.get("change_id") or "")
        if change_id and change_id in ledger_ids:
            ledger_shape_issues.append(f"修改清单 change_id 重复：{change_id}")
        ledger_ids.add(change_id)
        change_type = str(change.get("type") or "")
        status = str(change.get("status") or "")
        if change_type != "待确认" and not allowed_change_type(change_type):
            ledger_shape_issues.append(f"{prefix} type 不允许：{change_type}")
        if change_type == "待确认" and status != "pending":
            ledger_shape_issues.append(f"{prefix} type=待确认 时 status 必须为 pending")
        if change_type in ALLOWED_CHANGE_TYPES and status != "applied":
            ledger_shape_issues.append(f"{prefix} 正式校对变更 status 必须为 applied")
    checks.append(make_check("change-ledger-shape-and-types", "mechanical", "修改清单字段与允许类型", ledger_shape_issues))

    offset_issues: list[str] = []
    applied: list[dict[str, Any]] = []
    for number, change in enumerate(ledger, start=1):
        prefix = f"修改清单第 {number} 项"
        change_type = str(change.get("type") or "")
        status = str(change.get("status") or "")
        if change_type == "待确认":
            if str(change.get("original_text") or "") != str(change.get("corrected_text") or ""):
                offset_issues.append(f"{prefix} 待确认项不得改变正文")
            continue
        if status != "applied":
            continue
        start, end = change.get("original_start"), change.get("original_end")
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
            offset_issues.append(f"{prefix} original_start/original_end 必须是整数")
            continue
        if start < 0 or end < start or end > len(original_text):
            offset_issues.append(f"{prefix} 原文偏移越界：{start}:{end}")
            continue
        listed = str(change.get("original_text") or "")
        actual = original_text[start:end]
        if listed != actual:
            offset_issues.append(f"{prefix} original_text 与原文偏移片段不一致")
        applied.append(change)
    ordered = sorted(applied, key=lambda item: (int(item.get("original_start", -1)), int(item.get("original_end", -1))))
    prior_end = -1
    for change in ordered:
        start = int(change["original_start"])
        if start < prior_end:
            offset_issues.append("已应用修改的原文偏移存在重叠")
        prior_end = max(prior_end, int(change["original_end"]))
    checks.append(make_check("change-offset-and-original-slice", "mechanical", "修改片段与原识别全文偏移", offset_issues))

    replay_issues: list[str] = []
    if not offset_issues and corrected_text:
        pieces: list[str] = []
        cursor = 0
        for change in ordered:
            start, end = int(change["original_start"]), int(change["original_end"])
            pieces.append(original_text[cursor:start])
            pieces.append(str(change.get("corrected_text") or ""))
            cursor = end
        pieces.append(original_text[cursor:])
        if "".join(pieces) != corrected_text:
            replay_issues.append("修改清单重放结果与校对后全文不一致，存在未记录文本改写或清单错误")
    checks.append(make_check("replay-without-unrecorded-rewrite", "content", "无未记录的文本改写", replay_issues))

    pending_issues: list[str] = []
    for number, change in enumerate(ledger, start=1):
        if str(change.get("status") or "") == "pending" and str(change.get("type") or "") != "待确认":
            pending_issues.append(f"修改清单第 {number} 项 pending 必须标为 type=待确认")
    checks.append(make_check("pending-isolation", "content", "待确认项隔离且不改正文", pending_issues))
    return checks, {
        "candidate": project_rel(candidate), "candidate_sha256": sha256_bytes(candidate_bytes),
        "source_id": source_id, "original_source_path": project_rel(source_path),
        "change_count": len(ledger), "applied_change_count": len(applied),
        "pending_change_count": sum(1 for item in ledger if str(item.get("status") or "") == "pending"),
    }


def write_receipt(receipt_path: Path, task_id: str, attempt: int, candidate: Path, checks: list[Check], notes: dict[str, Any]) -> dict[str, Any]:
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    mechanical_path = receipt_path.with_name(receipt_path.stem + ".mechanical.json")
    semantic_path = receipt_path.with_name(receipt_path.stem + ".semantic-review.json")
    mechanical = [item.as_dict() for item in checks if item.layer == "mechanical"]
    semantic = [item.as_dict() for item in checks if item.layer != "mechanical"]
    mechanical_path.write_text(json.dumps({"schema": "video-source-correction-mechanical-audit-v1", "checks": mechanical, "notes": notes, "audited_at": now()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    semantic_path.write_text(json.dumps({"schema": "video-source-correction-semantic-review-v1", "reviewer": "xiaoshen", "checks": semantic, "notes": notes, "audited_at": now()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidate_hash = sha256_bytes(candidate.read_bytes()) if candidate.is_file() else ""
    status = "approved" if all(item.status == "passed" for item in checks) else "rejected"
    payload = {
        "schema": "audit-receipt-v3", "artifactType": ARTIFACT_TYPE, "status": status,
        "task_id": task_id, "attempt": attempt, "auditor": "xiaoshen", "auditor_skill_id": "xiaoshen-audit", "auditor_version": "3.4.0",
        "generatedAt": now(), "audited_at": now(), "required_check_ids": REQUIRED_CHECK_IDS,
        "subject": {"candidate": project_rel(candidate), "candidateSha256": candidate_hash, "source_id": notes.get("source_id", "")},
        "artifact": {"type": ARTIFACT_TYPE, "artifact_id": f"video-source-correction-audit:{candidate_hash[:12]}", "candidate_path": project_rel(candidate), "candidate_sha256": candidate_hash, "source_path": notes.get("original_source_path", ""), "source_sha256": ""},
        "checks": [item.as_dict() for item in checks],
        "mechanical_result": {"status": "passed" if all(item["status"] == "passed" for item in mechanical) else "failed", "path": project_rel(mechanical_path), "sha256": sha256_bytes(mechanical_path.read_bytes()), "check_ids": [item["id"] for item in mechanical]},
        "semantic_review": {"status": "passed" if all(item["status"] == "passed" for item in semantic) else "failed", "path": project_rel(semantic_path), "sha256": sha256_bytes(semantic_path.read_bytes()), "reviewer": "xiaoshen", "required_block_ids": [item["id"] for item in semantic]},
        "original_outputs": [{"path": project_rel(candidate), "sha256": candidate_hash}], "final_outputs": [{"path": project_rel(candidate), "sha256": candidate_hash}],
        "notes": notes, "note": "仅审核，未改写校对候选或原识别源文档。",
    }
    receipt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审核单篇视频文案校对版候选；只审不改")
    parser.add_argument("--candidate", required=True, help="运行区内的校对版 Markdown 候选")
    parser.add_argument("--receipt", required=True, help="审核回执 JSON 输出路径（必须在运行区）")
    parser.add_argument("--task-id", default="", help="16 位小写十六进制；省略则从候选路径生成")
    parser.add_argument("--attempt", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate, receipt_path = Path(args.candidate).resolve(), Path(args.receipt).resolve()
    if ".runtime" not in candidate.parts:
        raise SystemExit("--candidate 必须位于 .runtime 运行区，校对候选不得直接写入正式资产目录")
    if ".runtime" not in receipt_path.parts:
        raise SystemExit("--receipt 必须位于 .runtime 运行区")
    default_task_id = hashlib.sha256(project_rel(candidate).encode("utf-8")).hexdigest()[:16]
    task_id = args.task_id or default_task_id
    if not re.fullmatch(r"[a-f0-9]{16}", task_id):
        raise SystemExit("--task-id 必须是 16 位小写十六进制")
    checks, notes = audit_candidate(candidate)
    payload = write_receipt(receipt_path, task_id, args.attempt, candidate, checks, notes)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "approved" else 2


if __name__ == "__main__":
    sys.exit(main())
