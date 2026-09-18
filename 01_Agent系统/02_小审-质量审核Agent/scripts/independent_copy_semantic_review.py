#!/usr/bin/env python3
"""Independent V19 structure review generated from the V3 contract."""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from workflow.writing_contract import guidance_snapshot, resolve_contract, rule_ids, rules_for, validate_guidance_snapshot

def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def card_ids(candidate: dict) -> list[str]:
    found=[]
    for name in ("structure_one", "structure_two", "structure_three"):
        rows=(((candidate.get("structures") or {}).get(name) or {}).get("core_frameworks") or [])
        for framework in rows:
            for card in framework.get("small_framework_cards", []) if isinstance(framework, dict) else []:
                if isinstance(card, dict) and str(card.get("content") or "").strip(): found.append(f"{name}/{framework.get('core_framework_id') or ''}/{card.get('small_framework_id') or ''}")
    return found

def active(plan: Path, candidate: Path) -> tuple[dict, dict, dict, list[str]]:
    handoff=json.loads(plan.read_text(encoding="utf-8")); artifact=json.loads(candidate.read_text(encoding="utf-8"))
    if (handoff.get("schema"), artifact.get("schema")) != ("copy-structure-handoff-v19", "copy-structure-v19"): raise ValueError("独立结构审核只接受 V19 handoff/candidate")
    binding=artifact.get("writing_contract") if isinstance(artifact.get("writing_contract"),dict) else {}; resolve_contract(binding); rules=rule_ids(binding,"structure")
    if handoff.get("writing_contract") != binding or handoff.get("writing_contract_rule_ids") != rules or artifact.get("writing_contract_rule_ids") != rules: raise ValueError("V19 结构候选未完整锁定 V3 合同及规则 ID")
    validate_guidance_snapshot(handoff.get("writing_contract_guidance_snapshot"), binding, "structure")
    validate_guidance_snapshot(artifact.get("writing_contract_guidance_snapshot"), binding, "structure")
    return handoff, artifact, binding, rules

def prepare(kind: str, plan: Path, candidate: Path, target: Path) -> Path:
    if kind != "copy-structure": raise ValueError("当前独立语义审核只服务 V19 文案结构")
    _, artifact, binding, rules=active(plan,candidate)
    snapshot=guidance_snapshot(binding,"structure"); by_id={rule["id"]:rule for rule in snapshot["rules"]}
    payload={"schema":"independent-copy-semantic-review-v19","kind":kind,"status":"needs-review","reviewer":{"reviewer_id":"","independence_attestation":""},"plan_path":str(plan.resolve()),"candidate_path":str(candidate.resolve()),"plan_sha256":digest(plan),"candidate_sha256":digest(candidate),"created_at":datetime.now(timezone.utc).isoformat(),"writing_contract":binding,"writing_contract_rule_ids":rules,"writing_contract_guidance_snapshot":snapshot,"contract_checks":[{"id":key,"source_anchors":by_id[key]["source_anchors"],"rule_text":by_id[key]["directive"],"original_guidance":by_id[key]["original_guidance"],"status":"needs-review","summary":"","evidence":[{"item_id":"","candidate_quote":"","reasoning":""}]} for key in rules],"item_reviews":[{"id":key,"verdict":"needs-review","reasoning":"","candidate_quote":"","source_content_quote":"","specificness_evidence":"","evidence":[]} for key in card_ids(artifact)],"route_comparison_reviews":[{"pair":key,"verdict":"needs-review","reader_entry_evidence":"","reasoning_path_evidence":"","delivery_form_evidence":""} for key in ("structure_one/structure_two","structure_one/structure_three","structure_two/structure_three")]}
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");return target

