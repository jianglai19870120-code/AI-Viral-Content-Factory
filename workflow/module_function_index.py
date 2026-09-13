"""Build a read-only functional index for formal processing-library modules.

The index deliberately separates *what a source says* from *what a structure
needs*.  It records original text only as a traceable asset reference; future
matching must use the new topic plus target framework and function labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import os
import time
import uuid
from pathlib import Path
from typing import Iterator


ROOT = Path(__file__).resolve().parents[1]
PROCESSING_ROOT = ROOT / "02_资产中心" / "02_处理库"
INDEX_FILE = ROOT / "04_数据中心" / "03_查询索引" / "module-function-index.jsonl"
CASE_CARD_INDEX_FILE = PROCESSING_ROOT / "05_案例_内容模块（会员专享）" / "02_案例卡索引" / "案例卡索引.jsonl"

FRAMEWORKS = {
    "01_观点_内容模块": "观点",
    "02_痛点_内容模块（会员专享）": "痛点",
    "03_误区_内容模块": "误区",
    "04_解决方案_内容模块": "解决方案",
    "05_案例_内容模块（会员专享）": "案例",
    "06_推荐理由_内容模块": "推荐理由",
}

# Pain cards are callable only through video-pain-angle-index.jsonl.  Their
# category taxonomy, archives, legacy cards and ordinary list documents are
# deliberately not generic function assets.
NON_MODULE_NAME_MARKERS = ("分类法", "清单", "列表", "索引", "目录", "汇总")

FUNCTION_KEYWORDS = (
    ("对象引入", ("引入", "对象", "主题")), ("可信度建立", ("背书", "权威", "经历", "筛选")),
    ("认知反转", ("误区", "反转", "纠偏", "借口")), ("问题呈现", ("痛点", "问题", "困境", "症状")),
    ("损失放大", ("损失", "代价", "后果", "风险")), ("情绪加压", ("焦虑", "压力", "恐惧", "不甘")),
    ("机制解释", ("机制", "原理", "逻辑", "为什么")), ("行动步骤", ("步骤", "方法", "执行", "怎么做")),
    ("结果验证", ("验证", "结果", "效果", "复盘")), ("情境引入", ("情境", "场景", "故事", "案例")),
    ("证据加压", ("证据", "数据", "事实", "证明")), ("结果兑现", ("兑现", "变化", "收获")),
    ("推荐收束", ("推荐", "收束", "总结", "建议")),
)


def supported_functions(*values: str) -> list[str]:
    text = " ".join(values).lower()
    matched = [function for function, words in FUNCTION_KEYWORDS if any(word in text for word in words)]
    return matched or ["待人工复核"]


def _id(path: Path, ordinal: int, text: str) -> str:
    raw = f"{path.as_posix()}:{ordinal}:{text}".encode("utf-8")
    return f"module-function:{hashlib.sha256(raw).hexdigest()[:16]}"


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _extract(path: Path, framework: str) -> Iterator[dict[str, object]]:
    """Yield one traceable record for each module bullet without modifying it."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return
    source_section = ""
    local_tag = ""
    ordinal = 0
    for line in lines:
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        h3 = re.match(r"^###\s+(.+?)\s*$", line)
        bullet = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if h2:
            source_section = h2.group(1)
            continue
        if h3:
            local_tag = h3.group(1).lstrip("#").strip()
            continue
        if not bullet:
            continue
        content = bullet.group(1).strip()
        if not content:
            continue
        ordinal += 1
        # The content remains evidence, never an automatic matching keyword.
        yield {
            "id": _id(path, ordinal, content),
            "kind": "processing-module-function",
            "framework": framework,
            "functionalCandidates": supported_functions(source_section, local_tag, content),
            "title": path.stem,
            "path": _relative(path),
            "sourcePath": _relative(path),
            "sourceSection": source_section,
            "localTag": local_tag,
            "ordinal": ordinal,
            "contentSha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "selectionBoundary": "本索引不复制模块正文。必须由文案结构生成 Skill 按新选题语义、目标大框架和目标小框架复核后，再读取 sourcePath 中的完整模块；不得按原文人名、案例、数字、行业词或结论作相似匹配。",
        }


