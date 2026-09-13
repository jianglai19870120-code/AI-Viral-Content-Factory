#!/usr/bin/env python3
"""Independent audit gate for active V11/V12 copy structures."""
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
FUTURE_RELEASE_NAME=re.compile(r"^.+_(?:GHX|HKX)-\d{3}_\d{8}-\d{6}(?:_\d{2})?\.md$")

def future_release_name_valid(name:str)->bool:
    return bool(FUTURE_RELEASE_NAME.fullmatch(name)) and not re.match(r"^[A-Z]{3}-\d{3}_",name)

def load(path:Path)->dict:return json.loads(path.read_text(encoding="utf-8"))
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def frameworks(plan:dict)->list[dict]:return [x for x in plan.get("core_frameworks",[]) if isinstance(x,dict)] if isinstance(plan.get("core_frameworks"),list) else []
def by_id(plan:dict)->dict:return {str(x.get("core_framework_id") or ""):x for x in frameworks(plan)}
def cell(value:object)->str:return str(value or "").replace("|","\\|").replace("\n","<br>")
def claim(row:dict)->str:return str(row.get("core_claim") or "").strip()
def sentence(value:object)->str:
    text=str(value or "").strip()
    return text if not text or text[-1] in "。！？!?；;" else text+"。"
def content(row:dict)->str:
    chain=row.get("evidence_chain") if isinstance(row.get("evidence_chain"),list) else []
    if chain:
        parts=[]
        for index,item in enumerate(chain,1):
            if not isinstance(item,dict):continue
            roles="、".join(str(role).strip() for role in item.get("logic_roles",[]) if str(role).strip())
            method=str(item.get("evidence_method") or "").strip()
            text=sentence(item.get("text"))
            if text:parts.append(f"{index}. {roles}（{method}）：{text}")
        return "<br>".join([f"**核心金句：** {sentence(row.get('core_claim'))}"]+parts) if claim(row) and parts else ""
    value=str(row.get("core_evidence") or "").strip();method=str(row.get("evidence_method") or "").strip()
    if method=="机制":method="机制解释"
    return f"**核心金句：** {sentence(row.get('core_claim'))}论据（{method}）：{sentence(value)}" if claim(row) and value and method else ""
def sources(row:dict)->str:
    entries=row.get("processing_sources") if isinstance(row.get("processing_sources"),list) else []
    if entries:return "<br>".join(dict.fromkeys(f"{str(x.get('path') or '').strip()}#{str(x.get('section') or '').strip()}".rstrip("#") for x in entries if isinstance(x,dict) and str(x.get("path") or "").strip()))
    note=str(row.get("source_note") or "").strip()
    return note or "<br>".join(dict.fromkeys(str(x.get("wikilink") or "") for x in row.get("asset_calls",[]) if isinstance(x,dict) and str(x.get("wikilink") or "")))
def section(text:str,title:str)->str:
    marker=f"## {title}"
    if marker not in text:return ""
    start=text.index(marker)+len(marker);end=text.find("\n## ",start)
    return text[start:end+1] if end>=0 else text[start:]
def strict_table(section_text:str,header:str,divider:str,label:str,errors:list[str])->None:
    raw=section_text.splitlines();lines=[line for line in raw if line.strip()]
    if header not in lines:errors.append(f"{label} 缺少严格 GFM 表头");return
    index=lines.index(header)
    if index+1>=len(lines) or lines[index+1]!=divider:errors.append(f"{label} 分隔行不规范")
    for line in lines[index:index+2]+[x for x in lines[index+2:] if x.startswith("|")]:
        if not re.fullmatch(r"\|(?: [^|]* \|)+",line):errors.append(f"{label} 含不规范 GFM 表格行");break
    raw_index=raw.index(header)
    if raw_index==0 or raw[raw_index-1].strip():errors.append(f"{label} 表格前必须留空行")
    end=raw_index+2
    while end<len(raw) and raw[end].startswith("|"):end+=1
    if end>=len(raw) or raw[end].strip():errors.append(f"{label} 表格后必须留空行")
