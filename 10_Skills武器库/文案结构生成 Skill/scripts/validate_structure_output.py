#!/usr/bin/env python3
"""Mechanical gate for v11/v10 claim-and-evidence copy structures."""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

STRUCTURES=("structure_one","structure_two","structure_three","structure_four")
FORMAL={"观点","痛点","误区","解决方案","案例","推荐理由"}
PROCESSING_ROOT="02_资产中心/02_处理库"
ROUTE_FIELDS=("core_question","core_judgment","causal_mechanism","persuasion_path","evidence_strategy","final_landing")
EVIDENCE_METHODS={"案例","故事","举例","对比","反证","机制","机制解释","小技巧","步骤验证","数据证据","其他"}
TOPIC_TYPES={"binary_parallel","causal_mechanism","counterintuitive_correction","problem_solution_steps","comparison_choice","object_scene_result"}
FORBIDDEN={"small_framework_rows","small_framework_id","small_framework_name","small_structure_function","core_content_groups","core_content","core_statement","what_to_say","how_to_say"}

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def under(path:Path,root:Path)->bool:
    try:return path.resolve().is_relative_to(root.resolve())
    except ValueError:return False
def load_index(path:Path)->dict:
    result={}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item=json.loads(line);result[str(item.get("id") or item.get("angle_id") or "")]=item
    return result
def forbidden(value:object,path:str="$",found:list[str]|None=None)->list[str]:
    found=[] if found is None else found
    if isinstance(value,dict):
        for key,child in value.items():
            here=f"{path}.{key}"
            if key in FORBIDDEN:found.append(here)
            forbidden(child,here,found)
    elif isinstance(value,list):
        for n,child in enumerate(value):forbidden(child,f"{path}[{n}]",found)
    return found
def fmap(h:dict)->dict:return {str(x.get("core_framework_id") or ""):x for x in h.get("core_frameworks",[]) if isinstance(x,dict)}
def pmap(h:dict)->dict:return {str(x.get("proposition_id") or ""):x for x in h.get("topic_propositions",[]) if isinstance(x,dict)}
def nonempty(data:dict,keys)->bool:return all(str(data.get(key) or "").strip() for key in keys)
def valid_statement(value:object)->bool:
    text=str(value or "")
    return bool(text and text==text.strip() and "\n" not in text and "<br>" not in text.lower() and not text.startswith(("**","#","- ")) and not re.search(r"(?:怎么讲|如何写|写作|展开|先.+再(?:讲|写|展开|说明|解释))",text) and len(re.findall(r"[。！？!?]",text))<=1)
def evidence_method_matches(method:str,text:str)->bool:
    rules={
        "对比":r"对比|同样|相比|一个.+(?:另一个|另一路)|前者|后者|却|不如|而|.+时.+，.+时",
        "反证":r"如果|一旦|只会|导致|最后|反而|无法|越.+越|不会",
        "案例":r"案例|创业者|团队|公司|项目|有人|客户|的人",
        "故事":r"后来|起初|一开始|最后|故事|有人",
        "举例":r"比如|例如|举例|一个|三个|十个",
        "机制":r"因为|所以|导致|使|决定|会|越.+越|说明|只有.+才",
        "机制解释":r"因为|所以|导致|使|决定|会|越.+越|说明|只有.+才",
        "小技巧":r"先|每次|每周|只要|记录|测试|核对|把",
        "步骤验证":r"第一步|第二步|先|再|随后|记录|完成|把|建议|用",
        "数据证据":r"\d|百分之|成|倍|率",
    }
    return method=="其他" or bool(re.search(rules.get(method,r"$^"),text))
def check_segments(h:dict,errors:list[str])->None:
    segments=h.get("structure_segments");blueprint=(h.get("benchmark_framework") or {}).get("small_structure_blueprint",[])
    expected=[str(x.get("small_structure_id") or "") for x in blueprint]
    actual=[str(s.get("small_structure_id") or "") for seg in segments or [] if isinstance(seg,dict) for s in seg.get("small_structures",[]) if isinstance(s,dict)]
    if not isinstance(segments,list) or not segments or actual!=expected or len(actual)!=len(set(actual)):errors.append("structure_segments 未完整、连续且唯一覆盖锁定小结构")
