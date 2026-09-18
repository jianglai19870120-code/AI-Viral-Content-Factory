#!/usr/bin/env python3
"""Render and publish the only supported public structure view: V19."""
from __future__ import annotations
import argparse, hashlib, json, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from workflow.case_output_directories import assert_case_output_path, resolve_case_output_directory
from workflow.common import append_brand_footer
from workflow.topic_structure_releases import build_release_entry, write_release_index_entry
FORMAL=ROOT/"02_资产中心"/"03_输出库"/"01_文案结构"; CST=timezone(timedelta(hours=8)); NAMES={"structure_one":"结构一","structure_two":"结构二","structure_three":"结构三","structure_four":"结构四"}
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def cell(value:object)->str:return str(value or "").replace("|","\\|").replace("\n","<br>")
def rows(plan:dict)->list[dict]:return [item for item in plan.get("core_frameworks",[]) if isinstance(item,dict)] if isinstance(plan.get("core_frameworks"),list) else []
def by_id(plan:dict)->dict:return {str(item.get("core_framework_id") or ""):item for item in rows(plan)}
def content(row:dict)->str:
    return "<br>".join(str(card.get("content") or "").strip() for card in row.get("small_framework_cards",[]) if isinstance(card,dict) and str(card.get("content") or "").strip())
def release_directory(data:dict)->Path:return resolve_case_output_directory(str(data.get("benchmark_case_id") or ""),"structure",create=True)
def release_path(data:dict,directory:Path,now:datetime|None=None)->Path:
    stamp=(now or datetime.now(CST)).astimezone(CST).strftime("%Y%m%d-%H%M%S");topic=re.sub(r"[^\w\u4e00-\u9fff-]+","_",str(data.get("topic") or "未命名")).strip("_")[:72] or "未命名";candidate=directory/f"{topic}_{data['benchmark_case_id']}_{stamp}.md";number=2
    while candidate.exists():candidate=directory/f"{topic}_{data['benchmark_case_id']}_{stamp}_{number:02d}.md";number+=1
    return candidate
def approved(candidate:Path,receipt:Path)->bool:
    data=json.loads(receipt.read_text(encoding="utf-8"));subject=data.get("subject") if isinstance(data.get("subject"),dict) else {};return data.get("schema")=="audit-receipt-v3" and data.get("artifactType")=="copy-structure-v19" and data.get("status")=="approved" and subject.get("candidateSha256")==digest(candidate)
def validate_release_plan(candidate:Path,receipt:Path,plan_path:Path,data:dict)->dict:
    plan=json.loads(plan_path.read_text(encoding="utf-8"));subject=json.loads(receipt.read_text(encoding="utf-8")).get("subject") or {};handoff=Path(str(plan.get("handoff_path") or "")).resolve();output=Path(str(plan.get("planned_output_path") or "")).resolve()
    if plan.get("schema")!="copy-structure-release-plan-v1" or plan.get("topic_table_binding")!=data.get("topic_table_binding") or plan.get("candidate_sha256")!=digest(candidate) or Path(str(plan.get("candidate_path") or "")).resolve()!=candidate.resolve() or not handoff.is_file() or plan.get("handoff_sha256")!=digest(handoff) or subject.get("handoffSha256")!=digest(handoff) or subject.get("releasePlanSha256")!=digest(plan_path):raise ValueError("发布计划或审核回执未锁定当前 V19 输入")
    if not output.is_relative_to(FORMAL.resolve()) or output.exists():raise ValueError("发布计划正式输出路径非法或已被占用")
    assert_case_output_path(str(data.get("benchmark_case_id") or ""),"structure",output);return plan
