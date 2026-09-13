#!/usr/bin/env python3
"""Create the runtime-only intent map that 小写 completes before final-copy writing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="创建结构四正文意图映射请求")
    parser.add_argument("--structure-four", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    structure = json.loads(args.structure_four.read_text(encoding="utf-8"))
    if structure.get("schema") != "final-copy-structure-four-freeze-v4":
        raise SystemExit("现役正文只接受 v11 统一核心大框架结构四")
    rows = [framework for framework in structure.get("core_frameworks", []) if isinstance(framework, dict)]
    if not rows:
        raise SystemExit("冻结结构四缺少核心内容行")
    result = []
    for index, row in enumerate(rows):
        def visible_text(item: dict) -> str:
            return " ".join(part for part in (str(item.get("user_claim") or "").strip(), str(item.get("user_evidence") or "").strip(), str(item.get("user_statement") or "").strip()) if part)
        before = next((visible_text(item) for item in reversed(rows[:index]) if visible_text(item)), "")
        after = next((visible_text(item) for item in rows[index + 1:] if visible_text(item)), "")
        origin = str(row.get("content_origin") or "user-filled")
        result.append({
            "intent_id": str(row.get("core_framework_id") or ""),
            "intent_scope": "core-framework-unified",
            "framework_block_id": str(row.get("framework_block_id") or ""),
            "small_structure_id": "",
            "origin": origin,
            "user_statement": str(row.get("user_statement") or "").strip(),
            "main_meaning": "", "required_keywords": [],
            # v4 的每个核心大框架必须由小写拆成可追溯内容锚点；正文不能只靠几个关键词蒙混覆盖。
            "content_anchors": [],
            "auto_fill_context": {"previous_user_statement": before, "next_user_statement": after, "framework_label": str(row.get("framework_label") or ""), "small_framework_name": ""},
            "auto_fill_reasoning": "",
        })
    payload = {
        "schema": "final-copy-structure-intent-map-v4", "status": "needs-authoring",
        "structure_four": str(args.structure_four.resolve()), "structure_four_sha256": digest(args.structure_four),
        "topic": str(structure.get("topic") or ""), "topic_terms": [], "topic_meaning": "",
        "rows": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "needs-authoring", "rows": len(result), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__": raise SystemExit(main())
