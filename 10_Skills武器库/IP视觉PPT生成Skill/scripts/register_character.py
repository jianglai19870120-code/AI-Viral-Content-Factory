#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import pathlib
import shutil

from PIL import Image, ImageChops

from common import CHARACTERS_DIR, ensure_dir, load_config, save_config, slugify, write_text


GRID_REFERENCE_FILENAME = "IP九宫格参考图.png"
FACE_ANCHOR_FILENAME = "ip-face-anchor-top-left.png"
REFERENCE_FILENAMES = [
    FACE_ANCHOR_FILENAME,
    "ip-ref-02-speaking-mic.png",
    "ip-ref-03-thinking.png",
    "ip-ref-04-questioning.png",
    "ip-ref-05-stop-pose.png",
    "ip-ref-06-pointing.png",
    "ip-ref-07-shocked.png",
    "ip-ref-08-confused.png",
    "ip-ref-09-idea.png",
]
REFERENCE_LIBRARY_TEMPLATE = [
    {
        "name": "ip-face-anchor-top-left",
        "path": f"refs/{FACE_ANCHOR_FILENAME}",
        "reference_kind": "face-anchor",
        "variant": "identity-anchor",
        "expression_intensity": "stable",
        "is_base_pose": True,
        "expression": "frontal-neutral",
        "framing": "upper-body",
        "tags": ["base", "front", "host", "cartoon-style", "hair-anchor", "skin-anchor", "face-anchor"],
        "use_cases": ["角色定标", "主脸模板", "发型锚定", "肤色锚定", "眼镜锚定", "脸型锚定"],
    },
    {
        "name": "ip-ref-02-speaking-mic",
        "path": "refs/ip-ref-02-speaking-mic.png",
        "reference_kind": "action-reference",
        "variant": "speaking-mic",
        "expression_intensity": "medium",
        "is_base_pose": False,
        "expression": "speaking",
        "framing": "half-body",
        "tags": ["action-reference", "speaking", "explaining", "host"],
        "use_cases": ["讲解", "推进", "说明"],
    },
    {
        "name": "ip-ref-03-thinking",
        "path": "refs/ip-ref-03-thinking.png",
        "reference_kind": "action-reference",
        "variant": "thinking",
        "expression_intensity": "medium",
        "is_base_pose": False,
        "expression": "thinking",
        "framing": "half-body",
        "tags": ["action-reference", "thinking", "analysis"],
        "use_cases": ["思考", "判断", "分析"],
    },
    {
        "name": "ip-ref-04-questioning",
        "path": "refs/ip-ref-04-questioning.png",
        "reference_kind": "action-reference",
        "variant": "questioning",
        "expression_intensity": "medium",
        "is_base_pose": False,
        "expression": "questioning",
        "framing": "half-body",
        "tags": ["action-reference", "questioning", "explaining"],
        "use_cases": ["讲解", "说明", "困惑"],
    },
    {
        "name": "ip-ref-05-stop-pose",
        "path": "refs/ip-ref-05-stop-pose.png",
        "reference_kind": "action-reference",
        "variant": "stop-pose",
        "expression_intensity": "high",
        "is_base_pose": False,
        "expression": "blocking",
        "framing": "full-body",
        "tags": ["action-reference", "blocking", "warning"],
        "use_cases": ["强调", "阻挡", "误区"],
    },
    {
        "name": "ip-ref-06-pointing",
        "path": "refs/ip-ref-06-pointing.png",
        "reference_kind": "action-reference",
        "variant": "pointing",
        "expression_intensity": "high",
        "is_base_pose": False,
        "expression": "pointing",
        "framing": "half-body",
        "tags": ["action-reference", "pointing", "cta"],
        "use_cases": ["指向", "号召", "结论"],
    },
    {
        "name": "ip-ref-07-shocked",
        "path": "refs/ip-ref-07-shocked.png",
        "reference_kind": "action-reference",
        "variant": "shocked",
        "expression_intensity": "high",
        "is_base_pose": False,
        "expression": "shocked",
        "framing": "half-body",
        "tags": ["action-reference", "shocked", "warning"],
        "use_cases": ["震惊", "踩坑", "强提醒"],
    },
    {
        "name": "ip-ref-08-confused",
        "path": "refs/ip-ref-08-confused.png",
        "reference_kind": "action-reference",
        "variant": "confused",
        "expression_intensity": "medium",
        "is_base_pose": False,
        "expression": "confused",
        "framing": "half-body",
        "tags": ["action-reference", "confused", "stuck"],
        "use_cases": ["困惑", "卡点", "不理解"],
    },
    {
        "name": "ip-ref-09-idea",
        "path": "refs/ip-ref-09-idea.png",
        "reference_kind": "action-reference",
        "variant": "idea",
        "expression_intensity": "medium-high",
        "is_base_pose": False,
        "expression": "idea",
        "framing": "half-body",
        "tags": ["action-reference", "idea", "conclusion"],
        "use_cases": ["结论", "总结", "顿悟"],
    },
]
CHARACTER_TEMPLATE = """---
slug: {slug}
display_name: {display_name}
character_type: 真人漫画化IP
reference_library: refs/reference-library.json
default_style: hand-drawn-visual-note
default_expression_level: high
brand_mark_mode: mic-only
default_reuse: true
---

# 角色包：{display_name}

## 固定识别点
1. 九宫格母版素材固定为 `refs/{grid_reference}`
2. 正式主脸锚点固定为 `refs/{face_anchor}`
3. 正式出图必须使用“主脸锚点 + 单页动作参考”的身份链路，不再走九宫格整图直参
4. 发型、脸型、眼镜、肤色和衣着身份必须服从主脸锚点，不允许动作参考图重新定义人物
5. 角色在不同页面可以夸张演出，但不能换脸、换发型、换眼镜、换衣着身份
6. 正式交付图默认走手绘视觉笔记风格，不走泛化写实插画

## 可变化元素
- 话筒
- 手势
- 姿态
- 表情
- 景别
- 人物大小
- 嵌入主结构的方式

## 规则说明

- 每页都要出现角色
- 表情和动作允许高张力夸张
- 但不能夸张到认不出同一个人
- 话筒只在讲述类页面按需出现
- 如果没有九宫格母版、主脸锚点和动作参考单图，这个角色包不能量产正式内容
- 跨电脑迁移时，必须同时带走整个 `characters/{slug}/` 目录，而不是只带单张九宫格图

## 英文 prompt 段
```text
Recurring IP character: a clean hand-drawn Chinese host character based on the approved top-left face anchor plus one selected action reference image. Keep the same face identity, hairstyle family, glasses structure, skin-tone direction, and outfit identity across pages. The face anchor is the only identity baseline. Action references may guide pose, gesture, and expression tendency only, and must never redefine the face.
```
"""