def validate(kind: str, plan: Path, candidate: Path, review_path: Path) -> list[str]:
    try: _, artifact, binding, rules=active(plan,candidate); review=json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc: return [f"V19 独立语义审核不可验证：{exc}"]
    errors=[]; expected_cards=set(card_ids(artifact)); expected_rules=set(rules)
    if review.get("schema")!="independent-copy-semantic-review-v19" or review.get("kind")!=kind or review.get("status")!="completed": return ["V19 独立语义审核类型或状态错误"]
    if review.get("plan_sha256")!=digest(plan) or review.get("candidate_sha256")!=digest(candidate) or review.get("writing_contract")!=binding or review.get("writing_contract_rule_ids")!=rules: errors.append("V19 独立语义审核未锁定当前哈希或 V3 合同")
    try: validate_guidance_snapshot(review.get("writing_contract_guidance_snapshot"), binding, "structure")
    except ValueError: errors.append("V19 独立语义审核未锁定完整口播原文与规则快照")
    reviewer=review.get("reviewer") if isinstance(review.get("reviewer"),dict) else {}
    if len(str(reviewer.get("reviewer_id") or "").strip())<3 or len(str(reviewer.get("independence_attestation") or "").strip())<16 or reviewer.get("reviewer_id")==(artifact.get("producer") or {}).get("agent_id"): errors.append("V19 审稿人或独立性声明不合格")
    checks=review.get("contract_checks") if isinstance(review.get("contract_checks"),list) else []
    by_id={rule["id"]:rule for rule in guidance_snapshot(binding,"structure")["rules"]}
    if {str(item.get("id") or "") for item in checks if isinstance(item,dict)}!=expected_rules or any(item.get("status")!="passed" or item.get("source_anchors")!=by_id.get(str(item.get("id") or ""),{}).get("source_anchors") or item.get("rule_text")!=by_id.get(str(item.get("id") or ""),{}).get("directive") or item.get("original_guidance")!=by_id.get(str(item.get("id") or ""),{}).get("original_guidance") or not str(item.get("summary") or "").strip() or not item.get("evidence") for item in checks if isinstance(item,dict)): errors.append("V3 合同规则未逐条给出完整原文、锚点、结论和证据")
    cards={}
    for name in ("structure_one","structure_two","structure_three"):
        for framework in (((artifact.get("structures") or {}).get(name) or {}).get("core_frameworks") or []):
            for card in framework.get("small_framework_cards",[]) if isinstance(framework,dict) else []: cards[f"{name}/{framework.get('core_framework_id') or ''}/{card.get('small_framework_id') or ''}"]=card
    for check in checks:
        evidence=check.get("evidence") if isinstance(check,dict) else []
        if not isinstance(evidence,list) or not evidence or any(not isinstance(row,dict) or str(row.get("item_id") or "") not in cards or not str(row.get("candidate_quote") or "").strip() or str(row.get("candidate_quote") or "") not in str(cards[str(row.get("item_id"))].get("content") or "") or not str(row.get("reasoning") or "").strip() for row in evidence): errors.append("V19 合同审核证据必须逐规则定位当前候选卡和原句");break
    items=review.get("item_reviews") if isinstance(review.get("item_reviews"),list) else []
    if {str(item.get("id") or "") for item in items if isinstance(item,dict)}!=expected_cards: errors.append("V19 审核未逐卡覆盖全部候选内容")
    for item in items:
        card=cards.get(str(item.get("id") or ""),{}) if isinstance(item,dict) else {}; coverage=card.get("source_coverage") if isinstance(card.get("source_coverage"),dict) else {}
        if not isinstance(item,dict) or item.get("verdict")!="passed" or len(str(item.get("reasoning") or "").strip())<12 or not str(item.get("candidate_quote") or "").strip() or str(item.get("candidate_quote") or "") not in str(card.get("content") or "") or not str(item.get("source_content_quote") or "").strip() or str(item.get("source_content_quote") or "") not in str(coverage.get("source_content_excerpt") or "") or len(str(item.get("specificness_evidence") or "").strip())<12 or not item.get("evidence"): errors.append("V19 审核必须逐卡引用候选原句、原小框架与具体性依据");break
    routes=review.get("route_comparison_reviews") if isinstance(review.get("route_comparison_reviews"),list) else []; pairs={"structure_one/structure_two","structure_one/structure_three","structure_two/structure_three"}
    if {str(item.get("pair") or "") for item in routes if isinstance(item,dict)}!=pairs or any(item.get("verdict")!="passed" or not all(str(item.get(key) or "").strip() for key in ("reader_entry_evidence","reasoning_path_evidence","delivery_form_evidence")) for item in routes if isinstance(item,dict)): errors.append("V19 审核未逐对证明三套结构的实质差异")
    return errors

def main() -> int:
    parser=argparse.ArgumentParser(description="创建 V19 文案结构独立语义审稿请求");parser.add_argument("--kind",choices=["copy-structure"],required=True);parser.add_argument("--plan",type=Path,required=True);parser.add_argument("--candidate",type=Path,required=True);parser.add_argument("--target",type=Path,required=True);args=parser.parse_args();target=prepare(args.kind,args.plan.resolve(),args.candidate.resolve(),args.target.resolve());print(json.dumps({"status":"needs-review","review":str(target)},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
