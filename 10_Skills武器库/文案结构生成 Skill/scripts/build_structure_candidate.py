#!/usr/bin/env python3
"""Bind Xiaochai-authored V12 content skeletons to an immutable handoff."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            result[str(item.get("id") or item.get("angle_id") or "")] = item
    return result


def evidence_chain(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        roles = item.get("logic_roles")
        result.append({
            "logic_roles": [str(role).strip() for role in roles] if isinstance(roles, list) else [],
            "evidence_method": str(item.get("evidence_method") or "").strip(),
            "text": str(item.get("text") or "").strip(),
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handoff", type=Path, required=True)
    parser.add_argument("--authoring", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
    if handoff.get("schema") == "copy-structure-handoff-v16":
        from structure_v16 import build_candidate_v16
        build_candidate_v16(args.handoff, args.authoring, args.output)
        print(json.dumps({"status": "built", "schema": "copy-structure-v16"}, ensure_ascii=False))
        return 0
    raise SystemExit("新链路只接受 copy-structure-handoff-v16；历史 handoff 不可再生成候选")
    authoring = json.loads(args.authoring.read_text(encoding="utf-8"))
    if handoff.get("schema") != "copy-structure-handoff-v12":
        raise SystemExit("只接受 copy-structure-handoff-v12")

    regular = load_index(Path(handoff["processing_index"]))
    pain = load_index(Path(handoff["pain_angle_index"]))
    frameworks = handoff.get("core_frameworks", [])
    contracts = {str(item["core_framework_id"]): item for item in handoff.get("framework_content_contracts", [])}
    plans: dict[str, object] = {}

    for name in ("structure_one", "structure_two", "structure_three"):
        source = authoring.get(name) if isinstance(authoring.get(name), dict) else {}
        authored_rows = source.get("frameworks") if isinstance(source.get("frameworks"), dict) else {}
        rows: list[dict[str, object]] = []
        for base in frameworks:
            ident = str(base["core_framework_id"])
            written = authored_rows.get(ident) if isinstance(authored_rows.get(ident), dict) else {}
            contract = contracts.get(ident)
            if not contract:
                raise SystemExit(f"handoff 缺少 {ident} 的内容功能合同")
            row = dict(base)
            row.update({
                "content_contract_id": contract["content_contract_id"],
                "core_claim": str(written.get("core_claim") or "").strip(),
                "evidence_chain": evidence_chain(written.get("evidence_chain")),
                "proposition_ids": written.get("proposition_ids") if isinstance(written.get("proposition_ids"), list) else [],
                "framework_answer_obligation_id": f"OB-{ident}",
                "contract_coverage": written.get("contract_coverage") if isinstance(written.get("contract_coverage"), list) else [],
                "distinct_target": str(written.get("distinct_target") or "").strip(),
            })
            if name == "structure_three":
                kind = str(base["formal_framework_type"])
                asset_kind = str(base["asset_framework_type"])
                pool = pain if asset_kind == "痛点" else regular
                pool_ids = list(pool) if asset_kind == "痛点" else [key for key, item in pool.items() if item.get("framework") == asset_kind]
                selected = [str(x) for x in written.get("module_ids", [])]
                evaluated = [str(x) for x in written.get("evaluated_asset_ids", [])]
                calls: list[dict[str, object]] = []
                for module_id in selected:
                    item = pool.get(module_id)
                    if not item:
                        raise SystemExit(f"{ident} 选择了不存在的资产 {module_id}")
                    if asset_kind == "痛点":
                        path = Path(str(item.get("card_path") or "")).resolve()
                        call = {"module_type": asset_kind, "angle_id": module_id, "pain_id": item.get("pain_id"), "module_path": str(path), "content_sha256": item.get("card_sha256"), "source_anchor": item.get("source_anchor"), "wikilink": f"[[{path.stem}]]"}
                    else:
                        if item.get("framework") != asset_kind:
                            raise SystemExit(f"{ident} 资产类型错误 {module_id}")
                        path = Path(str(item.get("path") or "")).resolve()
                        call = {"module_type": asset_kind, "module_id": module_id, "module_path": str(path), "module_sha256": digest(path), "source_anchor": {"source_path": item.get("sourcePath"), "source_section": item.get("sourceSection"), "content_sha256": item.get("contentSha256")}, "wikilink": f"[[{path.stem}]]"}
                    call["selection_reason"] = {"topic_fit": str(written.get("topic_fit") or "与当前选题命题直接相关"), "framework_fit": str(written.get("framework_fit") or f"承担{kind}大框架职责"), "main_meaning_support": str(written.get("main_meaning_support") or "直接支撑本大框架论点与论据链")}
                    call["proposition_support"] = {pid: str(written.get("proposition_support", {}).get(pid) or "资产内容支持该命题") for pid in row["proposition_ids"]}
                    calls.append(call)
                row["asset_calls"] = calls
                row["asset_search"] = {"framework_type": asset_kind, "source_framework_type": kind, "index_sha256": handoff["pain_angle_index_sha256"] if asset_kind == "痛点" else handoff["processing_index_sha256"], "candidate_count": len(pool_ids), "evaluated_asset_ids": evaluated, "selected_asset_ids": selected, "gap_reason": "" if calls else str(written.get("gap_reason") or "已检索对应正式库，未发现与当前选题语义相关的资产。")}
            rows.append(row)
        plans[name] = {"angle_fingerprint": source.get("angle_fingerprint"), "argument_route": source.get("argument_route"), "non_overlap_rationale": source.get("non_overlap_rationale"), "progression_logic": source.get("progression_logic"), "core_frameworks": rows}
        if name == "structure_three":
            plans[name]["asset_gap_note"] = str(source.get("asset_gap_note") or "**资产缺口说明**：所有大框架均已按对应正式资产族检索；未命中项保持空白并记录缺口。")

    plans["structure_four"] = {"core_frameworks": [dict(base) | {"content_contract_id": contracts[str(base["core_framework_id"])]["content_contract_id"], "core_claim": "", "evidence_chain": []} for base in frameworks]}
    keys = ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_framework_sha256", "processing_index_sha256", "pain_angle_index_sha256", "topic_structure_types", "topic_propositions", "topic_analysis_sha256", "topic_table_binding")
    candidate = {key: handoff.get(key) for key in keys if key in handoff}
    candidate.update({"schema": "copy-structure-v12", "producer": {"agent_id": "xiaochai"}, "structure_segments": handoff["structure_segments"], "structure_four_status": "user-pending", "structures": plans})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "built", "frameworks": len(frameworks)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
