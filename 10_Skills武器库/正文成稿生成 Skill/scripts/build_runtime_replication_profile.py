#!/usr/bin/env python3
"""Bind content-free sentence shapes to one audited benchmark at runtime."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path


def project_root() -> Path:
    candidates = (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "00_系统说明" / "benchmark-case-registry.json").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 00_系统说明/benchmark-case-registry.json")


ROOT = project_root()
sys.path.insert(0, str(ROOT))
from workflow.universal_copy_contract import digest, parse_breakdown

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-case-id", required=True); parser.add_argument("--benchmark", type=Path, required=True)
    parser.add_argument("--shape-source", type=Path, required=True, help="只含去内容化句式骨架的临时输入")
    parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    source = json.loads(args.shape_source.read_text(encoding="utf-8")); shapes = {str(row.get("unit_no") or ""): row for row in source.get("units", []) if isinstance(row, dict)}
    parsed = parse_breakdown(args.benchmark); units = []
    for unit in parsed["units"]:
        no = str(unit["unit_no"]); shape = shapes.get(no)
        if not shape or any(not shape.get(key) for key in ("sentence_shape", "clause_roles", "sentence_form")):
            raise SystemExit(f"复刻画像缺少 {no} 的去内容化句式骨架")
        units.append({"unit_no": no, "sentence_shape": shape["sentence_shape"], "clause_roles": shape["clause_roles"], "sentence_form": shape["sentence_form"], "source_text_sha256": unit["source_text_sha256"], "required_punctuation": unit.get("source_punctuation") or "", "word_range": unit["word_range"]})
    payload = {"schema":"benchmark-replication-profile-v2", "benchmark_case_id":args.benchmark_case_id, "benchmark_sha256":digest(args.benchmark), "purpose":"运行态去内容化逐句复刻画像；不保存对标原句。", "units":units}
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status":"built","units":len(units),"output":str(args.output)}, ensure_ascii=False)); return 0
if __name__ == "__main__": raise SystemExit(main())
