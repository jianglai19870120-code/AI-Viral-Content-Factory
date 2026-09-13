#!/usr/bin/env python3
"""Prepare the immutable big-framework handoff for structure design."""
from __future__ import annotations

import argparse
import json
import re
from collections import OrderedDict
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
from workflow.universal_copy_contract import digest, parse_breakdown, split_row

STRUCTURE_TOTAL_HEADER = ["大框架区块", "编号", "大框架", "小框架", "小框架作用", "小结构原文内容"]


def audited_small_framework_names(path: Path) -> dict[str, str]:
    """Read the original 小框架 labels from the audited structure-total table."""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if split_row(line) == STRUCTURE_TOTAL_HEADER]
    if len(starts) != 1:
        raise ValueError("对标拆解必须且只能有一张结构总表")
    result: dict[str, str] = {}
    index = starts[0] + 2
    while index < len(lines) and lines[index].startswith("|"):
        values = split_row(lines[index])
        if len(values) != len(STRUCTURE_TOTAL_HEADER):
            raise ValueError("结构总表列数错误")
        row = dict(zip(STRUCTURE_TOTAL_HEADER, values))
        small_id, name = row["编号"].strip(), row["小框架"].strip()
        if not small_id or not name or small_id in result:
            raise ValueError("结构总表小框架编号或名称无效")
        result[small_id] = name
        index += 1
    return result


