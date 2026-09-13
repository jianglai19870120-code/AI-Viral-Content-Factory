"""小审：视频文案痛点、观点、误区模块审核门禁。

只审不改。这个脚本读取标准化视频源文档的 manifest 和正文，验证候选或
正式模块的来源链、分类、证据与索引。它不依赖未冻结的业务正文模板：卡片
只需使用 frontmatter，证据可以放在卡片内或 JSON sidecar 中。

回执严格按现役 ``audit-receipt-v3`` 字段写入，同时保留可审计的 checks、
执行回执和 handoff 绑定扩展字段。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_ROOT = (
    ROOT / "02_资产中心" / "01_输入库" / "04_视频文案-源文件（会员专享）" / "00_标准化源文档"
)
DEFAULT_TAXONOMY = ROOT / "02_资产中心" / "02_处理库" / "02_痛点_内容模块（会员专享）" / "00_分类法" / "痛点分类法.md"
DEFAULT_INDEX = ROOT / "04_数据中心" / "03_查询索引" / "module-function-index.jsonl"

PAIN_SCHEMA = "video-pain-card-v1"
VIEWPOINT_SCHEMAS = {"video-viewpoint-card-v1", "video-opinion-card-v1", "video-quote-card-v1"}
MISCONCEPTION_SCHEMAS = {"video-misconception-card-v1", "video-mistake-card-v1"}
CARD_SCHEMAS = {PAIN_SCHEMA, *VIEWPOINT_SCHEMAS, *MISCONCEPTION_SCHEMAS}

REQUIRED_CHECK_IDS = [
    "schema-and-classification",
    "pain-id-uniqueness",
    "source-evidence",
    "corrected-source-original-locator",
    "machine-candidate-boundary",
    "pain-card-completeness",
    "plain-language-reader-fields",
    "expression-provenance",
    "expression-completeness",
    "pending-placement",
    "viewpoint-misconception-provenance",
    "index-paths",
]

EXPRESSION_CONTEXT_DIMENSIONS = (
    "object_or_person",
    "scene",
    "pain_or_contradiction",
    "consequence_or_realization",
)
MIN_COMPLETE_EXPRESSION_CHARS = 45


@dataclass(frozen=True)
class Check:
    id: str
    layer: str
    name: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "layer": self.layer, "name": self.name, "status": self.status, "detail": self.detail}


@dataclass
class Card:
    path: Path
    relpath: str
    frontmatter: dict[str, Any]
    body: str
    schema: str
    card_id: str


def expression_compact(value: str) -> str:
    return re.sub(r"[\s，。！？、；：,.!?;:—-]", "", value)


def check_expression_completeness(item: dict[str, Any], source_text: str, excerpt: str) -> list[str]:
    """Enforce original-first, context-complete pain expressions.

    Semantic dimension discovery is performed by 小拆, but each supplied
    dimension must be explicitly evidenced inside the rendered expression.
    This prevents a short conclusion from being passed off as a usable scene.
    """
    issues: list[str] = []
    evidence_id = str(item.get("evidence_id") or "<无 ID>")
    expression = str(item.get("short_video_expression") or "")
    mode = str(item.get("expression_mode") or "")
    cited_text = expression
    if mode == "light_splice":
        fragments = item.get("expression_source_fragments") if isinstance(item.get("expression_source_fragments"), list) else []
        if not fragments:
            return [f"机器证据 {evidence_id} light_splice 必须提供带字符定位的 expression_source_fragments"]
        pieces: list[str] = []
        for number, fragment in enumerate(fragments, start=1):
            if not isinstance(fragment, dict):
                issues.append(f"机器证据 {evidence_id} light_splice 第 {number} 个引用片段不是对象")
                continue
            text = str(fragment.get("text") or "")
            start, end = fragment.get("start_offset"), fragment.get("end_offset")
            if not text or not isinstance(start, int) or not isinstance(end, int) or source_text[start:end] != text:
                issues.append(f"机器证据 {evidence_id} light_splice 第 {number} 个引用片段无法精确回原文")
            else:
                pieces.append(text)
        cited_text = "".join(pieces)
        if pieces and expression_compact(expression) != expression_compact(cited_text):
            issues.append(f"机器证据 {evidence_id} light_splice 含未被引用片段支持的改写内容")
    elif mode == "direct_quote":
        if expression != excerpt:
            issues.append(f"机器证据 {evidence_id} direct_quote 必须逐字等于连续 source_excerpt")
    profile = item.get("expression_completeness") if isinstance(item.get("expression_completeness"), dict) else {}
    short_issue = ""
    if len(expression_compact(expression)) < MIN_COMPLETE_EXPRESSION_CHARS and len(expression_compact(source_text)) >= MIN_COMPLETE_EXPRESSION_CHARS and not str(profile.get("concise_complete_reason") or ""):
        short_issue = f"机器证据 {evidence_id} 为短表达但未说明其已完整承载可得上下文，疑为孤立结论"
    if profile.get("schema") != "pain-expression-completeness-v1":
        return issues + ([short_issue] if short_issue else []) + [f"机器证据 {evidence_id} 缺 pain-expression-completeness-v1 完整性声明"]
    available = profile.get("available_dimensions") if isinstance(profile.get("available_dimensions"), list) else []
    covered = profile.get("covered_dimensions") if isinstance(profile.get("covered_dimensions"), list) else []
    unavailable = profile.get("unavailable_dimensions") if isinstance(profile.get("unavailable_dimensions"), list) else []
    fragments = profile.get("dimension_fragments") if isinstance(profile.get("dimension_fragments"), dict) else {}
    if set(available) | set(unavailable) != set(EXPRESSION_CONTEXT_DIMENSIONS) or set(available) & set(unavailable):
        issues.append(f"机器证据 {evidence_id} 完整性维度必须穷尽且互斥：对象/场景/矛盾/结果")
    if set(covered) != set(available) or len(available) < 3:
        issues.append(f"机器证据 {evidence_id} 必须覆盖所有原文可得维度，且至少覆盖 3 个维度")
    for dimension in available:
        fragment = str(fragments.get(dimension) or "")
        if not fragment or expression_compact(fragment) not in expression_compact(expression) or fragment not in cited_text:
            issues.append(f"机器证据 {evidence_id} 的 {dimension} 未被当前表达及引用原文完整承载")
    for item_unavailable in unavailable:
        reason = profile.get("unavailable_reasons", {}).get(item_unavailable) if isinstance(profile.get("unavailable_reasons"), dict) else ""
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"机器证据 {evidence_id} 未说明 {item_unavailable} 为何原文不可得")
    if short_issue:
        issues.append(short_issue)
    return issues


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审核视频文案痛点/观点/误区卡片；只审不改")
    parser.add_argument("--candidate-root", required=True, help="候选或正式视频文案模块根目录")
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT), help="标准化源文档目录（含 manifest.jsonl）")
    parser.add_argument("--taxonomy", default=str(DEFAULT_TAXONOMY), help="痛点分类法 Markdown 或 JSON")
    parser.add_argument("--index", default=str(DEFAULT_INDEX), help="模块检索索引 JSONL")
    parser.add_argument("--evidence-root", action="append", default=[], help="额外 evidence JSON 目录；可重复")
    parser.add_argument("--mode", choices=("candidate", "formal"), default="candidate")
    parser.add_argument("--task-id", default="", help="调度任务 ID；为空时根据审核范围生成可重复 ID")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--receipt", required=True, help="正式 JSON 审核回执路径")
    parser.add_argument("--execution-receipt", required=True, help="当前任务的 receipt-v2 执行回执")
    parser.add_argument("--handoff-binding-sha256", required=True, help="当前 handoff 的 execution binding SHA-256")
    return parser.parse_args()


def scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("[") or value.startswith("{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value.strip("\"'")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse a deliberately small, dependency-free YAML frontmatter subset.

    Arrays may be JSON or YAML ``- item`` lines. Nested arbitrary YAML is left
    to sidecars, which keeps the production card format deliberately flexible.
    """
    if not text.startswith("---"):
        return {}, text
    end = re.search(r"^---\s*$", text[3:], re.M)
    if not end:
        return {}, text
    header_end = 3 + end.start()
    header = text[3:header_end].strip("\r\n")
    body = text[3 + end.end():].lstrip("\r\n")
    result: dict[str, Any] = {}
    active_list: str | None = None
    for raw in header.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if re.match(r"^\s*-\s+", line) and active_list:
            result.setdefault(active_list, []).append(scalar(re.sub(r"^\s*-\s+", "", line)))
            continue
        match = re.match(r"^([\w\-\u4e00-\u9fff]+)\s*:\s*(.*)$", line)
        if not match:
            active_list = None
            continue
        key, value = match.groups()
        result[key] = scalar(value)
        active_list = key if value.strip() == "" else None
    return result, body


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if "," in value:
            return [part.strip() for part in value.split(",") if part.strip()]
        return [value.strip()] if value.strip() else []
    return [str(value).strip()]


