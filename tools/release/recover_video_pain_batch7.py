#!/usr/bin/env python3
"""One-time controlled recovery for the post-angle-migration batch-0007.

It never changes a candidate.  It stages recoverable baseline cards and the
locked batch-0007 candidate outside the runtime tree, requires an approved
audit for each staging area, then atomically installs cards and the dedicated
angle index while updating the 547-source ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROCESS = ROOT / "02_资产中心" / "02_处理库"
FORMAL_ROOT = PROCESS / "02_痛点_内容模块（会员专享）"
OBSOLETE_FORMAL_ROOT = PROCESS / "02_痛点_内容模块"
ANGLE_INDEX = ROOT / "04_数据中心" / "03_查询索引" / "video-pain-angle-index.jsonl"
STATE = ROOT / ".runtime" / "video-pain-cards" / "five-source-batches" / "rebuild-547-state"
RUN = ROOT / ".runtime" / "video-pain-cards" / "expression-completeness-rebuild" / "batch-0007"
MIGRATION = ROOT / ".runtime" / "video-pain-cards" / "angle-index-migration-20260905"
STAGE = PROCESS / "_private" / "video-pain-recovery-9953d29ba732"


def load_vpc() -> Any:
    path = ROOT / "10_Skills武器库" / "视频文案-痛点卡拆解Skill（会员专享）" / "scripts" / "video_pain_cards.py"
    spec = importlib.util.spec_from_file_location("video_pain_cards", path)
    if not spec or not spec.loader:
        raise RuntimeError("无法加载视频痛点卡渲染器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VPC = load_vpc()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def approved(path: Path) -> None:
    receipt = read(path)
    if receipt.get("schema") != "audit-receipt-v3" or receipt.get("status") != "approved":
        raise ValueError("小审回执必须为 audit-receipt-v3 / approved")


def source_anchor(item: dict[str, Any]) -> dict[str, Any]:
    required = ("source_id", "original_source_path", "original_full_text_sha256", "original_start_offset", "original_end_offset", "original_excerpt")
    if any(item.get(key) in (None, "") for key in required):
        raise ValueError(f"证据 {item.get('evidence_id')} 缺少原识别来源锚点")
    return {
        "source_id": item["source_id"],
        "original_source_path": item["original_source_path"],
        "original_full_text_sha256": item["original_full_text_sha256"],
        "start_offset": item["original_start_offset"],
        "end_offset": item["original_end_offset"],
        "original_excerpt": item["original_excerpt"],
    }


def card_index_rows(angle_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in angle_rows:
        pain_id = str(row["pain_id"])
        grouped.setdefault(pain_id, {
            "schema": "video-pain-card-index-v1", "card_id": pain_id, "pain_id": pain_id,
            "module_type": "pain", "module_path": row["card_path"],
        })
    return [grouped[key] for key in sorted(grouped)]


def prepare_index_readdress() -> None:
    """Stage a path-only repair of the committed dedicated angle index.

    The 17 card files were already moved to the member-only formal root.  This
    repair deliberately keeps their bytes, angle IDs, anchors, and hashes intact
    and changes only the stale directory prefix in the index.
    """
    stage = STAGE / "index-readdress"
    if stage.exists():
        raise ValueError("索引地址修复暂存已存在，拒绝覆盖")
    rows = jsonl(ANGLE_INDEX)
    if len(rows) != 17:
        raise ValueError("当前专用角度索引不是预期的 17 条迁移基线")
    repaired: list[dict[str, Any]] = []
    for row in rows:
        old_path = Path(str(row.get("card_path") or "")).resolve()
        try:
            relative = old_path.relative_to(OBSOLETE_FORMAL_ROOT.resolve())
        except ValueError as exc:
            raise ValueError(f"索引卡路径不是待修复的旧目录：{old_path}") from exc
        actual = (FORMAL_ROOT / relative).resolve()
        if not actual.is_file() or sha(actual) != row.get("card_sha256"):
            raise ValueError(f"正式卡缺失或内容漂移：{actual}")
        updated = dict(row)
        updated["card_path"] = str(actual)
        repaired.append(updated)
    if len({str(row.get("angle_id") or "") for row in repaired}) != len(repaired):
        raise ValueError("待修复索引存在重复或空 angle_id")
    angle_path = stage / "video-pain-angle-index.jsonl"
    pain_path = stage / "pain-card-index.jsonl"
    write_jsonl(angle_path, repaired)
    write_jsonl(pain_path, card_index_rows(repaired))
    write(stage / "manifest.json", {
        "schema": "video-pain-index-readdress-stage-v1", "status": "awaiting_audit",
        "prior_angle_index": str(ANGLE_INDEX), "prior_angle_index_sha256": sha(ANGLE_INDEX),
        "angle_index": str(angle_path), "angle_index_sha256": sha(angle_path),
        "pain_index": str(pain_path), "pain_index_sha256": sha(pain_path),
        "formal_root": str(FORMAL_ROOT), "formal_root_sha256": tree_sha(FORMAL_ROOT),
        "changed_field": "card_path_only",
    })


def commit_index_readdress(audit: Path) -> None:
    approved(audit)
    stage = STAGE / "index-readdress"
    meta = read(stage / "manifest.json")
    staged = Path(meta["angle_index"])
    if sha(ANGLE_INDEX) != meta["prior_angle_index_sha256"]:
        raise ValueError("原正式索引在审核期间发生漂移")
    if sha(staged) != meta["angle_index_sha256"] or tree_sha(FORMAL_ROOT) != meta["formal_root_sha256"]:
        raise ValueError("索引修复暂存或正式卡在审核后漂移")
    archive = ANGLE_INDEX.parent / "99_归档" / "2026-09-08_会员目录索引修复"
    archive.mkdir(parents=True, exist_ok=False)
    old = archive / ANGLE_INDEX.name
    os.replace(ANGLE_INDEX, old)
    try:
        os.replace(staged, ANGLE_INDEX)
    except OSError:
        os.replace(old, ANGLE_INDEX)
        raise
    write(stage / "commit-receipt.json", {
        "schema": "video-pain-index-readdress-v1", "status": "readdressed",
        "audit_receipt": str(audit.resolve()), "archived_index": str(old),
        "formal_index": str(ANGLE_INDEX), "formal_index_sha256": sha(ANGLE_INDEX),
        "completed_at": now(),
    })


def prepare_baseline() -> None:
    manifest = read(MIGRATION / "angle-index-migration-manifest.json")
    switch = read(MIGRATION / "formal-switch-manifest.json")
    if switch.get("status") != "committed" or manifest.get("status") != "staged_pending_angle_audit":
        raise ValueError("角度迁移历史清单状态不允许恢复")
    old_stage = Path(manifest["staging_card_root"])
    old_index = Path(manifest["staging_angle_index"])
    if tree_sha(old_stage) != manifest["staging_card_root_sha256"] or sha(old_index) != manifest["staging_angle_index_sha256"]:
        raise ValueError("已审核迁移暂存资产发生漂移")
    if FORMAL_ROOT.exists() and any(FORMAL_ROOT.rglob("*.md")):
        raise ValueError("正式痛点库非空，拒绝恢复覆盖")
    base = STAGE / "baseline"
    if base.exists():
        raise ValueError("基线恢复暂存已存在，拒绝覆盖")
    cards = base / "cards"
    shutil.copytree(old_stage, cards)
    rows = jsonl(old_index)
    for row in rows:
        original = Path(row["card_path"])
        row["card_path"] = str((cards / original.relative_to(old_stage)).resolve())
        row["card_sha256"] = sha(Path(row["card_path"]))
        row["module_type"] = "pain"
        row["card_id"] = row["pain_id"]
    angles = base / "video-pain-angle-index.jsonl"
    write_jsonl(angles, rows)
    card_index = base / "pain-card-index.jsonl"
    write_jsonl(card_index, card_index_rows(rows))
    write(base / "manifest.json", {
        "schema": "video-pain-baseline-recovery-stage-v1", "status": "awaiting_audit",
        "cards": str(cards), "cards_sha256": tree_sha(cards),
        "angle_index": str(angles), "angle_index_sha256": sha(angles),
        "pain_index": str(card_index), "pain_index_sha256": sha(card_index),
        "migration_manifest": str(MIGRATION / "angle-index-migration-manifest.json"),
        "migration_manifest_sha256": sha(MIGRATION / "angle-index-migration-manifest.json"),
    })


def commit_baseline(audit: Path) -> None:
    approved(audit)
    base = STAGE / "baseline"
    meta = read(base / "manifest.json")
    cards = Path(meta["cards"]); angles = Path(meta["angle_index"])
    if tree_sha(cards) != meta["cards_sha256"] or sha(angles) != meta["angle_index_sha256"]:
        raise ValueError("基线暂存审核后漂移")
    if FORMAL_ROOT.exists() and any(FORMAL_ROOT.iterdir()):
        raise ValueError("正式痛点库非空，拒绝基线覆盖")
    FORMAL_ROOT.parent.mkdir(parents=True, exist_ok=True)
    if FORMAL_ROOT.exists():
        FORMAL_ROOT.rmdir()
    shutil.copytree(cards, FORMAL_ROOT)
    final_rows = jsonl(angles)
    for row in final_rows:
        staged = Path(row["card_path"])
        row["card_path"] = str((FORMAL_ROOT / staged.relative_to(cards)).resolve())
        row["card_sha256"] = sha(Path(row["card_path"]))
    final_index = base / "formal-video-pain-angle-index.jsonl"
    write_jsonl(final_index, final_rows)
    archive = ROOT / "04_数据中心" / "03_查询索引" / "99_归档" / "2026-09-08_迁移路径修复"
    archive.mkdir(parents=True, exist_ok=False)
    archived = archive / "video-pain-angle-index.jsonl"
    if ANGLE_INDEX.exists():
        os.replace(ANGLE_INDEX, archived)
    try:
        os.replace(final_index, ANGLE_INDEX)
    except OSError:
        if archived.exists() and not ANGLE_INDEX.exists():
            os.replace(archived, ANGLE_INDEX)
        raise
    final_card_index = base / "formal-pain-card-index.jsonl"
    write_jsonl(final_card_index, card_index_rows(final_rows))
    write(base / "commit-receipt.json", {
        "schema": "video-pain-baseline-recovery-v1", "status": "recovered",
        "audit_receipt": str(audit.resolve()), "formal_root": str(FORMAL_ROOT),
        "formal_root_sha256": tree_sha(FORMAL_ROOT), "formal_angle_index": str(ANGLE_INDEX),
        "formal_angle_index_sha256": sha(ANGLE_INDEX), "archived_broken_index": str(archived),
        "completed_at": now(),
    })


def grouped_cards_with_batch7() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    approved_rows = jsonl(STATE / "approved-evidence.jsonl")
    bundle = read(RUN / "evidence-bundle.json")
    sources = {row["source"]["source_id"]: row["source"] for row in approved_rows if row.get("kind") == "source"}
    sources.update({row["source_id"]: row for row in bundle["sources"]})
    evidence = [row["item"] for row in approved_rows if row.get("kind") == "evidence"] + list(bundle["evidence_items"])
    registry = read(STATE / "approved-pain-registry.json")
    registered = {str(row["pain_id"]): row for row in registry.get("entries", [])}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in evidence:
        groups[item["pain_id"]].append(item)
    taxonomy = VPC._subcategory_lookup(VPC._taxonomy())
    cards: list[dict[str, Any]] = []
    for pain_id, items in sorted(groups.items()):
        first = items[0]
        fixed = (first["pain_title"], first["taxonomy_id"])
        if any((item["pain_title"], item["taxonomy_id"]) != fixed for item in items):
            raise ValueError(f"{pain_id} 的标题或分类法字段冲突")
        # A previously released pain ID keeps its released definition.  Batch 7
        # may add a new angle/evidence but must not silently redefine the card.
        pain_definition = str(registered.get(pain_id, {}).get("pain_definition") or first["pain_definition"])
        by_angle: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            by_angle[(item["angle_title"], item["how_to_frame"], item["short_video_expression"])].append(item)
        tax = taxonomy[first["taxonomy_id"]]
        angles = []
        for (title, frame, expression), evidence_items in sorted(by_angle.items()):
            angles.append({"angle_title": title, "how_to_frame": frame, "short_video_expression": expression, "evidence": evidence_items})
        cards.append({
            "pain_id": pain_id, "pain_title": first["pain_title"], "pain_definition": pain_definition,
            "category_name": tax["category_name"], "subcategory_name": tax["name"],
            "audiences": sorted({value for item in items for value in item["audiences"]}),
            "scene_tags": sorted({value for item in items for value in item["scene_tags"]}), "angles": angles,
        })
    return cards, sources


def prepare_batch7() -> None:
    receipt = RUN / "xiaoshen-machine-audit-9953d29ba732.json"
    approved(receipt)
    candidate = RUN / "machine-evidence"
    if read(receipt).get("subject", {}).get("candidateSha256") != tree_sha(candidate):
        raise ValueError("第7批小审回执未绑定当前候选")
    state = read(STATE / "coverage-ledger.json")
    paused = state.get("paused_batch", {})
    if paused.get("status") != "machine_candidate_paused" or paused.get("machine_candidate_root_sha256") != tree_sha(candidate):
        raise ValueError("第7批暂停锁或候选哈希不匹配")
    stage = STAGE / "batch-0007"
    if stage.exists():
        raise ValueError("第7批暂存已存在，拒绝覆盖")
    cards, sources = grouped_cards_with_batch7()
    bundle = read(RUN / "evidence-bundle.json")
    affected = sorted({item["pain_id"] for item in bundle["evidence_items"]})
    selected = [card for card in cards if card["pain_id"] in affected]
    target_rows = jsonl(ANGLE_INDEX)
    kept = [row for row in target_rows if row.get("pain_id") not in affected]
    staged_cards = stage / "cards"
    new_rows: list[dict[str, Any]] = []
    for card in selected:
        # Formal folders are the fixed, slash-safe taxonomy folders.  The
        # taxonomy's slash-delimited classification is semantic metadata, not
        # an instruction to create another level of directories.
        dest = staged_cards / VPC._safe_name(card["category_name"], "CAT") / VPC._safe_name(card["subcategory_name"], "SUB") / f"{card['pain_id']}_{card['pain_title']}.md"
        VPC._render_formal_pain_card(dest, card, sources)
        for ordinal, angle in enumerate(card["angles"], 1):
            angle_id = VPC._angle_id(card["pain_id"], angle["angle_title"], angle["short_video_expression"], angle["evidence"])
            evidence = angle["evidence"][0]
            new_rows.append({
                "schema": "video-pain-angle-index-v1", "status": "active", "module_type": "pain", "card_id": card["pain_id"],
                "angle_id": angle_id, "pain_id": card["pain_id"], "angle_ordinal": ordinal, "angle_title": angle["angle_title"],
                "card_path": str(dest.resolve()), "card_sha256": sha(dest),
                "expression_sha256": hashlib.sha256(angle["short_video_expression"].encode("utf-8")).hexdigest(),
                "source_anchor": source_anchor(evidence), "target_people": card["audiences"],
                "scene_tags": sorted({tag for item in angle["evidence"] for tag in item.get("scene_tags", [])}),
                "core_contradiction": card["pain_definition"],
            })
    all_rows = kept + new_rows
    ids = [row["angle_id"] for row in all_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("暂存专用角度索引出现重复 angle_id")
    angle_path = stage / "video-pain-angle-index.jsonl"
    write_jsonl(angle_path, all_rows)
    pain_index = stage / "pain-card-index.jsonl"
    write_jsonl(pain_index, card_index_rows(all_rows))
    write(stage / "manifest.json", {
        "schema": "video-pain-batch7-recovery-stage-v1", "status": "awaiting_audit", "batch_number": 7,
        "affected_pain_ids": affected, "cards": str(staged_cards), "cards_sha256": tree_sha(staged_cards),
        "angle_index": str(angle_path), "angle_index_sha256": sha(angle_path),
        "pain_index": str(pain_index), "pain_index_sha256": sha(pain_index),
        "prior_angle_index_sha256": sha(ANGLE_INDEX), "machine_audit_receipt": str(receipt),
        "machine_audit_receipt_sha256": sha(receipt), "candidate_sha256": tree_sha(candidate),
    })


def commit_batch7(audit: Path) -> None:
    approved(audit)
    stage = STAGE / "batch-0007"
    meta = read(stage / "manifest.json")
    cards = Path(meta["cards"]); staged_index = Path(meta["angle_index"])
    if tree_sha(cards) != meta["cards_sha256"] or sha(staged_index) != meta["angle_index_sha256"]:
        raise ValueError("第7批暂存审核后漂移")
    if sha(ANGLE_INDEX) != meta["prior_angle_index_sha256"]:
        raise ValueError("正式专用角度索引在暂存后漂移")
    archive = PROCESS / "99_归档" / "视频痛点卡逐批版本" / datetime.now().strftime("%Y%m%dT%H%M%S")
    archive.mkdir(parents=True, exist_ok=False)
    installed: list[Path] = []; moved: list[tuple[Path, Path]] = []
    try:
        for src in sorted(cards.rglob("*.md")):
            dest = FORMAL_ROOT / src.relative_to(cards); dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                old = archive / dest.relative_to(FORMAL_ROOT); old.parent.mkdir(parents=True, exist_ok=True)
                os.replace(dest, old); moved.append((dest, old))
            os.replace(src, dest); installed.append(dest)
        final_rows = jsonl(staged_index)
        for row in final_rows:
            path = Path(row["card_path"])
            if cards in path.parents:
                final = FORMAL_ROOT / path.relative_to(cards)
                row["card_path"] = str(final.resolve()); row["card_sha256"] = sha(final)
        next_index = stage / "formal-video-pain-angle-index.jsonl"
        write_jsonl(next_index, final_rows)
        old_index = archive / "video-pain-angle-index.jsonl"
        os.replace(ANGLE_INDEX, old_index)
        try:
            os.replace(next_index, ANGLE_INDEX)
        except OSError:
            os.replace(old_index, ANGLE_INDEX)
            raise
    except Exception:
        for dest in reversed(installed):
            if dest.exists(): dest.unlink()
        for dest, old in reversed(moved):
            if old.exists(): os.replace(old, dest)
        raise
    ledger_path = STATE / "coverage-ledger.json"; ledger = read(ledger_path)
    bundle = read(RUN / "evidence-bundle.json"); approved_path = STATE / "approved-evidence.jsonl"
    existing = jsonl(approved_path); seen = {row.get("item", {}).get("evidence_id") for row in existing if row.get("kind") == "evidence"}
    additions = [{"kind": "source", "batch_number": 7, "source": source} for source in bundle["sources"]]
    additions += [{"kind": "evidence", "batch_number": 7, "item": item} for item in bundle["evidence_items"] if item["evidence_id"] not in seen]
    write_jsonl(approved_path, existing + additions)
    registry_path = STATE / "approved-pain-registry.json"; registry = read(registry_path); by_id = {row["pain_id"]: row for row in registry["entries"]}
    for item in bundle["evidence_items"]:
        row = by_id.get(item["pain_id"])
        if not row:
            row = {"pain_id": item["pain_id"], "pain_title": item["pain_title"], "taxonomy_id": item["taxonomy_id"], "pain_definition": item["pain_definition"], "status": "approved", "evidence_count": 0, "source_ids": []}
            registry["entries"].append(row); by_id[item["pain_id"]] = row
        row["evidence_count"] += 1
        if item["source_id"] not in row["source_ids"]: row["source_ids"].append(item["source_id"])
    write(registry_path, registry)
    source_ids = [source["source_id"] for source in bundle["sources"]]
    for row in ledger["sources"]:
        if row["source_id"] in source_ids: row.update({"status": "approved", "batch_number": 7})
    ledger.pop("paused_batch", None); ledger["active_batch"] = None; ledger["next_batch_ready"] = True
    ledger["completed_batches"].append({"batch_number": 7, "source_ids": source_ids, "machine_audit_receipt": meta["machine_audit_receipt"], "machine_audit_sha256": meta["machine_audit_receipt_sha256"], "release_status": "released", "release_audit_receipt": str(audit.resolve()), "release_audit_sha256": sha(audit), "released_at": now(), "release_mode": "post-angle-migration-recovery"})
    ledger["formal_baseline"] = {"pain_root": str(FORMAL_ROOT), "pain_root_sha256": tree_sha(FORMAL_ROOT), "index": str(ANGLE_INDEX), "index_sha256": sha(ANGLE_INDEX)}
    write(ledger_path, ledger)
    final_card_index = stage / "formal-pain-card-index.jsonl"
    write_jsonl(final_card_index, card_index_rows(jsonl(ANGLE_INDEX)))
    write(stage / "release-receipt.json", {"schema": "video-pain-batch-release-v1", "status": "released", "batch_number": 7, "affected_pain_ids": meta["affected_pain_ids"], "archive": str(archive), "formal_root": str(FORMAL_ROOT), "formal_index": str(ANGLE_INDEX), "completed_at": now()})


def archive_unindexed_duplicate(audit: Path) -> None:
    """Archive the one old-layout PAIN-A card superseded by batch 7.

    It is deliberately a move, never a deletion.  The final active index is
    the source of truth; refusing any other unindexed active card makes this a
    narrowly-scoped post-commit repair instead of broad cleanup.
    """
    approved(audit)
    rows = jsonl(ANGLE_INDEX)
    indexed = {Path(str(row["card_path"])).resolve() for row in rows}
    active = [path.resolve() for path in FORMAL_ROOT.rglob("PAIN-*.md") if "99_归档" not in path.parts]
    extras = [path for path in active if path not in indexed]
    if len(extras) != 1 or not extras[0].name.startswith("PAIN-A02-INNER-EXPRESSION_"):
        raise ValueError(f"未索引正式卡不符合受控修复范围：{extras}")
    target = extras[0]
    archive = PROCESS / "99_归档" / "视频痛点卡逐批版本" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "_重复卡收口")
    archive.mkdir(parents=True, exist_ok=False)
    archived = archive / target.relative_to(FORMAL_ROOT)
    archived.parent.mkdir(parents=True, exist_ok=True)
    os.replace(target, archived)
    write(STAGE / "batch-0007" / "duplicate-card-archive-receipt.json", {
        "schema": "video-pain-duplicate-card-archive-v1", "status": "archived",
        "audit_receipt": str(audit.resolve()), "former_active_card": str(target),
        "archived_card": str(archived), "archived_card_sha256": sha(archived),
        "final_angle_index": str(ANGLE_INDEX), "final_angle_index_sha256": sha(ANGLE_INDEX),
        "completed_at": now(),
    })


FIXED_FOLDER_REPAIRS = {
    ("内容与流量", "选题", "内容", "文案"): ("内容与流量", "选题_内容_文案"),
    ("创业者心智与能力", "情绪", "人生困境"): ("创业者心智与能力", "情绪_人生困境"),
}


def _fixed_folder_target(path: Path) -> Path | None:
    try:
        relative = path.resolve().relative_to(FORMAL_ROOT.resolve())
    except ValueError:
        return None
    for old_parts, new_parts in FIXED_FOLDER_REPAIRS.items():
        if relative.parts[:len(old_parts)] == old_parts:
            return (FORMAL_ROOT.joinpath(*new_parts) / Path(*relative.parts[len(old_parts):])).resolve()
    return None


def prepare_fixed_folder_normalization() -> None:
    """Stage a path-only merge into the already-existing fixed folders."""
    stage = STAGE / "fixed-folder-normalization"
    if stage.exists():
        raise ValueError("固定目录收口暂存已存在，拒绝覆盖")
    rows = jsonl(ANGLE_INDEX)
    affected_paths = sorted({Path(str(row["card_path"])).resolve() for row in rows if _fixed_folder_target(Path(str(row["card_path"])))})
    if len(affected_paths) != 3:
        raise ValueError(f"固定目录收口应精确处理本批建立的 3 张嵌套活跃卡，实际为 {len(affected_paths)}")
    cards = stage / "cards"
    replacements: dict[Path, Path] = {}
    for current in affected_paths:
        target = _fixed_folder_target(current)
        if target is None or not current.is_file():
            raise ValueError(f"嵌套活跃卡不存在或无法映射：{current}")
        if target.exists():
            raise ValueError(f"固定目标已存在，拒绝覆盖：{target}")
        staged = cards / target.relative_to(FORMAL_ROOT)
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current, staged)
        if sha(staged) != sha(current):
            raise ValueError(f"暂存卡哈希漂移：{current}")
        replacements[current] = staged.resolve()
    staged_rows: list[dict[str, Any]] = []
    for row in rows:
        current = Path(str(row["card_path"])).resolve()
        updated = dict(row)
        if current in replacements:
            updated["card_path"] = str(replacements[current])
            updated["card_sha256"] = sha(replacements[current])
        staged_rows.append(updated)
    angle_path = stage / "video-pain-angle-index.jsonl"; pain_path = stage / "pain-card-index.jsonl"
    write_jsonl(angle_path, staged_rows); write_jsonl(pain_path, card_index_rows(staged_rows))
    write(stage / "manifest.json", {
        "schema": "video-pain-fixed-folder-normalization-stage-v1", "status": "awaiting_audit",
        "prior_angle_index_sha256": sha(ANGLE_INDEX), "formal_root_sha256": tree_sha(FORMAL_ROOT),
        "cards": str(cards), "cards_sha256": tree_sha(cards), "angle_index": str(angle_path),
        "angle_index_sha256": sha(angle_path), "pain_index": str(pain_path), "pain_index_sha256": sha(pain_path),
        "affected_active_cards": [str(path) for path in affected_paths], "fixed_folder_repairs": {"/".join(k): "/".join(v) for k, v in FIXED_FOLDER_REPAIRS.items()},
    })


def commit_fixed_folder_normalization(audit: Path) -> None:
    approved(audit)
    stage = STAGE / "fixed-folder-normalization"; meta = read(stage / "manifest.json")
    cards = Path(meta["cards"]); staged_index = Path(meta["angle_index"])
    if sha(ANGLE_INDEX) != meta["prior_angle_index_sha256"] or tree_sha(FORMAL_ROOT) != meta["formal_root_sha256"]:
        raise ValueError("正式库或索引在固定目录收口审核期间发生漂移")
    if tree_sha(cards) != meta["cards_sha256"] or sha(staged_index) != meta["angle_index_sha256"]:
        raise ValueError("固定目录收口暂存审核后漂移")
    moved: list[tuple[Path, Path]] = []
    archive = ANGLE_INDEX.parent / "99_归档" / "2026-09-08_固定分类目录收口"
    archive.mkdir(parents=True, exist_ok=False)
    try:
        for current_text in meta["affected_active_cards"]:
            current = Path(current_text).resolve(); target = _fixed_folder_target(current)
            if target is None or not current.is_file() or target.exists():
                raise ValueError(f"固定目录提交前置条件失败：{current}")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(current, target); moved.append((current, target))
        final_rows = jsonl(staged_index)
        for row in final_rows:
            staged = Path(str(row["card_path"])).resolve()
            try:
                relative = staged.relative_to(cards.resolve())
            except ValueError:
                continue
            final = (FORMAL_ROOT / relative).resolve()
            row["card_path"] = str(final); row["card_sha256"] = sha(final)
        next_index = stage / "formal-video-pain-angle-index.jsonl"; write_jsonl(next_index, final_rows)
        old_index = archive / ANGLE_INDEX.name; os.replace(ANGLE_INDEX, old_index)
        try:
            os.replace(next_index, ANGLE_INDEX)
        except OSError:
            os.replace(old_index, ANGLE_INDEX); raise
    except Exception:
        for current, target in reversed(moved):
            if target.exists(): os.replace(target, current)
        raise
    # Remove only the exact empty directory chains that this repair vacated.
    for old_parts in FIXED_FOLDER_REPAIRS:
        for depth in range(len(old_parts), 1, -1):
            path = FORMAL_ROOT.joinpath(*old_parts[:depth])
            if path.exists() and not any(path.iterdir()): path.rmdir()
    final_pain_index = stage / "formal-pain-card-index.jsonl"; write_jsonl(final_pain_index, card_index_rows(jsonl(ANGLE_INDEX)))
    write(stage / "commit-receipt.json", {
        "schema": "video-pain-fixed-folder-normalization-v1", "status": "committed", "audit_receipt": str(audit.resolve()),
        "formal_index": str(ANGLE_INDEX), "formal_index_sha256": sha(ANGLE_INDEX), "formal_pain_index": str(final_pain_index),
        "archived_prior_index": str(archive / ANGLE_INDEX.name), "moved_card_count": len(moved), "completed_at": now(),
    })


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare-index-readdress")
    p = sub.add_parser("commit-index-readdress"); p.add_argument("--audit", required=True)
    sub.add_parser("prepare-baseline")
    p = sub.add_parser("commit-baseline"); p.add_argument("--audit", required=True)
    sub.add_parser("prepare-batch7")
    p = sub.add_parser("commit-batch7"); p.add_argument("--audit", required=True)
    p = sub.add_parser("archive-unindexed-duplicate"); p.add_argument("--audit", required=True)
    sub.add_parser("prepare-fixed-folder-normalization")
    p = sub.add_parser("commit-fixed-folder-normalization"); p.add_argument("--audit", required=True)
    args = parser.parse_args()
    if args.cmd == "prepare-index-readdress": prepare_index_readdress()
    elif args.cmd == "commit-index-readdress": commit_index_readdress(Path(args.audit).resolve())
    elif args.cmd == "prepare-baseline": prepare_baseline()
    elif args.cmd == "commit-baseline": commit_baseline(Path(args.audit).resolve())
    elif args.cmd == "prepare-batch7": prepare_batch7()
    elif args.cmd == "archive-unindexed-duplicate": archive_unindexed_duplicate(Path(args.audit).resolve())
    elif args.cmd == "prepare-fixed-folder-normalization": prepare_fixed_folder_normalization()
    elif args.cmd == "commit-fixed-folder-normalization": commit_fixed_folder_normalization(Path(args.audit).resolve())
    else: commit_batch7(Path(args.audit).resolve())
    print(json.dumps({"status": "ok", "command": args.cmd}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
