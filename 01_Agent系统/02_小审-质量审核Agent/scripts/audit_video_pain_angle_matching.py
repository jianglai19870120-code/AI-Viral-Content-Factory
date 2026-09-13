"""小审：视频痛点卡角度索引与结构选择的独立匹配门禁。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_PATH_PARTS = ("99_归档", "00_分类法", "分类法", ".runtime", "video-pain-card-v1")
REASON_FIELDS = ("target_people", "scene", "core_contradiction", "functional_fit")


def resolved(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^## 全文\s*\n\s*(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return (match.group(1) if match else text).strip()


def card_angles(path: Path) -> list[tuple[int, str, str]]:
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw:
        raise ValueError("正式人读卡必须为 UTF-8，不能是 UTF-16 或包含 NUL")
    text = raw.decode("utf-8")
    if not text.startswith("# 痛点卡｜"):
        raise ValueError("不是正式人读痛点卡")
    pattern = re.compile(r"^### 角度[ \t]*(\d+)｜([^\r\n]+)(?:\r?\n)+#### 表达方式[ \t]*(?:\r?\n)+\s*(.*?)(?=\r?\n\r?\n来源：)", re.M | re.S)
    return [(int(number), title.strip(), expression.strip()) for number, title, expression in pattern.findall(text)]


def anchor_ok(anchor: Any, source_root: Path) -> str | None:
    if not isinstance(anchor, dict):
        return "缺 source_anchor 对象"
    required = ("source_id", "original_source_path", "original_full_text_sha256", "start_offset", "end_offset", "original_excerpt")
    if any(anchor.get(key) in (None, "") for key in required):
        return "source_anchor 缺少来源、哈希、偏移或原文片段"
    path = resolved(str(anchor["original_source_path"]))
    if not path.is_file() or source_root.resolve() not in path.resolve().parents:
        return "source_anchor 指向非标准化原文"
    full = source_text(path)
    if hashlib.sha256(full.encode("utf-8")).hexdigest() != str(anchor["original_full_text_sha256"]):
        return "source_anchor 原文全文哈希不匹配"
    try:
        start, end = int(anchor["start_offset"]), int(anchor["end_offset"])
    except (TypeError, ValueError):
        return "source_anchor 偏移不是整数"
    excerpt = str(anchor["original_excerpt"])
    if start < 0 or end <= start or full[start:end] != excerpt:
        return "source_anchor 偏移无法逐字回到原文"
    return None


def angle_index_checks(angle_index: Path, pain_index: Path, pain_root: Path, source_root: Path) -> list[str]:
    issues: list[str] = []
    rows = jsonl(angle_index)
    pain_rows = {str(row.get("pain_id") or ""): row for row in jsonl(pain_index) if row.get("module_type") == "pain"}
    seen_ids: set[str] = set()
    indexed_card_keys: set[tuple[Path, int, str, str]] = set()
    for position, row in enumerate(rows, 1):
        if row.get("schema") != "video-pain-angle-index-v1" or row.get("status") != "active":
            issues.append(f"角度索引第 {position} 行 schema 或 active 状态不正确")
        angle_id = str(row.get("angle_id") or "")
        if not angle_id or angle_id in seen_ids:
            issues.append(f"角度索引第 {position} 行 angle_id 缺失或重复")
        seen_ids.add(angle_id)
        pain_id = str(row.get("pain_id") or "")
        card_path = resolved(str(row.get("card_path") or ""))
        if pain_id not in pain_rows or card_path != resolved(str(pain_rows.get(pain_id, {}).get("module_path") or "")):
            issues.append(f"{angle_id} 未与正式 pain 索引卡一一对应")
        if any(part in str(card_path) for part in FORBIDDEN_PATH_PARTS) or pain_root.resolve() not in card_path.parents:
            issues.append(f"{angle_id} 指向归档、分类法、旧格式或非正式卡")
        if not card_path.is_file() or row.get("card_sha256") != sha(card_path):
            issues.append(f"{angle_id} 正式卡不存在或哈希漂移")
            continue
        try:
            angles = card_angles(card_path)
        except (ValueError, UnicodeDecodeError) as exc:
            issues.append(f"{angle_id} {exc}")
            continue
        ordinal, title = row.get("angle_ordinal"), str(row.get("angle_title") or "")
        match = next((expr for number, card_title, expr in angles if number == ordinal and card_title == title), None)
        if match is None:
            issues.append(f"{angle_id} 未与正式卡角度标题及序号一一对应")
        else:
            expression_hash = hashlib.sha256(match.encode("utf-8")).hexdigest()
            key = (card_path, int(ordinal), title, expression_hash)
            if key in indexed_card_keys:
                issues.append(f"{angle_id} 重复映射同一个正式卡角度")
            indexed_card_keys.add(key)
            if row.get("expression_sha256") != expression_hash:
                issues.append(f"{angle_id} 表达哈希与正式卡不一致")
        anchor_issue = anchor_ok(row.get("source_anchor"), source_root)
        if anchor_issue:
            issues.append(f"{angle_id} {anchor_issue}")
        for key in ("target_people", "scene_tags", "core_contradiction"):
            value = row.get(key)
            if not value or (isinstance(value, list) and not any(str(item).strip() for item in value)):
                issues.append(f"{angle_id} 缺少 {key}")
    for pain_id, row in pain_rows.items():
        card_path = resolved(str(row.get("module_path") or ""))
        if not card_path.is_file():
            continue
        try:
            for number, title, expression in card_angles(card_path):
                key = (card_path, number, title, hashlib.sha256(expression.encode("utf-8")).hexdigest())
                if key not in indexed_card_keys:
                    issues.append(f"正式卡 {pain_id} 的角度 {number} 未进入活跃角度索引")
        except (ValueError, UnicodeDecodeError) as exc:
            issues.append(f"正式卡 {pain_id} {exc}")
    return issues


def release_checks(previous: Path, current: Path, affected_pain_ids: set[str]) -> list[str]:
    issues: list[str] = []
    prior = {str(row.get("angle_id") or ""): row for row in jsonl(previous)}
    now = {str(row.get("angle_id") or ""): row for row in jsonl(current)}
    for angle_id, row in prior.items():
        if row.get("pain_id") not in affected_pain_ids:
            if angle_id not in now:
                issues.append(f"未受影响角度 {angle_id} 被错误删除")
            elif now[angle_id] != row:
                issues.append(f"未受影响角度 {angle_id} 的 ID、来源锚点或表达发生漂移")
        elif angle_id in now:
            old_anchor = row.get("source_anchor")
            if now[angle_id].get("source_anchor") != old_anchor:
                issues.append(f"保留的旧角度 {angle_id} 变更了来源锚点")
    return issues


def tree_sha(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8")); digest.update(b"\0")
        digest.update(sha(path).encode("ascii")); digest.update(b"\n")
    return digest.hexdigest()


def migration_checks(manifest_path: Path, source_root: Path, formal_index: Path | None = None, expected_formal_index_sha256: str = "") -> list[str]:
    """Audit a private marker/index migration without treating staging as formal."""
    issues: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "video-pain-angle-migration-v1" or manifest.get("status") != "staged_pending_angle_audit":
        issues.append("迁移清单 schema 或待审核状态不正确")
    baseline_root = resolved(str(manifest.get("baseline_card_root") or "")); staging_root = resolved(str(manifest.get("staging_card_root") or ""))
    approved_root = resolved(str(manifest.get("approved_machine_runtime_root") or "")); angle_path = resolved(str(manifest.get("staging_angle_index") or ""))
    for root, expected, label in ((baseline_root, manifest.get("baseline_card_root_sha256"), "正式基线卡根"), (staging_root, manifest.get("staging_card_root_sha256"), "暂存卡根"), (approved_root, manifest.get("approved_machine_runtime_root_sha256"), "已审机器证据最小池")):
        if not root.is_dir() or tree_sha(root) != expected:
            issues.append(f"{label} 不存在或哈希漂移")
    if not angle_path.is_file() or sha(angle_path) != manifest.get("staging_angle_index_sha256"):
        issues.append("暂存专用角度索引不存在或哈希漂移")
        return issues
    try:
        index_rows = jsonl(angle_path)
    except (OSError, json.JSONDecodeError):
        return issues + ["暂存专用角度索引不是有效 JSONL"]
    if manifest.get("card_count") != 14 or manifest.get("angle_count") != 17 or len(index_rows) != 17:
        issues.append("迁移包必须精确覆盖 14 张卡与 17 个角度")
    if formal_index is not None:
        if not formal_index.is_file() or sha(formal_index) != expected_formal_index_sha256:
            issues.append("正式旧索引不存在或迁移期间发生哈希漂移")
        else:
            try:
                legacy_rows = jsonl(formal_index)
                if len(legacy_rows) != 14 or any("angle_id" in row or "angle_ids" in row for row in legacy_rows):
                    issues.append("正式旧索引范围或字段已被迁移操作提前改写")
            except (OSError, json.JSONDecodeError):
                issues.append("正式旧索引不是有效 JSONL")
    by_id = {str(row.get("angle_id") or ""): row for row in index_rows}
    if len(by_id) != len(index_rows) or any(not angle_id for angle_id in by_id):
        issues.append("暂存专用索引 angle_id 缺失或重复")
    cards = manifest.get("cards", []) if isinstance(manifest.get("cards"), list) else []
    if len(cards) != 14:
        issues.append("迁移清单卡片数不为 14")
    for item in cards:
        if not isinstance(item, dict):
            issues.append("迁移清单含非对象卡片项"); continue
        baseline = resolved(str(item.get("baseline_card_path") or "")); staged = resolved(str(item.get("staging_card_path") or "")); pain_id = str(item.get("pain_id") or "")
        if not baseline.is_file() or baseline_root not in baseline.parents or sha(baseline) != item.get("baseline_card_sha256"):
            issues.append(f"{pain_id} 正式基线卡不存在、越界或哈希漂移")
        if not staged.is_file() or staging_root not in staged.parents or sha(staged) != item.get("staging_card_sha256"):
            issues.append(f"{pain_id} 暂存卡不存在、越界或哈希漂移"); continue
        base_bytes, stage_bytes = baseline.read_bytes(), staged.read_bytes()
        if stage_bytes.startswith(b"\xef\xbb\xbf") or stage_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in stage_bytes:
            issues.append(f"{pain_id} 暂存卡不是无 BOM 的 UTF-8")
            continue
        try:
            base_text, stage_text = base_bytes.decode("utf-8"), stage_bytes.decode("utf-8")
        except UnicodeDecodeError:
            issues.append(f"{pain_id} 暂存卡不能按 UTF-8 读取"); continue
        marker_ids = re.findall(r"<!--\s*pain-angle-id:\s*([A-Za-z0-9_-]+)\s*-->\r?\n", stage_text)
        expected_ids = item.get("angle_ids", []) if isinstance(item.get("angle_ids"), list) else []
        if set(marker_ids) != set(expected_ids) or len(marker_ids) != len(expected_ids) or len(marker_ids) != len(card_angles(staged)):
            issues.append(f"{pain_id} 隐藏 angle_id 标记缺失、重复或未与角度一一对应")
        normalized = re.sub(r"<!--\s*pain-angle-id:\s*[A-Za-z0-9_-]+\s*-->\r?\n", "", stage_text).replace("\r\n", "\n")
        if normalized != base_text.replace("\r\n", "\n"):
            issues.append(f"{pain_id} 暂存卡除隐藏 angle_id 外发生正文、标题或来源漂移")
        try:
            staged_angles = card_angles(staged)
        except (ValueError, UnicodeDecodeError) as exc:
            issues.append(f"{pain_id} {exc}"); continue
        for marker_id, (ordinal, title, expression) in zip(marker_ids, staged_angles):
            row = by_id.get(marker_id, {})
            if (row.get("schema") != "video-pain-angle-index-v1" or row.get("status") != "active" or row.get("pain_id") != pain_id
                    or resolved(str(row.get("card_path") or "")) != staged or row.get("card_sha256") != sha(staged)
                    or row.get("angle_ordinal") != ordinal or row.get("angle_title") != title
                    or row.get("expression_sha256") != hashlib.sha256(expression.encode("utf-8")).hexdigest()):
                issues.append(f"{marker_id} 未与暂存卡角度、标题或表达一一对应")
            if any(part in str(row.get("card_path") or "") for part in ("99_归档", "00_分类法", "分类法")):
                issues.append(f"{marker_id} 混入归档或分类法路径")
            source_issue = anchor_ok(row.get("source_anchor"), source_root)
            if source_issue:
                issues.append(f"{marker_id} {source_issue}")
            for key in ("target_people", "scene_tags", "core_contradiction"):
                if not row.get(key): issues.append(f"{marker_id} 缺少 {key}")
    declared = {angle_id for item in cards if isinstance(item, dict) for angle_id in (item.get("angle_ids", []) if isinstance(item.get("angle_ids"), list) else [])}
    if declared != set(by_id):
        issues.append("迁移清单与专用索引的 17 个 angle_id 范围不一致")
    return issues


def switch_checks(manifest_path: Path, commit_receipt: Path, source_root: Path, structure_contract: Path, structure_skill: Path) -> list[str]:
    """Read-only post-release verification for the marker/index atomic switch."""
    issues: list[str] = []
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); receipt = json.loads(commit_receipt.read_text(encoding="utf-8"))
    if manifest.get("schema") != "video-pain-angle-switch-v1" or manifest.get("status") != "committed": issues.append("正式切换清单 schema 或状态不正确")
    if receipt.get("schema") != "video-pain-angle-migration-commit-v1" or receipt.get("status") != "committed": issues.append("正式切换提交回执 schema 或状态不正确")
    if resolved(str(receipt.get("switch_manifest") or "")) != manifest_path.resolve() or receipt.get("switch_manifest_sha256") != sha(manifest_path): issues.append("提交回执未精确绑定当前切换清单")
    source_manifest = resolved(str(manifest.get("source_manifest") or "")); audit = resolved(str(manifest.get("audit_receipt") or ""))
    if not source_manifest.is_file() or manifest.get("source_manifest_sha256") != sha(source_manifest): issues.append("切换清单未绑定已审迁移来源清单")
    if not audit.is_file() or manifest.get("audit_receipt_sha256") != sha(audit) or json.loads(audit.read_text(encoding="utf-8")).get("status") != "approved": issues.append("切换清单未绑定 approved 迁移审核回执")
    angle_path = resolved(str(manifest.get("formal_angle_index") or "")); retired = resolved(str(manifest.get("retired_video_module_index") or "")); archived_index = resolved(str(manifest.get("archive_legacy_index") or "")); generic = resolved(str(manifest.get("generic_function_index") or ""))
    if not angle_path.is_file() or sha(angle_path) != manifest.get("formal_angle_index_sha256"): issues.append("正式专用角度索引不存在或哈希漂移")
    if not archived_index.is_file() or sha(archived_index) != manifest.get("archive_legacy_index_sha256"): issues.append("旧视频索引归档缺失或哈希不匹配")
    if not retired.is_file() or retired.read_text(encoding="utf-8").strip(): issues.append("现役旧 video-module-index 未清空")
    if not generic.is_file() or sha(generic) != manifest.get("generic_function_index_sha256"): issues.append("通用功能索引不存在或哈希漂移")
    elif any(str(row.get("module_type") or "") == "pain" or str(row.get("framework") or "") == "痛点" or "pain_id" in row or "angle_id" in row for row in jsonl(generic)):
        issues.append("通用功能索引混入 pain 资产")
    cards = manifest.get("cards", []) if isinstance(manifest.get("cards"), list) else []
    if len(cards) != 14 or receipt.get("formal_cards") != 14 or receipt.get("angle_index_rows") != 17: issues.append("切换后的 14 卡/17角度计数不正确")
    rows = jsonl(angle_path) if angle_path.is_file() else []
    by_id = {str(row.get("angle_id") or ""): row for row in rows}
    if len(rows) != 17 or len(by_id) != 17 or any(not key for key in by_id): issues.append("正式专用索引不是 17 条唯一 angle_id")
    marker_ids: set[str] = set()
    for item in cards:
        if not isinstance(item, dict): issues.append("切换清单含非对象卡片项"); continue
        pain_id = str(item.get("pain_id") or ""); formal = resolved(str(item.get("formal_path") or "")); archived = resolved(str(item.get("archived_path") or ""))
        if not archived.is_file() or sha(archived) != item.get("before_sha256"): issues.append(f"{pain_id} 切换前卡片归档缺失或哈希不匹配")
        if not formal.is_file() or sha(formal) != item.get("after_sha256"): issues.append(f"{pain_id} 正式切换后卡片不存在或哈希漂移"); continue
        raw = formal.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf") or raw.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in raw: issues.append(f"{pain_id} 正式卡不是无 BOM UTF-8"); continue
        text = raw.decode("utf-8"); old = archived.read_text(encoding="utf-8")
        ids = re.findall(r"<!--\s*pain-angle-id:\s*([A-Za-z0-9_-]+)\s*-->\r?\n", text); marker_ids.update(ids)
        normalized = re.sub(r"<!--\s*pain-angle-id:\s*[A-Za-z0-9_-]+\s*-->\r?\n", "", text).replace("\r\n", "\n")
        if normalized != old.replace("\r\n", "\n"): issues.append(f"{pain_id} 正式卡除隐藏 marker 外出现标题、表达或来源漂移")
        try: angles = card_angles(formal)
        except (ValueError, UnicodeDecodeError) as exc: issues.append(f"{pain_id} {exc}"); continue
        if len(ids) != len(angles): issues.append(f"{pain_id} hidden marker 与正式卡角度数不一致")
        for angle_id, (ordinal, title, expression) in zip(ids, angles):
            row = by_id.get(angle_id, {})
            if (row.get("schema") != "video-pain-angle-index-v1" or row.get("status") != "active" or row.get("pain_id") != pain_id
                    or resolved(str(row.get("card_path") or "")) != formal or row.get("card_sha256") != sha(formal)
                    or row.get("angle_ordinal") != ordinal or row.get("angle_title") != title
                    or row.get("expression_sha256") != hashlib.sha256(expression.encode("utf-8")).hexdigest()): issues.append(f"{angle_id} 正式卡与专用索引未一一对应")
            source_issue = anchor_ok(row.get("source_anchor"), source_root)
            if source_issue: issues.append(f"{angle_id} {source_issue}")
    if marker_ids != set(by_id): issues.append("正式卡 hidden angle_id 与专用索引范围不一致")
    for contract, label in ((structure_contract, "结构调用合同"), (structure_skill, "结构调用 Skill")):
        text = contract.read_text(encoding="utf-8") if contract.is_file() else ""
        if "video-pain-angle-index.jsonl" not in text or "angle_id" not in text:
            issues.append(f"{label} 未声明只读专用角度索引及排除边界")
    protected = manifest.get("protected_batch7") if isinstance(manifest.get("protected_batch7"), dict) else {}
    expected = (
        ("machine_candidate_root", "machine_candidate_root_sha256", "batch7 机器候选根"),
        ("evidence_bundle", "evidence_bundle_sha256", "batch7 证据包"),
        ("handoff_binding", "handoff_binding_sha256", "batch7 handoff"),
        ("no_pain_coverage", "no_pain_coverage_sha256", "batch7 无痛点覆盖"),
        ("ledger", "ledger_sha256", "batch7 冻结台账"),
    )
    if not protected:
        issues.append("切换清单未锁定迁移前已存在的 batch7 候选")
    else:
        for path_key, hash_key, label in expected:
            path = resolved(str(protected.get(path_key) or "")); expected_hash = str(protected.get(hash_key) or "")
            actual = tree_sha(path) if path.is_dir() else sha(path) if path.is_file() else ""
            if not actual or actual != expected_hash:
                issues.append(f"{label} 不存在或迁移期间哈希漂移")
        root = resolved(str(protected.get("machine_candidate_root") or ""))
        if (root.parent / "accepted-ledger-record.json").exists() or (root.parent / "replacement-staging").exists() or any(root.parent.glob("**/commit-receipt.json")):
            issues.append("batch7 候选已被 accept、release 或 commit")
        ledger_path = resolved(str(protected.get("ledger") or ""))
        if ledger_path.is_file():
            ledger = json.loads(ledger_path.read_text(encoding="utf-8")); active = ledger.get("active_batch")
            active_number = active.get("batch_number") if isinstance(active, dict) else active if isinstance(active, int) else None
            completed = ledger.get("completed_batches", []) if isinstance(ledger.get("completed_batches"), list) else []
            if active_number == 7 or ledger.get("next_batch_ready") is True or any(item.get("batch_number") == 7 for item in completed if isinstance(item, dict)):
                issues.append("batch7 台账已被 accept 或解锁")
            paused = ledger.get("paused_batch") if isinstance(ledger.get("paused_batch"), dict) else {}
            pause_path = resolved(str(protected.get("pause_receipt") or "")); pause_hash = str(protected.get("pause_receipt_sha256") or "")
            if not pause_path.is_file() or sha(pause_path) != pause_hash:
                issues.append("batch7 受控暂停回执不存在或哈希漂移")
            else:
                pause = json.loads(pause_path.read_text(encoding="utf-8"))
                if (pause.get("schema") != "video-pain-batch-pause-receipt-v1" or pause.get("status") != "machine_candidate_paused"
                        or pause.get("batch_number") != 7 or pause.get("active_batch") is not None or pause.get("next_batch_ready") is not False
                        or pause.get("ledger") != str(ledger_path) or pause.get("ledger_sha256") != sha(ledger_path)
                        or pause.get("machine_candidate_root") != str(root) or pause.get("machine_candidate_root_sha256") != tree_sha(root)
                        or pause.get("handoff_binding") != str(resolved(str(protected.get("handoff_binding") or "")))
                        or pause.get("handoff_binding_sha256") != str(protected.get("handoff_binding_sha256") or "")
                        or paused.get("batch_number") != 7 or paused.get("status") != "machine_candidate_paused"):
                    issues.append("batch7 受控暂停回执未精确绑定候选树、台账与暂停状态")
    batch_base = ROOT / ".runtime" / "video-pain-cards"
    if any((batch_base / subtree / "batch-0008").exists() for subtree in ("expression-completeness-rebuild", "five-source-batches/rebuild-547-state/batches")):
        issues.append("batch8 已被生成或解锁")
    return issues


def meaningful_overlap(value: str, candidates: Any) -> bool:
    source = " ".join(str(item) for item in candidates) if isinstance(candidates, list) else str(candidates or "")
    tokens = [token for token in re.split(r"[，、；。\s/]+", source) if len(token) >= 2]
    return any(token in value for token in tokens)


def structure_checks(candidate: Path, angle_index: Path) -> list[str]:
    issues: list[str] = []
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    angles = {str(row.get("angle_id") or ""): row for row in jsonl(angle_index)}
    for position, row in enumerate(payload.get("small_structures", []), 1):
        if not isinstance(row, dict):
            issues.append(f"第 {position} 行不是对象")
            continue
        third = row.get("structure_three") if isinstance(row.get("structure_three"), dict) else {}
        if third.get("asset_gap"):
            continue
        angle_id = str(third.get("angle_id") or "")
        angle = angles.get(angle_id)
        if not angle:
            issues.append(f"第 {position} 行选择的 angle_id 不存在或非 active")
            continue
        if resolved(str(third.get("module_path") or "")) != resolved(str(angle.get("card_path") or "")):
            issues.append(f"第 {position} 行模块路径未指向 angle_id 所属正式卡")
        if third.get("source_anchor") != angle.get("source_anchor"):
            issues.append(f"第 {position} 行来源锚点与所选角度不一致")
        reason = third.get("selection_reason")
        if not isinstance(reason, dict) or any(not str(reason.get(key) or "").strip() for key in REASON_FIELDS):
            issues.append(f"第 {position} 行 selection_reason 必须包含对象、场景、矛盾和功能适配")
            continue
        if not meaningful_overlap(str(reason["target_people"]), angle.get("target_people")):
            issues.append(f"第 {position} 行匹配理由未说明所选角度的人群对应")
        if not meaningful_overlap(str(reason["scene"]), angle.get("scene_tags")):
            issues.append(f"第 {position} 行匹配理由未说明所选角度的场景对应")
        if not meaningful_overlap(str(reason["core_contradiction"]), angle.get("core_contradiction")):
            issues.append(f"第 {position} 行匹配理由未说明所选角度的核心矛盾对应")
        if str(row.get("replication_function") or "") not in str(reason["functional_fit"]):
            issues.append(f"第 {position} 行匹配理由未说明目标小框架功能适配")
    return issues


def write_receipt(path: Path, status: str, checks: list[dict[str, Any]], subject: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "audit-receipt-v3", "artifactType": "video-pain-angle-match-v1", "status": status,
               "task_id": hashlib.sha256(json.dumps(subject, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16],
               "attempt": 1, "auditor": "xiaoshen", "auditor_skill_id": "xiaoshen-audit",
               "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "subject": subject,
               "required_check_ids": [item["id"] for item in checks], "checks": checks,
               "note": "只审核，未改写正式卡、索引、结构候选或归档。"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="审核视频痛点角度索引及结构选择匹配链路")
    sub = parser.add_subparsers(dest="command", required=True)
    common = sub.add_parser("angle-index")
    common.add_argument("--angle-index", required=True, type=Path); common.add_argument("--pain-index", required=True, type=Path)
    common.add_argument("--pain-root", required=True, type=Path); common.add_argument("--source-root", required=True, type=Path); common.add_argument("--receipt", required=True, type=Path)
    release = sub.add_parser("angle-release")
    release.add_argument("--previous-angle-index", required=True, type=Path); release.add_argument("--current-angle-index", required=True, type=Path); release.add_argument("--affected-pain-ids", required=True); release.add_argument("--receipt", required=True, type=Path)
    structure = sub.add_parser("structure-selection")
    structure.add_argument("--candidate", required=True, type=Path); structure.add_argument("--angle-index", required=True, type=Path); structure.add_argument("--receipt", required=True, type=Path)
    migration = sub.add_parser("migration")
    migration.add_argument("--manifest", required=True, type=Path); migration.add_argument("--source-root", required=True, type=Path); migration.add_argument("--formal-index", type=Path); migration.add_argument("--expected-formal-index-sha256", default=""); migration.add_argument("--receipt", required=True, type=Path)
    switch = sub.add_parser("post-switch")
    switch.add_argument("--manifest", required=True, type=Path); switch.add_argument("--commit-receipt", required=True, type=Path); switch.add_argument("--source-root", required=True, type=Path); switch.add_argument("--structure-contract", required=True, type=Path); switch.add_argument("--structure-skill", required=True, type=Path); switch.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "angle-index":
        issues = angle_index_checks(args.angle_index, args.pain_index, args.pain_root, args.source_root)
        check_id, subject = "pain-angle-index-integrity", {"angle_index": rel(args.angle_index), "pain_index": rel(args.pain_index)}
    elif args.command == "angle-release":
        issues = release_checks(args.previous_angle_index, args.current_angle_index, {item for item in args.affected_pain_ids.split(",") if item})
        check_id, subject = "pain-angle-id-preservation", {"previous": rel(args.previous_angle_index), "current": rel(args.current_angle_index)}
    elif args.command == "structure-selection":
        issues = structure_checks(args.candidate, args.angle_index)
        check_id, subject = "pain-angle-structure-selection", {"candidate": rel(args.candidate), "angle_index": rel(args.angle_index)}
    elif args.command == "migration":
        issues = migration_checks(args.manifest, args.source_root, args.formal_index, args.expected_formal_index_sha256)
        check_id, subject = "pain-angle-migration-staging", {"manifest": rel(args.manifest), "formal_index": rel(args.formal_index) if args.formal_index else ""}
    else:
        issues = switch_checks(args.manifest, args.commit_receipt, args.source_root, args.structure_contract, args.structure_skill)
        check_id, subject = "pain-angle-formal-switch", {"manifest": rel(args.manifest), "commit_receipt": rel(args.commit_receipt)}
    checks = [{"id": check_id, "status": "passed" if not issues else "failed", "detail": "；".join(issues) or "通过"}]
    status = "approved" if not issues else "returned"
    write_receipt(args.receipt, status, checks, subject)
    print(json.dumps({"status": status, "checks": checks}, ensure_ascii=False))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