def audit_mapping(h:dict,c:dict,errors:list[str])->None:
    expected=[str(x.get("core_framework_id") or "") for x in h.get("core_frameworks",[]) if isinstance(x,dict)]
    plans=c.get("structures") if isinstance(c.get("structures"),dict) else {}
    for name in ("structure_one","structure_two","structure_three","structure_four"):
        actual=[str(x.get("core_framework_id") or "") for x in frameworks(plans.get(name,{}) if isinstance(plans.get(name),dict) else {})]
        if actual!=expected:errors.append(f"{name} 未逐项保留正式大框架")
    if any("small_framework" in json.dumps(plans.get(name,{}),ensure_ascii=False) for name in plans):errors.append("前台结构不得包含小框架字段")
    all_rows=[x for x in h.get("big_frameworks",[]) if isinstance(x,dict)]
    cores=[x for x in h.get("core_frameworks",[]) if isinstance(x,dict)]
    final_only=[x for x in h.get("final_copy_only_frameworks",[]) if isinstance(x,dict)]
    all_ids=[str(x.get("core_framework_id") or "") for x in all_rows];core_ids=[str(x.get("core_framework_id") or "") for x in cores];final_ids=[str(x.get("core_framework_id") or "") for x in final_only]
    if not final_only and any(x.get("formal_framework_type") is None for x in all_rows):errors.append("非处理库支撑段必须显式交给正文阶段")
    if any(x.get("formal_framework_type") is None for x in cores) or any(x.get("formal_framework_type") is not None or x.get("generation_owner")!="final-copy" for x in final_only):errors.append("核心框架与正文专属支撑段的职责边界错误")
    if set(core_ids)&set(final_ids) or [ident for ident in all_ids if ident in core_ids or ident in final_ids]!=all_ids:errors.append("核心框架和正文专属支撑段未完整且无重叠覆盖 FNN")
    if c.get("final_copy_only_frameworks")!=h.get("final_copy_only_frameworks"):errors.append("候选未锁定正文专属支撑段")
def audit_preview_v13(path:Path,c:dict,errors:list[str])->None:
    text=path.read_text(encoding="utf-8")
    v14=c.get("schema")=="copy-structure-v14";v15=c.get("schema") in {"copy-structure-v15","copy-structure-v16"}
    for forbidden in ("logic_roles", "evidence_method", "content_object_id", "content_sha256", "module_sha256", "source_anchor", "CF-F"):
        if forbidden in text:errors.append(f"V13 人读预览泄漏内部元数据：{forbidden}")
    if "**核心金句：**" in text or "**核心论点：**" not in text:errors.append("V13 人读预览必须使用核心论点且不得使用核心金句")
    if re.search(r"(?m)^###\\s+",text):errors.append("人读预览不得使用卡片式三级标题")
    public_sources=bool(((c.get("presentation") or {}).get("structure_three_public_sources")))
    for label in ("结构一", "结构二", "结构三", "结构四"):
        body=section(text,label)
        if (v14 or v15) and label=="结构三":
            strict_table(body,"| 编号 | 核心大框架 | 核心内容 | 出处 |","| --- | --- | --- | --- |",label,errors)
        elif v14 or v15:
            strict_table(body,"| 编号 | 核心大框架 | 核心内容 |","| --- | --- | --- |",label,errors)
        elif label=="结构三" and public_sources:
            strict_table(body,"| 核心大框架 | 核心内容 | 出处 |","| --- | --- | --- |",label,errors)
        else:
            strict_table(body,"| 核心大框架 | 核心内容 |","| --- | --- |",label,errors)
    if v14 or v15:
        body=section(text,"结构三")
        strict_table(body,"| 编号 | 核心大框架 | 核心内容 | 出处 |","| --- | --- | --- | --- |","结构三",errors)
        table_rows=[x for x in body.splitlines() if x.startswith("|")][2:]
        candidate_rows=frameworks((c.get("structures") or {}).get("structure_three",{}))
        if len(table_rows)!=len(candidate_rows):errors.append("结构三出处表未逐项覆盖候选核心大框架")
        for index,row in enumerate(candidate_rows):
            note=sources(row)
            if row.get("source_note") is not None:errors.append("结构三不得使用 source_note 作为出处")
            if row.get("core_claim") and not note:errors.append("结构三存在未标明出处的核心大框架")
            elif index<len(table_rows) and cell(note) not in table_rows[index]:errors.append("结构三出处未与候选 source_note 一致")
    if not v14 and not v15 and not public_sources and "出处 |" in section(text,"结构三"):
        errors.append("V13 结构三未经候选授权显示出处列")
    if not v14 and "结构三" in text and "资产缺口说明" not in text and any(not row.get("asset_calls") for row in frameworks((c.get("structures") or {}).get("structure_three",{}))):errors.append("V13 结构三有资产缺口却未在人读稿说明")
    final_labels={str(x.get("framework_label") or "").strip() for x in c.get("final_copy_only_frameworks",[]) if isinstance(x,dict)}
    for label in final_labels:
        if label and re.search(rf"(?m)^\| F\d{{2}} \| {re.escape(label)} \|",text):errors.append(f"人读预览泄漏仅供正文生成的支撑段：{label}")
