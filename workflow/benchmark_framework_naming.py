"""The owner-confirmed naming dictionary for benchmark big frameworks."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = (
    PROJECT_ROOT
    / "10_Skills武器库"
    / "对标视频-结构拆解Skill（会员专享）"
    / "references"
    / "big-framework-naming"
    / "registry.json"
)
SCHEMA = "benchmark-big-framework-naming-v1"
ORDINAL = "一二三四五六七八九十0123456789"


def registry_path(path: Path | None = None) -> Path:
    configured = os.environ.get("AI_VIRAL_BIG_FRAMEWORK_NAMING_REGISTRY")
    return (path or (Path(configured) if configured else DEFAULT_REGISTRY)).resolve()


def digest(path: Path | None = None) -> str:
    return hashlib.sha256(registry_path(path).read_bytes()).hexdigest()


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = registry_path(path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"大框架命名词典不可读取：{exc}") from exc
    validate_registry(data)
    return data


def _entry_source_label(source: dict[str, Any]) -> str:
    return f"{source['caseId']}：{source['label']}"


def validate_registry(data: dict[str, Any]) -> None:
    if data.get("schema") != SCHEMA or not isinstance(data.get("version"), int):
        raise ValueError("大框架命名词典 schema 或版本不正确")
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("大框架命名词典必须至少包含一个词条")
    ids: set[str] = set()
    labels: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("大框架命名词典词条必须是对象")
        entry_id, name, role = entry.get("id"), entry.get("name"), entry.get("role")
        if not isinstance(entry_id, str) or not entry_id or entry_id in ids:
            raise ValueError("大框架命名词典词条 ID 必须唯一")
        if not isinstance(name, str) or not name or name in labels:
            raise ValueError("大框架命名词典名称必须唯一")
        if role not in {"processing-module", "structure-support"}:
            raise ValueError("大框架命名词典角色必须是处理库正式类型或结构支撑类型")
        module = entry.get("processingModule")
        if role == "processing-module" and module not in {"观点", "痛点", "误区", "解决方案", "案例", "推荐理由"}:
            raise ValueError(f"{name} 必须映射到一个处理库正式模块")
        if role == "structure-support" and module is not None:
            raise ValueError(f"{name} 是结构支撑类型，不得映射处理库模块")
        for field in ("definition",):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{name} 缺少{field}")
        for field in ("matchFeatures", "contentTypeHints", "confirmedSources", "displayForms", "exactAliases"):
            if not isinstance(entry.get(field), list):
                raise ValueError(f"{name} 的 {field} 必须是列表")
        if not entry["confirmedSources"]:
            raise ValueError(f"{name} 必须有已确认案例来源")
        for source in entry["confirmedSources"]:
            if not isinstance(source, dict) or not all(isinstance(source.get(key), str) and source[key].strip() for key in ("caseId", "label")):
                raise ValueError(f"{name} 的已确认案例来源不完整")
        ids.add(entry_id); labels.add(name)


def _matches_form(name: str, canonical: str, form: str) -> bool:
    if form == "exact":
        return name == canonical
    if form == "suffix-ordinal":
        return bool(re.fullmatch(re.escape(canonical) + rf"[{ORDINAL}]+", name))
    if form == "point-prefix":
        return bool(re.fullmatch(rf"第[{ORDINAL}]+点[：:]" + re.escape(canonical) + rf"(?:[{ORDINAL}]+)?", name))
    raise ValueError(f"词典包含未知展示形式：{form}")


def framework_metadata(label: str, *, path: Path | None = None) -> dict[str, Any]:
    value = str(label or "").strip()
    for entry in load_registry(path)["entries"]:
        names = [entry["name"], *entry["exactAliases"]]
        if value in names or any(_matches_form(value, entry["name"], form) for form in entry["displayForms"]):
            return {
                "label": value,
                "dictionaryEntryId": entry["id"],
                "canonicalName": entry["name"],
                "role": entry["role"],
                "processingModule": entry["processingModule"],
                "definition": entry["definition"],
            }
    raise ValueError(f"大框架名称未在已确认命名词典中登记：{value}")


def unknown_labels(labels: list[str], *, path: Path | None = None) -> list[str]:
    result: list[str] = []
    for label in labels:
        try:
            framework_metadata(label, path=path)
        except ValueError:
            if label not in result:
                result.append(label)
    return result


def render_markdown(data: dict[str, Any]) -> str:
    validate_registry(data)
    role_label = {"processing-module": "处理库正式类型", "structure-support": "结构支撑类型"}
    lines = [
        "# 大框架命名词典",
        "",
        "本文件由同目录 `registry.json` 生成；JSON 是机器唯一真源。新增、修改、删除词条必须先取得工作区所有者明确确认。",
        "",
        f"- 合同：`{data['schema']}`",
        f"- 词典版本：`{data['version']}`",
        "- 适用文案类型仅用于匹配提示，不构成硬性拒绝。",
    ]
    for entry in data["entries"]:
        forms = "、".join(entry["displayForms"]) or "仅精确名称"
        aliases = "、".join(entry["exactAliases"]) or "无"
        module = entry["processingModule"] or "不参与处理库检索"
        sources = "；".join(_entry_source_label(item) for item in entry["confirmedSources"])
        lines.extend([
            "",
            f"## {entry['name']}",
            "",
            f"- 角色：{role_label[entry['role']]}",
            f"- 处理库关系：{module}",
            f"- 定义：{entry['definition']}",
            f"- 可匹配原文特征：{'；'.join(entry['matchFeatures'])}",
            f"- 适用文案类型提示：{'、'.join(entry['contentTypeHints'])}",
            f"- 允许展示形式：{forms}",
            f"- 精确兼容别名：{aliases}",
            f"- 已确认案例来源：{sources}",
        ])
    return "\n".join(lines).rstrip() + "\n"


def markdown_path(path: Path | None = None) -> Path:
    return registry_path(path).with_name("大框架命名词典.md")


def validate_markdown_sync(path: Path | None = None) -> None:
    expected = render_markdown(load_registry(path))
    target = markdown_path(path)
    if not target.is_file() or target.read_text(encoding="utf-8") != expected:
        raise ValueError("大框架命名词典 Markdown 与 registry.json 不一致；请通过受控维护命令重新生成")


def write_registry(data: dict[str, Any], *, path: Path | None = None) -> None:
    validate_registry(data)
    target = registry_path(path); target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    markdown_path(target).write_text(render_markdown(data), encoding="utf-8")
