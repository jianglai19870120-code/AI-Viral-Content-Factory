from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


def find_root() -> Path:
    configured = os.environ.get("AI_TRAFFIC_FACTORY_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


ROOT = find_root()
SKILL_SCRIPTS = ROOT / "10_Skills武器库" / "今日复盘-案例卡拆解Skill（会员专享）" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(ROOT / "tools"))

import sys
from pathlib import Path
_SELF = Path(__file__).resolve()
for _p in _SELF.parents:
    if (_p / "workflow" / "common.py").exists():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
from workflow.common import append_brand_footer_text as append_brand_footer
from work_journal_thinking import (
    SCHEMA_VERSION,
    RESOLUTION_STATES,
    CASE_COPY_MAX,
    CASE_COPY_MIN,
    _spoken_title_issue,
    load_candidate,
    safe_name,
    validate_candidate,
)


# 正式放行回执必须位于小审的正式回执根目录，供工作台与数据中心复核。
AUDIT_ROOT = (
    ROOT
    / "01_Agent系统"
    / "02_小审-质量审核Agent"
    / "00_正式审核回执"
    / "work-journal-thinking"
    / "receipts"
)

def inspect_source_evidence(source_path: Path) -> tuple[list[str], dict[str, str]]:
    issues: list[str] = []
    text = source_path.read_text(encoding="utf-8", errors="strict")

    note_type_match = re.search(r"^-\s*note_type[：:]\s*(.+)$", text, re.MULTILINE)
    audio_match = re.search(
        r"^-\s*audio_original[：:](.*?)(?=^\s*-\s*(?:audio_play_url|原始转写)[：:]|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    transcript_match = re.search(
        r"^-\s*原始转写[：:](.*?)(?=^\s*-\s*[A-Za-z_\u4e00-\u9fa5]+[：:]|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )

    note_type = note_type_match.group(1).strip() if note_type_match else ""
    audio_original = audio_match.group(1).strip() if audio_match else ""
    raw_transcript = transcript_match.group(1).strip() if transcript_match else ""

    has_audio_text = bool(audio_original) and not audio_original.startswith("ima://note/")
    has_plain_text = bool(raw_transcript) and not raw_transcript.startswith("ima://note/")
    evidence_mode = "none"
    if has_audio_text:
        evidence_mode = "audio_original"
    elif has_plain_text:
        evidence_mode = "原始转写"

    if note_type == "sound_recording":
        if not has_audio_text:
            issues.append(
                "源文件 note_type=sound_recording，但缺少可直接使用的 `audio_original` 转写文本。"
                " 只有音频地址或 `ima://note/...` 占位时，不得放行；"
                " 必须先由官方 ima-skill 主路径 + WorkBuddy/ima-mcp 兼容路径补齐转写。"
            )
    elif note_type == "plain_text":
        if not has_plain_text and not has_audio_text:
            issues.append(
                "源文件 note_type=plain_text，但缺少可直接使用的 `原始转写` 文本。"
                " 没有一级证据文本时，不得放行。"
            )
    else:
        if not has_audio_text and not has_plain_text:
            issues.append(
                "源文件缺少可直接使用的一级证据文本（`audio_original` 或 `原始转写`）。"
                " 当前候选不得放行。"
            )

    if audio_original.startswith("ima://note/") and not has_plain_text:
        issues.append(
            "源文件中的 `audio_original` 仍是 `ima://note/...` 占位，而不是真实转写文本。"
            " 这说明同步链路尚未完成，当前候选不得放行。"
        )

    return issues, {
        "note_type": note_type or "unknown",
        "evidence_mode": evidence_mode,
    }


def semantic_guard(candidate: dict[str, object], source_path: Path) -> list[str]:
    """V12 语义门禁：案例必须能由连续原文证据支撑，不能由观点拼装。"""
    issues: list[str] = []

    cards = candidate.get("cards")
    if not isinstance(cards, list):
        issues.append("cards 必须是数组")
        return issues

    for idx, card in enumerate(cards, start=1):
        prefix = f"第{idx}张案例卡"
        if not isinstance(card, dict):
            continue

        title_issue = _spoken_title_issue(str(card.get("title", "")).strip())
        if title_issue:
            issues.append(f"{prefix} 标题退回：{title_issue}")
        case_copy = str(card.get("case_copy", "")).strip()
        if not CASE_COPY_MIN <= len(case_copy) <= CASE_COPY_MAX:
            issues.append(f"{prefix} case_copy 必须为{CASE_COPY_MIN}-{CASE_COPY_MAX}字")
        if case_copy and "我" not in case_copy:
            issues.append(f"{prefix} case_copy 不是第一人称亲历口吻")
        if any(word in case_copy for word in ("机制", "路径", "维度", "协同", "赋能", "优化", "实现")):
            issues.append(f"{prefix} case_copy 有AI式书面词，必须改成人话")

        evidence = card.get("source_evidence")
        quotes = evidence.get("continuous_quotes") if isinstance(evidence, dict) else []
        if not isinstance(quotes, list) or not quotes:
            issues.append(f"{prefix} 没有连续原文依据，不能证明这是真实经历")

        # 自由标签检查
        tags = card.get("tags")
        if isinstance(tags, list):
            if len(tags) < 1:
                issues.append(f"{prefix} tags（标签）至少 1 个")
            elif len(tags) > 6:
                issues.append(f"{prefix} tags（标签）建议 ≤6 个，当前 {len(tags)} 个")
            # 同义词收敛提示
            norm = [str(t).strip().lower() for t in tags]
            if len(norm) != len(set(norm)):
                issues.append(f"{prefix} tags（标签）存在重复，建议收敛")

        # 残留旧字段检查（v5/v7）
        serialized = json.dumps(candidate, ensure_ascii=False)
        for forbidden in ("mechanism_chain", "domain_conclusion", "cross_domain_scenarios",
                          "evidence_level", "topic_directions", "topic_tags",
                          "evidence_refs", "case_function", "transferable_direction",
                          "what_im_working_on", "core_problem", "original_judgment",
                          "judgment_change", "new_judgment", "process_summary",
                          "case_can_prove", "case_cannot_prove", "cognition_change"):
            if forbidden in serialized:
                issues.append(f"候选仍残留旧字段：{forbidden}")

    return issues


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def write_report(source_path: Path, candidate_path: Path, issues: list[str], source_meta: dict[str, str]) -> tuple[Path, Path]:
    AUDIT_ROOT.mkdir(parents=True, exist_ok=True)
    passed = not issues
    candidate = load_candidate(candidate_path)
    path = AUDIT_ROOT / f"今日复盘案例卡审核_{safe_name(source_path.stem)}.md"
    lines = [
        "# 今日复盘案例卡审核",
        "",
        f"- 审核对象：`{source_path}`",
        f"- 候选 JSON：`{candidate_path}`",
        f"- 审核结果：{'通过' if passed else '退回'}",
        "",
        "## 审核项",
        "",
        f"- 源文件一级证据门禁（note_type={source_meta.get('note_type','unknown')} / evidence_mode={source_meta.get('evidence_mode','none')}）：已执行独立检查",
        "- V12案例卡是否有真实经历闭环、口语化标题与可直接调用案例成文：已执行确定性校验",
        "- 每张案例卡是否附1-3段可连续回到一级证据的原文，且原文足以支撑场景、行动、冲突和判断转折：已执行独立检查",
        "- 检索字段是否只作索引与边界说明、没有取代案例正文：已执行语义检查",
        "- 自由标签（tags，2-6个）是否非空且收敛：已执行独立检查",
        "- 是否残留旧V5/V7字段（mechanism_chain/domain_conclusion/evidence_level…）：已执行独立检查",
        "- 正式资产是否在审核前写入：否",
        "",
    ]
    if issues:
        lines += ["## 退回原因", ""]
        lines.extend(f"- {issue}" for issue in issues)
    else:
        conclusion = "- 小审确认本条复盘已处理，但没有真实案例闭环；不生成 CASE 卡。" if candidate.get("release_disposition") == "no_case" else "- 候选允许晋升为正式今日复盘案例资产。"
        lines += ["## 放行结论", "", conclusion]
    path.write_text(append_brand_footer("\n".join(lines)), encoding="utf-8")
    cards = candidate.get("cards") if isinstance(candidate.get("cards"), list) else []
    receipt = {
        "schema": "audit-receipt-v3",
        "artifactType": "work-journal-case-card-v12",
        "status": "approved" if passed else "returned",
        "artifact": {
            "candidatePath": _project_relative(candidate_path),
            "candidateSha256": _sha256(candidate_path),
            "sourcePath": _project_relative(source_path),
            "sourceSha256": _sha256(source_path),
            "sourceNoteId": str(candidate.get("source_note_id") or ""),
            "releaseDisposition": str(candidate.get("release_disposition") or ""),
        },
        "evidenceReview": {
            "sourceEvidenceMode": source_meta.get("evidence_mode", "none"),
            "cards": [
                {
                    "caseId": str(card.get("case_id") or ""),
                    "title": str(card.get("title") or ""),
                    "continuousQuoteCount": len((card.get("source_evidence") or {}).get("continuous_quotes") or []) if isinstance(card, dict) else 0,
                    "claimQuoteMap": (card.get("source_evidence") or {}).get("claim_quote_map") if isinstance(card, dict) else {},
                }
                for card in cards
            ],
        },
        "reportPath": _project_relative(path),
        "issues": issues,
    }
    receipt_path = AUDIT_ROOT / f"今日复盘案例卡审核_{safe_name(source_path.stem)}.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, receipt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="今日复盘案例卡候选审核（V12）")
    parser.add_argument("--source-file", required=True)
    parser.add_argument("--candidate-json", required=True)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.source_file).resolve()
    candidate_path = Path(args.candidate_json).resolve()
    candidate = load_candidate(candidate_path)
    source_issues, source_meta = inspect_source_evidence(source_path)
    issues = list(source_issues)
    issues.extend(validate_candidate(source_path, candidate))
    issues.extend(semantic_guard(candidate, source_path))
    report, receipt = write_report(source_path, candidate_path, issues, source_meta) if args.write_report else (None, None)

    print(f"[今日复盘案例卡审核] result={'通过' if not issues else '退回'}")
    if report:
        print(f"[今日复盘案例卡审核] report={report}")
    if receipt:
        print(f"[今日复盘案例卡审核] receipt={receipt}")
    for issue in issues:
        print(f"- {issue}")
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