def audited_framework_labels(path: Path) -> dict[str, str]:
    """Use the audited structure-total big-framework family, never a blueprints's safe function alias."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if split_row(line) == STRUCTURE_TOTAL_HEADER), None)
    if start is None:
        raise ValueError("对标拆解缺少结构总表")
    labels: dict[str, str] = {}
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        row = dict(zip(STRUCTURE_TOTAL_HEADER, split_row(line)))
        block, label = row["大框架区块"].strip(), row["大框架"].strip()
        if not block or not label or (block in labels and labels[block] != label):
            raise ValueError("结构总表大框架区块或名称无效")
        labels[block] = label
    return labels


def benchmark_framework(path: Path) -> dict[str, object]:
    """Read ordered big-framework identifiers plus safe downstream function labels."""
    parsed = parse_breakdown(path)
    blocks: OrderedDict[str, dict[str, str]] = OrderedDict()
    blueprint: list[dict[str, str]] = []
    names = audited_small_framework_names(path)
    labels = audited_framework_labels(path)
    for row in parsed["functional_blueprint"]:
        block_id = str(row.get("大框架区块") or "").strip()
        function = str(row.get("大框架功能") or "").strip()
        if not block_id or not function:
            raise ValueError("对标拆解卡缺少大结构编号或功能")
        label = labels.get(block_id, "")
        if not label:
            raise ValueError("结构总表与下游功能蓝图的大框架区块不一致")
        existing = blocks.setdefault(block_id, {"framework_block_id": block_id, "framework_function": function, "framework_label": label})
        if existing["framework_function"] != function:
            raise ValueError(f"对标拆解卡的大结构 {block_id} 功能不一致")
        small_id = str(row.get("小结构编号") or "").strip()
        task = str(row.get("功能任务") or "").strip()
        small_name = names.get(small_id, "")
        if not small_id or not task or not small_name:
            raise ValueError("对标拆解卡缺少小结构编号或功能任务")
        blueprint.append({
            "framework_block_id": block_id,
            "framework_function": function,
            "small_structure_id": small_id,
            "small_framework_name": small_name,
            "small_structure_function": display_small_function(task),
            "small_structure_detail": task,
            "input_relation": str(row.get("前置推进") or "").strip(),
            "output_relation": str(row.get("后续交付") or "").strip(),
        })
    if not blocks:
        raise ValueError("对标拆解卡缺少大结构")
    if set(names) != {str(row["small_structure_id"]) for row in blueprint}:
        raise ValueError("结构总表与下游功能蓝图的小结构编号不一致")
    return {"framework_blocks": list(blocks.values()), "small_structure_blueprint": blueprint}


def display_small_function(detail: str) -> str:
    """Return the safe functional label, not the benchmark sentence or prose detail."""
    mapping = (("替读者", "读者代入追问"), ("建立全文", "观点提出"), ("预告下文", "路径预告"), ("预告接下来", "路径预告"), ("结束开场", "承接转场"),
               ("切入需要", "承接转场"), ("深层原因", "错误机制说明"), ("多重代价", "真实损失"),
               ("结果定性", "观点回扣"), ("可替换情境", "对照示范"), ("回扣到本段", "观点回扣"),
               ("心理压力", "真实损失"), ("连续自问", "读者代入追问"), ("界定需要", "误区定义"),
               ("界定第二", "误区定义"), ("将常见判断", "常识反转"), ("推翻错误", "常识反转"), ("新判断在行动", "正确路径机制"),
               ("呈现读者", "理解阻力承认"), ("对照结果", "对照示范"), ("跨主题", "立场强化"),
               ("阻碍推进", "错误机制说明"), ("反向行动", "正确路径机制"), ("付出的代价", "后果加压"),
               ("改变后", "阶段收获归纳"), ("条件依赖", "脆弱机制说明"), ("两种可替换路径", "对照机制说明"), ("依赖模式", "依赖后果加压"),
               ("否定极端", "路径纠偏"), ("限定启动", "执行边界"), ("转入方案", "承接转场"), ("限定本段", "方案范围限定"),
               ("命名本段", "方法提出"), ("完成方案链中的第一", "第一步"), ("完成方案链中的第二", "第二步"), ("完成方案链中的第三", "第三步"),
               ("首个可启动动作", "第一步"), ("动作启动后", "结果验证"), ("回收全文", "观点回扣"), ("回收前述", "观点回扣"), ("立即开始", "明确行动引导"))
    return next((label for marker, label in mapping if marker in detail), detail)


# These are *content functions*, not content-type routing keys.  The first six
# map one-to-one to the formal asset families; the remaining labels make a
# benchmark's audited framework usable without pretending it is a different
# type of topic.
FORMAL_TYPES = {
    "观点", "痛点", "误区", "解决方案", "案例", "推荐理由",
    "方法", "原因", "购买理由", "证据", "反常识", "对比", "结果", "行动建议",
}

ASSET_TYPE_BY_FORMAL = {
    "观点": "观点", "痛点": "痛点", "误区": "误区", "解决方案": "解决方案",
    "案例": "案例", "推荐理由": "推荐理由", "方法": "解决方案",
    "行动建议": "解决方案", "购买理由": "推荐理由", "原因": "观点",
    "证据": "观点", "反常识": "观点", "对比": "观点", "结果": "观点",
}


def formal_framework_type(label: str) -> str | None:
    """Return a formal family only for an audited *formal* big-framework label.

    Labels such as 开场引导、承接转场、观点回扣、收束行动 are support
    segments, not disguised 观点.  We deliberately accept only an exact family
    name or its numbered form (例如“误区一”“解决方案2”).
    """
    value = re.split(r"[：:]", label.strip())[-1].strip()
    for formal in FORMAL_TYPES:
        suffix = value.removeprefix(formal)
        if value == formal or (suffix and all(char in "一二三四五六七八九十0123456789" for char in suffix)):
            return formal
    return None


def structure_segments(framework: dict[str, object]) -> list[dict[str, object]]:
    """Create the complete ordered backend map, including support-only blocks."""
    rows = framework["small_structure_blueprint"]
    segments: list[dict[str, object]] = []
    for block in framework["framework_blocks"]:
        block_id = str(block["framework_block_id"])
        label = str(block["framework_label"])
        block_rows = [row for row in rows if row["framework_block_id"] == block_id]
        segments.append({
            "framework_block_id": block_id,
            "framework_label": label,
            "formal_framework_type": formal_framework_type(label),
            "small_structures": [{
                "small_structure_id": row["small_structure_id"],
                "small_framework_name": row["small_framework_name"],
                "small_structure_function": row["small_structure_function"],
                "small_structure_detail": row["small_structure_detail"],
                "input_relation": row["input_relation"],
                "output_relation": row["output_relation"],
            } for row in block_rows],
        })
    expected = [row["small_structure_id"] for row in rows]
    actual = [small["small_structure_id"] for segment in segments for small in segment["small_structures"]]
    if actual != expected or len(actual) != len(set(actual)):
        raise ValueError("structure_segments 必须完整、连续且不重复覆盖全部小结构")
    return segments


def core_frameworks(segments: list[dict[str, object]]) -> list[dict[str, object]]:
    """Expose one editable row per formal big framework.

    Small structures remain exclusively in ``structure_segments`` as the
    downstream final-copy blueprint.  They must never become structure-stage
    writing rows again.
    """
    result: list[dict[str, object]] = []
    for segment in segments:
        formal = segment["formal_framework_type"]
        if formal is None:
            continue
        smalls = segment["small_structures"]
        result.append({
            "core_framework_id": f"CF-{segment['framework_block_id']}",
            "framework_block_id": segment["framework_block_id"],
            "framework_label": segment["framework_label"],
            "formal_framework_type": formal,
            "asset_framework_type": ASSET_TYPE_BY_FORMAL[formal],
            "downstream_small_structure_ids": [item["small_structure_id"] for item in smalls],
        })
    return result


TOPIC_STRUCTURE_TYPES = {"binary_parallel", "causal_mechanism", "counterintuitive_correction", "problem_solution_steps", "comparison_choice", "object_scene_result"}


def load_topic_analysis(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("topic analysis 必须是对象")
    structure_types = raw.get("topic_structure_types")
    values = raw.get("topic_propositions")
    if not isinstance(structure_types, list) or not structure_types or not set(structure_types).issubset(TOPIC_STRUCTURE_TYPES):
        raise ValueError("topic_structure_types 必须包含一个或多个已支持的选题命题结构类型")
    if not isinstance(values, list) or not 2 <= len(values) <= 5:
        raise ValueError("topic_propositions 必须是 2-5 条命题的 JSON 数组")
    required = ("proposition_id", "structure_types", "original_phrase", "canonical_proposition", "key_entities", "key_actions", "key_results", "constraints", "must_answer_question", "accepted_expressions")
    ids: set[str] = set()
    for item in values:
        if not isinstance(item, dict) or any(not item.get(key) for key in required):
            raise ValueError("每条命题必须含 ID、结构类型、原始短语、规范命题、实体/动作/结果、限制条件、必答问题和明确表达")
        identifier = str(item["proposition_id"])
        if identifier in ids:
            raise ValueError("topic_propositions 的 proposition_id 必须唯一")
        ids.add(identifier)
        if not isinstance(item["accepted_expressions"], list) or not all(isinstance(x, str) and x.strip() for x in item["accepted_expressions"]):
            raise ValueError("accepted_expressions 必须是可在人读内容中核对的非空短语列表")
        if not isinstance(item["structure_types"], list) or not item["structure_types"] or not set(item["structure_types"]).issubset(TOPIC_STRUCTURE_TYPES):
            raise ValueError("每条命题必须关联一个或多个已识别的结构类型")
    return {"topic_structure_types": structure_types, "topic_propositions": values}


def framework_content_contracts(frameworks: list[dict[str, object]]) -> list[dict[str, object]]:
    """Create the hidden V12 function contract for each editable framework.

    It intentionally describes *what must be established*, rather than giving
    prose to imitate.  The authoring agent may change wording, but cannot turn
    a case into a generic opinion or a misconception into a one-line slogan.
    """
    contracts: list[dict[str, object]] = []
    case_count = 0
    templates: dict[str, dict[str, object]] = {
        "误区": {
            "content_function": "完整拆解一个不同的错误判断",
            "must_answer": "错在哪里、读者为何会相信、漏洞或机制是什么、真正变量是什么、继续相信的后果是什么？",
            "required_logic_roles": ["错误认知", "为何相信", "漏洞或机制", "真正变量", "后果"],
            "min_evidence_points": 3, "max_evidence_points": 4,
            "allowed_evidence_methods": ["机制解释", "对照", "反问", "因果推演", "情境"],
        },
        "痛点": {
            "content_function": "还原读者正在承受的具体障碍",
            "must_answer": "发生在哪个场景、卡在哪里、付出什么代价、感受如何、真正需要被解决什么？",
            "required_logic_roles": ["场景", "障碍", "代价", "情绪", "深层需求"],
            "min_evidence_points": 3, "max_evidence_points": 4,
            "allowed_evidence_methods": ["情境", "结果", "因果推演", "反问"],
        },
        "解决方案": {
            "content_function": "给出最少充分、可核验的处理动作",
            "must_answer": "先处理什么、具体怎么做、适用条件或对象是什么、怎样知道动作有效？",
            "required_logic_roles": ["问题对象", "动作", "条件或对象", "验证标准"],
            "min_evidence_points": 1, "max_evidence_points": 5,
            "allowed_evidence_methods": ["步骤验证", "条件限定", "结果", "对照"],
        },
        "观点": {
            "content_function": "建立可被后文证明的判断",
            "must_answer": "核心判断是什么、依据哪条因果或条件、为何它比直觉判断更成立？",
            "required_logic_roles": ["判断依据", "因果或条件", "反直觉校正"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["机制解释", "因果推演", "对照", "反问"],
        },
        "推荐理由": {
            "content_function": "证明对象为什么值得被选择",
            "must_answer": "目标读者的成本或困境是什么、对象提供什么路径、为什么此刻值得行动？",
            "required_logic_roles": ["读者成本", "对象路径", "选择理由", "行动时机"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["对照", "结果", "机制解释", "情境"],
        },
        "方法": {
            "content_function": "说明一套方法如何运行",
            "must_answer": "方法解决什么、关键动作和顺序是什么、怎样检验是否真的奏效？",
            "required_logic_roles": ["问题对象", "关键动作", "顺序或条件", "验证标准"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["步骤验证", "机制解释", "条件限定"],
        },
        "原因": {
            "content_function": "定位结果背后的真正变量",
            "must_answer": "表面原因是什么、真正变量是什么、变量如何造成结果？",
            "required_logic_roles": ["表面解释", "真正变量", "因果链"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["机制解释", "因果推演", "对照"],
        },
        "购买理由": {
            "content_function": "完成成本到选择的购买论证",
            "must_answer": "不解决的成本、期望结果、自行解决成本、对象路径和为什么现在选择？",
            "required_logic_roles": ["不作为成本", "期望结果", "自行成本", "对象路径", "行动时机"],
            "min_evidence_points": 3, "max_evidence_points": 4,
            "allowed_evidence_methods": ["对照", "因果推演", "结果", "情境"],
        },
        "证据": {
            "content_function": "用可核验依据支持前述判断",
            "must_answer": "要证明什么、依据来自哪里、依据如何导向结论？",
            "required_logic_roles": ["待证判断", "依据", "推理连接"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["证据", "对照", "因果推演"],
        },
        "反常识": {
            "content_function": "推翻直觉并建立更准确判断",
            "must_answer": "常见直觉是什么、它为什么不成立、替代判断依据什么成立？",
            "required_logic_roles": ["常见直觉", "直觉漏洞", "替代判断", "成立依据"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["对照", "反问", "机制解释", "因果推演"],
        },
        "对比": {
            "content_function": "比较两种路径并指出差异变量",
            "must_answer": "两种路径各做什么、各自造成什么结果、关键差异是什么？",
            "required_logic_roles": ["路径A", "路径B", "结果差异", "差异变量"],
            "min_evidence_points": 3, "max_evidence_points": 4,
            "allowed_evidence_methods": ["对照", "结果", "机制解释"],
        },
        "结果": {
            "content_function": "把行动或机制收束为可理解的结果",
            "must_answer": "结果是什么、由什么造成、它对下一步意味着什么？",
            "required_logic_roles": ["结果", "成因", "下一步含义"],
            "min_evidence_points": 2, "max_evidence_points": 4,
            "allowed_evidence_methods": ["结果", "因果推演", "对照"],
        },
        "行动建议": {
            "content_function": "把判断转为可立即执行的建议",
            "must_answer": "谁在什么条件下先做什么、避免什么、如何确认完成？",
            "required_logic_roles": ["适用对象", "首个动作", "禁止或边界", "完成标准"],
            "min_evidence_points": 1, "max_evidence_points": 5,
            "allowed_evidence_methods": ["步骤验证", "条件限定", "结果"],
        },
    }
    for index, framework in enumerate(frameworks):
        formal = str(framework["formal_framework_type"])
        if formal == "案例":
            case_count += 1
            if case_count == 1:
                position, function, required = (
                    "开场场景", "用熟悉场景和异常结果暴露问题",
                    ["具体场景", "异常结果", "问题暴露"],
                )
            elif case_count == 2:
                position, function, required = (
                    "对比案例", "并置两种路径，以结果差异说明关键变量",
                    ["路径A", "路径B", "结果差异", "关键变量"],
                )
            else:
                position, function, required = (
                    "论证案例", "用具体事件、结果和结论支撑本节点判断",
                    ["具体事件", "结果", "结论关联"],
                )
            template = {
                "content_function": function,
                "must_answer": "具体发生了什么、出现了什么异常或结果、它暴露或证明了什么？",
                "required_logic_roles": required,
                "min_evidence_points": 2, "max_evidence_points": 4,
                "allowed_evidence_methods": ["情境", "对照", "结果", "因果推演"],
            }
        else:
            position = "正文论证节点" if index else "首个正文节点"
            template = templates[formal]
        contracts.append({
            "content_contract_id": f"FC-{framework['core_framework_id']}",
            "core_framework_id": framework["core_framework_id"],
            "framework_block_id": framework["framework_block_id"],
            "framework_label": framework["framework_label"],
            "formal_framework_type": formal,
            "asset_framework_type": framework["asset_framework_type"],
            "position_role": position,
            "non_repeat_target": f"{framework['framework_label']}：只处理本节点的{template['content_function']}，不得与其他节点复用对象或结论。",
            **template,
        })
    return contracts


def answer_obligations(frameworks: list[dict[str, object]], propositions: list[dict[str, object]], contracts: list[dict[str, object]]) -> list[dict[str, object]]:
    proposition_ids = [str(item["proposition_id"]) for item in propositions]
    by_framework = {str(item["core_framework_id"]): item for item in contracts}
    return [{
        "obligation_id": f"OB-{framework['core_framework_id']}",
        "core_framework_id": framework["core_framework_id"],
        "framework_block_id": framework["framework_block_id"],
        "framework_label": framework["framework_label"],
        "eligible_proposition_ids": proposition_ids,
        "obligation": f"{by_framework[str(framework['core_framework_id'])]['must_answer']} 同时直接回应至少一条选题命题及其必答问题，不得泛化为主题口号。",
    } for framework in frameworks]


def build_handoff(*, topic: str, benchmark_id: str, topic_analysis: dict[str, object], topic_analysis_path: Path, topic_table_binding: dict[str, object] | None = None) -> dict[str, object]:
    """Build the immutable V12 payload for direct or topic-table invocation."""
    try:
        case = approved_case(benchmark_id)
        benchmark = case["breakdownPath"]
        framework = benchmark_framework(benchmark)
    except ValueError as exc:
        raise ValueError(f"对标案例不可调用：{exc}") from exc
    processing_index = ROOT / "04_数据中心" / "03_查询索引" / "module-function-index.jsonl"
    pain_angle_index = ROOT / "04_数据中心" / "03_查询索引" / "video-pain-angle-index.jsonl"
    formal_asset_root = ROOT / "02_资产中心" / "02_处理库"
    segments = structure_segments(framework)
    cores = core_frameworks(segments)
    contracts = framework_content_contracts(cores)
    payload = {
        "schema": "copy-structure-handoff-v12",
        "topic": topic,
        "benchmark_case_id": benchmark_id,
        "benchmark_path": str(benchmark.resolve()),
        "benchmark_sha256": digest(benchmark),
        "benchmark_audit_receipt": str(case["auditPath"].resolve()),
        "benchmark_framework": framework,
        "benchmark_framework_sha256": digest(benchmark),
        "structure_segments": segments,
        "topic_structure_types": topic_analysis["topic_structure_types"],
        "topic_propositions": topic_analysis["topic_propositions"],
        "topic_analysis_sha256": digest(topic_analysis_path),
        "core_frameworks": cores,
        "framework_content_contracts": contracts,
        "framework_answer_obligations": answer_obligations(cores, topic_analysis["topic_propositions"], contracts),
        "processing_index": str(processing_index.resolve()),
        "processing_index_sha256": digest(processing_index),
        "pain_angle_index": str(pain_angle_index.resolve()),
        "pain_angle_index_sha256": digest(pain_angle_index),
        "formal_asset_root": str(formal_asset_root.resolve()),
        "case_asset_root": str((formal_asset_root / "05_案例_内容模块（会员专享）").resolve()),
        "allowed_asset_frameworks": ["观点", "痛点", "误区", "解决方案", "案例", "推荐理由"],
        "route_design_requirements": {
            "required_fields": ["mother_proposition", "critical_target", "causal_mechanism", "evidence_strategy", "solution_direction"],
            "pairwise_independence": "三条路线的角度指纹必须至少有三个字段实质不同；不得只换词、换案例、调整顺序或更换论据手法。",
            "framework_order_rule": "三条路线均保持锁定大框架顺序；顺序相同不代表论证路线可以相同。"
        },
        "structure_generation_rule": "结构一至四只按正式核心大框架生成。结构一、二每行必须写一句 core_claim 和 2-4 条 evidence_chain 短论据；每条标注 logic_roles 与 evidence_method，联合覆盖该行 content contract。结构三仅按 asset_framework_type 检索正式库：命中时绑定 1-N 个资产并完成同样的论据链；无相关资产时整行留空并记录缺口。结构四按同一大框架序列留空，绝不自动覆盖。",
        "downstream_rule": "全部小结构只保存在 structure_segments。正文阶段让每个正式大框架的冻结意图覆盖其全部下游小结构，再由小结构功能、前后关系和逐句复刻画像控制推进与表达；support-only 段继承相邻正式大框架意图，不得重新检索资产。",
    }
    if topic_table_binding is not None:
        payload["topic_table_binding"] = topic_table_binding
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="创建按对标大结构生成文案结构的 handoff")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--benchmark-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    # 新链路只有 V16。历史版本只可查阅，不能再作为新的 handoff 输出。
    args = parser.parse_args()
    try:
        from structure_v16 import build_handoff_v16
        from workflow.topic_structure_releases import handoff_binding, resolve_selected_topic
        selected = resolve_selected_topic(args.topic, benchmark_case_id=args.benchmark_id)
        payload = build_handoff_v16(topic=args.topic, benchmark_id=args.benchmark_id, topic_table_binding=handoff_binding(selected))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "prepared", "schema": payload["schema"], "frameworkBlocks": len(payload["big_frameworks"]), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
