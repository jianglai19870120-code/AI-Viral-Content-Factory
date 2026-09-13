#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Finalize the declared body-page no-draw zone before visual output audit.

This is deliberately not a text compositor.  It is a constrained export
normalizer: only the already-declared bottom-left no-draw rectangle is written
with the page's declared RGB background, and it records the renderer input and
final-output hashes plus a digest proving all pixels outside that rectangle are
unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from PIL import Image


CONTRACT_VERSION = "4.1.0"
PPT_PAGE_HEIGHT_CM = 19.05
RESERVED_ZONE_SIZE_CM = [3, 3]
MANIFEST_NAME = "reserved-zone-normalization.json"
SEMANTIC_REVIEW_NAME = "visual-output-semantic-review.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_hex_color(value: object) -> tuple[int, int, int]:
    text = str(value or "").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", text):
        raise ValueError(f"background_color 必须是 #RRGGBB，当前为 {value!r}")
    return tuple(int(text[index:index + 2], 16) for index in (1, 3, 5))  # type: ignore[return-value]


def reserved_zone_side_px(image_height: int) -> int:
    return max(1, round(image_height * RESERVED_ZONE_SIZE_CM[1] / PPT_PAGE_HEIGHT_CM))


def outside_zone_rgb_sha256(image: Image.Image, side: int) -> str:
    """Digest RGB pixels outside the no-draw zone, in deterministic row order."""
    rgb = image if image.mode == "RGB" else image.convert("RGB")
    width, height = rgb.size
    digest = hashlib.sha256()
    for y in range(height):
        left = 0 if y < height - side else side
        if left < width:
            digest.update(rgb.crop((left, y, width, y + 1)).tobytes())
    return digest.hexdigest()


def normalize_page(path: Path, background_color: str) -> dict[str, Any]:
    expected_rgb = parse_hex_color(background_color)
    before_sha256 = sha256_file(path)
    with Image.open(path) as source:
        if source.format != "PNG" or source.mode != "RGB":
            raise ValueError(f"{path.name} 必须是 RGB PNG；当前 format={source.format} mode={source.mode}")
        image = source.copy()
    width, height = image.size
    side = min(reserved_zone_side_px(height), width, height)
    box = (0, height - side, side, height)
    before_outside_sha256 = outside_zone_rgb_sha256(image, side)
    crop = image.crop(box)
    changed_pixels = sum(1 for pixel in crop.getdata() if pixel != expected_rgb)
    if changed_pixels:
        image.paste(Image.new("RGB", (side, side), expected_rgb), box)
    after_outside_sha256 = outside_zone_rgb_sha256(image, side)
    if before_outside_sha256 != after_outside_sha256:
        raise RuntimeError(f"{path.name} 归一化越过禁绘区，拒绝写入")
    temp_path = path.with_name(f"{path.stem}.reserved-zone.tmp.png")
    try:
        image.save(temp_path, format="PNG")
        with Image.open(temp_path) as check:
            if check.mode != "RGB" or check.size != (width, height):
                raise RuntimeError(f"{path.name} 临时导出规格漂移")
            check_crop = check.crop(box)
            if any(pixel != expected_rgb for pixel in check_crop.getdata()):
                raise RuntimeError(f"{path.name} 临时导出未达到精确背景 RGB")
            if outside_zone_rgb_sha256(check, side) != before_outside_sha256:
                raise RuntimeError(f"{path.name} 临时导出改变了禁绘区外像素")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {
        "asset_id": path.stem,
        "path": str(path),
        "background_color": background_color,
        "expected_rgb": list(expected_rgb),
        "zone": {"x": 0, "y": height - side, "width": side, "height": side},
        "renderer_input_sha256": before_sha256,
        "final_png_sha256": sha256_file(path),
        "outside_zone_rgb_sha256_before": before_outside_sha256,
        "outside_zone_rgb_sha256_after": after_outside_sha256,
        "outside_zone_pixels_unchanged": True,
        "changed_pixels_inside_declared_no_draw_zone": changed_pixels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="把 v4.1 正文页左下禁绘区归一化为精确背景 RGB")
    parser.add_argument("--workdir", required=True, help="已通过预审、尚未创建成图语义审核表的 v4.1 工作包")
    parser.add_argument(
        "--validation-allow-preflight-not-approved",
        action="store_true",
        help="仅允许独立 Skill 验证包在预审仍为 needs-review/rejected 时测试归一化；生产任务禁止使用",
    )
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    handoff_path = workdir / "codex-handoff.json"
    review_dir = workdir / "final-review"
    evidence_dir = review_dir / "evidence"
    review_path = evidence_dir / SEMANTIC_REVIEW_NAME
    if review_path.exists():
        raise RuntimeError("已创建 visual-output-semantic-review.json；禁止在哈希审核表创建后修改最终 PNG")
    handoff = load_json(handoff_path)
    if handoff.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("只接受 v4.1.0 工作包")
    preflight_path = workdir / "visual-preflight-audit.json"
    if not preflight_path.is_file():
        raise FileNotFoundError("缺少视觉预审回执，禁止处理最终 PNG")
    preflight_status = str(load_json(preflight_path).get("status") or "")
    validation_override = bool(args.validation_allow_preflight_not_approved)
    if preflight_status != "approved" and not validation_override:
        raise RuntimeError(f"视觉预审状态为 {preflight_status!r}，生产任务禁止归一化最终 PNG")
    export_contract = handoff.get("reserved_zone_export_normalization") or {}
    if export_contract.get("enabled") is not True or export_contract.get("stage") != "before-output-audit":
        raise ValueError("工作包未声明受控禁绘区导出归一化合同")

    pages = list(handoff.get("pages") or [])
    if not pages:
        raise ValueError("codex-handoff.json 缺少正文页")
    assets: list[dict[str, Any]] = []
    for page in pages:
        index = int(page.get("page_index") or 0)
        if index <= 0 or page.get("reserved_zone_enabled") is not True:
            raise ValueError(f"page-{index:02d} 未声明正文禁绘区，拒绝归一化")
        path = review_dir / f"page-{index:02d}.png"
        if not path.is_file():
            raise FileNotFoundError(f"缺少最终 PNG：{path}")
        assets.append(normalize_page(path, str(page.get("background_color") or "")))

    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "reserved-zone-background-rgb-normalization-v1",
        "contract_version": CONTRACT_VERSION,
        "status": "completed",
        "stage": "before-output-audit",
        "operation": "overwrite only the declared bottom-left no-draw pixels with declared background RGB",
        "text_overlay": "forbidden",
        "drawing_or_semantic_edit": "forbidden",
        "hash_audit": "renderer_input_sha256 and final_png_sha256 are both recorded; output audit must bind final_png_sha256",
        "preflight_status": preflight_status,
        "validation_preflight_override": validation_override,
        "assets": assets,
    }
    manifest_path = evidence_dir / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "assets": assets}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
