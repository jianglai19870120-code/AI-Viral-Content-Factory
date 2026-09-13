#!/usr/bin/env python3
"""Freeze a user-confirmed big-framework structure-four Markdown table."""
from __future__ import annotations
import argparse,hashlib,json,re,sys
from datetime import datetime,timezone
from pathlib import Path


def project_root() -> Path:
    """Find the factory root from either the source Skill or its installed mirror."""
    candidates = (Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "00_系统说明" / "benchmark-case-registry.json").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 00_系统说明/benchmark-case-registry.json")


ROOT=project_root();sys.path.insert(0,str(ROOT))
from workflow.benchmark_cases import approved_case
from workflow.universal_copy_contract import parse_breakdown,split_row
TOTAL_HEADER=["大框架区块","编号","大框架","小框架","小框架作用","小结构原文内容"]
FOUR_V11=["核心大框架","核心内容"]
FORMAL={"观点","痛点","误区","解决方案","案例","推荐理由"}
LABELED_CONTENT=re.compile(r"^\s*论点[：:]\s*(?P<claim>.+?)\s*论据[（(](?P<method>[^）)]+)[）)]\s*[：:]\s*(?P<evidence>.+?)\s*$",re.S)
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def formal_type(label:str)->str:
    value=re.split(r"[：:]",label.strip())[-1].strip()
    for kind in FORMAL:
        suffix=value.removeprefix(kind)
        if value==kind or (suffix and all(char in "一二三四五六七八九十0123456789" for char in suffix)):return kind
    return ""
def table_after(lines:list[str],heading:str,header:list[str])->list[dict[str,str]]:
    try:start=lines.index(heading)
    except ValueError as exc:raise ValueError(f"缺少章节：{heading}") from exc
    index=start+1
    while index<len(lines) and not lines[index].strip():index+=1
    if index>=len(lines) or split_row(lines[index])!=header:raise ValueError(f"{heading} 的表头不符合合同")
    index+=2;rows=[]
    while index<len(lines) and lines[index].startswith("|"):
        values=split_row(lines[index])
        if len(values)!=len(header):raise ValueError(f"{heading} 存在非 {len(header)} 列数据行")
        rows.append(dict(zip(header,values)));index+=1
    return rows
def parse_unified_content(value:str)->dict[str,str]:
    statement=value.strip()
    if not statement:return {"content_mode":"auto-fill-required","core_claim":"","core_evidence":"","evidence_method":""}
    matched=LABELED_CONTENT.fullmatch(statement)
    if matched:
        return {"content_mode":"labeled-claim-evidence","core_claim":matched.group("claim").strip(),"core_evidence":matched.group("evidence").strip(),"evidence_method":matched.group("method").strip()}
    if "论据" in statement:raise ValueError("结构四明确填写‘论据’时，必须采用‘论据（写作手法）：……’格式")
    return {"content_mode":"user-unified","core_claim":"","core_evidence":"","evidence_method":""}
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--structure-markdown",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();source=a.structure_markdown.resolve();lines=source.read_text(encoding="utf-8").splitlines()
    title=next((line.removeprefix("# 文案结构｜").strip() for line in lines if line.startswith("# 文案结构｜")),"");benchmark_id=next((line.removeprefix("对标复刻拆解：").strip() for line in lines if line.startswith("对标复刻拆解：")),"")
    if not title or not benchmark_id:raise SystemExit("结构文件缺少标题或对标编号")
    case=approved_case(benchmark_id);breakdown=Path(case["breakdownPath"]);total=table_after(breakdown.read_text(encoding="utf-8").splitlines(),"## 结构总表",TOTAL_HEADER);blueprint=parse_breakdown(breakdown)["functional_blueprint"]
    blocks=[]
    for block_id in dict.fromkeys(row["大框架区块"] for row in total):
        rows=[row for row in total if row["大框架区块"]==block_id];label=rows[0]["大框架"]
        blocks.append((block_id,label,formal_type(label),rows))
    visible=table_after(lines,"## 结构四",FOUR_V11);mode="v11-unified"
    formal_blocks=[item for item in blocks if item[2]];segments=[]
    for block_id,label,kind,rows in blocks:
        details=[]
        for row in rows:
            detail=next((x for x in blueprint if str(x.get("小结构编号"))==row["编号"]),{})
            details.append({"small_structure_id":row["编号"],"small_framework_name":row["小框架"],"small_structure_function":str(detail.get("功能任务") or row["小框架作用"]),"input_relation":str(detail.get("前置推进") or ""),"output_relation":str(detail.get("后续交付") or "")})
        segments.append({"framework_block_id":block_id,"framework_label":label,"formal_framework_type":kind or None,"small_structures":details})
    frameworks=[]
    if len(visible)!=len(formal_blocks):raise SystemExit(f"结构四必须有 {len(formal_blocks)} 条大框架，实际为 {len(visible)} 条")
    for n,(actual,(block_id,label,kind,rows)) in enumerate(zip(visible,formal_blocks),1):
        if actual["核心大框架"]!=label:raise SystemExit(f"结构四第 {n} 行未锁定大框架")
        statement=actual["核心内容"].strip()
        try:parsed_content=parse_unified_content(statement)
        except ValueError as exc:raise SystemExit(f"结构四第 {n} 行格式错误：{exc}") from exc
        frameworks.append({"core_framework_id":f"CF-{block_id}","framework_block_id":block_id,"framework_label":label,"formal_framework_type":kind,"downstream_small_structure_ids":[row["编号"] for row in rows],"core_statement":statement,"content_origin":"user-filled" if statement else "auto-fill-required","user_statement":statement,**parsed_content})
    schema="final-copy-structure-four-freeze-v4"
    payload={"schema":schema,"structure_four_status":"frozen","topic":title,"benchmark_case_id":benchmark_id,"source_markdown":str(source),"source_markdown_sha256":digest(source),"benchmark":str(breakdown),"benchmark_sha256":digest(breakdown),"benchmark_audit":str(case["auditPath"]),"frozen_at":datetime.now(timezone.utc).isoformat(),"core_frameworks":frameworks,"structure_segments":segments,"functional_blueprint_sha256":hashlib.sha256(json.dumps(blueprint,ensure_ascii=False,sort_keys=True).encode("utf-8")).hexdigest()}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n");print(json.dumps({"status":"frozen","mode":mode,"coreFrameworks":len(frameworks),"smallStructures":len(total)},ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
