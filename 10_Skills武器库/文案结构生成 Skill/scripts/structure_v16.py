"""V16: title-bound argument chains plus source-native evidence for structure three."""
from __future__ import annotations

import json
import re
from pathlib import Path

from structure_v15 import CHAIN_FIELDS, STRUCTURES, _merge_rows, _text, validate_logic_chain, validate_title_contract
from structure_v15 import build_handoff_v15

SOURCE_EVIDENCE_FIELDS = ("source_index", "source_section", "excerpt", "evidence_role", "support_explanation")


def build_handoff_v16(*, topic: str, benchmark_id: str, topic_table_binding: dict | None = None) -> dict:
    payload = build_handoff_v15(topic=topic, benchmark_id=benchmark_id, topic_table_binding=topic_table_binding)
    payload["schema"] = "copy-structure-handoff-v16"
    return payload


def section_text(path: Path, section: str) -> str:
    """Return one Markdown section, keeping a source excerpt independently verifiable."""
    text = path.read_text(encoding="utf-8")
    if not section.strip():
        return text
    marker = re.compile(rf"(?m)^#+\s+{re.escape(section.strip())}\s*$")
    found = marker.search(text)
    if not found:
        # Some normalized modules use labels such as “步骤1-3” rather than a heading.
        return text if section.strip() in text or re.fullmatch(r"步骤\d+(?:-\d+)?", section.strip()) else ""
    following = re.search(r"(?m)^#+\s+", text[found.end():])
    return text[found.start(): found.end() + following.start()] if following else text[found.start():]