def check_props(row:dict,props:dict,errors:list[str],label:str)->list[str]:
    ids=row.get("proposition_ids");content=f"{row.get('core_claim') or ''} {row.get('core_evidence') or ''}"
    if not isinstance(ids,list) or not ids or len(ids)!=len(set(map(str,ids))):errors.append(f"{label} 必须绑定不重复命题");return []
    valid=[]
    for ident in map(str,ids):
        expressions=props.get(ident,{}).get("accepted_expressions",[])
        if not any(str(x).strip() in content for x in expressions if str(x).strip()):errors.append(f"{label} 未明确表达命题 {ident}")
        else:valid.append(ident)
    return valid
def asset_id(call:dict)->str:return str(call.get("angle_id") or call.get("module_id") or "")
def candidates(kind:str,regular:dict,pain:dict)->list[str]:
    if kind=="痛点":return list(pain)
    return [ident for ident,item in regular.items() if item.get("framework")==kind]
def check_asset(call:dict,h:dict,fw:dict,regular:dict,pain:dict,prop_ids:list[str],errors:list[str],label:str)->None:
    kind=str(call.get("module_type") or "");path=Path(str(call.get("module_path") or "")).resolve()
    if kind!=fw.get("formal_framework_type") or kind not in FORMAL:errors.append(f"{label} 资产类型与大框架不匹配");return
    if not path.is_file() or not under(path,Path(str(h["formal_asset_root"]))) or any(x in {"99_归档","00_分类法","archive",".runtime"} for x in path.parts):errors.append(f"{label} 不是正式现役资产");return
    if call.get("wikilink")!=f"[[{path.stem}]]":errors.append(f"{label} Obsidian 链接错误")
    if kind=="痛点":
        item=pain.get(str(call.get("angle_id") or ""))
        if not item or item.get("pain_id")!=call.get("pain_id") or Path(str(item.get("card_path") or "")).resolve()!=path or call.get("content_sha256")!=item.get("card_sha256") or call.get("source_anchor")!=item.get("source_anchor"):errors.append(f"{label} 痛点来源不一致")
    else:
        item=regular.get(str(call.get("module_id") or ""));anchor={"source_path":item.get("sourcePath"),"source_section":item.get("sourceSection"),"content_sha256":item.get("contentSha256")} if item else {}
        if not item or item.get("framework")!=kind or Path(str(item.get("path") or "")).resolve()!=path or call.get("module_sha256")!=sha(path) or call.get("source_anchor")!=anchor:errors.append(f"{label} 正式模块来源不一致")
    reason=call.get("selection_reason") if isinstance(call.get("selection_reason"),dict) else {};support=call.get("proposition_support") if isinstance(call.get("proposition_support"),dict) else {}
    if not nonempty(reason,("topic_fit","framework_fit","main_meaning_support")):errors.append(f"{label} 缺少大框架调用理由")
    if set(support)!=set(prop_ids) or not nonempty(support,prop_ids):errors.append(f"{label} 缺少逐命题支撑")
def check_search(row:dict,h:dict,fw:dict,regular:dict,pain:dict,calls:list[dict],errors:list[str],label:str)->None:
    search=row.get("asset_search") if isinstance(row.get("asset_search"),dict) else {};kind=str(fw.get("formal_framework_type") or "");pool=candidates(kind,regular,pain)
    index_hash=h.get("pain_angle_index_sha256") if kind=="痛点" else h.get("processing_index_sha256")
    evaluated=search.get("evaluated_asset_ids") if isinstance(search.get("evaluated_asset_ids"),list) else [];selected=search.get("selected_asset_ids") if isinstance(search.get("selected_asset_ids"),list) else []
    if search.get("framework_type")!=kind or search.get("index_sha256")!=index_hash or search.get("candidate_count")!=len(pool):errors.append(f"{label} 未按大框架类型登记完整检索范围")
    if pool and (not evaluated or any(str(x) not in pool for x in evaluated)):errors.append(f"{label} 缺少同类型资产评估记录")
    if list(map(str,selected))!=[asset_id(x) for x in calls]:errors.append(f"{label} 检索选择与资产调用不一致")
    if not calls and not str(search.get("gap_reason") or "").strip():errors.append(f"{label} 无匹配时必须记录缺口理由")
    if calls and str(search.get("gap_reason") or "").strip():errors.append(f"{label} 已命中时不得伪报缺口")
