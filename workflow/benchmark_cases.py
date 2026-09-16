"""唯一对标复刻案例编号登记与已审核案例解析。"""
from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "00_系统说明" / "benchmark-case-registry.json"
AUDIT_ROOT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "00_正式审核回执" / "benchmark-video-structure"
CASE_ID = re.compile(r"^[A-Z]+-\d{3}$")
TYPE_CODE = re.compile(r"^[A-Z]+$")
SOURCE_CATEGORY_DIRECTORY = re.compile(r"^(?P<ordinal>\d{2})_(?P<type>.+)原文(?P<member>（会员专享）)?$")
BREAKDOWN_ROOT = ROOT / "02_资产中心" / "05_案例库" / "02_对标复刻拆解"
SOURCE_ROOT = ROOT / "02_资产中心" / "05_案例库" / "01_对标视频原文"
SYNC_ROOT = ROOT / ".runtime" / "benchmark-case-sync"
OWNER_APPROVAL_ROOT = ROOT / "01_Agent系统" / "01_小姜-CEO助理Agent" / "人工确认回执" / "benchmark-video-structure"


def load_registry() -> dict[str, Any]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise ValueError("案例编号登记表 cases 必须为列表")
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("id") or "")
        if not CASE_ID.fullmatch(case_id) or case_id in seen:
            raise ValueError(f"案例编号登记表存在非法或重复编号：{case_id}")
        seen.add(case_id)
    type_codes = data.get("typeCodes") or {}
    if not isinstance(type_codes, dict):
        raise ValueError("案例编号登记表 typeCodes 必须为对象")
    used_codes: set[str] = set()
    for content_type, code in type_codes.items():
        if not str(content_type).strip() or not TYPE_CODE.fullmatch(str(code or "")) or str(code) in used_codes:
            raise ValueError(f"案例类型代码无效或重复：{content_type}={code}")
        used_codes.add(str(code))
    return data


def get_case(case_id: str) -> dict[str, Any]:
    if not CASE_ID.fullmatch(case_id):
        raise ValueError("对标复刻拆解编号必须为 <大写类型代码>-<三位流水号>")
    for case in load_registry()["cases"]:
        if case["id"] == case_id:
            result = dict(case)
            source_path = SOURCE_ROOT / f"{case['sourceTitle']}.md"
            if not source_path.is_file():
                matches = [path for path in SOURCE_ROOT.rglob(f"{case['sourceTitle']}.md") if path.is_file()]
                if len(matches) == 1:
                    source_path = matches[0]
            result["sourcePath"] = source_path
            result["breakdownPath"] = ROOT / str(case["breakdownPath"])
            # The registry default applies to generated cases.  A workspace
            # owner can explicitly promote one manually edited case without
            # weakening the audit policy for every other registered case.
            policy = str(result.get("manualEditPolicy") or load_registry().get("manualEditPolicy") or "")
            result["approvalMode"] = policy
            result["auditPath"] = (OWNER_APPROVAL_ROOT / f"{case_id}_人工确认回执.json"
                                   if policy == "owner-approved" else AUDIT_ROOT / f"{case_id}_审核回执.json")
            return result
    raise ValueError(f"案例编号不存在：{case_id}")


def _relative(path: Path) -> str:
    return Path(os.path.relpath(path.resolve(), ROOT)).as_posix()


def source_industry(source_title: str) -> str:
    """Return the industry segment of a source filename without its topic.

    Source filenames remain ``类型_行业：原文选题``.  The colon suffix is
    source-only context and must never be carried into a breakdown title.
    """
    title = str(source_title or "").strip()
    if "_" not in title:
        raise ValueError("源稿标题必须为“内容类型_行业：选题”")
    _, remainder = title.split("_", 1)
    industry = re.split(r"[：:]", remainder, maxsplit=1)[0].strip()
    if not industry:
        raise ValueError("源稿标题缺少行业字段")
    return industry


