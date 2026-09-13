"""V13 content-object planning, candidate binding and mechanical validation."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from prepare_structure_task import (
    ROOT, approved_case, benchmark_framework, core_frameworks, digest,
    structure_segments,
)

STRUCTURES = ("structure_one", "structure_two", "structure_three", "structure_four")
ANGLE_TYPES = {"平台规则", "内容策略", "用户心理", "商业变现", "账号增长", "创作者效率", "认知判断", "产品", "AI", "成本", "风险", "竞争", "长期经营"}
FACT_STATUSES = {"conceptual", "common_pattern", "user_provided", "asset_backed", "requires_verification"}
FORMAL_TYPES = {"观点", "痛点", "误区", "解决方案", "案例", "推荐理由", "方法", "原因", "购买理由", "证据", "反常识", "对比", "结果", "行动建议"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _norm(value: object) -> str:
    return re.sub(r"\W+", "", _text(value))


def _index(path: Path) -> dict[str, dict]:
    data: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            data[str(item.get("id") or item.get("angle_id") or "")] = item
    return data


def load_topic_analysis_v13(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not _text(raw.get("topic_promise")):
        raise ValueError("V13 topic analysis 必须包含 topic_promise")
    pool = raw.get("content_object_pool")
    if not isinstance(pool, list) or not 3 <= len(pool) <= 30:
        raise ValueError("content_object_pool 必须包含 3-30 个具体内容对象")
    seen: set[str] = set()
    for item in pool:
        if not isinstance(item, dict):
            raise ValueError("content_object_pool 项必须是对象")
        identifier = _text(item.get("content_object_id"))
        required = (identifier, _text(item.get("category")), _text(item.get("statement")), _text(item.get("scope")), _text(item.get("source_status")))
        if not all(required) or identifier in seen or item.get("source_status") not in FACT_STATUSES:
            raise ValueError("内容对象必须有唯一 ID、类别、具体说法、适用范围和合法事实等级")
        if item.get("source_status") == "asset_backed" and not _text(item.get("asset_hint")):
            raise ValueError("asset_backed 内容对象必须声明 asset_hint")
        seen.add(identifier)
    propositions = raw.get("topic_propositions", [])
    if not isinstance(propositions, list) or len(propositions) > 5:
        raise ValueError("topic_propositions 仅作为全篇约束，最多 5 条")
    return {"topic_promise": _text(raw["topic_promise"]), "content_object_pool": pool, "topic_propositions": propositions}


def framework_contracts_v13(frameworks: list[dict]) -> list[dict]:
    templates = {
        "误区": ("拆掉一个具体错误认知", ["错误认知", "不成立原因或边界"], ["为何相信", "后果", "反例", "对比", "真正变量"]),
        "痛点": ("还原具体对象正在承受的障碍", ["场景", "障碍或代价"], ["情绪", "深层需求"]),
        "解决方案": ("给出最少充分的可执行动作", ["solution_steps"], ["对象", "原因", "成功标准"]),
        "案例": ("用具体对象、行为冲突和结果证明判断", ["case_subtype", "具体对象", "具体行为或冲突", "具体结果"], ["结论关联"]),
        "观点": ("建立可被后文证明的明确判断", ["判断", "依据或边界"], ["反直觉校正", "结果"]),
        "推荐理由": ("说明对象为何值得目标读者选择", ["读者成本", "对象路径"], ["行动时机", "结果"]),
    }
    contracts: list[dict] = []
    for item in frameworks:
        kind = _text(item.get("formal_framework_type"))
        function, required, optional = templates.get(kind, ("完成当前大框架的内容功能", ["明确对象", "核心判断"], ["原因", "案例", "结果"]))
        contracts.append({
            "content_contract_id": f"FC-{item['core_framework_id']}", "core_framework_id": item["core_framework_id"],
            "formal_framework_type": kind, "content_function": function,
            "required_content": required, "optional_expansions": optional,
        })
    return contracts


def build_handoff_v13(*, topic: str, benchmark_id: str, topic_analysis: dict, topic_analysis_path: Path, topic_table_binding: dict | None = None) -> dict:
    case = approved_case(benchmark_id)
    benchmark = case["breakdownPath"]
    framework = benchmark_framework(benchmark)
    segments = structure_segments(framework)
    cores = core_frameworks(segments)
    processing = ROOT / "04_数据中心" / "03_查询索引" / "module-function-index.jsonl"
    pain = ROOT / "04_数据中心" / "03_查询索引" / "video-pain-angle-index.jsonl"
    return {
        "schema": "copy-structure-handoff-v13", "topic": topic, "benchmark_case_id": benchmark_id,
        "benchmark_path": str(benchmark.resolve()), "benchmark_sha256": digest(benchmark),
        "benchmark_audit_receipt": str(case["auditPath"].resolve()), "benchmark_framework": framework,
        "benchmark_framework_sha256": digest(benchmark), "structure_segments": segments, "core_frameworks": cores,
        "framework_content_contracts": framework_contracts_v13(cores),
        "topic_promise": topic_analysis["topic_promise"], "content_object_pool": topic_analysis["content_object_pool"],
        "topic_propositions": topic_analysis.get("topic_propositions", []), "topic_analysis_sha256": digest(topic_analysis_path),
        "processing_index": str(processing.resolve()), "processing_index_sha256": digest(processing),
        "pain_angle_index": str(pain.resolve()), "pain_angle_index_sha256": digest(pain),
        "formal_asset_root": str((ROOT / "02_资产中心" / "02_处理库").resolve()),
        "topic_table_binding": topic_table_binding,
    }


def _asset_calls(written: dict, base: dict, handoff: dict, regular: dict, pain: dict) -> tuple[list[dict], dict]:
    kind = _text(base.get("asset_framework_type"))
    pool = pain if kind == "痛点" else {key: value for key, value in regular.items() if value.get("framework") == kind}
    chosen = [str(value) for value in written.get("module_ids", [])]
    calls: list[dict] = []
    for identifier in chosen:
        item = pool.get(identifier)
        if not item:
            raise ValueError(f"结构三选择了不存在或类型不匹配的资产：{identifier}")
        path = Path(str(item.get("card_path") if kind == "痛点" else item.get("path"))).resolve()
        if kind == "痛点":
            call = {"module_type": kind, "angle_id": identifier, "pain_id": item.get("pain_id"), "module_path": str(path), "content_sha256": item.get("card_sha256"), "source_anchor": item.get("source_anchor"), "wikilink": f"[[{path.stem}]]"}
        else:
            call = {"module_type": kind, "module_id": identifier, "module_path": str(path), "module_sha256": digest(path), "source_anchor": {"source_path": item.get("sourcePath"), "source_section": item.get("sourceSection"), "content_sha256": item.get("contentSha256")}, "wikilink": f"[[{path.stem}]]"}
            if kind == "案例" and item.get("kind") == "case-card-v12":
                call.update({
                    "case_id": item.get("caseId"),
                    "case_copy": item.get("caseCopy"),
                    "case_copy_sha256": item.get("caseCopySha256"),
                    "continuous_quotes": (item.get("sourceEvidence") or {}).get("continuousQuotes", []),
                    "evidence_boundary": item.get("evidenceBoundary"),
                })
        calls.append(call)
    search = {"framework_type": kind, "index_sha256": handoff["pain_angle_index_sha256"] if kind == "痛点" else handoff["processing_index_sha256"], "candidate_count": len(pool), "evaluated_asset_ids": [str(v) for v in written.get("evaluated_asset_ids", [])], "selected_asset_ids": chosen, "gap_reason": "" if calls else _text(written.get("gap_reason"))}
    return calls, search


def build_candidate_v13(handoff_path: Path, authoring_path: Path, output: Path) -> None:
    h = json.loads(handoff_path.read_text(encoding="utf-8"))
    if h.get("schema") != "copy-structure-handoff-v13":
        raise ValueError("仅接受 copy-structure-handoff-v13")
    authored = json.loads(authoring_path.read_text(encoding="utf-8"))
    regular, pain = _index(Path(h["processing_index"])), _index(Path(h["pain_angle_index"]))
    contracts = {str(x["core_framework_id"]): x for x in h["framework_content_contracts"]}
    plans: dict[str, dict] = {}
    for name in ("structure_one", "structure_two", "structure_three"):
        source = authored.get(name, {}) if isinstance(authored.get(name), dict) else {}
        authored_rows = source.get("frameworks", {}) if isinstance(source.get("frameworks"), dict) else {}
        rows: list[dict] = []
        for base in h["core_frameworks"]:
            ident = str(base["core_framework_id"])
            written = authored_rows.get(ident, {}) if isinstance(authored_rows.get(ident), dict) else {}
            row = dict(base) | {"content_contract_id": contracts[ident]["content_contract_id"], "content_object_id": _text(written.get("content_object_id")), "core_claim": _text(written.get("core_claim")), "evidence_chain": written.get("evidence_chain", []) if isinstance(written.get("evidence_chain"), list) else [], "solution_steps": written.get("solution_steps", []) if isinstance(written.get("solution_steps"), list) else [], "case_subtype": _text(written.get("case_subtype")), "fact_status": _text(written.get("fact_status")), "verification_note": _text(written.get("verification_note"))}
            if name == "structure_three":
                calls, search = _asset_calls(written, base, h, regular, pain)
                row["asset_calls"], row["asset_search"] = calls, search
                if calls:
                    row["fact_status"] = "asset_backed"
                else:
                    for key in ("content_object_id", "core_claim", "evidence_chain", "solution_steps", "case_subtype", "fact_status", "verification_note"):
                        row[key] = [] if key in {"evidence_chain", "solution_steps"} else ""
            rows.append(row)
        plans[name] = {"mother_angle_type": _text(source.get("mother_angle_type")), "angle_fingerprint": source.get("angle_fingerprint"), "progression_map": source.get("progression_map"), "core_frameworks": rows, "asset_gap_note": _text(source.get("asset_gap_note")) if name == "structure_three" else ""}
    plans["structure_four"] = {"core_frameworks": [dict(base) | {"content_contract_id": contracts[str(base["core_framework_id"])]["content_contract_id"], "core_claim": "", "evidence_chain": [], "solution_steps": []} for base in h["core_frameworks"]]}
    keys = ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_framework_sha256", "structure_segments", "topic_promise", "content_object_pool", "topic_propositions", "topic_analysis_sha256", "processing_index_sha256", "pain_angle_index_sha256", "topic_table_binding")
    candidate = {key: h.get(key) for key in keys} | {"schema": "copy-structure-v13", "producer": {"agent_id": "xiaochai"}, "structure_four_status": "user-pending", "structures": plans}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _is_concrete_case(row: dict) -> bool:
    text = " ".join([_text(row.get("core_claim"))] + [_text(x.get("text")) for x in row.get("evidence_chain", []) if isinstance(x, dict)])
    return bool(_text(row.get("case_subtype")) and len(text) >= 28 and re.search(r"(?:有人|创作者|账号|用户|客户|一次|视频|内容|发布|看到|做了)", text) and re.search(r"(?:结果|却|后来|导致|没有|变成|反馈)", text))


def validate_v13(handoff: dict, candidate: dict) -> list[str]:
    errors: list[str] = []
    if handoff.get("schema") != "copy-structure-handoff-v13" or candidate.get("schema") != "copy-structure-v13":
        return ["handoff/candidate schema 必须为 V13/V13"]
    for key in ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_framework_sha256", "structure_segments", "topic_promise", "content_object_pool", "topic_analysis_sha256", "processing_index_sha256", "pain_angle_index_sha256", "topic_table_binding"):
        if candidate.get(key) != handoff.get(key): errors.append(f"候选未锁定 handoff 的 {key}")
    pool = {str(x.get("content_object_id")): x for x in handoff.get("content_object_pool", []) if isinstance(x, dict)}
    expected = [str(x.get("core_framework_id")) for x in handoff.get("core_frameworks", [])]
    fingerprints: list[dict] = []; route_sets: list[set[str]] = []
    for name in STRUCTURES:
        plan = candidate.get("structures", {}).get(name, {})
        rows = plan.get("core_frameworks", []) if isinstance(plan, dict) else []
        if [str(x.get("core_framework_id")) for x in rows if isinstance(x, dict)] != expected:
            errors.append(f"{name} 未完整保留大框架顺序"); continue
        if name == "structure_four":
            for row in rows:
                if any(row.get(key) for key in ("core_claim", "evidence_chain", "solution_steps")): errors.append("结构四 user-pending 必须留空")
            continue
        if _text(plan.get("mother_angle_type")) not in ANGLE_TYPES: errors.append(f"{name} 缺少合法 mother_angle_type")
        fingerprint = plan.get("angle_fingerprint") if isinstance(plan.get("angle_fingerprint"), dict) else {}
        if not all(_text(fingerprint.get(key)) for key in ("mother_proposition", "critical_target", "causal_mechanism", "evidence_strategy", "solution_direction")): errors.append(f"{name} 缺少五维角度指纹")
        else: fingerprints.append(fingerprint)
        progression = plan.get("progression_map") if isinstance(plan.get("progression_map"), dict) else {}
        if set(progression) != set(expected) or any(not isinstance(progression.get(key), dict) or not _text(progression[key].get("new_information")) or not _text(progression[key].get("builds_on")) for key in expected): errors.append(f"{name} 必须逐节点说明新增信息与承接关系")
        seen: set[str] = set()
        for row in rows:
            ident = _text(row.get("core_framework_id")); kind = _text(row.get("formal_framework_type")); calls = row.get("asset_calls", []) if isinstance(row.get("asset_calls"), list) else []
            if name == "structure_three" and not calls:
                search = row.get("asset_search", {}) if isinstance(row.get("asset_search"), dict) else {}
                if any(row.get(key) for key in ("content_object_id", "core_claim", "evidence_chain", "solution_steps", "case_subtype", "fact_status", "verification_note")) or not _text(search.get("gap_reason")): errors.append(f"{name}/{ident} 无资产时必须留空并记录缺口")
                continue
            object_id = _text(row.get("content_object_id"))
            if object_id not in pool or object_id in seen: errors.append(f"{name}/{ident} 必须绑定本路线唯一具体内容对象")
            seen.add(object_id)
            status = _text(row.get("fact_status"))
            if status not in FACT_STATUSES: errors.append(f"{name}/{ident} 缺少合法事实等级")
            if name == "structure_three" and status != "asset_backed": errors.append(f"{name}/{ident} 结构三非空内容必须 asset_backed")
            if status == "requires_verification" and not _text(row.get("verification_note")): errors.append(f"{name}/{ident} 待核验事实缺少核验说明")
            if status in {"conceptual", "common_pattern"} and re.search(r"\d|官方|平台规定|百分之|万元", " ".join([_text(row.get("core_claim"))] + [_text(x.get("text")) for x in row.get("evidence_chain", []) if isinstance(x, dict)])): errors.append(f"{name}/{ident} 无来源内容不得写具体可核验事实")
            if not _text(row.get("core_claim")): errors.append(f"{name}/{ident} 缺少核心论点")
            if kind == "解决方案":
                steps = row.get("solution_steps", [])
                if not 1 <= len(steps) <= 5 or any(not isinstance(x, dict) or not _text(x.get("action")) or not _text(x.get("object")) or not (_text(x.get("reason")) or _text(x.get("success_criteria"))) for x in steps): errors.append(f"{name}/{ident} 解决方案必须有 1-5 个独立步骤")
            elif not isinstance(row.get("evidence_chain"), list) or not 1 <= len(row["evidence_chain"]) <= 4 or any(not _text(x.get("text")) for x in row["evidence_chain"] if isinstance(x, dict)):
                errors.append(f"{name}/{ident} 必须有 1-4 条直接论据")
            if kind == "案例" and not _is_concrete_case(row): errors.append(f"{name}/{ident} 案例必须包含具体对象、行为冲突与结果")
            if kind == "误区":
                text = " ".join([_text(row.get("core_claim"))] + [_text(x.get("text")) for x in row.get("evidence_chain", []) if isinstance(x, dict)])
                if not re.search(r"(?:以为|误以为|觉得|相信|不是|其实)", text) or not re.search(r"(?:因为|所以|导致|不成立|边界|却)", text): errors.append(f"{name}/{ident} 误区必须说明错误认知及其不成立原因或边界")
        route_sets.append(seen)
    for left in range(len(route_sets)):
        for right in range(left + 1, len(route_sets)):
            union = route_sets[left] | route_sets[right]
            if union and len(route_sets[left] & route_sets[right]) / len(union) > .4: errors.append("三条结构的具体内容对象重合率超过 40%")
    for left in range(len(fingerprints)):
        for right in range(left + 1, len(fingerprints)):
            different = sum(_norm(fingerprints[left].get(key)) != _norm(fingerprints[right].get(key)) for key in ("mother_proposition", "critical_target", "causal_mechanism", "evidence_strategy", "solution_direction"))
            if different < 3: errors.append("两条路线的五维角度指纹少于三个实质差异字段")
    return errors