def render(data:dict)->str:
    plans=data.get("structures") if isinstance(data.get("structures"),dict) else {};one=plans.get("structure_one") if isinstance(plans.get("structure_one"),dict) else {};two=by_id(plans.get("structure_two") if isinstance(plans.get("structure_two"),dict) else {});three=by_id(plans.get("structure_three") if isinstance(plans.get("structure_three"),dict) else {})
    lines=[f"# 文案结构｜{data['topic']}","",f"对标复刻拆解：{data['benchmark_case_id']}","","## 三套结构方向对比","","| 大框架 | 结构一 | 结构二 | 结构三 |","| --- | --- | --- | --- |"]
    for item in rows(one):
        ident=str(item.get("core_framework_id") or "");lines.append(f"| {cell(item.get('framework_label'))} | {cell(content(item))} | {cell(content(two.get(ident,{})))} | {cell(content(three.get(ident,{})))} |")
    contract=data.get("title_contract") if isinstance(data.get("title_contract"),dict) else {};lines.extend(["","## 选题扣题合同",""]+[f"- {label}：{contract.get(key,'')}" for key,label in (("audience","目标对象"),("title_promise","标题承诺"),("core_conflict","核心冲突"),("terminal_conclusion","最终结论"),("completion_criteria","判断完成的标准"))])
    for name,label in NAMES.items():
        plan=plans.get(name) if isinstance(plans.get(name),dict) else {};lines.extend(["",f"## {label}",""])
        if name!="structure_four":
            lines.extend([f"**母逻辑：** {plan.get('mother_logic','')}",f"**扣题结论：** {plan.get('terminal_conclusion','')}","","**FNN 推进链：**",""])
            for item in rows(plan):
                chain=item.get("logic_chain") if isinstance(item.get("logic_chain"),dict) else {};lines.append(f"- {item.get('framework_block_id') or item.get('core_framework_id')}：{chain.get('answering_question','')} → {chain.get('necessary_conclusion','')} → {chain.get('next_question','')}")
            lines.append("")
        lines.extend(["| 编号 | 大框架 | 核心内容 |","| --- | --- | --- |"])
        for item in rows(plan):lines.append(f"| {cell(item.get('framework_block_id') or item.get('core_framework_id'))} | {cell(item.get('framework_label'))} | {'' if name=='structure_four' else cell(content(item))} |")
    return "\n".join(lines).rstrip()+"\n"
def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--candidate",type=Path,required=True);parser.add_argument("--output",type=Path);parser.add_argument("--release",action="store_true");parser.add_argument("--audit-receipt",type=Path);parser.add_argument("--release-plan",type=Path);args=parser.parse_args();candidate=args.candidate.resolve();data=json.loads(candidate.read_text(encoding="utf-8"))
    if data.get("schema")!="copy-structure-v19":raise SystemExit("结构 renderer 只接受 copy-structure-v19 候选")
    plan=None
    if args.release:
        if not args.audit_receipt or not args.audit_receipt.is_file() or not approved(candidate,args.audit_receipt.resolve()):raise SystemExit("正式发布需要当前候选对应的 approved 小审回执")
        if isinstance(data.get("topic_table_binding"),dict):
            if not args.release_plan:raise SystemExit("选题表直连发布必须携带 --release-plan")
            try:plan=validate_release_plan(candidate,args.audit_receipt.resolve(),args.release_plan.resolve(),data);output=Path(str(plan["planned_output_path"])).resolve()
            except ValueError as exc:raise SystemExit(str(exc)) from exc
        else:output=release_path(data,release_directory(data))
    else:
        if not args.output:raise SystemExit("运行区渲染必须提供 --output")
        output=args.output.resolve()
        if output.is_relative_to(FORMAL.resolve()):raise SystemExit("正式目录只能通过 --release 发布")
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(render(data),encoding="utf-8",newline="\n")
    if args.release:
        append_brand_footer(output)
        if plan is not None:
            write_release_index_entry(build_release_entry(binding=data["topic_table_binding"],output_path=output,candidate_path=candidate,audit_receipt_path=args.audit_receipt.resolve(),release_plan_path=args.release_plan.resolve()))
            refresh=ROOT/"10_Skills武器库"/"爆款选题分类Skill"/"scripts"/"refresh_topic_stats.py";run=subprocess.run([sys.executable,"-X","utf8",str(refresh),"--root",str(ROOT)],text=True,capture_output=True,encoding="utf-8")
            if run.returncode:raise SystemExit("结构已发布，但选题状态回写失败："+(run.stdout.strip() or run.stderr.strip()))
    print(output);return 0
if __name__=="__main__":raise SystemExit(main())
