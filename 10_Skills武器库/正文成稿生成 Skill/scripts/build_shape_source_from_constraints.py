#!/usr/bin/env python3
"""Turn an audited, content-free unit-constraint map into a profile shape source."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="从去内容化逐句约束生成复刻画像形状源")
    parser.add_argument("--constraints", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = json.loads(args.constraints.read_text(encoding="utf-8"))
    if not isinstance(source, dict):
        raise SystemExit("逐句约束必须是对象")
    units = []
    for number in range(1, 29):
        unit_no = f"{number:02d}"
        item = source.get(unit_no)
        if not isinstance(item, dict):
            raise SystemExit(f"逐句约束缺少 {unit_no}")
        if "group_relation" in item:
            clauses = item.get("clauses") if isinstance(item.get("clauses"), dict) else {}
            if not clauses:
                raise SystemExit(f"句群 {unit_no} 缺少去内容化分句约束")
            shape = str(item.get("group_relation") or "").strip()
            roles = [str(item.get("group_function") or "").strip(), *[
                str(value.get("mechanism") or "").strip()
                for value in clauses.values() if isinstance(value, dict)
            ]]
            sentence_form = "句群"
        else:
            shape = str(item.get("template") or "").strip()
            roles = [str(item.get("mechanism") or "").strip()]
            sentence_form = str(item.get("tone") or "模板句").strip()
        if not shape or not all(roles) or not sentence_form:
            raise SystemExit(f"逐句约束 {unit_no} 缺少句式骨架、结构角色或句型")
        units.append({"unit_no": unit_no, "sentence_shape": shape, "clause_roles": roles, "sentence_form": sentence_form})
    payload = {"schema": "benchmark-replication-shape-source-v1", "purpose": "仅含经审核的去内容化句式骨架；不含对标原句。", "units": units}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "built", "units": len(units), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
