#!/usr/bin/env python3
"""Render v9 big-framework previews and controlled releases."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from workflow.common import append_brand_footer
from workflow.topic_structure_releases import build_release_entry,write_release_index_entry
NAMES={"structure_one":"结构一","structure_two":"结构二","structure_three":"结构三","structure_four":"结构四"};FORMAL=ROOT/"02_资产中心"/"03_输出库"/"01_文案结构";CST=timezone(timedelta(hours=8))
TYPE_DIRECTORIES={"干货型":"01_干货型文案结构","推荐型":"02_推荐型文案结构（会员专享）","获客型":"03_获客型文案结构（会员专享）"}
FUTURE_RELEASE_NAME=re.compile(r"^.+_[A-Z]{3}-\d{3}_\d{8}-\d{6}(?:_\d{2})?\.md$")
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def under(path:Path,parent:Path)->bool:
    try:return path.resolve().is_relative_to(parent.resolve())
    except ValueError:return False
def release_allowed(candidate:Path,receipt:Path)->bool:
    data=json.loads(receipt.read_text(encoding="utf-8"));subject=data.get("subject") if isinstance(data.get("subject"),dict) else {}
    schema=json.loads(candidate.read_text(encoding="utf-8")).get("schema")
    return data.get("schema")=="audit-receipt-v3" and data.get("artifactType")==schema and schema=="copy-structure-v16" and data.get("status")=="approved" and subject.get("candidateSha256")==digest(candidate)
def future_release_name_valid(name:str)->bool:return bool(FUTURE_RELEASE_NAME.fullmatch(name)) and not re.match(r"^[A-Z]{3}-\d{3}_",name)
def release_plan_allowed(candidate:Path,receipt:Path,plan_path:Path,data:dict)->dict:
    plan=json.loads(plan_path.read_text(encoding="utf-8"));subject=json.loads(receipt.read_text(encoding="utf-8")).get("subject") or {};binding=data.get("topic_table_binding")
    if not isinstance(binding,dict) or plan.get("schema")!="copy-structure-release-plan-v1":raise ValueError("选题表直连发布必须使用合法发布计划")
    if plan.get("topic_table_binding")!=binding or plan.get("topic")!=data.get("topic") or plan.get("benchmark_case_id")!=data.get("benchmark_case_id"):raise ValueError("发布计划绑定已漂移")
    if plan.get("candidate_sha256")!=digest(candidate) or Path(str(plan.get("candidate_path") or "")).resolve()!=candidate:raise ValueError("发布计划未锁定当前候选")
    handoff=Path(str(plan.get("handoff_path") or "")).resolve()
    if not handoff.is_file() or plan.get("handoff_sha256")!=digest(handoff) or subject.get("handoffSha256")!=digest(handoff) or subject.get("releasePlanSha256")!=digest(plan_path):raise ValueError("正式发布需要小审批准当前 handoff 与发布计划")
    output=Path(str(plan.get("planned_output_path") or "")).resolve()
    if not under(output,FORMAL) or not future_release_name_valid(output.name) or output.exists():raise ValueError("发布计划的正式路径非法、过期或已存在")
    return plan
def safe_topic(value:str)->str:return (re.sub(r"[^\w\u4e00-\u9fff-]+","_",value,flags=re.UNICODE).strip("_")[:72] or "未命名选题")
def release_directory(data:dict)->Path:
    from workflow.benchmark_cases import get_case
    case_type=str(get_case(str(data.get("benchmark_case_id") or "")).get("type") or "").strip()
    directory=TYPE_DIRECTORIES.get(case_type)
    if not directory:raise ValueError(f"对标案例类型没有文案结构发布目录：{case_type or '空'}")
    target=FORMAL/directory
    if not target.is_dir():raise ValueError(f"文案结构发布目录不存在：{target}")
    return target
def release_path(data:dict,directory:Path,now:datetime|None=None)->Path:
    stamp=(now or datetime.now(CST)).astimezone(CST).strftime("%Y%m%d-%H%M%S");base=f"{safe_topic(str(data['topic']))}_{data['benchmark_case_id']}_{stamp}";target=directory/f"{base}.md";n=2
    while target.exists():target=directory/f"{base}_{n:02d}.md";n+=1
    return target
def cell(value:object)->str:return str(value or "").replace("|","\\|").replace("\n","<br>")
def frameworks(plan:dict)->list[dict]:return [x for x in plan.get("core_frameworks",[]) if isinstance(x,dict)] if isinstance(plan.get("core_frameworks"),list) else []
def by_id(plan:dict)->dict:return {str(x.get("core_framework_id") or ""):x for x in frameworks(plan)}
def claim(row:dict)->str:return str(row.get("core_claim") or "").strip()
def sentence(value:object)->str:
    text=str(value or "").strip()
    return text if not text or text.endswith(("。","！","？","!","?")) else text+"。"
def content(row:dict,v13:bool=False,debug:bool=False)->str:
    if v13:
        claim_text=sentence(row.get("core_claim"))
        if not claim_text:return ""
        parts=[f"**核心论点：** {claim_text}"]
        steps=row.get("solution_steps") if isinstance(row.get("solution_steps"),list) else []
        if steps:
            for index,item in enumerate(steps,1):
                if isinstance(item,dict):
                    detail=str(item.get("reason") or item.get("success_criteria") or "").strip()
                    if detail:parts.append(f"{index}. {sentence(item.get('action'))}对象：{sentence(item.get('object'))}原因/判断标准：{sentence(detail)}")
        else:
            for index,item in enumerate(row.get("evidence_chain",[]) if isinstance(row.get("evidence_chain"),list) else [],1):
                if isinstance(item,dict) and sentence(item.get("text")):
                    parts.append(f"{index}. {sentence(item.get('text'))}")
                    proof=item.get("source_evidence") if isinstance(item.get("source_evidence"),dict) else {}
                    if proof:
                        parts.append(f"　原文依据（{proof.get('source_section','')}）：{sentence(proof.get('excerpt'))}")
        if debug:
            parts.append(f"[调试：对象={row.get('content_object_id') or '空'}；事实等级={row.get('fact_status') or '空'}；案例类型={row.get('case_subtype') or '空'}]")
        return "<br>".join(parts)
    chain=row.get("evidence_chain") if isinstance(row.get("evidence_chain"),list) else []
    if chain:
        claim_text=sentence(row.get("core_claim"))
        parts=[]
        for index,item in enumerate(chain,1):
            if not isinstance(item,dict):continue
            method=str(item.get("evidence_method") or "").strip()
            roles="、".join(str(role).strip() for role in item.get("logic_roles",[]) if str(role).strip())
            text=sentence(item.get("text"))
            if text:parts.append(f"{index}. {roles}（{method}）：{text}")
        return "<br>".join([f"**核心金句：** {claim_text}"]+parts) if claim_text and parts else ""
    claim_text=sentence(row.get("core_claim"));evidence_text=sentence(row.get("core_evidence"));method=str(row.get("evidence_method") or "").strip()
    if method=="机制":method="机制解释"
    return f"**核心金句：** {claim_text}论据（{method}）：{evidence_text}" if claim_text and evidence_text and method else ""
def sources(row:dict,v13:bool=False)->str:
    processing=row.get("processing_sources") if isinstance(row.get("processing_sources"),list) else []
    if processing:
        return "<br>".join(dict.fromkeys(f"{str(x.get('path') or '').strip()}#{str(x.get('section') or '').strip()}".rstrip("#") for x in processing if isinstance(x,dict) and str(x.get("path") or "").strip()))
    if str(row.get("source_note") or "").strip():
        return str(row["source_note"]).strip()
    if v13:
        return "<br>".join(dict.fromkeys(str((x.get("source_anchor") or {}).get("source_section") or "").strip() for x in row.get("asset_calls",[]) if isinstance(x,dict) and str((x.get("source_anchor") or {}).get("source_section") or "").strip()))
    return "<br>".join(dict.fromkeys(str(x.get("wikilink") or "") for x in row.get("asset_calls",[]) if isinstance(x,dict) and str(x.get("wikilink") or "")))
def append_table(lines:list[str],plan:dict,source:bool=False,pending:bool=False,v13:bool=False,v14:bool=False,v15:bool=False,debug:bool=False)->None:
    if v14 or v15:
        lines.extend((["| 编号 | 核心大框架 | 核心内容 | 出处 |","| --- | --- | --- | --- |"] if source else ["| 编号 | 核心大框架 | 核心内容 |","| --- | --- | --- |"]))
    else:
        lines.extend((["| 核心大框架 | 核心内容 | 出处 |","| --- | --- | --- |"] if source else ["| 核心大框架 | 核心内容 |","| --- | --- |"]))
    for row in frameworks(plan):
        values=([cell(str(row.get("framework_block_id") or row.get("core_framework_id") or "").removeprefix("CF-"))] if v14 or v15 else [])+[cell(row.get("framework_label")),"" if pending else cell(content(row,v13,debug))]
        if source:values.append(cell(sources(row,v13)))
        lines.append("| "+" | ".join(values)+" |")
    lines.append("")
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--candidate",type=Path,required=True);p.add_argument("--output",type=Path);p.add_argument("--release",action="store_true");p.add_argument("--audit-receipt",type=Path);p.add_argument("--release-plan",type=Path);p.add_argument("--debug",action="store_true");a=p.parse_args();candidate=a.candidate.resolve();data=json.loads(candidate.read_text(encoding="utf-8"));release_plan=None
    if data.get("schema")!="copy-structure-v16":raise SystemExit("新链路 renderer 只接受 copy-structure-v16 候选")
    if a.release and a.debug:raise SystemExit("正式发布不能使用 --debug")
    # V14 keeps the V13 public table shape, but its input has only FNN 大框架，
    # 不再包含任何小结构、逐句或复刻蓝图字段。
    v14=data.get("schema")=="copy-structure-v14";v15=data.get("schema") in {"copy-structure-v15","copy-structure-v16"}
    v13=data.get("schema") in {"copy-structure-v13","copy-structure-v14","copy-structure-v15","copy-structure-v16"}
    if a.release:
        if not a.audit_receipt or not a.audit_receipt.is_file() or not release_allowed(candidate,a.audit_receipt.resolve()):raise SystemExit("正式发布需要当前候选对应的 approved 审核回执")
        if isinstance(data.get("topic_table_binding"),dict):
            if not a.release_plan:raise SystemExit("选题表直连发布必须携带 --release-plan")
            try:release_plan=release_plan_allowed(candidate,a.audit_receipt.resolve(),a.release_plan.resolve(),data)
            except ValueError as exc:raise SystemExit(str(exc)) from exc
            output=Path(str(release_plan["planned_output_path"])).resolve()
        else:
            try:output=release_path(data,release_directory(data))
            except ValueError as exc:raise SystemExit(str(exc)) from exc
        if a.output and a.output.resolve()!=output:raise SystemExit("正式发布文件名由候选自动构建")
    else:
        if not a.output:raise SystemExit("运行区渲染必须提供 --output")
        output=a.output.resolve()
        if under(output,FORMAL):raise SystemExit("正式目录只能通过 --release 发布")
    plans=data.get("structures",{});one=plans.get("structure_one",{});two=by_id(plans.get("structure_two",{}));three=by_id(plans.get("structure_three",{}));show_public_sources=v14 or v15 or (v13 and bool((data.get("presentation") or {}).get("structure_three_public_sources")))
    lines=[f"# 文案结构｜{data['topic']}","",f"对标复刻拆解：{data['benchmark_case_id']}","","## 三套结构方向对比","","| 核心大框架 | 结构一 | 结构二 | 结构三 |","| --- | --- | --- | --- |"]
    for row in frameworks(one):
        ident=str(row.get("core_framework_id") or "");other=two.get(ident,{});asset=three.get(ident,{})
        lines.append(f"| {cell(row.get('framework_label'))} | {cell(content(row,v13,a.debug))} | {cell(content(other,v13,a.debug))} | {cell(content(asset,v13,a.debug))} |")
    lines.append("")
    contract=data.get("title_contract") if isinstance(data.get("title_contract"),dict) else {}
    lines.extend(["## 选题扣题合同",""]+[f"- {label}：{contract.get(key,'')}" for key,label in (("audience","目标对象"),("title_promise","标题承诺"),("core_conflict","核心冲突"),("terminal_conclusion","最终结论"),("completion_criteria","判断完成的标准"))]+[""])
    for name,label in NAMES.items():
        plan=plans.get(name,{}) if isinstance(plans.get(name),dict) else {};lines.extend(["",f"## {label}",""])
        if name!="structure_four":
            lines.extend([f"**母逻辑：** {plan.get('mother_logic','')}",f"**扣题结论：** {plan.get('terminal_conclusion','')}","","**FNN 推进链：**",""])
            for row in frameworks(plan):
                chain=row.get("logic_chain") if isinstance(row.get("logic_chain"),dict) else {}
                lines.append(f"- {row.get('framework_block_id') or row.get('core_framework_id')}：{chain.get('answering_question','')} → {chain.get('necessary_conclusion','')} → {chain.get('next_question','')}")
            lines.append("")
            if v13:
                mapping=plan.get("progression_map") if isinstance(plan.get("progression_map"),dict) else {}
                steps=[str((mapping.get(str(row.get('core_framework_id'))) or {}).get("new_information") or "").strip() for row in frameworks(plan)]
            else:steps=plan.get("progression_logic") if isinstance(plan.get("progression_logic"),list) else []
            lines.extend(["**本结构推进逻辑**",""]+[f"{n}. {cell(step)}" for n,step in enumerate(steps,1) if step]+[""])
        if name=="structure_three":
            if v14 and any(not row.get("processing_sources") for row in frameworks(plan)):lines.extend([str(plan.get("asset_gap_note") or "**处理库检索缺口**：未匹配大框架已逐项检索并留痕。"),""])
            elif not v14 and any(not row.get("asset_calls") for row in frameworks(plan)):lines.extend([str(plan.get("asset_gap_note") or "**资产缺口说明**：未匹配大框架已逐项检索并留痕。"),""])
            append_table(lines,plan,source=not v13 or show_public_sources,pending=False,v13=v13,v14=v14,v15=v15,debug=a.debug)
        else:append_table(lines,plan,pending=name=="structure_four",v13=v13,v14=v14,v15=v15,debug=a.debug)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text("\n".join(lines).rstrip("\n")+"\n\n",encoding="utf-8",newline="\n")
    if a.release:
        append_brand_footer(output)
        if release_plan is not None:
            write_release_index_entry(build_release_entry(binding=data["topic_table_binding"],output_path=output,candidate_path=candidate,audit_receipt_path=a.audit_receipt.resolve(),release_plan_path=a.release_plan.resolve()))
            refresh=ROOT/"10_Skills武器库"/"爆款选题分类Skill"/"scripts"/"refresh_topic_stats.py";status=subprocess.run([sys.executable,"-X","utf8",str(refresh),"--root",str(ROOT)],capture_output=True,text=True,encoding="utf-8")
            if status.returncode:raise SystemExit("结构已发布，但选题状态回写失败："+(status.stdout.strip() or status.stderr.strip()))
    print(output);return 0
if __name__=="__main__":raise SystemExit(main())