def _source_category(source: Path) -> tuple[str, str, str, str]:
    source = source.resolve()
    if not source.is_file() or source.suffix.lower() != ".md" or not source.is_relative_to(SOURCE_ROOT.resolve()):
        raise ValueError("新案例源稿必须是案例库对标视频原文目录内的 Markdown 文件")
    if "_" not in source.stem:
        raise ValueError("新案例源稿文件名必须为“内容类型_主题.md”")
    content_type, subject = (part.strip() for part in source.stem.split("_", 1))
    directory = SOURCE_CATEGORY_DIRECTORY.fullmatch(source.parent.name)
    if not content_type or not subject or not directory or directory.group("type") != content_type:
        raise ValueError("新案例源稿必须位于“NN_内容类型原文（会员专享）”目录，且文件名前缀须等于内容类型")
    output_directory = f"{directory.group('ordinal')}_{content_type}拆解{directory.group('member') or ''}"
    return content_type, subject, source.stem, output_directory


def _case_code(case_id: str) -> str:
    return case_id.rsplit("-", 1)[0]


def plan_case_registration(*, source: Path, type_code: str | None = None) -> dict[str, Any]:
    """Build a runtime-only plan for a registered or first-time benchmark case.

    This deliberately does not alter the registry or create a formal directory.
    New types require an explicit code on their first plan; published output is
    the only point at which the mapping and case are committed.
    """
    source = source.resolve()
    content_type, subject, source_title, output_directory = _source_category(source)
    registry = load_registry()
    matches = [item for item in registry["cases"] if str(item.get("sourceTitle") or "") == source_title]
    if len(matches) > 1:
        raise ValueError(f"源稿存在多个案例登记，无法选择：{source_title}")
    configured_code = str((registry.get("typeCodes") or {}).get(content_type) or "")
    requested_code = str(type_code or "").strip()
    if requested_code and not TYPE_CODE.fullmatch(requested_code):
        raise ValueError("首次内容类型代码必须只含大写英文字母")
    if matches:
        case = matches[0]
        case_id = str(case.get("id") or "")
        if str(case.get("type") or "") != content_type:
            raise ValueError("已登记案例的内容类型与当前源稿不一致")
        if requested_code and requested_code != _case_code(case_id):
            raise ValueError("已登记案例不得更换类型代码")
        registered_output = (ROOT / str(case.get("breakdownPath") or "")).resolve()
        return {
            "schema": "benchmark-case-registration-plan-v1", "status": "registered", "case_id": case_id,
            "type": content_type, "type_code": _case_code(case_id), "source_path": str(source),
            "source_sha256": _digest(source), "source_title": source_title,
            "formal_directory": str(registered_output.parent),
            "registered_breakdown_path": str(registered_output),
        }
    if configured_code and requested_code and configured_code != requested_code:
        raise ValueError(f"内容类型 {content_type} 已登记代码 {configured_code}，不得改为 {requested_code}")
    code = configured_code or requested_code
    if not code:
        raise ValueError(f"新内容类型 {content_type} 首次处理必须明确提供大写类型代码")
    owner = next((name for name, value in (registry.get("typeCodes") or {}).items() if str(value) == code and name != content_type), "")
    if owner:
        raise ValueError(f"类型代码 {code} 已被内容类型 {owner} 使用")
    sequence = max((int(str(item["id"]).rsplit("-", 1)[1]) for item in registry["cases"] if _case_code(str(item["id"])) == code), default=0) + 1
    if sequence > 999:
        raise ValueError(f"类型代码 {code} 的三位流水号已用尽")
    return {
        "schema": "benchmark-case-registration-plan-v1", "status": "new", "case_id": f"{code}-{sequence:03d}",
        "type": content_type, "type_code": code, "source_path": str(source), "source_sha256": _digest(source),
        "source_title": source_title, "subject": subject,
        "formal_directory": str((BREAKDOWN_ROOT / output_directory).resolve()),
    }


def write_case_registration_plan(plan: dict[str, Any], *, runtime_root: Path = SYNC_ROOT / "plans") -> Path:
    """Persist a candidate-scoped plan outside formal assets and the registry."""
    if plan.get("schema") != "benchmark-case-registration-plan-v1":
        raise ValueError("案例登记计划 schema 不正确")
    target = runtime_root.resolve() / f"{plan['case_id']}_{str(plan['source_sha256'])[:16]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return target


def load_case_registration_plan(path: Path, *, source: Path, case_id: str) -> dict[str, Any]:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"案例登记计划不可读取：{exc}") from exc
    expected = plan_case_registration(source=source, type_code=str(plan.get("type_code") or ""))
    for key in ("schema", "case_id", "type", "type_code", "source_path", "source_sha256", "formal_directory"):
        if plan.get(key) != expected.get(key):
            raise ValueError("案例登记计划与当前源稿或注册表已漂移")
    if plan.get("case_id") != case_id:
        raise ValueError("案例登记计划编号与发布编号不一致")
    return plan