def audit_preview(path:Path,c:dict,errors:list[str])->None:
    if c.get("schema") in {"copy-structure-v13", "copy-structure-v14", "copy-structure-v15", "copy-structure-v16"}:
        audit_preview_v13(path,c,errors);return
    text=path.read_text(encoding="utf-8")
    for forbidden in ("对标小结构推进摘要","对标小框架","small_framework","proposition_id","content_sha256","module_sha256","source_anchor","CF-F"):
        if forbidden in text:errors.append(f"人读预览泄漏禁用内容：{forbidden}")
    if re.search(r"(?m)^###\s+",text):errors.append("人读预览不得使用卡片式三级标题")
    plans=c.get("structures",{});one=plans.get("structure_one",{});two=by_id(plans.get("structure_two",{}));three=by_id(plans.get("structure_three",{}))
    compare=section(text,"三套结构方向对比");strict_table(compare,"| 核心大框架 | 结构一 | 结构二 | 结构三 |","| --- | --- | --- | --- |","三向比较",errors)
    expected_compare=[]
    for row in frameworks(one):
        ident=str(row.get("core_framework_id") or "");other=two.get(ident,{});asset=three.get(ident,{})
        expected_compare.append(f"| {cell(row.get('framework_label'))} | {cell(content(row))} | {cell(content(other))} | {cell(content(asset))} |")
    if [x for x in compare.splitlines() if x.startswith("|")][2:]!=expected_compare:errors.append("三向比较未与候选逐大框架一致")
    for name,label in (("structure_one","结构一"),("structure_two","结构二"),("structure_four","结构四")):
        body=section(text,label);strict_table(body,"| 核心大框架 | 核心内容 |","| --- | --- |",label,errors);expected=[]
        for row in frameworks(plans.get(name,{}) if isinstance(plans.get(name),dict) else {}):
            expected.append(f"| {cell(row.get('framework_label'))} | {'' if name=='structure_four' else cell(content(row))} |")
        if [x for x in body.splitlines() if x.startswith("|")][2:]!=expected:errors.append(f"{label} 未按大框架候选展示")
    body=section(text,"结构三");strict_table(body,"| 核心大框架 | 核心内容 | 出处 |","| --- | --- | --- |","结构三",errors);expected=[]
    for row in frameworks(plans.get("structure_three",{})):
        expected.append(f"| {cell(row.get('framework_label'))} | {cell(content(row))} | {cell(sources(row))} |")
    if [x for x in body.splitlines() if x.startswith("|")][2:]!=expected:errors.append("结构三内容或出处未与候选一致")
    if any(not row.get("asset_calls") for row in frameworks(plans.get("structure_three",{}))) and "资产缺口说明" not in body:errors.append("结构三存在空缺但未显示资产缺口说明")