def normalized(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def validate_case_card_binding(row: dict) -> list[str]:
    """案例节点只能直接调用已审核 V12 卡的 case_copy，不能改写成说明文。"""
    if str(row.get("formal_framework_type") or "") != "案例":
        return []
    errors: list[str] = []
    sources = row.get("processing_sources") if isinstance(row.get("processing_sources"), list) else []
    root = Path(__file__).resolve().parents[3]
    copies: list[str] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        path = (root / str(source.get("path") or "")).resolve()
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "- 合同版本：work-journal-case-card-v12" not in text:
            continue
        found = re.search(r"^##\s*可直接调用案例\s*\n+(.+?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
        if found and found.group(1).strip():
            copies.append(found.group(1).strip())
    unique = list(dict.fromkeys(copies))
    if len(unique) != 1:
        return ["案例节点必须且只能绑定一张 V12 正式案例卡"]
    if str(row.get("core_claim") or "").strip() != unique[0]:
        errors.append("案例节点的核心内容必须逐字等于已审核案例卡的 case_copy")
    return errors


def validate_source_evidence(row: dict) -> list[str]:
    """Verify each rendered structure-three proof is a literal, relevant source extract."""
    errors: list[str] = []
    sources = row.get("processing_sources") if isinstance(row.get("processing_sources"), list) else []
    evidences = row.get("evidence_chain") if isinstance(row.get("evidence_chain"), list) else []
    kind = str(row.get("formal_framework_type") or "")
    roles: list[str] = []
    for number, item in enumerate(evidences, 1):
        proof = item.get("source_evidence") if isinstance(item, dict) and isinstance(item.get("source_evidence"), dict) else {}
        missing = [field for field in SOURCE_EVIDENCE_FIELDS if not _text(proof.get(field)) and field != "source_index"]
        if not isinstance(proof.get("source_index"), int):
            missing.append("source_index")
        if missing:
            errors.append(f"论据{number} 缺少 source_evidence：{'、'.join(missing)}"); continue
        index = proof["source_index"]
        if not 0 <= index < len(sources):
            errors.append(f"论据{number} source_index 未绑定 processing_sources"); continue
        source = sources[index] if isinstance(sources[index], dict) else {}
        if proof.get("source_section") != source.get("section"):
            errors.append(f"论据{number} 原文证据章节与出处不一致"); continue
        path = Path(str(source.get("path") or ""))
        absolute = (Path(__file__).resolve().parents[3] / path).resolve()
        if not absolute.is_file():
            errors.append(f"论据{number} 原文证据文件不存在"); continue
        source_text = section_text(absolute, str(source.get("section") or ""))
        if normalized(proof.get("excerpt")) not in normalized(source_text):
            errors.append(f"论据{number} 原文摘录不在指定出处章节"); continue
        roles.append(str(proof.get("evidence_role") or ""))
        if kind == "解决方案":
            step = proof.get("step_no")
            if not isinstance(step, int) or step < 1 or not re.search(rf"步骤\s*{step}\b", str(proof.get("excerpt"))):
                errors.append(f"论据{number} 解决方案必须引用带步骤号的原文动作")
    if kind == "案例":
        needed = ({"场景", "触发"}, {"行动", "转折"}, {"结果", "结论"})
        if not all(any(role in group for role in roles) for group in needed):
            errors.append("案例必须以原文证据覆盖场景或触发、行动或转折、结果或结论")
    if kind == "误区" and not (any(role == "误区" for role in roles) and any(role in {"漏洞", "后果", "纠正"} for role in roles)):
        errors.append("误区必须以原文证据覆盖原误区及漏洞、后果或纠正依据")
    return errors


def build_candidate_v16(handoff_path: Path, authoring_path: Path, output: Path) -> None:
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    if handoff.get("schema") != "copy-structure-handoff-v16":
        raise ValueError("仅接受 copy-structure-handoff-v16")
    authored = json.loads(authoring_path.read_text(encoding="utf-8"))
    errors = validate_title_contract(authored.get("title_contract"))
    if errors: raise ValueError("；".join(errors))
    base_rows = handoff.get("core_frameworks") if isinstance(handoff.get("core_frameworks"), list) else []
    expected = [str(row.get("core_framework_id") or "") for row in base_rows]
    plans = authored.get("structures") if isinstance(authored.get("structures"), dict) else {}
    result: dict[str, dict] = {}
    mothers: list[str] = []
    shared_conclusion = _text((authored.get("title_contract") or {}).get("terminal_conclusion"))
    for name in STRUCTURES:
        authored_plan = plans.get(name) if isinstance(plans.get(name), dict) else {}
        rows = _merge_rows(base_rows, authored_plan.get("core_frameworks"), name)
        plan = dict(authored_plan) | {"core_frameworks": rows}
        errors = validate_logic_chain(plan, expected, name)
        if _text(plan.get("terminal_conclusion")) != shared_conclusion:
            errors.append(f"{name} 扣题结论必须与标题合同最终结论完全一致")
        if errors: raise ValueError("；".join(errors))
        mothers.append(_text(plan.get("mother_logic")))
        for row in rows:
            row["logic_chain"] = plan["logic_chain"]["nodes"][str(row["core_framework_id"])]
            if name in {"structure_one", "structure_two"} and (not _text(row.get("core_claim")) or not row.get("evidence_chain")):
                raise ValueError(f"{name}/{row['core_framework_id']} 必须在逻辑链锁定后填写核心内容")
            if name == "structure_three":
                has_content = bool(_text(row.get("core_claim")))
                if has_content and not isinstance(row.get("processing_sources"), list):
                    raise ValueError("structure_three 的非空内容必须提供 processing_sources")
                if not has_content and (row.get("processing_sources") or row.get("evidence_chain")):
                    raise ValueError("structure_three 未命中时内容、原文证据与出处必须同时留空")
                if has_content:
                    source_errors = validate_source_evidence(row)
                    source_errors.extend(validate_case_card_binding(row))
                    if source_errors: raise ValueError(f"structure_three/{row['core_framework_id']}：" + "；".join(source_errors))
        result[name] = plan
    if len(set(mothers)) != 3:
        raise ValueError("三条结构必须采用不同的母逻辑，不能仅换词")
    result["structure_four"] = {"core_frameworks": [dict(row) | {"core_claim": "", "evidence_chain": [], "solution_steps": []} for row in base_rows]}
    keys = ("topic", "benchmark_case_id", "benchmark_path", "benchmark_audit_receipt", "benchmark_sha256", "big_frameworks", "final_copy_only_frameworks", "topic_table_binding")
    payload = {key: handoff.get(key) for key in keys} | {"schema": "copy-structure-v16", "producer": {"agent_id": "xiaochai"}, "title_contract": authored["title_contract"], "structure_four_status": "user-pending", "structures": result}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
