"""Canonical, machine-readable writing-expression contract loader."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "10_Skills武器库" / "contracts"
ACTIVE_CONTRACT_PATH = CONTRACT_ROOT / "writing-expression-contract-v3.json"
ACTIVE_CONTRACT_VIEW_PATH = ROOT / "10_Skills武器库" / "写作文案表达合同.md"
ARCHIVE_CONTRACT_PATH = CONTRACT_ROOT / "history" / "writing-expression-contract-v1.md"
REQUIRED_RULE_FIELDS = {"id", "section", "title", "scopes", "severity", "directive", "evidence", "source_anchors"}
REQUIRED_CHECK_FIELDS = {"id", "scopes", "kind", "message", "source_anchors"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _guidance_text(guidance: dict[str, Any]) -> str:
    lines = guidance.get("source_lines")
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        raise ValueError("写作文案表达合同缺少完整口播原文规范")
    return "\n".join(lines).rstrip() + "\n"


def guidance_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(_guidance_text(value["verbatim_guidance"]).encode("utf-8")).hexdigest()


def _guidance_entries(value: dict[str, Any]) -> dict[str, dict[str, str]]:
    guidance = value["verbatim_guidance"]
    text = _guidance_text(guidance)
    entries = guidance.get("anchors")
    if not isinstance(entries, list) or not entries:
        raise ValueError("写作文案表达合同缺少口播原文锚点")
    result: dict[str, dict[str, str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("写作文案表达合同口播原文锚点无效")
        anchor, heading = str(entry.get("id") or "").strip(), str(entry.get("heading") or "").strip()
        if not anchor or not heading or anchor in result or heading not in text:
            raise ValueError("写作文案表达合同口播原文锚点不可定位")
        start = text.index(heading)
        end = text.find("\n---", start)
        result[anchor] = {"id": anchor, "heading": heading, "text": text[start:(end if end >= 0 else len(text))].strip()}
    return result


def contract(path: Path = ACTIVE_CONTRACT_PATH) -> dict[str, Any]:
    """Load the structured source without consulting the human-readable view."""
    if path.resolve() != ACTIVE_CONTRACT_PATH.resolve():
        raise ValueError("运行时只允许读取 writing-expression-contract-v3 结构化权威源")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("写作文案表达合同结构化权威源不可读取") from exc
    rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
    checks = payload.get("mechanical_checks") if isinstance(payload.get("mechanical_checks"), list) else []
    ids = [str(rule.get("id") or "").strip() for rule in rules if isinstance(rule, dict)]
    try:
        anchors = _guidance_entries(payload)
        _guidance_text(payload["verbatim_guidance"])
    except (KeyError, ValueError) as exc:
        raise ValueError("写作文案表达合同口播原文规范无效") from exc
    if (
        payload.get("contract_id") != "writing-expression-contract-v3"
        or payload.get("version") != "v3"
        or len(rules) != len(ids) or not ids or len(ids) != len(set(ids))
        or any(
            not REQUIRED_RULE_FIELDS.issubset(rule) or not isinstance(rule.get("scopes"), list) or not rule["scopes"]
            or not isinstance(rule.get("source_anchors"), list) or not rule["source_anchors"]
            or any(anchor not in anchors for anchor in rule["source_anchors"])
            for rule in rules
        )
        or any(
            not isinstance(check, dict) or not REQUIRED_CHECK_FIELDS.issubset(check)
            or not isinstance(check.get("scopes"), list) or not isinstance(check.get("source_anchors"), list)
            or any(anchor not in anchors for anchor in check["source_anchors"])
            for check in checks
        )
    ):
        raise ValueError("写作文案表达合同规则、范围、原文锚点或机器门禁无效")
    return {
        "contract_id": payload["contract_id"], "version": payload["version"], "sha256": digest(path),
        "path": str(path.resolve()), "title": payload.get("title", ""), "intro": payload.get("intro", ""),
        "rules": rules, "mechanical_checks": checks, "verbatim_guidance": payload["verbatim_guidance"],
        "verbatim_guidance_sha256": guidance_sha256(payload), "guidance_entries": anchors,
    }


def active_contract() -> dict[str, Any]:
    value = contract()
    verify_contract_view()
    return value


def binding() -> dict[str, str]:
    value = active_contract()
    return {key: value[key] for key in ("contract_id", "version", "sha256")}


def resolve_contract(value: dict[str, Any]) -> dict[str, Any]:
    current = active_contract()
    if not isinstance(value, dict) or any(value.get(key) != current[key] for key in ("contract_id", "version", "sha256")):
        raise ValueError("新链路只接受当前 writing-expression-contract-v3 及其哈希")
    return current


def rules_for(value: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    return [rule for rule in resolve_contract(value)["rules"] if scope in rule["scopes"]]


def rule_ids(value: dict[str, Any], scope: str) -> list[str]:
    return [str(rule["id"]) for rule in rules_for(value, scope)]


def guidance_snapshot(value: dict[str, Any], scope: str) -> dict[str, Any]:
    current = resolve_contract(value)
    scoped_rules = []
    for rule in rules_for(value, scope):
        scoped_rules.append({**rule, "original_guidance": [current["guidance_entries"][anchor] for anchor in rule["source_anchors"]]})
    return {
        "contract_id": current["contract_id"], "version": current["version"], "contract_sha256": current["sha256"], "scope": scope,
        "verbatim_guidance_sha256": current["verbatim_guidance_sha256"], "verbatim_guidance": current["verbatim_guidance"],
        "rules": scoped_rules, "mechanical_checks": [check for check in current["mechanical_checks"] if scope in check["scopes"]],
    }


def validate_guidance_snapshot(snapshot: Any, value: dict[str, Any], scope: str) -> None:
    if snapshot != guidance_snapshot(value, scope):
        raise ValueError("写作文案表达合同原文规范、规则快照或哈希漂移")


def mechanical_checks_for(value: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    return guidance_snapshot(value, scope)["mechanical_checks"]


def render_contract_markdown() -> str:
    value = contract()
    sections: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for rule in value["rules"]:
        sections.setdefault(str(rule["section"]), []).append(rule)
    lines = [
        f"# {value['title']}", "", "<!-- GENERATED FROM writing-expression-contract-v3.json; DO NOT EDIT -->", "",
        f"合同 ID：`{value['contract_id']}`", f"版本：`{value['version']}`", f"结构化源 SHA-256：`{value['sha256']}`",
        f"口播原文 SHA-256：`{value['verbatim_guidance_sha256']}`", "", str(value["intro"]), "",
        "## 完整口播规范（运行时与阅读版共用）", "", _guidance_text(value["verbatim_guidance"]).rstrip(), "", "## 机器规则索引", "",
    ]
    for number, (section, rules) in enumerate(sections.items(), 1):
        lines.extend([f"### {number}. {section}", ""])
        for rule in rules:
            scopes = "、".join("结构" if scope == "structure" else "正文" for scope in rule["scopes"])
            lines.extend([
                f"#### {rule['id']}｜{rule['title']}", "", f"- 适用：{scopes}", f"- 强制级别：{rule['severity']}",
                f"- 原文锚点：{'、'.join(rule['source_anchors'])}", f"- 生成要求：{rule['directive']}", f"- 审核证据：{rule['evidence']}", "",
            ])
    return "\n".join(lines).rstrip() + "\n"


def verify_contract_view() -> None:
    if not ACTIVE_CONTRACT_VIEW_PATH.is_file() or ACTIVE_CONTRACT_VIEW_PATH.read_text(encoding="utf-8") != render_contract_markdown():
        raise ValueError("写作文案表达合同阅读版未由当前结构化权威源生成或已被手工改写")
