#!/usr/bin/env python3
"""Prepare a V3 final-copy task from frozen core frameworks and full FNN order."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from workflow.topic_structure_releases import verified_release_bindings

HEADER=['编号','核心大框架','核心内容']
def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def row(line:str)->list[str]:return [x.strip() for x in line.strip().strip('|').split('|')]
def current_candidate(topic:str,case:str,source:Path)->tuple[dict,dict]:
    entry=verified_release_bindings().get((topic,case))
    if entry is None:raise ValueError('正文计划必须绑定当前、已审核发布的文案结构')
    expected_source=Path(str(entry.get('output_path') or '')).resolve()
    if expected_source != source.resolve() or entry.get('output_sha256') != digest(source):
        raise ValueError('正文计划必须使用当前有效的正式结构输入；人工冻结结构四须以带 √ 的当前文件和当前哈希调用')
    path=Path(str(entry.get('candidate_path') or ''));data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') not in {'copy-structure-v14','copy-structure-v15','copy-structure-v16'}:raise ValueError('当前结构不是可用于正文的正式候选')
    return data,entry
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--structure-markdown',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    source=a.structure_markdown.resolve();lines=source.read_text(encoding='utf-8').splitlines()
    title=next((x.removeprefix('# 文案结构｜').strip() for x in lines if x.startswith('# 文案结构｜')),'')
    case=next((x.removeprefix('对标复刻拆解：').strip() for x in lines if x.startswith('对标复刻拆解：')),'')
    section=next((i for i,x in enumerate(lines) if x.strip()=='## 结构四'),None)
    if not title or not case or section is None:raise SystemExit('结构四缺少标题、对标编号或结构四章节')
    starts=[i for i,x in enumerate(lines[section+1:],section+1) if row(x)==HEADER]
    if len(starts)!=1:raise SystemExit('结构四必须且只能有一张 FNN 核心框架表')
    candidate,entry=current_candidate(title,case,source)
    expected_core=[x for x in ((candidate.get('structures') or {}).get('structure_four') or {}).get('core_frameworks',[]) if isinstance(x,dict)]
    expected_ids=[str(x.get('framework_block_id') or '') for x in expected_core]
    frozen=[];i=starts[0]+2
    while i<len(lines) and lines[i].lstrip().startswith('|'):
        values=row(lines[i])
        if len(values)!=3 or not all(values):raise SystemExit('结构四每个核心 FNN 框架必须填写非空核心内容')
        ident,label,content=values;frozen.append({'framework_id':ident,'framework_label':label,'frozen_content':content});i+=1
    if not frozen or [x['framework_id'] for x in frozen]!=expected_ids:raise SystemExit('结构四必须完整保持当前正式核心框架的相对 FNN 顺序')
    if any(item['framework_label']!=str(expected_core[n].get('framework_label') or '') for n,item in enumerate(frozen)):raise SystemExit('结构四核心大框架名称与当前正式结构不一致')
    frozen_by_id={x['framework_id']:x for x in frozen};support={str(x.get('framework_block_id') or ''):x for x in candidate.get('final_copy_only_frameworks',[]) if isinstance(x,dict)}
    all_rows=[x for x in candidate.get('big_frameworks',[]) if isinstance(x,dict)]
    ids=[str(x.get('framework_block_id') or '') for x in all_rows]
    if not all_rows or any(not str(x.get('framework_function') or '').strip() for x in all_rows):raise SystemExit('当前正式结构缺少完整 FNN 框架功能定义；需先受控更新结构候选')
    frameworks=[]
    for n,base in enumerate(all_rows):
        ident=ids[n];previous=ids[n-1] if n else '';following=ids[n+1] if n+1<len(ids) else ''
        if ident in frozen_by_id:
            value=frozen_by_id[ident]
            frameworks.append({**value,'framework_function':str(base['framework_function']),'generation_owner':'structure-core','content_source':'user-frozen','previous_framework_id':previous,'next_framework_id':following})
        else:
            bridge=support.get(ident)
            if bridge is None:raise SystemExit('当前结构的非核心 FNN 框架未作为正文专属框架交接')
            frameworks.append({'framework_id':ident,'framework_label':str(base.get('framework_label') or ''),'framework_function':str(base['framework_function']),'frozen_content':'','generation_owner':'final-copy','content_source':'ai-framework-function','generation_instruction':str(bridge.get('generation_instruction') or ''),'previous_framework_id':previous,'next_framework_id':following})
    payload={'schema':'final-copy-plan-v3','topic':title,'benchmark_case_id':case,'structure_markdown':str(source),'structure_markdown_sha256':digest(source),'structure_candidate_path':str(Path(str(entry['candidate_path'])).resolve()),'structure_candidate_sha256':digest(Path(str(entry['candidate_path']))),'structure_input_authority':str(entry.get('structure_input_authority') or 'audit-released'),'frameworks':frameworks,'content_source':'完整 FNN 只使用已审核框架名称和功能定义；核心段扩写用户冻结结构四，非核心段依据框架功能与相邻推进关系补足，不读取对标原文、逐句画像、处理库或输入库。'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':'prepared','frameworks':len(frameworks),'coreFrameworks':len(frozen)},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