def check_plan(plan:dict,h:dict,name:str,status:str,props:dict,regular:dict,pain:dict,errors:list[str])->None:
    expected=fmap(h);rows=plan.get("core_frameworks")
    if not isinstance(rows,list):errors.append(f"{name} 缺少 core_frameworks");return
    if [str(x.get("core_framework_id") or "") for x in rows if isinstance(x,dict)]!=list(expected):errors.append(f"{name} 未完整保留大框架顺序")
    for row in rows:
        if not isinstance(row,dict):errors.append(f"{name} 含非法大框架行");continue
        ident=str(row.get("core_framework_id") or "");base=expected.get(ident)
        if not base:errors.append(f"{name}/{ident} 不是锁定大框架");continue
        for key in ("framework_block_id","framework_label","formal_framework_type","downstream_small_structure_ids"):
            if row.get(key)!=base.get(key):errors.append(f"{name}/{ident} 篡改大框架映射")
        claim=str(row.get("core_claim") or "");evidence=str(row.get("core_evidence") or "");method=str(row.get("evidence_method") or "")
        if name=="structure_four":
            if status=="user-pending" and (claim or evidence or method):errors.append(f"{name}/{ident} user-pending 时论点、论据和方法必须留空")
            if status=="frozen" and ((claim and not valid_statement(claim)) or (evidence and not valid_statement(evidence))):errors.append(f"{name}/{ident} frozen 内容格式非法")
            if any(key in row for key in ("proposition_ids","asset_calls","asset_search")):errors.append(f"{name}/{ident} 不得自动填命题或资产")
        elif name in {"structure_one","structure_two"}:
            if not valid_statement(claim) or not valid_statement(evidence) or method not in EVIDENCE_METHODS or row.get("framework_answer_obligation_id")!=f"OB-{ident}":errors.append(f"{name}/{ident} 必须填写单句论点、单句论据、论据方法并绑定回答义务")
            elif not evidence_method_matches(method,evidence):errors.append(f"{name}/{ident} 论据内容与标注的{method}手法不匹配")
            if re.sub(r"\W+","",claim)==re.sub(r"\W+","",evidence):errors.append(f"{name}/{ident} 论据不得复述论点")
            check_props(row,props,errors,f"{name}/{ident}")
            if "asset_calls" in row or "asset_search" in row:errors.append(f"{name}/{ident} 只有结构三可检索资产")
        else:
            calls=row.get("asset_calls") if isinstance(row.get("asset_calls"),list) else [];check_search(row,h,base,regular,pain,calls,errors,f"{name}/{ident}")
            if calls:
                if not valid_statement(claim) or not valid_statement(evidence) or method not in EVIDENCE_METHODS or row.get("framework_answer_obligation_id")!=f"OB-{ident}":errors.append(f"{name}/{ident} 命中后必须填写单句论点、单句论据和论据方法")
                elif not evidence_method_matches(method,evidence):errors.append(f"{name}/{ident} 论据内容与标注的{method}手法不匹配")
                if re.sub(r"\W+","",claim)==re.sub(r"\W+","",evidence):errors.append(f"{name}/{ident} 论据不得复述论点")
                used=check_props(row,props,errors,f"{name}/{ident}")
                for n,call in enumerate(calls,1):
                    if isinstance(call,dict):check_asset(call,h,base,regular,pain,used,errors,f"{name}/{ident}/asset[{n}]")
                    else:errors.append(f"{name}/{ident} 资产调用非法")
            elif claim or evidence or method or "proposition_ids" in row or "framework_answer_obligation_id" in row:errors.append(f"{name}/{ident} 无资产时不得伪造论点、论据或方法")