def commit_published_case_registration(*, plan_path: Path, source: Path, case_id: str, formal_output: Path) -> dict[str, Any]:
    """Atomically add the first approved output of a new type to the registry."""
    plan = load_case_registration_plan(plan_path, source=source, case_id=case_id)
    formal = formal_output.resolve()
    target_directory = Path(str(plan["formal_directory"])).resolve()
    if formal.parent != target_directory or not formal.is_file() or not formal.is_relative_to(BREAKDOWN_ROOT.resolve()):
        raise ValueError("正式输出必须位于登记计划派生的镜像案例拆解目录")
    normalized = formal.stem.lstrip("√✓").strip()
    if not normalized.startswith(f"{plan['type']}_") or not normalized.endswith(case_id):
        raise ValueError("正式输出文件名必须保留内容类型和案例编号")
    registry = load_registry()
    existing = next((item for item in registry["cases"] if str(item.get("id") or "") == case_id), None)
    if existing:
        if str(existing.get("sourceTitle") or "") != str(plan["source_title"]):
            raise ValueError("案例编号已被其他源稿登记")
        return {"status": "already-registered", "case_id": case_id, "breakdown_path": str(formal)}
    type_codes = dict(registry.get("typeCodes") or {})
    mapped = str(type_codes.get(str(plan["type"])) or "")
    if mapped and mapped != plan["type_code"]:
        raise ValueError("发布时内容类型代码已变化")
    owner = next((name for name, value in type_codes.items() if str(value) == plan["type_code"] and name != plan["type"]), "")
    if owner:
        raise ValueError(f"发布时类型代码已被 {owner} 占用")
    type_codes[str(plan["type"])] = str(plan["type_code"])
    registry["typeCodes"] = type_codes
    registry["cases"].append({
        "id": case_id, "type": str(plan["type"]), "sourceTitle": str(plan["source_title"]),
        "breakdownTitle": formal.stem, "breakdownPath": _relative(formal),
    })
    temporary = REGISTRY.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, REGISTRY)
    return {"status": "registered", "case_id": case_id, "breakdown_path": str(formal)}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_owner_approval(case: dict[str, Any]) -> dict[str, Any]:
    source, breakdown = Path(case["sourcePath"]), Path(case["breakdownPath"])
    if not source.is_file() or not breakdown.is_file():
        raise ValueError(f"案例 {case['id']} 的源稿或正式拆解不存在")
    valid, reason = _valid_breakdown_candidate(breakdown, case)
    if not valid:
        raise ValueError(f"案例 {case['id']} 的手动版本身份校验失败：{reason}")
    target = OWNER_APPROVAL_ROOT / f"{case['id']}_人工确认回执.json"
    source_hash, output_hash = _digest(source), _digest(breakdown)
    if target.is_file():
        current = json.loads(target.read_text(encoding="utf-8"))
        if (current.get("status") == "approved" and current.get("source_sha256") == source_hash
                and current.get("output_sha256") == output_hash):
            return current
    receipt = {
        "schema": "benchmark-owner-approval-v1",
        "benchmark_case_id": case["id"],
        "status": "approved",
        "approval_basis": "workspace-owner-manual-edit",
        "approval_note": "工作区所有者声明：手动编辑后的正式拆解即为确认版本，只同步路径与哈希，不触发小审或自动修文。",
        "source_sha256": source_hash,
        "output_sha256": output_hash,
        "breakdown_path": str(breakdown.resolve()),
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return receipt


def _valid_breakdown_candidate(path: Path, case: dict[str, Any]) -> tuple[bool, str]:
    if not path.is_file() or path.suffix.lower() != ".md":
        return False, "文件不是 Markdown"
    normalized_stem = path.stem.lstrip("√✓").strip()
    if not normalized_stem.endswith(str(case["id"])):
        return False, "文件名未以案例编号结尾"
    if any(part.lower() in {"history", "archive", "99_归档"} for part in path.parts):
        return False, "文件位于历史或归档目录"
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() not in {f"# {path.stem}", f"# {normalized_stem}"}:
        return False, "H1 必须与文件名一致"
    if not normalized_stem.startswith(f"{case['type']}_"):
        return False, "文件名内容类型与案例登记不一致"
    return True, ""


def _registered_case_for_breakdown(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve a registered formal case by its exact current breakdown path."""
    resolved = path.resolve()
    registry = load_registry()
    for entry in registry["cases"]:
        registered = (ROOT / str(entry.get("breakdownPath") or "")).resolve()
        if registered == resolved:
            return registry, entry
    raise ValueError("只有已登记的正式对标拆解可以由所有者直接确认")


def validate_owner_approved_case_edit(*, previous_breakdown: Path, breakdown_markdown: Path, content: str) -> str:
    """Validate a proposed owner-confirmed edit before the workbench writes it."""
    _, entry = _registered_case_for_breakdown(previous_breakdown)
    target = breakdown_markdown.resolve()
    if not target.is_relative_to(BREAKDOWN_ROOT.resolve()):
        raise ValueError("手动确认的对标拆解必须保留在正式案例库目录")
    if not isinstance(content, str):
        raise ValueError("手动确认的对标拆解内容无效")
    normalized_stem = target.stem.lstrip("√✓").strip()
    case_id = str(entry["id"])
    if not normalized_stem.endswith(case_id) or not normalized_stem.startswith(f"{entry['type']}_"):
        raise ValueError("标题加 √ 时必须保留原内容类型和案例编号")
    first_line = content.splitlines()[0].strip() if content.splitlines() else ""
    if first_line not in {f"# {target.stem}", f"# {normalized_stem}"}:
        raise ValueError("标题加 √ 后，H1 必须保留同一案例标题")
    if "| 编号 | 大框架 | 小框架 | 小框架原文内容 |" not in content:
        raise ValueError("手动确认的对标拆解必须保留大/小框架四列表")
    from workflow.benchmark_structure_v3 import validate_portable_case_markdown
    validate_portable_case_markdown(content)
    return case_id


def record_owner_approved_case_edit(*, previous_breakdown: Path, breakdown_markdown: Path) -> dict[str, Any]:
    """Bind one owner-confirmed edit to its current path/hash and receipt."""
    content = breakdown_markdown.read_text(encoding="utf-8")
    case_id = validate_owner_approved_case_edit(
        previous_breakdown=previous_breakdown,
        breakdown_markdown=breakdown_markdown,
        content=content,
    )
    registry, entry = _registered_case_for_breakdown(previous_breakdown)
    relative = Path(os.path.relpath(breakdown_markdown.resolve(), ROOT)).as_posix()
    entry["breakdownTitle"] = breakdown_markdown.stem
    entry["breakdownPath"] = relative
    entry["manualEditPolicy"] = "owner-approved"
    temporary = REGISTRY.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, REGISTRY)
    receipt = _write_owner_approval(get_case(case_id))
    return {"case_id": case_id, "receipt_path": str((OWNER_APPROVAL_ROOT / f"{case_id}_人工确认回执.json").resolve()), "receipt": receipt}


def sync_registered_case_title(*, previous_breakdown: Path, breakdown_markdown: Path) -> dict[str, Any]:
    """Move a formally audited case's registry binding to its renamed output.

    This is deliberately narrower than normal publication: callers must prove
    the new file has already passed the appropriate current approval gate.
    It only changes the registry's title/path, never the case identity or
    approval policy.
    """
    target = breakdown_markdown.resolve()
    if not target.is_file() or not target.is_relative_to(BREAKDOWN_ROOT.resolve()):
        raise ValueError("标题同步目标必须是案例库内存在的正式 Markdown")
    registry, entry = _registered_case_for_breakdown(previous_breakdown)
    case_id = str(entry["id"])
    normalized_stem = target.stem.lstrip("√✓").strip()
    if (not normalized_stem.startswith(f"{entry['type']}_")
            or not normalized_stem.endswith(case_id)):
        raise ValueError("标题同步目标必须保留内容类型和案例编号")
    text = target.read_text(encoding="utf-8")
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    if first_line not in {f"# {target.stem}", f"# {normalized_stem}"}:
        raise ValueError("标题同步目标的 H1 必须与文件名一致")
    entry["breakdownTitle"] = target.stem
    entry["breakdownPath"] = _relative(target)
    temporary = REGISTRY.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, REGISTRY)
    return {"case_id": case_id, "breakdown_path": str(target)}


def discover_breakdown(case_id: str) -> Path:
    """Find one current formal breakdown by its stable terminal case ID."""
    case = get_case(case_id)
    candidates: list[Path] = []
    rejected: list[str] = []
    for path in BREAKDOWN_ROOT.rglob(f"*{case_id}.md"):
        valid, reason = _valid_breakdown_candidate(path, case)
        if valid:
            candidates.append(path.resolve())
        else:
            rejected.append(f"{path.resolve()}：{reason}")
    if len(candidates) != 1:
        detail = "；".join(str(path) for path in candidates) or "；".join(rejected) or "无候选"
        if len(candidates) > 1:
            raise ValueError(f"案例 {case_id} 存在多个同编号正式拆解，不能自动选择：{detail}")
        raise ValueError(f"案例 {case_id} 未发现合法的新拆解：{detail}")
    return candidates[0]


def reconcile_case_registration(case_id: str) -> dict[str, Any]:
    """Repair a stale registered breakdown path and write an auditable sync receipt."""
    case = get_case(case_id)
    registered = Path(case["breakdownPath"]).resolve()
    if registered.is_file():
        return {"status": "unchanged", "case_id": case_id, "breakdown_path": str(registered)}
    discovered = discover_breakdown(case_id)
    registry = load_registry()
    entry = next(item for item in registry["cases"] if item["id"] == case_id)
    old_path = str(entry["breakdownPath"])
    audit_path = AUDIT_ROOT / f"{case_id}_审核回执.json"
    prior_receipt = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    old_hash = str(prior_receipt.get("output_sha256") or "")
    new_hash = _digest(discovered)
    archived_receipt = ""
    if audit_path.is_file() and old_hash != new_hash:
        history = AUDIT_ROOT / "history"
        history.mkdir(parents=True, exist_ok=True)
        archived = history / f"{case_id}_审核_路径同步前_{old_hash[:16] or 'unknown'}.json"
        if not archived.exists():
            shutil.copyfile(audit_path, archived)
        archived_receipt = str(archived.resolve())
    # os.path.relpath normalizes Windows long/8.3 aliases more reliably than
    # Path.relative_to when a temporary or workspace root is exposed both ways.
    relative = Path(os.path.relpath(discovered, ROOT)).as_posix()
    entry["breakdownTitle"] = discovered.stem
    entry["breakdownPath"] = relative
    temporary = REGISTRY.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, REGISTRY)
    owner_approved = str(entry.get("manualEditPolicy") or registry.get("manualEditPolicy") or "") == "owner-approved"
    receipt = {
        "schema": "benchmark-case-sync-v1",
        "case_id": case_id,
        "status": "owner-approved" if owner_approved else ("path-synced" if old_hash == new_hash else "needs-current-reapproval"),
        "reason": "registered-breakdown-path-missing-and-unique-id-match-found",
        "old_breakdown_path": old_path,
        "new_breakdown_path": relative,
        "old_output_sha256": old_hash,
        "new_output_sha256": new_hash,
        "content_changed": old_hash != new_hash,
        "archived_prior_audit_receipt": archived_receipt,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    target = SYNC_ROOT / "cases" / case_id / f"{new_hash[:16]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if owner_approved:
        _write_owner_approval(get_case(case_id))
    return {**receipt, "sync_receipt": str(target.resolve())}


def approved_case(case_id: str) -> dict[str, Any]:
    reconcile_case_registration(case_id)
    case = get_case(case_id)
    if not case["sourcePath"].is_file() or not case["breakdownPath"].is_file():
        raise ValueError(f"案例 {case_id} 的源稿或正式拆解不存在")
    if case.get("approvalMode") == "owner-approved":
        _write_owner_approval(case)
    if not case["auditPath"].is_file():
        raise ValueError(f"案例 {case_id} 尚无对应正式批准回执")
    receipt = json.loads(case["auditPath"].read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(case["sourcePath"].read_bytes()).hexdigest()
    output_hash = hashlib.sha256(case["breakdownPath"].read_bytes()).hexdigest()
    if receipt.get("status") != "approved" or receipt.get("benchmark_case_id") != case_id:
        raise ValueError(f"案例 {case_id} 未通过与编号一致的正式批准")
    if receipt.get("source_sha256") != source_hash or receipt.get("output_sha256") != output_hash:
        raise ValueError(f"案例 {case_id} 的正式文件或源稿已变化，必须重新确认")
    case["audit"] = receipt
    return case