def audit_release_plan(path:Path|None,h:dict,c:dict,candidate_path:Path,errors:list[str])->str:
    if path is None:errors.append("选题表直连缺少发布计划");return ""
    try:plan=load(path)
    except Exception as exc:errors.append(f"发布计划不可读：{exc}");return ""
    if plan.get("schema")!="copy-structure-release-plan-v1" or plan.get("topic_table_binding")!=h.get("topic_table_binding") or plan.get("candidate_sha256")!=digest(candidate_path):errors.append("发布计划未锁定当前选题表行或候选")
    return digest(path)
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--topic-analysis",type=Path);p.add_argument("--handoff",type=Path,required=True);p.add_argument("--candidate",type=Path,required=True);p.add_argument("--preview",type=Path,required=True);p.add_argument("--semantic-review",type=Path);p.add_argument("--release-plan",type=Path);p.add_argument("--receipt",type=Path,required=True);a=p.parse_args();h,c,errors=load(a.handoff),load(a.candidate),[]
    allowed={("copy-structure-handoff-v16","copy-structure-v16")}
    if (h.get("schema"),c.get("schema")) not in allowed:errors.append("新链路 handoff/candidate schema 必须为同版本 V16")
    if "structure_segments" in h or "structure_segments" in c or "small_structure" in json.dumps({"handoff":h,"candidate":c},ensure_ascii=False):errors.append("V14 不得包含小结构或 structure_segments")
    audit_mapping(h,c,errors);audit_preview(a.preview,c,errors)
    if c.get("schema")=="copy-structure-v16":
        for required in ("## 选题扣题合同","**母逻辑：**","**FNN 推进链：**"):
            if required not in a.preview.read_text(encoding="utf-8"):errors.append(f"V15 预览缺少逻辑链门禁摘要：{required}")
        if "原文依据（" not in a.preview.read_text(encoding="utf-8") and any(str(row.get("core_claim") or "").strip() for row in frameworks(((c.get("structures") or {}).get("structure_three") or {}))):
            errors.append("V16 结构三预览缺少逐条原文依据")
    validator=ROOT/"10_Skills武器库"/"文案结构生成 Skill"/"scripts"/"validate_structure_output.py";mechanical=subprocess.run([sys.executable,"-X","utf8",str(validator),"--handoff",str(a.handoff),"--candidate",str(a.candidate)],capture_output=True,text=True,encoding="utf-8")
    if mechanical.returncode:errors.append("生成侧机械校验未通过："+(mechanical.stdout.strip() or mechanical.stderr.strip()))
    semantic=[]
    if a.semantic_review:
        from independent_copy_semantic_review import validate
        semantic=validate("copy-structure",a.release_plan or a.handoff,a.candidate,a.semantic_review);errors.extend(semantic)
    elif not errors:errors.append("缺少独立语义审核回执")
    release_sha=audit_release_plan(a.release_plan,h,c,a.candidate,errors) if h.get("topic_table_binding") is not None else ""
    subject={"candidateSha256":digest(a.candidate),"handoffSha256":digest(a.handoff),"previewSha256":digest(a.preview)}
    if release_sha:subject["releasePlanSha256"]=release_sha
    receipt={"schema":"audit-receipt-v3","artifactType":c.get("schema"),"status":"approved" if not errors else "returned","auditor":"xiaoshen","generatedAt":datetime.now(timezone.utc).isoformat(),"subject":subject,"checks":{"mapping":not any("框架" in x for x in errors),"preview":not any("预览" in x or "表格" in x for x in errors),"semantic":not semantic,"releasePlan":not any("发布计划" in x for x in errors)},"generatorMechanicalResult":mechanical.stdout.strip() or mechanical.stderr.strip(),"issues":errors}
    a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n");print(json.dumps(receipt,ensure_ascii=False));return 0 if not errors else 1
if __name__=="__main__":raise SystemExit(main())
