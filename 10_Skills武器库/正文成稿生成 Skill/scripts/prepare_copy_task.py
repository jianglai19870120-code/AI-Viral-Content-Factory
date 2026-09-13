#!/usr/bin/env python3
"""Create a sentence-plan handoff from frozen core-framework structure four."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def project_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents, Path(__file__).resolve().parents[3]):
        if (candidate / "00_系统说明" / "benchmark-case-registry.json").is_file():
            return candidate
    raise RuntimeError("找不到项目的 benchmark-case-registry.json；请在 AI爆款内容工厂项目根目录执行")


ROOT = project_root()
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))
from workflow.benchmark_cases import approved_case
from workflow.universal_copy_contract import digest, parse_breakdown


def frozen_frameworks(structure: dict) -> list[dict]:
    status = structure.get("structure_four_status") or structure.get("status")
    if status != "frozen":
        raise ValueError("结构四尚未冻结")
    if isinstance(structure.get("structures"), dict):
        section = structure["structures"].get("structure_four")
    else:
        section = structure
    frameworks = section.get("core_frameworks") if isinstance(section, dict) else None
    if not isinstance(frameworks, list) or not frameworks:
        raise ValueError("结构四必须保留完整核心大框架骨架")
    if any(not isinstance(item, dict) or not str(item.get("core_framework_id") or "").strip() for item in frameworks):
        raise ValueError("结构四必须保留全部核心大框架")
    return frameworks


def frozen_framework_rows(frameworks: list[dict], schema: str = "copy-structure-v12") -> dict[str, dict]:
    """Resolve the only active format: unified core-framework structure four."""
    if schema not in {"copy-structure-v11", "copy-structure-v12", "copy-structure-v13", "final-copy-structure-four-freeze-v4"}:
        raise ValueError("现役正文只接受 V11/V12/V13 统一核心大框架结构四或冻结 V4；旧 v7-v10 仅保留为历史文件，不得进入正文生成")
    result: dict[str, dict] = {}
    for framework in frameworks:
        row = dict(framework)
        identifier = str(row.get("core_framework_id") or "")
        if not identifier or identifier in result:
            raise ValueError("核心大框架 ID 必须唯一")
        statement = str(row.get("core_statement") or row.get("user_statement") or "").strip()
        origin = str(row.get("content_origin") or ("user-filled" if statement else "auto-fill-required"))
        if not statement and origin != "auto-fill-required":
            raise ValueError("活动结构四空白单元格必须标记为 auto-fill-required")
        chain = row.get("evidence_chain") if isinstance(row.get("evidence_chain"), list) else []
        row.update({"content_origin": origin, "user_statement": str(row.get("user_statement") or statement).strip(), "resolved_core_statement": statement, "evidence_chain": chain, "small_framework_id": identifier, "mapping_scope": "core-framework-unified"})
        result[identifier] = row
    return result


def load_intent_map(path: Path, structure: dict, rows: dict[str, dict]) -> tuple[dict[str, dict], dict]:
    intent = json.loads(path.read_text(encoding="utf-8"))
    expected_schema = "final-copy-structure-intent-map-v4"
    if intent.get("schema") != expected_schema or intent.get("status") != "completed":
        raise ValueError(f"结构四意图映射必须是 completed 的 {expected_schema}")
    if intent.get("structure_four_sha256") != digest(Path(str(structure.get("_path") or ""))):
        raise ValueError("结构四意图映射未绑定当前冻结结构四")
    topic_terms = intent.get("topic_terms") if isinstance(intent.get("topic_terms"), list) else []
    topic = str(structure.get("topic") or "")
    if not str(intent.get("topic_meaning") or "").strip() or not topic_terms or any(not isinstance(term, str) or not term.strip() or term.strip() not in topic for term in topic_terms):
        raise ValueError("结构四意图映射必须给出来自选题标题的主题词和主题含义")
    entries = intent.get("rows") if isinstance(intent.get("rows"), list) else []
    mapped = {str(item.get("intent_id") or ""): item for item in entries if isinstance(item, dict)}
    if set(mapped) != set(rows):
        raise ValueError("结构四意图映射必须逐行覆盖且只覆盖冻结小框架")
    for intent_id, row in rows.items():
        item = mapped[intent_id]
        origin = str(row.get("content_origin") or "user-filled")
        expected_scope = str(row.get("mapping_scope") or "small-framework")
        if item.get("origin") != origin or item.get("intent_scope", "small-framework") != expected_scope or item.get("user_statement") != str(row.get("user_statement") or "").strip():
            raise ValueError(f"结构四意图映射 {intent_id} 的来源或用户内容漂移")
        keywords = item.get("required_keywords") if isinstance(item.get("required_keywords"), list) else []
        if not str(item.get("main_meaning") or "").strip() or not keywords or any(not isinstance(term, str) or not term.strip() for term in keywords):
            raise ValueError(f"结构四意图映射 {intent_id} 缺少主旨或关键词")
        if origin == "user-filled" and any(term.strip() not in str(row.get("user_statement") or "") for term in keywords):
            raise ValueError(f"结构四意图映射 {intent_id} 为用户填写行加入了非用户关键词")
        anchors = item.get("content_anchors") if isinstance(item.get("content_anchors"), list) else []
        if origin == "user-filled":
            if not anchors:
                raise ValueError(f"结构四意图映射 {intent_id} 缺少框架内容锚点")
            seen_anchor_ids: set[str] = set()
            for anchor in anchors:
                if not isinstance(anchor, dict):
                    raise ValueError(f"结构四意图映射 {intent_id} 含非法内容锚点")
                anchor_id = str(anchor.get("anchor_id") or "").strip()
                source_text = str(anchor.get("source_text") or "").strip()
                anchor_terms = anchor.get("required_keywords") if isinstance(anchor.get("required_keywords"), list) else []
                assigned = anchor.get("assigned_small_structure_ids") if isinstance(anchor.get("assigned_small_structure_ids"), list) else []
                if (not anchor_id or anchor_id in seen_anchor_ids or not source_text
                        or source_text not in str(row.get("user_statement") or "")
                        or not str(anchor.get("main_meaning") or "").strip() or not anchor_terms or not assigned):
                    raise ValueError(f"结构四意图映射 {intent_id} 的内容锚点不完整或脱离用户原文")
                if any(not isinstance(term, str) or not term.strip() or term.strip() not in source_text for term in anchor_terms):
                    raise ValueError(f"结构四意图映射 {intent_id}/{anchor_id} 的锚点关键词必须来自锚点原文")
                seen_anchor_ids.add(anchor_id)
        if origin == "auto-fill-required" and not str(item.get("auto_fill_reasoning") or "").strip():
            raise ValueError(f"结构四意图映射 {intent_id} 缺少空白行自动补全理由")
    return mapped, intent


def map_segments_to_rows(segments: list[dict], frameworks: list[dict], rows: dict[str, dict]) -> dict[str, dict]:
    """Map every small structure, including support-only blocks, to a frozen row."""
    if not isinstance(segments, list) or not segments:
        raise ValueError("结构四缺少锁定 structure_segments")
    by_block = {str(value.get("framework_block_id") or ""): value for value in frameworks}

    def resolved_block_rows(block: dict | None) -> list[dict]:
        if isinstance(block, dict):
            core_id = str(block.get("core_framework_id") or "")
            if core_id in rows and rows[core_id].get("mapping_scope") == "core-framework-unified":
                return [rows[core_id]]
        raw = block.get("small_framework_rows", []) if isinstance(block, dict) else []
        return [rows[str(row.get("small_framework_id") or "")] for row in raw if isinstance(row, dict) and str(row.get("small_framework_id") or "") in rows]
    mapped: dict[str, dict] = {}
    nearest: dict | None = None
    for index, segment in enumerate(segments):
        block_id = str(segment.get("framework_block_id") or "")
        framework = by_block.get(block_id)
        candidate_rows = resolved_block_rows(framework)
        target = candidate_rows[0] if candidate_rows else None
        if target is not None:
            nearest = candidate_rows[-1]
        if target is None:
            # A leading support segment inherits the next formal framework.
            future = next((next(iter(resolved_block_rows(by_block.get(str(item.get("framework_block_id") or "")))), None) for item in segments[index + 1:] if resolved_block_rows(by_block.get(str(item.get("framework_block_id") or "")))), None)
            target = nearest or future
        if target is None:
            raise ValueError("support-only 结构段找不到相邻小框架行")
        for small in segment.get("small_structures", []):
            if not isinstance(small, dict): raise ValueError("structure_segments 含非法小结构")
            small_id = str(small.get("small_structure_id") or "")
            mapped[small_id] = next((row for row in rows.values() if str(row.get("small_structure_id") or "") == small_id), target)
    return mapped


def main() -> int:
    parser = argparse.ArgumentParser(description="创建正文成稿逐句复刻 handoff")
    parser.add_argument("--structure-four", type=Path, required=True, help="冻结的文案结构候选或结构四 JSON")
    parser.add_argument("--replication-profile", type=Path, required=True, help="已校验的逐单元句式复刻画像 JSON")
    parser.add_argument("--replication-profile-audit", type=Path, required=True, help="复刻画像对应的 approved 小审回执")
    parser.add_argument("--structure-intent-map", type=Path, required=True, help="小写完成的结构四主题/关键词/空白补全映射")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    structure = json.loads(args.structure_four.read_text(encoding="utf-8"))
    structure["_path"] = str(args.structure_four.resolve())
    try:
        frameworks = frozen_frameworks(structure)
        frozen_rows = frozen_framework_rows(frameworks, str(structure.get("schema") or ""))
        intent_by_row, intent_map = load_intent_map(args.structure_intent_map, structure, frozen_rows)
        small_to_row = map_segments_to_rows(structure.get("structure_segments"), frameworks, frozen_rows)
    except ValueError as exc:
        raise SystemExit(str(exc))
    benchmark_id = str(structure.get("benchmark_case_id") or "")
    try:
        case = approved_case(benchmark_id)
        benchmark = case["breakdownPath"]
        parsed = parse_breakdown(benchmark)
    except ValueError as exc:
        raise SystemExit(f"对标拆解不可调用：{exc}")
    profile = json.loads(args.replication_profile.read_text(encoding="utf-8"))
    profile_audit = json.loads(args.replication_profile_audit.read_text(encoding="utf-8"))
    if profile.get("schema") != "benchmark-replication-profile-v2":
        raise SystemExit("复刻画像 schema 必须为 benchmark-replication-profile-v2")
    if profile.get("benchmark_case_id") != benchmark_id or profile.get("benchmark_sha256") != digest(benchmark):
        raise SystemExit("复刻画像没有绑定当前已审核对标案例，或对标拆解哈希已变化")
    profile_sha256 = digest(args.replication_profile)
    profile_subject = profile_audit.get("subject") if isinstance(profile_audit.get("subject"), dict) else {}
    if profile_audit.get("schema") != "audit-receipt-v3" or profile_audit.get("artifactType") != "benchmark-replication-profile-v1" or profile_audit.get("status") != "approved" or profile_subject.get("profileSha256") != profile_sha256 or profile_subject.get("benchmarkSha256") != digest(benchmark):
        raise SystemExit("复刻画像必须具有当前对标案例与画像哈希对应的 approved 小审回执")
    profile_units = profile.get("units") if isinstance(profile.get("units"), list) else []
    profile_by_no = {str(item.get("unit_no") or ""): item for item in profile_units if isinstance(item, dict)}
    expected_profile_fields = ("sentence_shape", "clause_roles", "required_punctuation", "sentence_form", "source_text_sha256", "word_range")
    if len(profile_by_no) != len(parsed["units"]) or any(
        not isinstance(profile_by_no.get(str(unit.get("unit_no") or "")), dict)
        or any(not profile_by_no[str(unit["unit_no"])].get(field) for field in expected_profile_fields)
        or profile_by_no[str(unit["unit_no"])]["required_punctuation"] != unit.get("source_punctuation")
        or profile_by_no[str(unit["unit_no"])]["source_text_sha256"] != unit.get("source_text_sha256")
        or profile_by_no[str(unit["unit_no"])]["word_range"] != unit.get("word_range")
        for unit in parsed["units"]
    ):
        raise SystemExit("复刻画像必须逐单元覆盖，并锁定句式骨架、分句角色、标点和句型")
    blueprint = parsed["functional_blueprint"]
    display_by_small = {
        str(small.get("small_structure_id") or ""): {
            "framework": str(segment.get("framework_label") or ""),
            "small": str(small.get("small_framework_name") or ""),
        }
        for segment in structure.get("structure_segments", []) if isinstance(segment, dict)
        for small in segment.get("small_structures", []) if isinstance(small, dict)
    }
    expected_ids: list[str] = []
    enriched_blueprint: list[dict] = []
    for row in blueprint:
        block_id = str(row["大框架区块"])
        expected_ids.append(block_id)
        enriched = dict(row)
        small_id = str(row["小结构编号"])
        row_content = small_to_row.get(small_id)
        if row_content is None: raise SystemExit(f"结构四小框架缺少对标小结构 {small_id}")
        enriched["parent_framework_block_id"] = block_id
        enriched["parent_small_framework_id"] = row_content.get("small_framework_id")
        enriched["parent_core_framework_id"] = row_content.get("core_framework_id")
        enriched["intent_scope"] = row_content.get("mapping_scope", "small-framework")
        row_intent = intent_by_row[str(row_content.get("small_framework_id") or "")]
        enriched["parent_core_statement"] = row_content.get("resolved_core_statement")
        enriched["parent_core_claim"] = str(row_content.get("core_claim") or "")
        enriched["parent_core_evidence"] = str(row_content.get("core_evidence") or "")
        enriched["parent_evidence_chain"] = row_content.get("evidence_chain") if isinstance(row_content.get("evidence_chain"), list) else []
        enriched["intent_id"] = row_intent["intent_id"]
        enriched["intent_origin"] = row_intent["origin"]
        enriched["intent_main_meaning"] = row_intent["main_meaning"]
        enriched["intent_required_keywords"] = row_intent["required_keywords"]
        enriched["content_anchors"] = row_intent.get("content_anchors", [])
        enriched["intent_auto_fill_context"] = row_intent.get("auto_fill_context", {})
        enriched["intent_auto_fill_reasoning"] = row_intent.get("auto_fill_reasoning", "")
        enriched["is_hidden_support_node"] = small_id != str(row_content.get("small_structure_id") or "")
        enriched["display_framework_label"] = display_by_small.get(small_id, {}).get("framework") or enriched["大框架功能"]
        enriched["display_small_framework_name"] = display_by_small.get(small_id, {}).get("small") or enriched["通用复刻功能"]
        enriched_blueprint.append(enriched)
    # 每个结构四核心框架只能向自身以及开场继承的支持节点提供内容。
    valid_small_ids_by_core: dict[str, set[str]] = {}
    for small_id, row_content in small_to_row.items():
        core_id = str(row_content.get("core_framework_id") or row_content.get("small_framework_id") or "")
        valid_small_ids_by_core.setdefault(core_id, set()).add(str(small_id))
    anchors_by_core: dict[str, list[dict]] = {}
    for row_id, row_intent in intent_by_row.items():
        core_id = str(frozen_rows[row_id].get("core_framework_id") or row_id)
        anchors = row_intent.get("content_anchors") if isinstance(row_intent.get("content_anchors"), list) else []
        if anchors:
            allowed_small_ids = valid_small_ids_by_core.get(core_id, set())
            for anchor in anchors:
                assigned = {str(value) for value in anchor.get("assigned_small_structure_ids", [])}
                if not assigned or not assigned.issubset(allowed_small_ids):
                    raise SystemExit(f"内容锚点 {anchor.get('anchor_id')} 只能分配给所属核心大框架的小结构")
            anchors_by_core[core_id] = anchors
    units = []
    for unit in parsed["units"]:
        copied = dict(unit)
        shape = profile_by_no[str(unit["unit_no"])]
        for field in ("sentence_shape", "clause_roles", "required_punctuation", "sentence_form"):
            copied[field] = shape[field]
        parent = next((row for row in enriched_blueprint if str(row["小结构编号"]) == str(unit["small_structure_id"])), None)
        if parent is None:
            raise SystemExit(f"复刻单元 {unit['unit_no']} 缺少所属大结构")
        copied["parent_framework_block_id"] = parent["parent_framework_block_id"]
        copied["parent_small_framework_id"] = parent["parent_small_framework_id"]
        copied["parent_core_framework_id"] = parent.get("parent_core_framework_id")
        copied["intent_scope"] = parent.get("intent_scope", "small-framework")
        copied["parent_core_statement"] = parent["parent_core_statement"]
        for field in ("intent_id", "intent_origin", "intent_main_meaning", "intent_required_keywords", "intent_auto_fill_context", "intent_auto_fill_reasoning"):
            copied[field] = parent[field]
        for field in ("parent_core_claim","parent_core_evidence","parent_evidence_chain","claim_intent","evidence_intent"):
            if field in parent:copied[field]=parent[field]
        copied["is_hidden_support_node"] = parent["is_hidden_support_node"]
        core_id = str(copied.get("parent_core_framework_id") or "")
        anchors = anchors_by_core.get(core_id, [])
        copied["content_anchors"] = anchors
        copied["allowed_content_anchor_ids"] = [
            str(anchor["anchor_id"]) for anchor in anchors
            if str(unit["small_structure_id"]) in {str(value) for value in anchor.get("assigned_small_structure_ids", [])}
        ]
        if copied.get("intent_origin") == "user-filled" and not copied["allowed_content_anchor_ids"]:
            raise SystemExit(f"复刻单元 {unit['unit_no']} 未分配所属结构四内容锚点")
        own_source = str(copied.get("parent_core_statement") or "")
        copied["forbidden_cross_framework_terms"] = sorted({
            str(term).strip()
            for other_core, other_anchors in anchors_by_core.items() if other_core != core_id
            for anchor in other_anchors for term in anchor.get("protected_terms", anchor.get("required_keywords", []))
            if isinstance(term, str) and len(term.strip()) >= 2 and term.strip() not in own_source
        })
        # 对标决定“怎样推进”，结构四决定“写什么”。候选必须逐角色说明如何实现。
        copied["mechanism_contract"] = {
            "schema": "benchmark-sentence-mechanism-v1",
            "source_unit_no": str(unit["unit_no"]),
            "benchmark_template": str(copied.get("template") or ""),
            "benchmark_mechanism": str(copied.get("mechanism") or ""),
            "required_role_slots": [str(role) for role in copied.get("clause_roles", []) if str(role).strip()],
            "required_punctuation": str(copied.get("required_punctuation") or ""),
            "reasoning_rule": "先复刻本对标句的推理动作、前提、关系与结论，再以本小结构获准内容锚点填入槽位；不得只复刻字数、标点或泛功能标签。",
            "illustration_policy": "可为填满锁定句式补充说明性场景、数字或比喻，但必须从本句获准内容锚点推导、记录理由，且不得新增独立观点、跨框架素材或未经说明的事实经历。",
        }
        units.append(copied)
    payload = {
        "schema": "final-copy-sentence-plan-v8",
        "structure_four": str(args.structure_four.resolve()),
        "structure_four_sha256": digest(args.structure_four),
        "topic": str(structure.get("topic") or ""), "topic_terms": intent_map["topic_terms"], "topic_meaning": intent_map["topic_meaning"],
        "structure_intent_map": str(args.structure_intent_map.resolve()), "structure_intent_map_sha256": digest(args.structure_intent_map),
        "benchmark_case_id": benchmark_id,
        "benchmark": str(benchmark.resolve()),
        "benchmark_sha256": digest(benchmark),
        "benchmark_audit": str(case["auditPath"].resolve()),
        "replication_profile": str(args.replication_profile.resolve()),
        "replication_profile_sha256": profile_sha256,
        "replication_profile_audit": str(args.replication_profile_audit.resolve()),
        "core_frameworks": frameworks,
        "structure_segments": structure.get("structure_segments"),
        "units": units,
        "functional_blueprint": enriched_blueprint,
        "content_source": "活动结构四按核心大框架封闭供给正文：每一条用户内容拆为带原文片段、主旨、关键词、保护词和所属小结构的内容锚点；长内容只在其自身小结构内压缩展开，禁止跨框架借用。对标只提供结构功能与表达约束。",
        "forbidden_sources": ["处理库", "输入库", "案例卡", "开头卡", "其他对标案例", "对标原文证据层"],
        "copying_rule": "正文阶段读取锁定对标卡的小结构与复刻单元，先复刻每句的推理动作、前提、关系、转折与结论，再用本小结构获准内容锚点填槽；逐单元执行复刻画像锁定的句式骨架、分句角色、连接标点、句型、功能、推进、语气、节奏与字数范围。不得只复刻字数、标点或泛功能标签，不复用原文内容。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "prepared", "coreFrameworks": len(frameworks), "units": len(units), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
