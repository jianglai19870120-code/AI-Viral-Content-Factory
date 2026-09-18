#!/usr/bin/env python3
"""Prepare a V5 final-copy task from a filled or workbench-frozen Structure Four."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from workflow.topic_structure_releases import resolve_filled_structure_input, verified_release_bindings
from workflow.writing_contract import guidance_snapshot, resolve_contract, rule_ids, validate_guidance_snapshot

HEADER=['编号','大框架','核心内容']
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def row(line:str)->list[str]:return [x.strip() for x in line.strip().strip('|').split('|')]
def current_candidate(topic:str,case:str,source:Path,input_mode:str)->tuple[dict,dict]:
    if input_mode == 'owner-frozen':
        entry=verified_release_bindings().get((topic,case))
        if entry is None or not entry.get('structure_four_frozen'):
            raise ValueError('工作台正文计划必须绑定当前、已冻结的文案结构')
        expected_source=Path(str(entry.get('output_path') or '')).resolve()
        if expected_source != source.resolve() or entry.get('output_sha256') != digest(source):
            raise ValueError('工作台正文计划必须使用当前带 √ 且哈希可核验的冻结结构四')
    elif input_mode == 'owner-filled-direct':
        entry=resolve_filled_structure_input(structure_markdown=source)
        if entry.get('topic') != topic or entry.get('benchmark_case_id') != case:
            raise ValueError('直接正文计划的填写结构四与标题或对标编号不一致')
    else:raise ValueError('未知结构四输入模式')
    path=Path(str(entry.get('candidate_path') or ''));data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 'copy-structure-v19':raise ValueError('新正文只接受当前 copy-structure-v19 结构候选')
    try:
        binding=data.get('writing_contract') if isinstance(data.get('writing_contract'),dict) else {}
        resolve_contract(binding)
        validate_guidance_snapshot(data.get('writing_contract_guidance_snapshot'), binding, 'structure')
    except ValueError as exc:raise ValueError('当前结构的写作文案表达合同不可验证') from exc
    return data,entry
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--structure-markdown',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--input-mode',choices=('owner-filled-direct','owner-frozen'),default='owner-filled-direct');a=p.parse_args()
    source=a.structure_markdown.resolve();lines=source.read_text(encoding='utf-8').splitlines()
    title=next((x.removeprefix('# 文案结构｜').strip() for x in lines if x.startswith('# 文案结构｜')),'')
    case=next((x.removeprefix('对标复刻拆解：').strip() for x in lines if x.startswith('对标复刻拆解：')),'')
    section=next((i for i,x in enumerate(lines) if x.strip()=='## 结构四'),None)
    if not title or not case or section is None:raise SystemExit('结构四缺少标题、对标编号或结构四章节')
    starts=[i for i,x in enumerate(lines[section+1:],section+1) if row(x)==HEADER]
    if len(starts)!=1:raise SystemExit('结构四必须且只能有一张 FNN 核心框架表')
    candidate,entry=current_candidate(title,case,source,a.input_mode)
    expected_core=[x for x in ((candidate.get('structures') or {}).get('structure_four') or {}).get('core_frameworks',[]) if isinstance(x,dict)]
    expected_ids=[str(x.get('framework_block_id') or '') for x in expected_core]
    filled=[];i=starts[0]+2
    while i<len(lines) and lines[i].lstrip().startswith('|'):
        values=row(lines[i])
        if len(values)!=3 or not all(values):raise SystemExit('结构四每个核心 FNN 框架必须填写非空核心内容')
        ident,label,content=values;filled.append({'framework_id':ident,'framework_label':label,'filled_content':content});i+=1
    if not filled or [x['framework_id'] for x in filled]!=expected_ids:raise SystemExit('结构四必须完整保持当前正式核心框架的相对 FNN 顺序')
    if any(item['framework_label']!=str(expected_core[n].get('framework_label') or '') for n,item in enumerate(filled)):raise SystemExit('结构四大框架名称与当前正式结构不一致')
    contract_binding=candidate.get('writing_contract') if isinstance(candidate.get('writing_contract'),dict) else {}
    resolve_contract(contract_binding)
    filled_by_id={x['framework_id']:x for x in filled};support={str(x.get('framework_block_id') or ''):x for x in candidate.get('final_copy_only_frameworks',[]) if isinstance(x,dict)}
    all_rows=[x for x in candidate.get('big_frameworks',[]) if isinstance(x,dict)]
    ids=[str(x.get('framework_block_id') or '') for x in all_rows]
    if not all_rows or any(not str(x.get('framework_function') or '').strip() for x in all_rows):raise SystemExit('当前正式结构缺少完整 FNN 框架功能定义；需先受控更新结构候选')
    frameworks=[]
    for n,base in enumerate(all_rows):
        ident=ids[n];previous=ids[n-1] if n else '';following=ids[n+1] if n+1<len(ids) else ''
        if ident in filled_by_id:
            value=filled_by_id[ident]
            framework={**value,'framework_function':str(base['framework_function']),'generation_owner':'structure-core','content_source':'user-filled-structure-four','previous_framework_id':previous,'next_framework_id':following}
            frameworks.append(framework)
        else:
            bridge=support.get(ident)
            if bridge is None:raise SystemExit('当前结构的非核心 FNN 框架未作为正文专属框架交接')
            frameworks.append({'framework_id':ident,'framework_label':str(base.get('framework_label') or ''),'framework_function':str(base['framework_function']),'filled_content':'','generation_owner':'final-copy','content_source':'ai-framework-function','generation_instruction':str(bridge.get('generation_instruction') or ''),'previous_framework_id':previous,'next_framework_id':following})
    payload={'schema':'final-copy-plan-v5','topic':title,'benchmark_case_id':case,'structure_markdown':str(source),'structure_markdown_sha256':digest(source),'structure_candidate_path':str(Path(str(entry['candidate_path'])).resolve()),'structure_candidate_sha256':digest(Path(str(entry['candidate_path']))),'structure_input_authority':str(entry.get('structure_input_authority') or a.input_mode),'frameworks':frameworks,'content_source':'完整 FNN 按结构四人工填写的大框架内容生成；不得读取、携带或校验小框架上下文，也不读取额外对标原文、处理库或输入库。','writing_contract':contract_binding,'writing_contract_rule_ids':rule_ids(contract_binding,'final-copy'),'writing_contract_guidance_snapshot':guidance_snapshot(contract_binding,'final-copy')}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'prepared','frameworks':len(frameworks),'coreFrameworks':len(filled)},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
