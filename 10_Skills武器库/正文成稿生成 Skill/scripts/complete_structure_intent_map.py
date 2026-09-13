#!/usr/bin/env python3
"""Complete a generated intent-map request without changing frozen user content."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def anchors_for_user_statement(item: dict, user_text: str, intent_id: str) -> list[dict]:
    """Validate framework-local content anchors without rewriting user text."""
    anchors = item.get("content_anchors") if isinstance(item.get("content_anchors"), list) else []
    if not anchors:
        raise SystemExit(f"{intent_id} 必须拆出至少一个结构四内容锚点")
    result: list[dict] = []
    seen: set[str] = set()
    for index, anchor in enumerate(anchors, start=1):
        if not isinstance(anchor, dict):
            raise SystemExit(f"{intent_id} 的第 {index} 个内容锚点非法")
        anchor_id = str(anchor.get("anchor_id") or "").strip()
        source_text = str(anchor.get("source_text") or "").strip()
        main_meaning = str(anchor.get("main_meaning") or "").strip()
        keywords = anchor.get("required_keywords") if isinstance(anchor.get("required_keywords"), list) else []
        assigned = anchor.get("assigned_small_structure_ids") if isinstance(anchor.get("assigned_small_structure_ids"), list) else []
        protected = anchor.get("protected_terms") if isinstance(anchor.get("protected_terms"), list) else keywords
        if (not anchor_id or anchor_id in seen or not source_text or source_text not in user_text or not main_meaning
                or not keywords or not assigned):
            raise SystemExit(f"{intent_id} 的内容锚点必须含唯一编号、原文片段、主旨、关键词和所属小框架")
        if any(not isinstance(value, str) or not value.strip() or value.strip() not in source_text for value in keywords):
            raise SystemExit(f"{intent_id}/{anchor_id} 的关键词必须来自该锚点原文片段")
        if any(not isinstance(value, str) or not value.strip() for value in assigned + protected):
            raise SystemExit(f"{intent_id}/{anchor_id} 的小框架编号或保护词非法")
        seen.add(anchor_id)
        result.append({
            "anchor_id": anchor_id,
            "source_text": source_text,
            "main_meaning": main_meaning,
            "required_keywords": [value.strip() for value in keywords],
            "assigned_small_structure_ids": [value.strip() for value in assigned],
            "protected_terms": [value.strip() for value in protected],
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="补全结构四正文意图映射")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--completion", type=Path, required=True, help="仅含主题、主旨和用户原文关键词的完成信息")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    completion = json.loads(args.completion.read_text(encoding="utf-8"))
    source_rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    completed_rows = completion.get("rows") if isinstance(completion.get("rows"), list) else []
    by_id = {str(row.get("intent_id") or ""): row for row in completed_rows if isinstance(row, dict)}
    expected = {str(row.get("intent_id") or "") for row in source_rows if isinstance(row, dict)}
    if not expected or set(by_id) != expected:
        raise SystemExit("完成信息必须且只能覆盖当前冻结结构四的全部核心大框架")
    topic = str(payload.get("topic") or "")
    terms = completion.get("topic_terms") if isinstance(completion.get("topic_terms"), list) else []
    if not terms or any(not isinstance(term, str) or not term.strip() or term.strip() not in topic for term in terms):
        raise SystemExit("主题词必须来自当前选题标题")
    for row in source_rows:
        item = by_id[str(row["intent_id"])]
        keywords = item.get("required_keywords") if isinstance(item.get("required_keywords"), list) else []
        user_text = str(row.get("user_statement") or "")
        if not str(item.get("main_meaning") or "").strip() or not keywords or any(not isinstance(word, str) or not word.strip() or word.strip() not in user_text for word in keywords):
            raise SystemExit(f"{row['intent_id']} 必须提供来自用户结构四原文的关键词和主旨")
        row["main_meaning"] = str(item["main_meaning"]).strip()
        row["required_keywords"] = [word.strip() for word in keywords]
        if str(row.get("origin") or "") == "user-filled":
            anchors = anchors_for_user_statement(item, user_text, str(row["intent_id"]))
            row["content_anchors"] = anchors
        else:
            row["content_anchors"] = []
    payload["topic_terms"] = [term.strip() for term in terms]
    payload["topic_meaning"] = str(completion.get("topic_meaning") or "").strip()
    if not payload["topic_meaning"]:
        raise SystemExit("缺少选题主旨")
    payload["status"] = "completed"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "completed", "rows": len(source_rows), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