def first_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def load_cards(root: Path) -> tuple[list[Card], list[str]]:
    issues: list[str] = []
    cards: list[Card] = []
    if not root.is_dir():
        return [], [f"审核根目录不存在：{root}"]
    for path in sorted(root.rglob("*.md")):
        frontmatter, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
        schema = str(first_value(frontmatter, "schema", "卡片schema") or "")
        if schema not in CARD_SCHEMAS:
            # A taxonomy / README can coexist with cards; it is not an asset.
            continue
        card_id = str(first_value(frontmatter, "pain_id", "viewpoint_id", "misconception_id", "card_id", "id") or "")
        cards.append(Card(path, path.relative_to(root).as_posix(), frontmatter, body, schema, card_id))
    if not cards:
        issues.append("未发现具有受支持 schema 的视频模块卡片")
    return cards, issues


def load_sources(source_root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    manifest = source_root / "manifest.jsonl"
    sources: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    if not manifest.is_file():
        return sources, [f"缺少标准化来源清单：{manifest}"]
    for number, line in enumerate(manifest.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            issues.append(f"manifest 第 {number} 行不是 JSON")
            continue
        source_id = str(item.get("source_id") or "").strip()
        relative_path = str(item.get("relative_path") or "").strip()
        if not source_id or not relative_path:
            issues.append(f"manifest 第 {number} 行缺 source_id 或 relative_path")
            continue
        source_path = source_root / relative_path
        if not source_path.is_file():
            issues.append(f"{source_id} 指向的标准化源文档不存在：{relative_path}")
            continue
        frontmatter, body = parse_frontmatter(source_path.read_text(encoding="utf-8", errors="ignore"))
        if str(frontmatter.get("source_id") or "") != source_id:
            issues.append(f"{source_id} 的 manifest 与源文档 source_id 不一致")
            continue
        full_text = extract_full_text(body)
        if not full_text:
            issues.append(f"{source_id} 源文档缺少 ## 全文 或全文为空")
            continue
        expected_hash = str(item.get("full_text_sha256") or "")
        if expected_hash and hashlib.sha256(full_text.encode("utf-8")).hexdigest() != expected_hash:
            issues.append(f"{source_id} 全文哈希与 manifest 不一致")
        sources[source_id] = {"path": source_path, "full_text": full_text, "manifest": item}
    return sources, issues


def extract_full_text(body: str) -> str:
    match = re.search(r"^##\s+(?:全文|校对后全文)\s*$\s*(.*?)(?=^##\s+|\Z)", body, re.M | re.S)
    return match.group(1).strip() if match else ""


def correction_source_path(item: dict[str, Any]) -> Path | None:
    """Return the runtime correction source for an evidence item, if any."""
    value = first_value(item, "standardized_path", "corrected_source_path")
    if not value:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        return None
    frontmatter, _ = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
    return path if str(frontmatter.get("schema") or "") == "video-source-correction-candidate-v1" else None


def verify_correction_origin(item: dict[str, Any], sources: dict[str, dict[str, Any]]) -> list[str]:
    """Verify both corrected and original positions for runtime correction evidence."""
    correction_path = correction_source_path(item)
    if correction_path is None:
        return []
    prefix = f"校对版证据 {item.get('evidence_id') or item.get('card_id') or '<未知>'}"
    issues: list[str] = []
    correction_frontmatter, correction_body = parse_frontmatter(correction_path.read_text(encoding="utf-8", errors="ignore"))
    corrected_text = extract_full_text(correction_body)
    source_id = str(item.get("source_id") or "").strip()
    excerpt = str(first_value(item, "excerpt", "text", "quote", "原文片段", "原文") or "")
    start, end = item.get("start_offset"), item.get("end_offset")
    if str(correction_frontmatter.get("source_id") or "") != source_id:
        issues.append(f"{prefix} 的校对版 source_id 不匹配")
    expected_corrected_hash = str(first_value(item, "full_text_sha256", "corrected_full_text_sha256") or "")
    if not expected_corrected_hash or hashlib.sha256(corrected_text.encode("utf-8")).hexdigest() != expected_corrected_hash:
        issues.append(f"{prefix} 校对版全文哈希不匹配")
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or corrected_text[start:end] != excerpt:
        issues.append(f"{prefix} 校对版字符定位或片段不精确")
    original = sources.get(source_id)
    if not original:
        issues.append(f"{prefix} 无法找到 source_id 对应的原识别源")
        return issues
    original_path_value = str(item.get("original_source_path") or "").strip()
    if not original_path_value:
        issues.append(f"{prefix} 缺 original_source_path")
    else:
        original_path = Path(original_path_value)
        if not original_path.is_absolute():
            original_path = ROOT / original_path
        if original_path.resolve() != original["path"].resolve():
            issues.append(f"{prefix} original_source_path 未指向 source_id 的原识别源")
    original_text = original["full_text"]
    expected_original_hash = str(item.get("original_full_text_sha256") or "")
    if not expected_original_hash or hashlib.sha256(original_text.encode("utf-8")).hexdigest() != expected_original_hash:
        issues.append(f"{prefix} original_full_text_sha256 不匹配")
    original_excerpt = str(item.get("original_excerpt") or "")
    original_start, original_end = item.get("original_start_offset"), item.get("original_end_offset")
    if isinstance(original_start, bool) or isinstance(original_end, bool) or not isinstance(original_start, int) or not isinstance(original_end, int) or original_start < 0 or original_end < original_start or original_text[original_start:original_end] != original_excerpt:
        issues.append(f"{prefix} 原识别版字符定位或片段不精确")
    return issues


def load_taxonomy(path: Path) -> tuple[set[str], list[str]]:
    """Read paths from JSON or common Markdown taxonomy heading layouts."""
    if not path.is_file():
        return set(), [f"痛点分类法不存在：{path}"]
    text = path.read_text(encoding="utf-8", errors="ignore")
    paths: set[str] = set()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        if payload.get("schema") == "video-pain-taxonomy-v2":
            if payload.get("status") != "frozen":
                return set(), ["v2 痛点分类法尚未冻结"]
            for primary in payload.get("primary_categories", []) if isinstance(payload.get("primary_categories"), list) else []:
                name = str(primary.get("name") or "").strip()
                boundary = str(primary.get("boundary") or "").strip()
                children = primary.get("secondary_keywords") if isinstance(primary.get("secondary_keywords"), list) else []
                if not name or not boundary or len(children) < 2:
                    return set(), [f"v2 一级分类不具备大主题边界或两个二级词：{name or '空'}"]
                for child in children:
                    secondary = str(child.get("name") or "").strip()
                    if not secondary or any(token in secondary for token in ("、", "/", "-", "_", " ")):
                        return set(), [f"v2 二级分类不是单一问题词：{name}/{secondary or '空'}"]
                    paths.add(normalize_path(f"{name}/{secondary}"))
        values = first_value(payload, "classification_paths", "paths", "分类路径")
        for value in as_str_list(values):
            paths.add(normalize_path(value))
    elif isinstance(payload, list):
        for value in payload:
            if isinstance(value, dict):
                value = first_value(value, "classification_path", "path", "分类路径")
            for item in as_str_list(value):
                paths.add(normalize_path(item))
    else:
        current_major = ""
        for line in text.splitlines():
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if heading:
                level = len(heading.group(1))
                label = clean_heading(heading.group(2))
                if level == 1:
                    current_major = "" if label in {"痛点分类法", "分类法"} else label
                elif level == 2:
                    if current_major:
                        paths.add(normalize_path(f"{current_major}/{label}"))
                    else:
                        current_major = label
                continue
            bullet = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if bullet:
                candidate = clean_heading(bullet.group(1))
                if "/" in candidate:
                    paths.add(normalize_path(candidate))
    return {item for item in paths if item}, ([] if paths else ["痛点分类法未解析出任何分类路径"])


def clean_heading(value: str) -> str:
    return re.sub(r"\s*[-—:：].*$", "", value).strip().strip("`*")


def normalize_path(value: str) -> str:
    return re.sub(r"\s*/\s*", "/", str(value).replace("＞", "/").replace(">", "/").strip("/ "))


def load_evidence(roots: Iterable[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence: list[dict[str, Any]] = []
    issues: list[str] = []
    seen: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() and root.suffix.lower() == ".json" else sorted(root.rglob("*.json"))
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            try:
                payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            except json.JSONDecodeError:
                # An unrelated JSON candidate must not make the audit unable to run.
                continue
            extracted = list(iter_evidence_objects(payload))
            for item in extracted:
                item["_evidence_path"] = path
                evidence.append(item)
    return evidence, issues


def iter_evidence_objects(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from iter_evidence_objects(item)
    elif isinstance(payload, dict):
        if first_value(payload, "source_id") and first_value(payload, "excerpt", "text", "quote", "原文片段", "原文"):
            yield dict(payload)
        for key in ("evidence", "items", "records", "entries", "cards", "modules"):
            child = payload.get(key)
            if child is not None:
                yield from iter_evidence_objects(child)


def inline_evidence(card: Card) -> list[dict[str, Any]]:
    raw = first_value(card.frontmatter, "evidence", "evidences", "证据")
    entries: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        entries.append(raw)
    elif isinstance(raw, list):
        entries.extend(item for item in raw if isinstance(item, dict))
    # Quote blocks underneath an evidence/source heading are a convenient
    # Markdown-native alternative to a sidecar. Each quoted line is evidence.
    active = False
    source_ids = source_ids_for(card)
    for line in card.body.splitlines():
        if re.match(r"^#{2,6}\s+.*(原文|证据|场景).*$", line):
            active = True
            continue
        if active and line.startswith("##"):
            active = False
        if active and line.lstrip().startswith(">"):
            excerpt = line.lstrip()[1:].strip()
            if excerpt and source_ids:
                entries.append({"source_id": source_ids[0], "excerpt": excerpt, "card_id": card.card_id})
    return entries


def source_ids_for(card: Card) -> list[str]:
    return as_str_list(first_value(card.frontmatter, "source_ids", "source_id", "来源source_ids", "来源source_id"))


def evidence_for_card(card: Card, sidecar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aliases = {card.card_id, card.relpath, card.path.name, card.path.stem}
    matched: list[dict[str, Any]] = []
    for item in sidecar:
        candidates = set()
        for key in ("card_id", "pain_id", "viewpoint_id", "misconception_id", "module_id", "card_path", "module_path"):
            candidates.update(as_str_list(item.get(key)))
        if aliases & candidates:
            matched.append(item)
    return inline_evidence(card) + matched


def card_in_pending(card: Card) -> bool:
    return "待归类" in card.relpath.replace("\\", "/") or str(card.frontmatter.get("status") or "") in {"pending", "待归类"}


def has_field(card: Card, keys: tuple[str, ...], headings: tuple[str, ...] = ()) -> bool:
    if first_value(card.frontmatter, *keys) not in (None, "", [], {}):
        return True
    return any(re.search(rf"^#+\s*{re.escape(heading)}\s*$", card.body, re.M) for heading in headings)


def _machine_evidence_item(item: dict[str, Any]) -> dict[str, Any]:
    """Adapt the routed JSON record to the shared source-audit vocabulary."""
    binding = item.get("source_binding") if isinstance(item.get("source_binding"), dict) else {}
    return {
        "source_id": item.get("source_id"), "excerpt": item.get("source_excerpt"),
        "start_offset": item.get("start_offset"), "end_offset": item.get("end_offset"),
        "standardized_path": binding.get("standardized_path"), "full_text_sha256": binding.get("full_text_sha256"),
        "original_source_path": item.get("original_source_path"),
        "original_full_text_sha256": item.get("original_full_text_sha256"),
        "original_start_offset": item.get("original_start_offset"),
        "original_end_offset": item.get("original_end_offset"), "original_excerpt": item.get("original_excerpt"),
        "evidence_id": item.get("evidence_id"), "card_id": item.get("pain_id") or item.get("evidence_id"),
    }


def audit_machine_candidates(candidate_root: Path, source_root: Path, taxonomy_path: Path, index_path: Path, mode: str) -> tuple[list[Check], dict[str, Any]]:
    """Audit JSON-only v2 candidates without rendering or modifying a card.

    Runtime machine evidence intentionally has no Markdown browsing card. This
    performs the same source/provenance gates directly on routed-modules.json
    and leaves formal rendering exclusively to ``promote`` after approval.
    """
    routed_path = candidate_root / "routed-modules.json"
    sources, source_issues = load_sources(source_root)
    taxonomy, taxonomy_issues = load_taxonomy(taxonomy_path)
    issues: list[str] = []
    try:
        routed = json.loads(routed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        routed = {}
        issues.append(f"机器候选 routed-modules 无法读取：{exc}")
    markdown_cards = sorted(candidate_root.rglob("*.md")) if candidate_root.is_dir() else []
    boundary_issues = []
    if markdown_cards:
        boundary_issues.append("运行期机器候选不得含 Markdown 浏览卡：" + "；".join(project_rel(path) for path in markdown_cards))
    if routed.get("schema") != "video-module-machine-candidates-v2":
        boundary_issues.append("机器候选缺少 schema=video-module-machine-candidates-v2 的 routed-modules.json")
    checks: list[Check] = [make_check("machine-candidate-boundary", "mechanical", "运行期仅机器 JSON，浏览卡延迟渲染", boundary_issues)]
    cards = routed.get("pain_cards") if isinstance(routed.get("pain_cards"), list) else []
    micros = routed.get("micro_modules") if isinstance(routed.get("micro_modules"), list) else []
    notes = {"machine_candidate": True, "pain_card_count": len(cards), "micro_module_count": len(micros), "source_count": len(sources)}

    schema_issues = list(issues) + list(taxonomy_issues)
    for card in cards:
        if not isinstance(card, dict):
            schema_issues.append("pain_cards 含非对象记录")
            continue
        primary = str(card.get("primary_category") or card.get("category_name") or "")
        secondary = str(card.get("secondary_keyword") or card.get("subcategory_name") or "")
        path = normalize_path(f"{primary}/{secondary}")
        if not card.get("pain_id") or not card.get("pain_title") or not card.get("pain_definition"):
            schema_issues.append("机器痛点记录缺 pain_id/pain_title/pain_definition")
        if not primary or not secondary or any(token in secondary for token in ("、", "/", "-", "_", " ")):
            schema_issues.append(f"机器痛点 {card.get('pain_id') or '<无 ID>'} 缺一级/二级或二级不是单词")
        if not path or path not in taxonomy:
            schema_issues.append(f"机器痛点 {card.get('pain_id') or '<无 ID>'} 分类路径不在冻结分类法：{path}")
    checks.append(make_check("schema-and-classification", "mechanical", "机器候选 schema 与痛点分类路径", schema_issues))

    ids = [str(card.get("pain_id") or "") for card in cards if isinstance(card, dict)]
    id_issues = ["机器痛点缺 pain_id" for value in ids if not value]
    id_issues += ["pain_id 重复：" + key for key, amount in Counter(value for value in ids if value).items() if amount > 1]
    checks.append(make_check("pain-id-uniqueness", "mechanical", "机器痛点 ID 唯一性", id_issues))

    plain_language_terms = ("用户画像", "内容策略", "价值主张", "流量机制", "叙事", "心智", "转化链路", "方法论", "底层逻辑", "商业闭环", "颗粒度")
    hedging_terms = ("可能", "建议", "可考虑", "视情况")
    plain_language_fields = ("title", "definition", "audience", "angle", "framing")
    plain_language_issues: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("pain_id") or "<无 ID>")
        card_review = card.get("plain_language_review") if isinstance(card.get("plain_language_review"), dict) else {}
        if (card_review.get("schema") != "pain-card-plain-language-v1"
                or any(card_review.get(field) != "passed" for field in plain_language_fields)
                or card_review.get("reader_test") != "小学生能听懂，能直接说出口，不用专业词"):
            plain_language_issues.append(f"机器痛点 {card_id} 缺或未通过 pain-card-plain-language-v1 人读复核")
        fields = [("标题", card.get("pain_title")), ("痛点定义", card.get("pain_definition"))]
        fields.extend(("适用对象", item) for item in card.get("audiences", []) if isinstance(item, str))
        for label, value in fields:
            text = str(value or "")
            bad = [term for term in (*plain_language_terms, *hedging_terms) if term in text]
            if bad:
                plain_language_issues.append(f"机器痛点 {card_id} 的{label}含未解释行话或回避词：{'、'.join(bad)}")
        for angle in card.get("angles", []) if isinstance(card.get("angles"), list) else []:
            if not isinstance(angle, dict):
                continue
            angle_review = angle.get("plain_language_review") if isinstance(angle.get("plain_language_review"), dict) else {}
            if (angle_review.get("schema") != "pain-card-plain-language-v1"
                    or any(angle_review.get(field) != "passed" for field in plain_language_fields)
                    or angle_review.get("reader_test") != "小学生能听懂，能直接说出口，不用专业词"):
                plain_language_issues.append(f"机器痛点 {card_id} 的角度 {angle.get('angle_title') or '<无标题>'} 缺或未通过口语化复核")
            for label, value in (("切入角度", angle.get("angle_title")), ("怎么讲", angle.get("how_to_frame"))):
                text = str(value or "")
                bad = [term for term in (*plain_language_terms, *hedging_terms) if term in text]
                if bad:
                    plain_language_issues.append(f"机器痛点 {card_id} 的{label}含未解释行话或回避词：{'、'.join(bad)}")

    evidence_issues = list(source_issues)
    correction_issues: list[str] = []
    completeness_issues: list[str] = []
    expression_issues: list[str] = []
    expression_completeness_issues: list[str] = []
    seen_evidence: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        if not isinstance(card.get("audiences"), list) or not isinstance(card.get("scene_tags"), list) or not isinstance(card.get("angles"), list) or not card.get("angles"):
            completeness_issues.append(f"机器痛点 {card.get('pain_id') or '<无 ID>'} 缺 audiences/scene_tags/angles")
            continue
        for angle in card["angles"]:
            if not isinstance(angle, dict) or not angle.get("angle_title") or not angle.get("how_to_frame") or not angle.get("short_video_expression"):
                completeness_issues.append(f"机器痛点 {card.get('pain_id')} 含不完整切入角度")
                continue
            evidence = angle.get("evidence") if isinstance(angle.get("evidence"), list) else []
            if not evidence:
                completeness_issues.append(f"机器痛点 {card.get('pain_id')} 的角度 {angle.get('angle_title')} 缺证据")
                continue
            modes = {str(item.get("expression_mode") or "") for item in evidence if isinstance(item, dict)}
            bases = {str(item.get("expression_basis") or "") for item in evidence if isinstance(item, dict)}
            if bases != {"基于原文整理"} or not modes <= {"direct_quote", "light_splice"} or not modes:
                expression_issues.append(f"机器痛点 {card.get('pain_id')} 的表达来源声明或 expression_mode 不合法")
            for item in evidence:
                if not isinstance(item, dict):
                    evidence_issues.append(f"机器痛点 {card.get('pain_id')} 含非对象证据")
                    continue
                machine_item = _machine_evidence_item(item)
                evidence_id = str(machine_item.get("evidence_id") or "")
                if evidence_id:
                    seen_evidence.add(evidence_id)
                source_id = str(machine_item.get("source_id") or "")
                source = sources.get(source_id)
                if not source:
                    evidence_issues.append(f"机器证据 {evidence_id or '<无 ID>'} 指向不存在 source_id：{source_id}")
                    continue
                excerpt = str(machine_item.get("excerpt") or "")
                correction_path = correction_source_path(machine_item)
                if correction_path is None:
                    start, end = machine_item.get("start_offset"), machine_item.get("end_offset")
                    if not isinstance(start, int) or not isinstance(end, int) or source["full_text"][start:end] != excerpt:
                        evidence_issues.append(f"机器证据 {evidence_id or '<无 ID>'} 无法精确回到标准化全文")
                else:
                    correction_issues.extend(verify_correction_origin(machine_item, sources))
                expression_source_text = correction_path and extract_full_text(parse_frontmatter(correction_path.read_text(encoding="utf-8", errors="ignore"))[1]) or source["full_text"]
                if str(item.get("expression_mode") or "") == "light_splice":
                    fragments = item.get("expression_source_excerpts") if isinstance(item.get("expression_source_excerpts"), list) else []
                    if not fragments or any(str(fragment) not in expression_source_text for fragment in fragments):
                        expression_issues.append(f"机器证据 {evidence_id or '<无 ID>'} light_splice 缺可回溯 expression_source_excerpts")
                expression_completeness_issues.extend(check_expression_completeness(item, expression_source_text, excerpt))
    checks.append(make_check("source-evidence", "mechanical", "机器证据与原文片段精确追溯", evidence_issues))
    checks.append(make_check("corrected-source-original-locator", "mechanical", "校对版机器证据回原识别版定位", correction_issues))
    checks.append(make_check("pain-card-completeness", "content", "机器痛点场景、角度与表达字段", completeness_issues))
    checks.append(make_check("plain-language-reader-fields", "content", "标题、定义、对象、角度与怎么讲均为秒懂口语", plain_language_issues))
    checks.append(make_check("expression-provenance", "content", "表达方式的原文来源与轻拼接边界", expression_issues))
    checks.append(make_check("expression-completeness", "content", "表达优先连续原文且完整呈现对象、场景、矛盾与结果", expression_completeness_issues))

    pending_issues = []
    if mode == "formal":
        for card in cards:
            if isinstance(card, dict) and "待归类" in f"{card.get('primary_category')}/{card.get('secondary_keyword')}":
                pending_issues.append(f"正式机器候选混入待归类：{card.get('pain_id')}")
    checks.append(make_check("pending-placement", "mechanical", "待归类隔离", pending_issues))

    downstream_issues: list[str] = []
    for item in micros:
        if not isinstance(item, dict) or item.get("module_type") not in {"viewpoint", "misconception"}:
            downstream_issues.append("机器微模块类型非法")
            continue
        if not item.get("source_id") or not item.get("evidence_id"):
            downstream_issues.append("机器微模块缺 source_id/evidence_id")
        if item.get("module_type") == "viewpoint" and not item.get("reusable_statement"):
            downstream_issues.append(f"观点微模块 {item.get('evidence_id')} 缺 reusable_statement")
        if item.get("module_type") == "misconception" and (not item.get("misconception") or not item.get("correction")):
            downstream_issues.append(f"误区微模块 {item.get('evidence_id')} 缺 misconception/correction")
    checks.append(make_check("viewpoint-misconception-provenance", "mechanical", "机器观点与误区来源链", downstream_issues))

    index_issues: list[str] = []
    # A batch candidate owns its JSON-only index beside routed-modules.  When
    # callers use the generic default index, prefer that immutable candidate
    # index instead of accidentally inspecting the unrelated legacy module
    # index in the data centre.
    candidate_index = candidate_root / "candidate-module-index.jsonl"
    effective_index = candidate_index if index_path == DEFAULT_INDEX and candidate_index.is_file() else index_path
    if not effective_index.is_file():
        index_issues.append(f"机器候选索引不存在：{effective_index}")
    else:
        records = [json.loads(line) for line in effective_index.read_text(encoding="utf-8").splitlines() if line.strip()]
        for card in cards:
            if not isinstance(card, dict):
                continue
            card_id = str(card.get("pain_id") or "")
            matches = [row for row in records if str(row.get("card_id") or "") == card_id]
            if not matches or not any(Path(str(row.get("machine_candidate_path") or "")).is_file() for row in matches):
                index_issues.append(f"机器痛点 {card_id or '<无 ID>'} 缺只指向 JSON 机器证据的索引")
    checks.append(make_check("index-paths", "mechanical", "机器索引仅指向 JSON 证据", index_issues))
    return checks, notes


def audit(
    candidate_root: Path,
    source_root: Path,
    taxonomy_path: Path,
    index_path: Path,
    evidence_roots: list[Path],
    mode: str,
) -> tuple[list[Check], dict[str, Any]]:
    if (candidate_root / "routed-modules.json").is_file():
        return audit_machine_candidates(candidate_root, source_root, taxonomy_path, index_path, mode)
    cards, card_load_issues = load_cards(candidate_root)
    sources, source_issues = load_sources(source_root)
    taxonomy, taxonomy_issues = load_taxonomy(taxonomy_path)
    sidecar, _ = load_evidence([candidate_root / "evidence", *evidence_roots])
    notes: dict[str, Any] = {"card_count": len(cards), "source_count": len(sources), "taxonomy_path_count": len(taxonomy), "sidecar_evidence_count": len(sidecar)}

    schema_issues = list(card_load_issues) + list(taxonomy_issues)
    pain_cards = [card for card in cards if card.schema == PAIN_SCHEMA]
    for card in pain_cards:
        classification = normalize_path(str(first_value(card.frontmatter, "classification_path", "分类路径") or ""))
        if not classification:
            schema_issues.append(f"{card.relpath} 缺 classification_path")
        elif classification not in taxonomy:
            schema_issues.append(f"{card.relpath} 分类路径不在冻结分类法：{classification}")
    checks: list[Check] = [make_check("schema-and-classification", "mechanical", "schema 与痛点分类路径", schema_issues)]

    id_issues: list[str] = []
    duplicate_ids = [key for key, amount in Counter(card.card_id for card in pain_cards if card.card_id).items() if amount > 1]
    for card in pain_cards:
        if not card.card_id:
            id_issues.append(f"{card.relpath} 缺 pain_id")
        elif not re.fullmatch(r"P(?:AIN)?-[A-Za-z0-9][A-Za-z0-9_-]*", card.card_id):
            id_issues.append(f"{card.relpath} pain_id 格式不稳定：{card.card_id}")
    if duplicate_ids:
        id_issues.append("pain_id 重复：" + "、".join(sorted(duplicate_ids)))
    checks.append(make_check("pain-id-uniqueness", "mechanical", "痛点 ID 唯一性", id_issues))

    evidence_issues = list(source_issues)
    correction_locator_issues: list[str] = []
    evidence_by_card: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        evidence = evidence_for_card(card, sidecar)
        evidence_by_card[card.relpath] = evidence
        source_ids = source_ids_for(card)
        if not source_ids:
            evidence_issues.append(f"{card.relpath} 缺 source_id/source_ids")
        if not evidence:
            evidence_issues.append(f"{card.relpath} 缺可审核的原文证据（sidecar 或原文证据引用）")
        for item in evidence:
            source_id = str(item.get("source_id") or "").strip()
            excerpt = str(first_value(item, "excerpt", "text", "quote", "原文片段", "原文") or "").strip()
            if not source_id:
                evidence_issues.append(f"{card.relpath} 有证据但缺 source_id")
                continue
            if source_id not in sources:
                evidence_issues.append(f"{card.relpath} 引用不存在的 source_id：{source_id}")
                continue
            correction_path = correction_source_path(item)
            if not excerpt:
                evidence_issues.append(f"{card.relpath} 的 {source_id} 证据缺原文片段")
            elif correction_path is None and excerpt not in sources[source_id]["full_text"]:
                evidence_issues.append(f"{card.relpath} 的 {source_id} 证据片段未在标准化全文精确找到：{excerpt[:60]}")
            if correction_path is not None:
                correction_locator_issues.extend(verify_correction_origin(item, sources))
            if source_ids and source_id not in source_ids:
                evidence_issues.append(f"{card.relpath} 证据 source_id 未列入卡片 source_ids：{source_id}")
    checks.append(make_check("source-evidence", "mechanical", "来源与原文片段精确追溯", evidence_issues))
    checks.append(make_check("corrected-source-original-locator", "mechanical", "校对版证据回原识别版定位", correction_locator_issues))

    completeness_issues: list[str] = []
    for card in pain_cards:
        requirements = [
            (("pain_definition", "痛点定义"), ("痛点定义",)),
            (("target_people", "applicable_people", "适用人群"), ("适用人群", "目标人群")),
            (("scene_tags", "场景标签"), ("场景标签",)),
            (("entry_angles", "切入角度"), ("切入角度",)),
            (("how_to_tell", "怎么讲"), ("怎么讲",)),
        ]
        for keys, headings in requirements:
            if not has_field(card, keys, headings):
                completeness_issues.append(f"{card.relpath} 缺字段：{keys[0]}")
    checks.append(make_check("pain-card-completeness", "content", "痛点卡场景与讲法字段", completeness_issues))

    expression_issues: list[str] = []
    for card in pain_cards:
        has_expression = has_field(card, ("short_video_expression", "短视频表达"), ("短视频表达",))
        provenance = str(first_value(card.frontmatter, "expression_provenance", "短视频表达来源") or "")
        if not has_expression:
            expression_issues.append(f"{card.relpath} 缺短视频表达")
        if "基于原文整理" not in provenance and "基于原文整理" not in card.body:
            expression_issues.append(f"{card.relpath} 未明确短视频表达为“基于原文整理”")
    checks.append(make_check("expression-provenance", "content", "短视频表达来源声明", expression_issues))

    pending_issues: list[str] = []
    if mode == "formal":
        for card in cards:
            if card_in_pending(card):
                pending_issues.append(f"正式审核范围混入待归类候选：{card.relpath}")
    checks.append(make_check("pending-placement", "mechanical", "待归类隔离", pending_issues))

    downstream_issues: list[str] = []
    for card in cards:
        if card.schema not in VIEWPOINT_SCHEMAS | MISCONCEPTION_SCHEMAS:
            continue
        if not card.card_id:
            downstream_issues.append(f"{card.relpath} 缺卡片 ID")
        if not source_ids_for(card):
            downstream_issues.append(f"{card.relpath} 缺来源链 source_ids")
        if not evidence_by_card[card.relpath]:
            downstream_issues.append(f"{card.relpath} 缺来源原文证据")
        if card.schema in MISCONCEPTION_SCHEMAS and not has_field(card, ("wrong_belief", "错误观点"), ("错误观点", "错误认知")):
            downstream_issues.append(f"{card.relpath} 误区卡缺错误观点")
        if card.schema in VIEWPOINT_SCHEMAS and not has_field(card, ("viewpoint", "观点", "quote", "金句"), ("观点", "金句")):
            downstream_issues.append(f"{card.relpath} 观点卡缺观点/金句")
    checks.append(make_check("viewpoint-misconception-provenance", "mechanical", "观点与误区来源链", downstream_issues))

    index_issues = verify_index(index_path, cards)
    checks.append(make_check("index-paths", "mechanical", "检索索引与模块路径", index_issues))
    notes["pain_card_count"] = len(pain_cards)
    return checks, notes


def make_check(identifier: str, layer: str, name: str, issues: list[str]) -> Check:
    return Check(identifier, layer, name, "failed" if issues else "passed", "；".join(issues) if issues else "通过")


def verify_index(index_path: Path, cards: list[Card]) -> list[str]:
    if not index_path.is_file():
        return [f"模块检索索引不存在：{index_path}"]
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for number, line in enumerate(index_path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            issues.append(f"索引第 {number} 行不是 JSON")
    by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for key in ("pain_id", "viewpoint_id", "misconception_id", "card_id", "module_id", "id"):
            if record.get(key):
                by_id[str(record[key])].append(record)
    for card in cards:
        matches = by_id.get(card.card_id, [])
        if not matches:
            issues.append(f"{card.relpath} 缺索引记录：{card.card_id or '无 ID'}")
            continue
        expected = card.path.resolve()
        if not any(index_path_exists(record, expected) for record in matches):
            issues.append(f"{card.relpath} 的索引路径不存在或未指向该卡片")
    return issues


def index_path_exists(record: dict[str, Any], expected: Path) -> bool:
    value = first_value(record, "path", "module_path", "card_path", "asset_path")
    if not value:
        return False
    path = Path(str(value))
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve() == expected and path.is_file()


def stable_task_id(candidate_root: Path) -> str:
    return hashlib.sha256(project_rel(candidate_root).encode("utf-8")).hexdigest()[:16]


def file_record(path: Path) -> dict[str, Any]:
    return {"path": project_rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def output_records(cards: list[Card]) -> list[dict[str, Any]]:
    return [file_record(card.path) for card in cards]


def receipt_payload(
    task_id: str,
    attempt: int,
    candidate_root: Path,
    cards: list[Card],
    checks: list[Check],
    mechanical_path: Path,
    semantic_path: Path,
    execution_receipt: Path,
    handoff_binding_sha256: str,
) -> dict[str, Any]:
    failed = [check for check in checks if check.status != "passed"]
    status = "rejected" if failed else "approved"
    candidate_hash = sha256_tree(candidate_root)
    mechanical = [check for check in checks if check.layer == "mechanical"]
    semantic = [check for check in checks if check.layer != "mechanical"]
    # The root is an artifact collection. Hashing it, rather than rewriting it,
    # gives the receipt the same original/final immutability binding as v3.
    payload = {
        "schema": "audit-receipt-v3",
        "artifactType": "video-module-assets-v1",
        "task_id": task_id,
        "attempt": attempt,
        "auditor": "xiaoshen",
        "auditor_skill_id": "xiaoshen-audit",
        "auditor_version": "3.4.0",
        "status": status,
        "artifact": {
            "type": "video-module-assets-v1",
            "artifact_id": f"video-module-audit:{candidate_hash[:12]}",
            "candidate_path": project_rel(candidate_root),
            "candidate_sha256": candidate_hash,
            "source_path": project_rel(candidate_root),
            "source_sha256": candidate_hash,
        },
        "generatedAt": now(),
        "subject": {
            "candidate": project_rel(candidate_root),
            "candidateSha256": candidate_hash,
            "executionReceipt": project_rel(execution_receipt),
            "executionReceiptSha256": sha256_file(execution_receipt),
            "handoffBindingSha256": handoff_binding_sha256,
        },
        "required_check_ids": REQUIRED_CHECK_IDS,
        "checks": [check.as_dict() for check in checks],
        "mechanical_result": {
            "status": "failed" if any(check.status != "passed" for check in mechanical) else "passed",
            "path": project_rel(mechanical_path),
            "sha256": sha256_file(mechanical_path),
            "bytes": mechanical_path.stat().st_size,
            "check_ids": [check.id for check in mechanical],
            "issues": [check.detail for check in mechanical if check.status != "passed"],
        },
        "semantic_review": {
            "status": "failed" if any(check.status != "passed" for check in semantic) else "passed",
            "path": project_rel(semantic_path),
            "sha256": sha256_file(semantic_path),
            "bytes": semantic_path.stat().st_size,
            "reviewer": "xiaoshen",
            "required_block_ids": [check.id for check in semantic],
        },
        "handoff_binding_sha256": handoff_binding_sha256,
        "execution_receipt": project_rel(execution_receipt),
        "execution_receipt_sha256": sha256_file(execution_receipt),
        "original_outputs": output_records(cards),
        "final_outputs": output_records(cards),
        "note": "仅审核，未改写任何卡片或来源文档。",
        "audited_at": now(),
    }
    return payload


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def write_audit_records(receipt_path: Path, checks: list[Check], notes: dict[str, Any]) -> tuple[Path, Path]:
    """Persist the v3-required mechanical and semantic evidence before receipt."""
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    mechanical_path = receipt_path.with_name(receipt_path.stem + ".mechanical.json")
    semantic_path = receipt_path.with_name(receipt_path.stem + ".semantic-review.json")
    mechanical_checks = [check.as_dict() for check in checks if check.layer == "mechanical"]
    semantic_checks = [check.as_dict() for check in checks if check.layer != "mechanical"]
    mechanical_path.write_text(json.dumps({
        "schema": "video-module-mechanical-audit-v1", "checks": mechanical_checks,
        "notes": notes, "audited_at": now(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    semantic_path.write_text(json.dumps({
        "schema": "video-module-semantic-review-v1", "reviewer": "xiaoshen",
        "checks": semantic_checks, "notes": notes, "audited_at": now(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return mechanical_path, semantic_path


def main() -> int:
    args = parse_args()
    candidate_root = Path(args.candidate_root).resolve()
    checks, notes = audit(
        candidate_root,
        Path(args.source_root).resolve(),
        Path(args.taxonomy).resolve(),
        Path(args.index).resolve(),
        [Path(value).resolve() for value in args.evidence_root],
        args.mode,
    )
    task_id = args.task_id or stable_task_id(candidate_root)
    if not re.fullmatch(r"[a-f0-9]{16}", task_id):
        raise SystemExit("--task-id 必须是 16 位小写十六进制；或省略以自动生成")
    execution_receipt = Path(args.execution_receipt).resolve()
    handoff_binding = args.handoff_binding_sha256.strip()
    if not execution_receipt.is_file():
        raise SystemExit(f"--execution-receipt 不存在：{execution_receipt}")
    if not re.fullmatch(r"[a-f0-9]{64}", handoff_binding):
        raise SystemExit("--handoff-binding-sha256 必须是 64 位小写十六进制")
    receipt_path = Path(args.receipt).resolve()
    cards, _ = load_cards(candidate_root)
    mechanical_path, semantic_path = write_audit_records(receipt_path, checks, notes)
    receipt = receipt_payload(
        task_id, args.attempt, candidate_root, cards, checks, mechanical_path,
        semantic_path, execution_receipt, handoff_binding,
    )
    output = json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
    receipt_path.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if receipt["status"] == "approved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