def trim_white_border(image: Image.Image, padding: int = 12) -> Image.Image:
    rgb = image.convert("RGB")
    white_bg = Image.new("RGB", rgb.size, (255, 255, 255))
    diff = ImageChops.difference(rgb, white_bg)
    bbox = diff.getbbox()
    if bbox is None:
        return image
    left = max(0, bbox[0] - padding)
    top = max(0, bbox[1] - padding)
    right = min(image.width, bbox[2] + padding)
    bottom = min(image.height, bbox[3] + padding)
    return image.crop((left, top, right, bottom))


def split_reference_grid(source: pathlib.Path) -> list[Image.Image]:
    with Image.open(source) as img:
        width, height = img.size
        cell_width = width // 3
        cell_height = height // 3
        parts: list[Image.Image] = []
        for row in range(3):
            for col in range(3):
                left = col * cell_width
                top = row * cell_height
                right = width if col == 2 else (col + 1) * cell_width
                bottom = height if row == 2 else (row + 1) * cell_height
                part = img.crop((left, top, right, bottom))
                parts.append(trim_white_border(part))
        return parts


def write_reference_assets(source: pathlib.Path, refs_dir: pathlib.Path) -> pathlib.Path:
    mother_board_target = refs_dir / GRID_REFERENCE_FILENAME
    shutil.copy2(source, mother_board_target)
    split_parts = split_reference_grid(source)
    if len(split_parts) != len(REFERENCE_FILENAMES):
        raise ValueError("九宫格拆分结果数量异常，预期 9 张单图。")
    for filename, part in zip(REFERENCE_FILENAMES, split_parts):
        part.save(refs_dir / filename)
    return mother_board_target


def main() -> None:
    ap = argparse.ArgumentParser(description="注册一个可复用的人物型 IP 角色")
    ap.add_argument("--slug", required=True, help="角色 slug，例如 zhifuxingqiu-host")
    ap.add_argument("--display-name", required=True, help="角色显示名")
    ap.add_argument("--source-image", required=True, help="3x3 九宫格人物参考图路径")
    ap.add_argument("--set-default", action="store_true", help="注册后写入默认角色")
    ap.add_argument("--force", action="store_true", help="覆盖已有角色目录")
    args = ap.parse_args()

    slug = slugify(args.slug)
    display_name = args.display_name.strip()
    source = pathlib.Path(args.source_image).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"九宫格人物参考图不存在: {source}")

    char_dir = CHARACTERS_DIR / slug
    refs_dir = ensure_dir(char_dir / "refs")
    if char_dir.exists() and (char_dir / "character.md").exists() and not args.force:
        raise FileExistsError(f"角色已存在: {char_dir}，如需覆盖请加 --force")

    mother_board_target = write_reference_assets(source, refs_dir)
    (refs_dir / "reference-library.json").write_text(
        json.dumps(REFERENCE_LIBRARY_TEMPLATE, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_text(
        char_dir / "character.md",
        CHARACTER_TEMPLATE.format(
            slug=slug,
            display_name=display_name,
            grid_reference=GRID_REFERENCE_FILENAME,
            face_anchor=FACE_ANCHOR_FILENAME,
        ),
    )

    if args.set_default:
        cfg = load_config()
        cfg["default_character"] = slug
        save_config(cfg)

    print(f"已注册角色: {display_name}")
    print(f"角色目录: {char_dir}")
    print(f"九宫格母版素材: {mother_board_target}")
    print(f"主脸锚点图: {refs_dir / FACE_ANCHOR_FILENAME}")
    print(f"动作参考库: {refs_dir / 'reference-library.json'}")


if __name__ == "__main__":
    main()
