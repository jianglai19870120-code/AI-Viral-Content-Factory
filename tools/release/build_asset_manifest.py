#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.release.public_policy import classify as classify_release_path


SKIP_PARTS = {".git", ".runtime", ".workbuddy", ".obsidian", ".codex", "__pycache__", "__MACOSX", "dist", "_TEMP", "node_modules"}
MEMBER_EXCLUSIVE_SUFFIX = "（会员专享）"
ASSET_PUBLIC_ROOTS = (
    "02_资产中心/01_输入库/",
    "02_资产中心/02_处理库/",
    "02_资产中心/03_输出库/",
    "02_资产中心/06_配图库/",
)
ASSET_PROCESS_DIR_MARKERS = {
    "99_历史处理记录",
    "99_运行记录",
    "99_执行记录",
    "99_审核记录",
    "99_本地运行记录",
}
ASSET_PROCESS_FILENAMES = {
    ".sync-state.json",
    "ima_sync_state.json",
    ".processed_registry.jsonl",
    "skip_list.jsonl",
    "batch_split.json",
    "clean_batches.json",
    "real_batches.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(relative: Path) -> tuple[str, str, str]:
    status, policy_reason = classify_release_path(relative)
    if status == "private":
        return "private", policy_reason, "发布策略要求本机保留，不进入公开仓或发布包"
    text = relative.as_posix()
    if text.startswith("02_资产中心/") and relative.name in {"README.md", ".gitkeep"}:
        return "public", "empty-template-or-guide", "空白模板或目录说明，可随核心系统包发布"
    if any(text.startswith(prefix) for prefix in ASSET_PUBLIC_ROOTS):
        return "public", "business-asset", "非会员正式资产按 GitHub v1 基线公开"
    if "99_" in text and any(word in text for word in ("运行记录", "执行记录", "审核记录", "本地运行记录", "历史处理记录")):
        return "private", "runtime-record", "运行和审核历史不公开"
    return "public", "system-source", "系统源码与正式合同"


def build_manifest(root: Path, output: Path) -> dict:
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if path == output or any(part in SKIP_PARTS for part in relative.parts) or path.suffix.lower() == ".pyc" or path.name in {".DS_Store", "Thumbs.db"}:
            continue
        status, source_type, reason = classify(relative)
        source = "project-owned" if status == "public" else "unverified"
        rights_holder = "姜来已来" if status == "public" else "unverified"
        scope = "source-code-or-contract"
        if source_type == "business-asset":
            scope = "formal-business-asset"
        elif source_type == "member-exclusive-placeholder":
            scope = "placeholder-only"
        records.append({
            "path": relative.as_posix(),
            "status": status,
            "source": source,
            "author_or_rightsholder": rights_holder,
            "material_type": source_type,
            "content_scope": scope if status == "public" else "unverified-full-or-summary",
            "contains_personal_information": status != "public",
            "license_or_permission_basis": "AI流量工厂 Source-Available License v1.0" if status == "public" else "unverified",
            "allowed_platforms": ["github", "codex", "workbuddy", "skillhub"] if status == "public" else [],
            "reviewer": "system-rule" if status == "public" else "",
            "reviewed_at": "",
            "final_public_decision": status,
            "reason": reason,
            "sha256": sha256(path),
            "size": path.stat().st_size,
        })
    data = {"schema": "ai-traffic-public-assets-v2", "generated": True, "records": records}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="生成公开资产权利清单")
    parser.add_argument("--root")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    output = Path(args.output).resolve() if args.output else root / ".runtime" / "public-assets-manifest.json"
    data = build_manifest(root, output)
    records = data["records"]
    counts = {status: sum(1 for item in records if item["status"] == status) for status in ("public", "private", "review_required")}
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
