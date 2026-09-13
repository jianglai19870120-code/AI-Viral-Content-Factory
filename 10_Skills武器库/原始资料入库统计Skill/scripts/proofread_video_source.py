"""生成视频文案的可追溯校对版候选，不覆盖标准化识别原文。

本工具只处理已逐视频标准化的 Markdown。所有实际改动均由带原文偏移的
change set 驱动；不提供自由改写、摘要或润色能力。输出仅应放在 runtime，
经小审放行且人工确认后才能作为后续拆解的候选输入。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workflow.common import append_brand_footer

TEXT_MARKER = "\n## 全文\n\n"
SCHEMA = "video-source-correction-candidate-v1"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_source(source_path: Path) -> tuple[str, dict[str, str], str]:
    """读取标准化源文档并返回相对路径、frontmatter、未校对全文。"""
    content = source_path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError("源文档缺少 YAML frontmatter")
    frontmatter_end = content.find("\n---\n", 4)
    if frontmatter_end < 0 or TEXT_MARKER not in content:
        raise ValueError("源文档缺少完整 frontmatter 或 ## 全文")
    metadata: dict[str, str] = {}
    for line in content[4:frontmatter_end].splitlines():
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.+)$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        try:
            metadata[key] = str(json.loads(raw_value))
        except json.JSONDecodeError:
            metadata[key] = raw_value.strip().strip('"')
    text = content.split(TEXT_MARKER, 1)[1].rstrip("\n")
    try:
        relative = source_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:  # unit-test fixture; production candidates require a project-relative source
        relative = source_path.resolve().as_posix()
    return relative, metadata, text


def load_changes(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "video-source-correction-changes-v1":
        raise ValueError("修改清单 schema 必须是 video-source-correction-changes-v1")
    changes = payload.get("changes")
    if not isinstance(changes, list):
        raise ValueError("修改清单缺少 changes 数组")
    return changes


def _located_change(
    original_text: str,
    change_id: str,
    change_type: str,
    original_text_fragment: str,
    corrected_text: str,
    reason: str,
    status: str,
) -> dict[str, Any]:
    """仅为固定试跑样本生成可审的精确偏移；匹配不唯一即失败。"""
    start = original_text.find(original_text_fragment)
    if start < 0 or original_text.find(original_text_fragment, start + 1) >= 0:
        raise ValueError(f"试跑修改 {change_id} 的原文片段缺失或不唯一：{original_text_fragment}")
    return {
        "change_id": change_id,
        "type": change_type,
        "original_start": start,
        "original_end": start + len(original_text_fragment),
        "original_text": original_text_fragment,
        "corrected_text": corrected_text,
        "reason": reason,
        "status": status,
    }


def pilot_jingwei_changes(original_text: str) -> list[dict[str, Any]]:
    """固定试跑样本的保守修改集；疑义片段明确保持 pending。"""
    return [
        _located_change(original_text, "C-001", "明显错别字", "编利导", "编导", "行业通称与相邻“操盘手或者叫编导”语境一致", "applied"),
        _located_change(original_text, "C-002", "重复音节/标点", "当他意识到这件事。事情的时候", "当他意识到这件事情的时候", "同一句内“事。事情”重复且标点断裂", "applied"),
        _located_change(original_text, "C-003", "重复音节/标点", "老板。板他才会", "老板，他才会", "“板”与前一词“老板”重复，句内标点断裂", "applied"),
        _located_change(original_text, "P-001", "待确认", "但是这种审美他一定一个时间段录像。", "但是这种审美他一定一个时间段录像。", "疑似识别错漏，但无法仅凭上下文确定原话，保留原样", "pending"),
        _located_change(original_text, "P-002", "待确认", "但是你确定性。呢，给我出3条有用的视频", "但是你确定性。呢，给我出3条有用的视频", "疑似断句或漏字，但无法确定原话，保留原样", "pending"),
    ]


def validate_and_apply(original_text: str, changes: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """验证原文定位后，自后向前应用 approved 的非重叠替换。"""
    required = {"change_id", "type", "original_start", "original_end", "original_text", "corrected_text", "reason", "status"}
    prior_start = len(original_text) + 1
    applied: list[dict[str, Any]] = []
    for change in sorted(changes, key=lambda item: int(item["original_start"]), reverse=True):
        missing = required - set(change)
        if missing:
            raise ValueError(f"{change.get('change_id', 'unknown')} 缺少字段：{', '.join(sorted(missing))}")
        start, end = int(change["original_start"]), int(change["original_end"])
        if start < 0 or end < start or end > len(original_text):
            raise ValueError(f"{change['change_id']} 的原文偏移超出范围")
        if end > prior_start:
            raise ValueError(f"{change['change_id']} 与其他修改重叠")
        if original_text[start:end] != change["original_text"]:
            raise ValueError(f"{change['change_id']} 的 original_text 与原文偏移不匹配")
        prior_start = start
        if change["status"] == "applied":
            applied.append(change)

    corrected = original_text
    for change in sorted(applied, key=lambda item: int(item["original_start"]), reverse=True):
        start, end = int(change["original_start"]), int(change["original_end"])
        corrected = corrected[:start] + str(change["corrected_text"]) + corrected[end:]
    return corrected, sorted(changes, key=lambda item: (int(item["original_start"]), str(item["change_id"])))


def render_candidate(
    source_relative_path: str,
    source_path: Path,
    metadata: dict[str, str],
    original_text: str,
    corrected_text: str,
    changes: list[dict[str, Any]],
) -> str:
    source_id = metadata.get("source_id", "")
    if not source_id:
        raise ValueError("标准化源文档缺少 source_id")
    pending = [change for change in changes if change["status"] != "applied"]
    frontmatter = {
        "schema": SCHEMA,
        "source_id": source_id,
        "account": metadata.get("account", ""),
        "source_serial": metadata.get("source_serial", ""),
        "source_row": metadata.get("source_row", ""),
        "title": metadata.get("title", ""),
        "link": metadata.get("link", ""),
        "original_source_path": source_relative_path,
        "original_source_sha256": sha256_file(source_path),
        "original_full_text_sha256": sha256_text(original_text),
        "corrected_full_text_sha256": sha256_text(corrected_text),
        "correction_scope": "仅明显错别字、标点、断句、重复音节；不润色、不概括、不补充",
        "change_count": len(changes),
        "applied_change_count": len(changes) - len(pending),
        "pending_change_count": len(pending),
    }
    lines = ["---"]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in frontmatter.items())
    lines.extend([
        "---",
        "",
        f"# 校对版源文档候选｜{source_id}",
        "",
        "## 校对原则",
        "",
        "- 仅修正证据明确的错别字、标点、断句或重复音节。",
        "- 保留博主口语、语气、观点与表达顺序；不润色、不概括、不补充。",
        "- 语义无法确定处不改写，列入待确认项。",
        "",
        "## 校对后全文",
        "",
        corrected_text,
        "",
        "## 修改清单",
        "",
        "```jsonl",
    ])
    lines.extend(json.dumps(change, ensure_ascii=False, sort_keys=True) for change in changes)
    lines.extend(["```", "", "## 待确认项", ""])
    if pending:
        lines.extend(f"- `{change['change_id']}`｜{change['original_text']}｜{change['reason']}" for change in pending)
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def write_candidate(source_path: Path, changes: list[dict[str, Any]], output_dir: Path) -> Path:
    relative, metadata, original_text = read_source(source_path)
    corrected_text, validated_changes = validate_and_apply(original_text, changes)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / f"{metadata['source_id']}-校对版候选.md"
    candidate_path.write_text(
        render_candidate(relative, source_path, metadata, original_text, corrected_text, validated_changes),
        encoding="utf-8",
        newline="\n",
    )
    append_brand_footer(candidate_path)
    return candidate_path


def main() -> int:
    parser = argparse.ArgumentParser(description="生成视频文案的校对版候选（不覆盖识别原文）")
    parser.add_argument("--source", type=Path, required=True, help="标准化逐视频源文档")
    change_group = parser.add_mutually_exclusive_group(required=True)
    change_group.add_argument("--changes", type=Path, help="带精确偏移的 JSON 修改清单")
    change_group.add_argument("--pilot-jingwei-000001", action="store_true", help="使用固定试跑样本的保守修改集")
    parser.add_argument("--output-dir", type=Path, required=True, help="运行区候选目录")
    args = parser.parse_args()
    source_path = args.source.resolve()
    if args.pilot_jingwei_000001:
        _, metadata, original_text = read_source(source_path)
        if metadata.get("source_id") != "VS-jingwei-01-000001":
            raise ValueError("--pilot-jingwei-000001 只能用于 VS-jingwei-01-000001")
        changes = pilot_jingwei_changes(original_text)
        changes_path = args.output_dir.resolve() / "校对修改清单.json"
        changes_path.parent.mkdir(parents=True, exist_ok=True)
        changes_path.write_text(
            json.dumps({"schema": "video-source-correction-changes-v1", "source_id": metadata["source_id"], "changes": changes}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        changes = load_changes(args.changes.resolve())
    candidate_path = write_candidate(source_path, changes, args.output_dir.resolve())
    print(f"已生成校对版候选：{candidate_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