def validate_v15(h:dict,c:dict)->list[str]:
    """V15 first verifies the argument chain; assets may only fill that locked task."""
    from structure_v15 import STRUCTURES as V15_STRUCTURES, validate_logic_chain, validate_title_contract
    errors=[]
    if (h.get("schema"),c.get("schema")) != ("copy-structure-handoff-v15","copy-structure-v15"):errors.append("handoff/candidate 必须同时为 V15")
    for key in ("topic","benchmark_case_id","benchmark_path","benchmark_audit_receipt","benchmark_sha256","big_frameworks","final_copy_only_frameworks"):
        if c.get(key)!=h.get(key):errors.append(f"候选未锁定 handoff 的 {key}")
    errors.extend(validate_title_contract(c.get("title_contract")))
    expected=fmap(h); expected_ids=list(expected)
    all_rows=[x for x in h.get("big_frameworks",[]) if isinstance(x,dict)]; final_only=[x for x in h.get("final_copy_only_frameworks",[]) if isinstance(x,dict)]
    final_ids=[str(x.get("core_framework_id") or "") for x in final_only]
    if not all_rows or [str(x.get("core_framework_id") or "") for x in all_rows] != [f"CF-F{n:02d}" for n in range(1,len(all_rows)+1)]:errors.append("V15 big_frameworks 必须完整保持连续 FNN 顺序")
    if any(not str(x.get("framework_function") or "").strip() for x in all_rows):errors.append("V15 每个 FNN 大框架必须保留框架功能")
    if any(str(x.get("formal_framework_type") or "") not in FORMAL for x in expected.values()):errors.append("V15 核心框架只能包含正式内容类型")
    plans=c.get("structures") if isinstance(c.get("structures"),dict) else {}
    if set(plans)!={"structure_one","structure_two","structure_three","structure_four"}:errors.append("V15 必须且只能包含结构一至四")
    immutable=("framework_block_id","framework_label","framework_function","formal_framework_type","asset_framework_type")
    for name in V15_STRUCTURES:
        plan=plans.get(name) if isinstance(plans.get(name),dict) else {}; rows=plan.get("core_frameworks") if isinstance(plan.get("core_frameworks"),list) else []
        if [str(x.get("core_framework_id") or "") for x in rows if isinstance(x,dict)] != expected_ids:errors.append(f"{name} 未保持锁定的大框架顺序")
        for row in rows:
            if not isinstance(row,dict):errors.append(f"{name} 含非法大框架行");continue
            ident=str(row.get("core_framework_id") or "");base=expected.get(ident)
            if not base:continue
            for key in immutable:
                if row.get(key)!=base.get(key):errors.append(f"{name}/{ident} 未继承或篡改 {key}")
            if name in {"structure_one","structure_two","structure_three"}:
                chain=row.get("logic_chain") if isinstance(row.get("logic_chain"),dict) else {}
                for field in ("answering_question","previous_dependency","necessary_conclusion","removal_impact","next_question"):
                    if not str(chain.get(field) or "").strip():errors.append(f"{name}/{ident} 缺少 {field}")
            if name in {"structure_one","structure_two"} and (not valid_statement(row.get("core_claim")) or not isinstance(row.get("evidence_chain"),list) or not row.get("evidence_chain")):errors.append(f"{name}/{ident} 必须在已锁定逻辑任务后填写论点与论据")
            if name=="structure_three":
                sources=row.get("processing_sources"); has_content=bool(str(row.get("core_claim") or "").strip())
                if has_content and not isinstance(sources,list):errors.append(f"structure_three/{ident} 非空内容缺少 processing_sources")
                if not has_content and sources:errors.append(f"structure_three/{ident} 未命中时不得保留出处")
                for source in sources or []:
                    path=Path(str(source.get("path") or ""));absolute=(Path(__file__).resolve().parents[3]/path).resolve()
                    if not path.as_posix().startswith(PROCESSING_ROOT+"/"):errors.append(f"structure_three/{ident} 出处不在处理库")
                    elif not absolute.is_file() or source.get("sha256")!=sha(absolute):errors.append(f"structure_three/{ident} 出处文件或哈希不一致")
                    if source.get("framework_type")!=base.get("formal_framework_type"):errors.append(f"structure_three/{ident} 出处模块类型不一致")
    mothers=[str((plans.get(name) or {}).get("mother_logic") or "").strip() for name in ("structure_one","structure_two","structure_three")]
    if any(not x for x in mothers) or len(set(mothers))!=3:errors.append("三条结构必须各有不同且非空的母逻辑")
    return errors