def _extract_case_card(path: Path, record: dict[str, object]) -> Iterator[dict[str, object]]:
    """Expose one V12 case card as one callable case asset, never as loose bullets."""
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except OSError:
        return
    if "- 合同版本：work-journal-case-card-v12" not in text:
        return
    case_id = re.search(r"^-\s*案例卡编号[：:]\s*(.+)$", text, re.MULTILINE)
    callable_copy = re.search(r"^##\s*可直接调用案例\s*\n+(.+?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    boundary = re.search(r"^-\s*证据边界[：:]\s*(.+)$", text, re.MULTILINE)
    evidence_section = re.search(r"^##\s*原文依据\s*\n+(.+?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not case_id or not callable_copy:
        return
    case_copy = callable_copy.group(1).strip()
    if not case_copy:
        return
    continuous_quotes = re.findall(r"^>\s*(.+)$", evidence_section.group(1) if evidence_section else "", re.MULTILINE)
    if not continuous_quotes:
        return
    source_section = "可直接调用案例"
    yield {
        "id": f"case-card:{case_id.group(1).strip()}",
        "kind": "case-card-v12",
        "framework": "案例",
        "functionalCandidates": ["情境引入", "证据加压", "结果验证"],
        "title": path.stem,
        "path": _relative(path),
        "sourcePath": _relative(path),
        "sourceSection": source_section,
        "localTag": "",
        "ordinal": 1,
        "caseId": case_id.group(1).strip(),
        "caseCopy": case_copy,
        "caseCopySha256": hashlib.sha256(case_copy.encode("utf-8")).hexdigest(),
        "sourceEvidence": {"continuousQuotes": continuous_quotes},
        "evidenceBoundary": boundary.group(1).strip() if boundary else "",
        "sourceSha256": str(record.get("source_sha256") or ""),
        "auditReceiptPath": str(record.get("audit_receipt_path") or ""),
        "contentSha256": hashlib.sha256(case_copy.encode("utf-8")).hexdigest(),
        "selectionBoundary": "案例卡只能按选题、目标案例框架和框架功能检索。caseCopy 必须逐字进入结构三；不得按人名、行业词或原理关键词直接匹配。",
    }


def _case_card_rows() -> Iterator[dict[str, object]]:
    """Expose only CASE cards whose source and 小审 receipt still match the index."""
    try:
        lines = CASE_CARD_INDEX_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict) or record.get("schema_version") != "work-journal-case-card-v12":
            continue
        card_path = Path(str(record.get("card_path") or ""))
        source_path = Path(str(record.get("source_path") or ""))
        receipt_path = Path(str(record.get("audit_receipt_path") or ""))
        if not card_path.is_file() or not source_path.is_file() or not receipt_path.is_file():
            continue
        if str(record.get("source_sha256") or "") != hashlib.sha256(source_path.read_bytes()).hexdigest():
            continue
        if str(record.get("audit_receipt_sha256") or "") != hashlib.sha256(receipt_path.read_bytes()).hexdigest():
            continue
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        artifact = receipt.get("artifact") if isinstance(receipt.get("artifact"), dict) else {}
        if (
            receipt.get("schema") != "audit-receipt-v3"
            or receipt.get("artifactType") != "work-journal-case-card-v12"
            or receipt.get("status") != "approved"
            or str(artifact.get("sourceSha256") or "") != str(record.get("source_sha256") or "")
        ):
            continue
        yield from _extract_case_card(card_path, record)


def _is_generic_module(path: Path, framework: str) -> bool:
    relative = path.relative_to(PROCESSING_ROOT)
    if framework == "痛点":
        return False
    if "00_分类法" in relative.parts or "99_归档" in relative.parts:
        return False
    if path.name.startswith("00_") or path.name == "README.md" or any(marker in path.stem for marker in NON_MODULE_NAME_MARKERS):
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "schema: video-pain-card-v1" not in text


def build_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for folder, framework in FRAMEWORKS.items():
        root = PROCESSING_ROOT / folder
        if not root.is_dir():
            continue
        if framework == "案例":
            rows.extend(_case_card_rows())
            continue
        for path in sorted(root.rglob("*.md")):
            if not _is_generic_module(path, framework):
                continue
            rows.extend(_extract(path, framework))
    return rows


def write_index(rows: list[dict[str, object]]) -> None:
    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    last_error: PermissionError | None = None
    for attempt in range(8):
        temporary_root = ROOT / ".runtime" / "data-center-tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        temporary = temporary_root / f"{INDEX_FILE.name}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            os.replace(temporary, INDEX_FILE)
            return
        except PermissionError as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(f"模块索引被外部程序锁定，已重试 8 次：{INDEX_FILE}") from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="生成处理库模块功能索引（只读扫描）")
    parser.add_argument("--apply", action="store_true", help="写入数据中心查询索引")
    args = parser.parse_args()
    rows = build_rows()
    counts: dict[str, int] = {}
    for row in rows:
        framework = str(row["framework"])
        counts[framework] = counts.get(framework, 0) + 1
    if args.apply:
        write_index(rows)
    print(json.dumps({"status": "written" if args.apply else "dry-run", "rows": len(rows), "frameworkCounts": counts, "index": str(INDEX_FILE)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
