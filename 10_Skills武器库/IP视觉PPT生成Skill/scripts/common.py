#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import pathlib
import re
from typing import Any


SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
PROJECT_ROOT = SKILL_ROOT.parent.parent
CONFIG_PATH = SKILL_ROOT / "config" / "skill-config.json"
CHARACTERS_DIR = SKILL_ROOT / "characters"


def ensure_dir(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: pathlib.Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def read_json(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    meta: dict[str, str] = {}
    end_index = None
    for idx in range(1, len(lines)):
        line = lines[idx]
        if line.strip() == "---":
            end_index = idx
            break
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    if end_index is None:
        return {}, text
    body = "\n".join(lines[end_index + 1 :]).lstrip()
    return meta, body


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    if not value:
        raise ValueError("slug 不能为空")
    return value


INVALID_WINDOWS_NAME_RE = re.compile(r'[<>:"/\\|?*]+')


def sanitize_windows_name(name: str) -> str:
    cleaned = INVALID_WINDOWS_NAME_RE.sub("", name).strip().rstrip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if cleaned:
        return cleaned
    return slugify(name)


def load_config() -> dict[str, Any]:
    return read_json(CONFIG_PATH)


def save_config(cfg: dict[str, Any]) -> None:
    write_json(CONFIG_PATH, cfg)


def find_character_dir(slug: str) -> pathlib.Path:
    path = CHARACTERS_DIR / slug
    if not path.exists():
        raise FileNotFoundError(f"找不到角色: {slug}")
    return path


def load_character(slug: str) -> dict[str, Any]:
    character_dir = find_character_dir(slug)
    md_path = character_dir / "character.md"
    meta, body = load_frontmatter(read_text(md_path))
    refs_index_path = character_dir / "refs" / "reference-library.json"
    mother_board_path = character_dir / "refs" / "IP九宫格参考图.png"
    face_anchor_path = character_dir / "refs" / "ip-face-anchor-top-left.png"
    reference_profiles: list[dict[str, Any]] = []
    if refs_index_path.exists():
        raw_profiles = json.loads(refs_index_path.read_text(encoding="utf-8"))
        for item in raw_profiles:
            ref_path = character_dir / item["path"]
            if ref_path.exists():
                reference_profiles.append({
                    **item,
                    "file_path": ref_path,
                })
    face_anchor_profiles = [
        item for item in reference_profiles
        if item.get("reference_kind") == "face-anchor"
    ]
    action_reference_profiles = [
        item for item in reference_profiles
        if item.get("reference_kind") == "action-reference"
    ]
    if not mother_board_path.exists():
        raise FileNotFoundError(
            f"角色包格式不完整，缺少九宫格母版素材: {mother_board_path}"
        )
    if not face_anchor_path.exists():
        raise FileNotFoundError(
            f"角色包格式已淘汰或不完整，缺少主脸锚点图: {face_anchor_path}"
        )
    if not face_anchor_profiles:
        raise FileNotFoundError(
            f"角色包格式已淘汰或不完整，reference-library.json 缺少 face-anchor 条目: {refs_index_path}"
        )
    if not action_reference_profiles:
        raise FileNotFoundError(
            f"角色包格式已淘汰或不完整，reference-library.json 缺少 action-reference 条目: {refs_index_path}"
        )
    prompt_block = ""
    match = re.search(r"```text\s*(.*?)```", body, re.S)
    if match:
        prompt_block = match.group(1).strip()
    return {
        "slug": meta.get("slug", slug),
        "display_name": meta.get("display_name", slug),
        "meta": meta,
        "body": body,
        "prompt_block": prompt_block,
        "character_dir": character_dir,
        "reference_profiles": reference_profiles,
        "reference_images": [item["file_path"] for item in reference_profiles],
    }


def resolve_default_character(explicit_slug: str | None = None) -> str:
    if explicit_slug:
        return explicit_slug
    cfg = load_config()
    slug = cfg.get("default_character")
    if not slug:
        raise ValueError("config/skill-config.json 未配置 default_character")
    return str(slug)