def validate_v16(h:dict,c:dict)->list[str]:
    """V16 keeps V15 chain invariants and adds literal source proof for structure three."""
    import copy
    from structure_v16 import validate_source_evidence
    legacy_h,legacy_c=copy.deepcopy(h),copy.deepcopy(c)
    legacy_h["schema"]="copy-structure-handoff-v15";legacy_c["schema"]="copy-structure-v15"
    errors=validate_v15(legacy_h,legacy_c)
    if (h.get("schema"),c.get("schema")) != ("copy-structure-handoff-v16","copy-structure-v16"):
        errors.append("handoff/candidate 必须同时为 V16")
    for row in ((c.get("structures") or {}).get("structure_three") or {}).get("core_frameworks",[]):
        if isinstance(row,dict) and str(row.get("core_claim") or "").strip():
            errors.extend(f"structure_three/{row.get('core_framework_id')} {item}" for item in validate_source_evidence(row))
    return errors
def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--handoff",type=Path,required=True);p.add_argument("--candidate",type=Path,required=True);a=p.parse_args();h=json.loads(a.handoff.read_text(encoding="utf-8"));c=json.loads(a.candidate.read_text(encoding="utf-8"));errors=[]
    if h.get("schema")=="copy-structure-handoff-v13" or c.get("schema")=="copy-structure-v13":
        from structure_v13 import validate_v13
        errors=validate_v13(h,c)
        if errors:
            print("FAIL\\n"+"\\n".join("- "+item for item in errors));return 1
        print(f"PASS V13: {len(h.get('core_frameworks', []))} 个核心大框架已绑定具体内容对象；结构三未命中资产保持留白");return 0
    if h.get("schema")=="copy-structure-handoff-v15" or c.get("schema")=="copy-structure-v15":
        errors=validate_v15(h,c)
        if errors:
            print("FAIL\\n"+"\\n".join("- "+item for item in errors));return 1
        print(f"PASS V15: {len(h.get('core_frameworks', []))} 个核心大框架已继承元数据，并先锁定标题扣题合同与 FNN 推进链");return 0
    if h.get("schema")=="copy-structure-handoff-v16" or c.get("schema")=="copy-structure-v16":
        errors=validate_v16(h,c)
        if errors:
            print("FAIL\\n"+"\\n".join("- "+item for item in errors));return 1
        print(f"PASS V16: {len(h.get('core_frameworks', []))} 个核心大框架通过标题、母逻辑、FNN 链及结构三原文证据门禁");return 0
    if h.get("schema")=="copy-structure-handoff-v14" or c.get("schema")=="copy-structure-v14":
        if (h.get("schema"),c.get("schema")) != ("copy-structure-handoff-v14","copy-structure-v14"):
            errors.append("handoff/candidate 必须同时为 V14")
        for key in ("topic","benchmark_case_id","benchmark_path","benchmark_audit_receipt","benchmark_sha256","big_frameworks","final_copy_only_frameworks"):
            if c.get(key)!=h.get(key): errors.append(f"候选未锁定 handoff 的 {key}")
        if "structure_segments" in h or "structure_segments" in c or "small_structure" in json.dumps({"handoff":h,"candidate":c},ensure_ascii=False):
            errors.append("V14 不得含小结构或 structure_segments")
        expected=[str(x.get("core_framework_id") or "") for x in h.get("core_frameworks",[]) if isinstance(x,dict)]
        all_rows=[x for x in h.get("big_frameworks",[]) if isinstance(x,dict)]
        final_only=[x for x in h.get("final_copy_only_frameworks",[]) if isinstance(x,dict)]
        all_ids=[str(x.get("core_framework_id") or "") for x in all_rows]
        core_ids=expected;final_ids=[str(x.get("core_framework_id") or "") for x in final_only]
        if not all_rows or all_ids!=[f"CF-F{n:02d}" for n in range(1,len(all_ids)+1)]:errors.append("V14 big_frameworks 必须完整保持连续 FNN 顺序")
        if any(not str(x.get("framework_function") or "").strip() for x in all_rows):errors.append("V14 每个完整 FNN 大框架必须锁定非原文的框架功能定义")
        if any(str(x.get("formal_framework_type") or "") not in FORMAL for x in h.get("core_frameworks",[]) if isinstance(x,dict)):errors.append("core_frameworks 只能包含可映射处理库的正式内容类型")
        if any(x.get("formal_framework_type") is not None or x.get("generation_owner")!="final-copy" for x in final_only):errors.append("final_copy_only_frameworks 必须仅包含非处理库支撑段并归正文生成")
        if [ident for ident in all_ids if ident in core_ids or ident in final_ids]!=all_ids or set(core_ids)&set(final_ids):errors.append("核心框架与正文专属框架必须无重叠且完整覆盖 FNN")
        if any(not str(x.get("framework_function") or "").strip() for x in final_only):errors.append("正文专属框架必须保留其框架功能定义")
        plans=c.get("structures") if isinstance(c.get("structures"),dict) else {}
        if set(plans)!={"structure_one","structure_two","structure_three","structure_four"}: errors.append("V14 必须且只能包含结构一至四")
        for name in ("structure_one","structure_two","structure_three","structure_four"):
            rows=plans.get(name,{}).get("core_frameworks",[]) if isinstance(plans.get(name),dict) else []
            if [str(x.get("core_framework_id") or "") for x in rows if isinstance(x,dict)] != expected: errors.append(f"{name} 未保持锁定的大框架顺序")
            if any(str(x.get("core_framework_id") or "") in final_ids for x in rows if isinstance(x,dict)):errors.append(f"{name} 混入仅供正文生成的支撑段")
        for row in plans.get("structure_three",{}).get("core_frameworks",[]):
            if not isinstance(row,dict): continue
            ident=str(row.get("core_framework_id") or "")
            expected_type=next((str(x.get("formal_framework_type") or "") for x in h.get("core_frameworks",[]) if x.get("core_framework_id")==ident),"")
            has_content=bool(str(row.get("core_claim") or "").strip()); sources=row.get("processing_sources")
            if "source_note" in row: errors.append(f"structure_three/{ident} 禁止 source_note")
            if has_content and not isinstance(sources,list): errors.append(f"structure_three/{ident} 非空内容缺少 processing_sources"); continue
            if not has_content and sources: errors.append(f"structure_three/{ident} 未命中时不得保留出处")
            for source in sources or []:
                path=Path(str(source.get("path") or "")); absolute=(Path(__file__).resolve().parents[3]/path).resolve()
                if not str(path).replace("\\","/").startswith(PROCESSING_ROOT+"/"): errors.append(f"structure_three/{ident} 出处不在处理库")
                elif not absolute.is_file(): errors.append(f"structure_three/{ident} 出处文件不存在")
                elif source.get("sha256")!=sha(absolute): errors.append(f"structure_three/{ident} 出处哈希不一致")
                if source.get("framework_type")!=expected_type: errors.append(f"structure_three/{ident} 出处模块类型不一致")
        if errors:
            print("FAIL\\n"+"\\n".join("- "+item for item in errors));return 1
        print(f"PASS V14: {len(expected)} 个核心大框架按 FNN 顺序锁定；未接受小结构字段");return 0
    if h.get("schema")=="copy-structure-handoff-v12" or c.get("schema")=="copy-structure-v12":
        from validate_structure_v12 import validate
        errors=validate(h,c)
        if errors:
            print("FAIL\n"+"\n".join("- "+item for item in errors));return 1
        print(f"PASS V12: {len(h.get('core_frameworks', []))} 个可见大框架，均已绑定内容功能合同与论据链");return 0
    if h.get("schema")!="copy-structure-handoff-v11" or c.get("schema")!="copy-structure-v11":errors.append("handoff/candidate schema 必须为 v11/v11")
    for where in forbidden(h.get("core_frameworks",[])):errors.append(f"handoff 前台框架含禁用字段：{where}")
    for where in forbidden(c.get("structures",{})):errors.append(f"候选前台结构含禁用字段：{where}")
    for key in ("topic","benchmark_case_id","benchmark_path","benchmark_audit_receipt","benchmark_framework_sha256","processing_index_sha256","pain_angle_index_sha256","topic_analysis_sha256","topic_table_binding"):
        if c.get(key)!=h.get(key):errors.append(f"候选未锁定 handoff 的 {key}")
    if c.get("structure_segments")!=h.get("structure_segments"):errors.append("候选未锁定后台 structure_segments")
    check_segments(h,errors);props=pmap(h)
    if not 2<=len(props)<=5 or not set(h.get("topic_structure_types") or []).issubset(TOPIC_TYPES):errors.append("handoff 命题不合法")
    try:
        regular,pain=load_index(Path(h["processing_index"])),load_index(Path(h["pain_angle_index"]))
        if sha(Path(h["processing_index"]))!=h.get("processing_index_sha256") or sha(Path(h["pain_angle_index"]))!=h.get("pain_angle_index_sha256"):errors.append("调用索引已漂移")
    except Exception as exc:errors.append(f"调用索引不可读：{exc}");regular,pain={},{}
    plans=c.get("structures") if isinstance(c.get("structures"),dict) else {}
    if set(plans)!=set(STRUCTURES):errors.append("候选必须且只能包含结构一至四")
    for name in STRUCTURES:check_plan(plans.get(name,{}) if isinstance(plans.get(name),dict) else {},h,name,str(c.get("structure_four_status") or ""),props,regular,pain,errors)
    routes=[]
    for name in ("structure_one","structure_two","structure_three"):
        plan=plans.get(name,{}) if isinstance(plans.get(name),dict) else {};route=plan.get("argument_route") if isinstance(plan.get("argument_route"),dict) else {};steps=plan.get("progression_logic")
        if not nonempty(route,ROUTE_FIELDS) or not str(plan.get("non_overlap_rationale") or "").strip() or not isinstance(steps,list) or not 4<=len(steps)<=7 or not all(str(x).strip() for x in steps):errors.append(f"{name} 缺少完整论证路线或 4-7 步推进逻辑")
        else:routes.append(tuple(re.sub(r"\W+","",str(route.get(x))) for x in ROUTE_FIELDS))
    if len(routes)==3 and (len(set(routes))!=3 or any(len({route[index] for route in routes})!=3 for index in (0,1,2,3,5))):errors.append("三条路线的核心问题、判断、因果机制、说服路径或最终落点存在直接重叠")
    one={str(x.get("core_framework_id")):(re.sub(r"\W+","",str(x.get("core_claim") or "")),re.sub(r"\W+","",str(x.get("core_evidence") or ""))) for x in (plans.get("structure_one",{}) or {}).get("core_frameworks",[]) if isinstance(x,dict)};two={str(x.get("core_framework_id")):(re.sub(r"\W+","",str(x.get("core_claim") or "")),re.sub(r"\W+","",str(x.get("core_evidence") or ""))) for x in (plans.get("structure_two",{}) or {}).get("core_frameworks",[]) if isinstance(x,dict)}
    for ident in set(one)&set(two):
        if one[ident]==two[ident]:errors.append(f"结构一、二在 {ident} 同时复用了论点与论据")
    if errors:print("FAIL\n"+"\n".join("- "+x for x in errors));return 1
    print(f"PASS: {len(fmap(h))} 个可见大框架；小框架仅保留在后台 structure_segments");return 0
if __name__=="__main__":raise SystemExit(main())
