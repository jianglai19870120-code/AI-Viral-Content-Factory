#!/usr/bin/env python3
"""Render a reviewed final-copy candidate as spoken text plus a trace table."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


def project_root() -> Path:
    candidates = (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "00_系统说明" / "benchmark-case-registry.json").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 00_系统说明/benchmark-case-registry.json")


ROOT = project_root()
import sys
sys.path.insert(0, str(ROOT))
from workflow.common import append_brand_footer, append_brand_footer_text

CST = timezone(timedelta(hours=8))
# 正文类型只用于人工分类，不能决定发布路由；统一发布到现役正文成稿库。
FORMAL = ROOT / "02_资产中心" / "03_输出库" / "02_正文成稿"


def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def safe(value: str) -> str: return re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value, flags=re.UNICODE).strip("_")[:72] or "未命名选题"
def cell(value: str) -> str: return value.replace("|", "\\|").replace("\n", "<br>")

def spoken_lines(value: str) -> list[str]:
    """Keep each sentence readable by breaking long clauses at natural punctuation."""
    text = value.strip()
    if len(text) <= 28: return [text]
    return [part.strip() for part in re.sub(r"(?<=[，。！？；])", "\n", text).splitlines() if part.strip()]


def grouped(plan: dict, candidate: dict) -> list[tuple[dict, list[dict]]]:
    mappings = candidate.get("unit_mappings") if isinstance(candidate.get("unit_mappings"), list) else []
    by_small: dict[str, list[dict]] = {}
    for row in mappings:
        if isinstance(row, dict): by_small.setdefault(str(row.get("small_structure_id") or ""), []).append(row)
    return [(row, by_small.get(str(row.get("小结构编号") or ""), [])) for row in plan.get("functional_blueprint", []) if isinstance(row, dict)]


def render(plan: dict, candidate: dict) -> str:
    title = str(plan.get("topic") or "").strip()
    if not title: raise ValueError("逐句计划缺少选题标题")
    lines = [f"# {title}", ""]
    blocks = grouped(plan, candidate)
    for index, (_, units) in enumerate(blocks):
        for unit in units: lines.extend(spoken_lines(str(unit.get("text") or "")))
        if index < len(blocks) - 1: lines.extend(["", ""])
    lines.extend(["", "", "## 结构与口播对照", "", "| 核心大框架 | 对标小框架 | 对应口播内容 |", "| --- | --- | --- |"])
    for blueprint, units in blocks:
        spoken = "<br>".join(cell("\n".join(spoken_lines(str(unit.get("text") or "")))) for unit in units)
        lines.append(f"| {cell(str(blueprint.get('display_framework_label') or blueprint.get('大框架功能') or ''))} | {cell(str(blueprint.get('display_small_framework_name') or blueprint.get('通用复刻功能') or ''))} | {spoken} |")
    return "\n".join(lines).rstrip() + "\n"


def valid_receipt(receipt: Path, plan: Path, candidate: Path, preview: Path) -> bool:
    payload = json.loads(receipt.read_text(encoding="utf-8")); subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
    candidate_payload = json.loads(candidate.read_text(encoding="utf-8"))
    return (
        payload.get("schema") == "audit-receipt-v3"
        and payload.get("artifactType") == "final-copy-v1"
        and payload.get("status") == "approved"
        and subject.get("planSha256") == digest(plan)
        and subject.get("candidateSha256") == digest(candidate)
        and subject.get("previewSha256") == digest(preview)
        and candidate_payload.get("sentence_plan_sha256") == digest(plan)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染正文候选的口播稿与结构对照表")
    parser.add_argument("--plan", type=Path, required=True); parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path); parser.add_argument("--release", action="store_true"); parser.add_argument("--audit-receipt", type=Path); parser.add_argument("--preview", type=Path)
    parser.add_argument("--publication-receipt", type=Path, help="正式发布后的完整性记录；仅 --release 时必填")
    args = parser.parse_args(); plan = json.loads(args.plan.read_text(encoding="utf-8")); candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    if args.release:
        if not args.audit_receipt or not args.preview or not args.preview.is_file() or not args.publication_receipt or not valid_receipt(args.audit_receipt, args.plan, args.candidate, args.preview): raise SystemExit("正式发布需要当前计划、候选和预览对应的 approved 小审回执，以及发布记录路径")
        stamp = datetime.now(CST).strftime("%Y%m%d-%H%M%S"); output = FORMAL / f"{safe(str(plan['topic']))}_{plan['benchmark_case_id']}_{stamp}.md"; ordinal = 2
        while output.exists(): output = FORMAL / f"{safe(str(plan['topic']))}_{plan['benchmark_case_id']}_{stamp}_{ordinal:02d}.md"; ordinal += 1
    else:
        if not args.output: raise SystemExit("运行区渲染必须提供 --output")
        output = args.output
    rendered = render(plan, candidate)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.release:
        # 先在同目录暂存并追加品牌尾注；任何一致性失败都不能留下一个
        # 看似已发布、实则没有通过发布包完整性检查的正式文件。
        staging = output.with_suffix(output.suffix + ".pending")
        ordinal = 2
        while staging.exists():
            staging = output.with_suffix(output.suffix + f".pending-{ordinal:02d}"); ordinal += 1
        staging.write_text(rendered, encoding="utf-8", newline="\n")
        append_brand_footer(staging)
        formal = staging.read_text(encoding="utf-8")
        if formal != append_brand_footer_text(rendered):
            staging.unlink(missing_ok=True)
            raise SystemExit("正式正文与已审核预览渲染结果不一致；已停止发布记录写入")
        staging.replace(output)
        receipt = {
            "schema": "final-copy-publication-v1",
            "status": "published",
            "formalPath": str(output.resolve()),
            "formalSha256": digest(output),
            "renderedBodySha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "previewSha256": digest(args.preview),
            "candidateSha256": digest(args.candidate),
            "auditReceipt": str(args.audit_receipt.resolve()),
        }
        args.publication_receipt.parent.mkdir(parents=True, exist_ok=True)
        args.publication_receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    else:
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__": raise SystemExit(main())
