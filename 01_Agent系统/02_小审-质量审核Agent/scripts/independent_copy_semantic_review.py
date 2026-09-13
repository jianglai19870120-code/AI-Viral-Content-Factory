#!/usr/bin/env python3
"""Create and validate non-self-signed semantic reviews for universal copy assets."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def structure_review_ids(artifact: dict[str, Any]) -> list[str]:
    plans = artifact.get("structures") if isinstance(artifact.get("structures"), dict) else {}
    result: list[str] = []
    names = ("structure_one", "structure_two", "structure_three") if artifact.get("schema") in {"copy-structure-v13", "copy-structure-v14", "copy-structure-v15"} else ("structure_one", "structure_two", "structure_three", "structure_four")
    for name in names:
        plan = plans.get(name) if isinstance(plans.get(name), dict) else {}
        frameworks = plan.get("core_frameworks") if isinstance(plan.get("core_frameworks"), list) else []
        for framework in frameworks:
            if isinstance(framework, dict) and (artifact.get("schema") not in {"copy-structure-v13", "copy-structure-v14", "copy-structure-v15"} or str(framework.get("core_claim") or "").strip()):
                result.append(f"{name}/{framework.get('core_framework_id') or ''}")
    return result


def prepare(kind: str, plan: Path, candidate: Path, target: Path) -> Path:
    source = json.loads(plan.read_text(encoding="utf-8"))
    artifact = json.loads(candidate.read_text(encoding="utf-8"))
    if kind == "copy-structure" and artifact.get("schema") in {"copy-structure-v15", "copy-structure-v16"}:
        rows = structure_review_ids(artifact)
        payload = {
            "schema": "independent-copy-semantic-review-v16" if artifact.get("schema") == "copy-structure-v16" else "independent-copy-semantic-review-v15", "kind": kind, "status": "needs-review",
            "reviewer": {"reviewer_id": "", "independence_attestation": ""}, "plan_path": str(plan.resolve()), "candidate_path": str(candidate.resolve()),
            "plan_sha256": digest(plan), "candidate_sha256": digest(candidate), "created_at": datetime.now(timezone.utc).isoformat(),
            "scorecard": {key: None for key in ["选题兑现度", "内容具体度", "节点独立性", "逻辑推进", "框架功能正确", "论点论据匹配", "口播可扩写性"]}, "total_score": None,
            "vetoes": {key: False for key in ["标题承诺错位", "相邻节点无必然承接", "可替换并列知识点", "抽象案例", "伪多版本", "无资产伪装结构三", "编造可核验事实"]},
            "summary": "", "item_reviews": [{"id": row, "verdict": "needs-review", "reasoning": "", "evidence": []} for row in rows],
            "logic_chain_reviews": [{"structure": name, "verdict": "needs-review", "reasoning": "", "title_fulfillment_evidence": "", "dependency_evidence": "", "removal_impact_evidence": ""} for name in ("structure_one", "structure_two", "structure_three")],
        }
        if artifact.get("schema") == "copy-structure-v16":
            payload["source_evidence_reviews"] = [{"id": row, "verdict": "needs-review", "reasoning": "", "source_native_evidence": "", "type_specific_evidence": ""} for row in rows if row.startswith("structure_three/")]
        target.parent.mkdir(parents=True, exist_ok=True); target.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n",encoding="utf-8"); return target
    if kind == "copy-structure" and artifact.get("schema") in {"copy-structure-v13", "copy-structure-v14"}:
        rows = structure_review_ids(artifact)
        payload = {
            "schema": "independent-copy-semantic-review-v13", "kind": kind, "status": "needs-review",
            "reviewer": {"reviewer_id": "", "independence_attestation": ""},
            "plan_path": str(plan.resolve()), "candidate_path": str(candidate.resolve()),
            "plan_sha256": digest(plan), "candidate_sha256": digest(candidate), "created_at": datetime.now(timezone.utc).isoformat(),
            "scorecard": {key: None for key in ["选题兑现度", "内容具体度", "节点独立性", "逻辑推进", "框架功能正确", "论点论据匹配", "口播可扩写性"]},
            "total_score": None,
            "vetoes": {key: False for key in ["标题承诺错位", "三点以上同一观点", "抽象案例", "伪多版本", "无资产伪装结构三", "编造可核验事实"]},
            "summary": "", "item_reviews": [{"id": row, "verdict": "needs-review", "reasoning": "", "evidence": []} for row in rows],
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target
    if kind == "copy-structure":
        rows = structure_review_ids(artifact)
        item_key, criteria = "id", [
            "通用选题结构类型与命题完整性",
            "命题回答义务与逐大框架语义锚定",
            "三条路线核心问题判断因果机制说服路径与落点两两独立",
            "逐大框架核心论点清晰且核心论据直接证明论点",
            "论据手法适配框架职责且不是换手法伪装路线差异",
            "结构三逐大框架分类检索、论据来源与命题支撑",
            "后台小结构完整性、结构四双项空白状态与正文桥接",
        ]
    elif kind == "final-copy":
        rows = artifact.get("unit_mappings") if isinstance(artifact.get("unit_mappings"), list) else []
        item_key, criteria = "unit_no", ["结构与推进保持", "内容与主题意图符合", "表达复刻约束符合"]
    else:
        raise ValueError("kind 必须为 copy-structure 或 final-copy")
    payload = {
        "schema": "independent-copy-semantic-review-v1", "kind": kind, "status": "needs-review",
        "reviewer": {"reviewer_id": "", "independence_attestation": ""},
        "plan_path": str(plan.resolve()), "candidate_path": str(candidate.resolve()),
        "plan_sha256": digest(plan), "candidate_sha256": digest(candidate),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checks": [{"id": item, "status": "needs-review", "summary": "", "evidence": []} for item in criteria],
        "item_reviews": ([{"id": row, "verdict": "needs-review", "reasoning": "", "evidence": []} for row in rows]
                         if kind == "copy-structure" else [{"id": str(row.get(item_key) or ""), "verdict": "needs-review", "reasoning": "", "evidence": []} for row in rows if isinstance(row, dict)]),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def validate(kind: str, plan: Path, candidate: Path, review_path: Path) -> list[str]:
    errors: list[str] = []
    review = json.loads(review_path.read_text(encoding="utf-8"))
    artifact = json.loads(candidate.read_text(encoding="utf-8"))
    if kind == "copy-structure" and artifact.get("schema") in {"copy-structure-v15", "copy-structure-v16"}:
        expected=set(structure_review_ids(artifact))
        version="v16" if artifact.get("schema")=="copy-structure-v16" else "v15"
        if review.get("schema")!=f"independent-copy-semantic-review-{version}" or review.get("kind")!=kind or review.get("status")!="completed":return [f"{version.upper()} 独立语义审核类型或状态错误"]
        if review.get("plan_sha256")!=digest(plan) or review.get("candidate_sha256")!=digest(candidate):errors.append("V15 独立语义审核未绑定当前计划与候选哈希")
        reviewer=review.get("reviewer") if isinstance(review.get("reviewer"),dict) else {}
        if len(str(reviewer.get("reviewer_id") or "").strip())<3 or len(str(reviewer.get("independence_attestation") or "").strip())<16 or reviewer.get("reviewer_id")==(artifact.get("producer") or {}).get("agent_id"):errors.append("V15 独立语义审核的审稿人或独立性声明不合格")
        required=["选题兑现度", "内容具体度", "节点独立性", "逻辑推进", "框架功能正确", "论点论据匹配", "口播可扩写性"]; scorecard=review.get("scorecard") if isinstance(review.get("scorecard"),dict) else {}; scores=[scorecard.get(key) for key in required]
        if set(scorecard)!=set(required) or any(not isinstance(x,(int,float)) or x<0 or x>100 for x in scores):errors.append("V15 语义评分必须完整覆盖七项且每项为 0-100")
        elif review.get("total_score")!=round(sum(scores)/len(scores),1) or round(sum(scores)/len(scores),1)<80:errors.append("V15 语义总分必须等于七项平均分且不低于 80")
        vetoes=review.get("vetoes") if isinstance(review.get("vetoes"),dict) else {}; required_vetoes={"标题承诺错位", "相邻节点无必然承接", "可替换并列知识点", "抽象案例", "伪多版本", "无资产伪装结构三", "编造可核验事实"}
        if set(vetoes)!=required_vetoes or any(x is not False for x in vetoes.values()):errors.append("V15 一票否决项必须完整填写且全部为 false")
        reviews=review.get("item_reviews") if isinstance(review.get("item_reviews"),list) else []
        if {str(x.get("id") or "") for x in reviews if isinstance(x,dict)}!=expected or any(x.get("verdict")!="passed" or len(str(x.get("reasoning") or "").strip())<12 or not x.get("evidence") for x in reviews if isinstance(x,dict)):errors.append("V15 语义审核未逐节点给出合格判断和证据")
        chain=review.get("logic_chain_reviews") if isinstance(review.get("logic_chain_reviews"),list) else []; names={"structure_one","structure_two","structure_three"}
        if {str(x.get("structure") or "") for x in chain if isinstance(x,dict)}!=names or any(x.get("verdict")!="passed" or len(str(x.get("reasoning") or "").strip())<12 or not all(str(x.get(k) or "").strip() for k in ("title_fulfillment_evidence","dependency_evidence","removal_impact_evidence")) for x in chain if isinstance(x,dict)):errors.append("V15 母逻辑审核必须逐结构证明扣题、承接与删段断裂")
        if version == "v16":
            expected_sources={item for item in expected if item.startswith("structure_three/")}; source_reviews=review.get("source_evidence_reviews") if isinstance(review.get("source_evidence_reviews"),list) else []
            if {str(x.get("id") or "") for x in source_reviews if isinstance(x,dict)}!=expected_sources or any(x.get("verdict")!="passed" or len(str(x.get("reasoning") or "").strip())<12 or not str(x.get("source_native_evidence") or "").strip() or not str(x.get("type_specific_evidence") or "").strip() for x in source_reviews if isinstance(x,dict)):
                errors.append("V16 结构三原文证据审核未逐节点证明原文提取和类型任务")
        return errors
    if kind == "copy-structure" and artifact.get("schema") in {"copy-structure-v13", "copy-structure-v14"}:
        expected = set(structure_review_ids(artifact))
        if review.get("schema") != "independent-copy-semantic-review-v13" or review.get("kind") != kind or review.get("status") != "completed":
            return ["V13 独立语义审核类型或状态错误"]
        if review.get("plan_sha256") != digest(plan) or review.get("candidate_sha256") != digest(candidate):
            errors.append("V13 独立语义审核未绑定当前计划与候选哈希")
        reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), dict) else {}
        if len(str(reviewer.get("reviewer_id") or "").strip()) < 3 or len(str(reviewer.get("independence_attestation") or "").strip()) < 16 or reviewer.get("reviewer_id") == (artifact.get("producer") or {}).get("agent_id"):
            errors.append("V13 独立语义审核的审稿人或独立性声明不合格")
        required = ["选题兑现度", "内容具体度", "节点独立性", "逻辑推进", "框架功能正确", "论点论据匹配", "口播可扩写性"]
        scorecard = review.get("scorecard") if isinstance(review.get("scorecard"), dict) else {}
        scores = [scorecard.get(key) for key in required]
        if set(scorecard) != set(required) or any(not isinstance(value, (int, float)) or value < 0 or value > 100 for value in scores):
            errors.append("V13 语义评分必须完整覆盖七项且每项为 0-100")
        else:
            expected_total = round(sum(scores) / len(scores), 1)
            if review.get("total_score") != expected_total or expected_total < 80:
                errors.append("V13 语义总分必须等于七项平均分且不低于 80")
        vetoes = review.get("vetoes") if isinstance(review.get("vetoes"), dict) else {}
        required_vetoes = {"标题承诺错位", "三点以上同一观点", "抽象案例", "伪多版本", "无资产伪装结构三", "编造可核验事实"}
        if set(vetoes) != required_vetoes or any(value is not False for value in vetoes.values()):
            errors.append("V13 一票否决项必须完整填写且全部为 false")
        reviews = review.get("item_reviews") if isinstance(review.get("item_reviews"), list) else []
        if {str(item.get("id") or "") for item in reviews if isinstance(item, dict)} != expected or any(item.get("verdict") != "passed" or len(str(item.get("reasoning") or "").strip()) < 12 or not item.get("evidence") for item in reviews if isinstance(item, dict)):
            errors.append("V13 语义审核未逐项给出合格判断和证据")
        return errors
    if review.get("schema") != "independent-copy-semantic-review-v1" or review.get("kind") != kind or review.get("status") != "completed":
        errors.append("独立语义审核类型或状态错误")
    if review.get("plan_sha256") != digest(plan) or review.get("candidate_sha256") != digest(candidate):
        errors.append("独立语义审核未绑定当前计划与候选哈希")
    reviewer = review.get("reviewer") if isinstance(review.get("reviewer"), dict) else {}
    producer = artifact.get("producer") if isinstance(artifact.get("producer"), dict) else {}
    if len(str(reviewer.get("reviewer_id") or "").strip()) < 3 or len(str(reviewer.get("independence_attestation") or "").strip()) < 16:
        errors.append("独立语义审核缺少审稿人或独立性声明")
    if producer.get("agent_id") and producer.get("agent_id") == reviewer.get("reviewer_id"):
        errors.append("独立审稿人不得与执行人相同")
    checks = review.get("checks") if isinstance(review.get("checks"), list) else []
    if not checks or any(item.get("status") != "passed" or len(str(item.get("summary") or "").strip()) < 12 or not item.get("evidence") for item in checks if isinstance(item, dict)):
        errors.append("独立语义审核检查项缺少通过结论或可定位证据")
    if kind == "copy-structure":
        expected_ids = set(structure_review_ids(artifact))
    else:
        expected_rows = artifact.get("unit_mappings")
        expected_ids = {str(row.get("unit_no") or "") for row in expected_rows if isinstance(row, dict)} if isinstance(expected_rows, list) else set()
    reviews = review.get("item_reviews") if isinstance(review.get("item_reviews"), list) else []
    review_ids = {str(item.get("id") or "") for item in reviews if isinstance(item, dict)}
    if review_ids != expected_ids:
        errors.append("独立语义审核未逐项覆盖当前候选")
    elif any(item.get("verdict") != "passed" or len(str(item.get("reasoning") or "").strip()) < 12 or not item.get("evidence") for item in reviews if isinstance(item, dict)):
        errors.append("独立语义审核逐项判断或证据不足")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="创建通用文案独立语义审稿请求")
    parser.add_argument("--kind", choices=["copy-structure", "final-copy"], required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    target = prepare(args.kind, args.plan.resolve(), args.candidate.resolve(), args.target.resolve())
    print(json.dumps({"status": "needs-review", "review": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
