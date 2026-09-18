#!/usr/bin/env python3
"""V19-only audit gate: V3 contract, card evidence and public big-framework view."""
from __future__ import annotations
import argparse, hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
# This script is also loaded directly by the repository test suite.  Add its
# own directory explicitly so the sibling independent reviewer is available in
# both direct-script and importlib execution modes.
SCRIPT_ROOT=Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:sys.path.insert(0,str(SCRIPT_ROOT))
from independent_copy_semantic_review import validate as validate_semantic
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8"))
def uses_current_contract(handoff: dict, candidate: dict) -> bool:
    """Keep the V19-only gate independently testable without writing a receipt."""
    return (handoff.get("schema"), candidate.get("schema")) == ("copy-structure-handoff-v19", "copy-structure-v19")
def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--handoff",type=Path,required=True);parser.add_argument("--candidate",type=Path,required=True);parser.add_argument("--preview",type=Path,required=True);parser.add_argument("--semantic-review",type=Path,required=True);parser.add_argument("--release-plan",type=Path);parser.add_argument("--receipt",type=Path,required=True);args=parser.parse_args()
    handoff,candidate=load(args.handoff),load(args.candidate);errors=[]
    if not uses_current_contract(handoff,candidate):errors.append("小审只接受 V19 handoff/candidate")
    if not args.preview.is_file():errors.append("缺少结构预览")
    else:
        preview=args.preview.read_text(encoding="utf-8")
        for required in ("## 三套结构方向对比","## 选题扣题合同","## 结构一","## 结构二","## 结构三","## 结构四"):
            if required not in preview:errors.append(f"结构预览缺少 {required}")
        if "small_framework" in preview or "小框架" in preview:errors.append("前台预览泄露小框架上下文")
    validator=ROOT/"10_Skills武器库"/"文案结构生成 Skill"/"scripts"/"validate_structure_output.py";run=subprocess.run([sys.executable,"-X","utf8",str(validator),"--handoff",str(args.handoff),"--candidate",str(args.candidate)],text=True,capture_output=True,encoding="utf-8")
    if run.returncode:errors.append("生成侧机械校验未通过："+(run.stdout.strip() or run.stderr.strip()))
    errors.extend(validate_semantic("copy-structure",args.handoff,args.candidate,args.semantic_review))
    subject={"candidateSha256":digest(args.candidate),"handoffSha256":digest(args.handoff),"previewSha256":digest(args.preview) if args.preview.is_file() else ""}
    if args.release_plan and args.release_plan.is_file():
        plan=load(args.release_plan)
        if plan.get("schema")!="copy-structure-release-plan-v1" or plan.get("candidate_sha256")!=digest(args.candidate) or plan.get("handoff_sha256")!=digest(args.handoff):errors.append("发布计划未锁定当前 V19 输入")
        else:subject["releasePlanSha256"]=digest(args.release_plan)
    receipt={"schema":"audit-receipt-v3","artifactType":"copy-structure-v19","status":"approved" if not errors else "returned","auditor":"xiaoshen","generatedAt":datetime.now(timezone.utc).isoformat(),"subject":subject,"generatorMechanicalResult":run.stdout.strip() or run.stderr.strip(),"issues":errors}
    args.receipt.parent.mkdir(parents=True,exist_ok=True);args.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps(receipt,ensure_ascii=False));return 0 if not errors else 1
if __name__=="__main__":raise SystemExit(main())
