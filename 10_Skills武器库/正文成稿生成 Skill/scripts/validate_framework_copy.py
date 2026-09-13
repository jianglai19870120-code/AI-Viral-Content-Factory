#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from framework_copy_contract import WRITING_METHODS,method_matches
from render_framework_copy import render_annotations

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);a=p.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf-8'));candidate=json.loads(a.candidate.read_text(encoding='utf-8'))
    errors=[]
    if plan.get('schema')!='final-copy-plan-v3' or candidate.get('schema')!='final-copy-v3':errors.append('必须使用完整 FNN 的 V3 正文合同')
    if candidate.get('plan_sha256')!=digest(a.plan):errors.append('候选未绑定当前冻结结构四计划')
    expected=[x.get('framework_id') for x in plan.get('frameworks',[]) if isinstance(x,dict)];actual=[x.get('framework_id') for x in candidate.get('framework_mappings',[]) if isinstance(x,dict)]
    if actual!=expected:errors.append('正文必须按完整 FNN 顺序且仅一次覆盖每个大框架')
    mappings=candidate.get('framework_mappings',[])
    for planned,actual_row in zip(plan.get('frameworks',[]),mappings):
        if not isinstance(planned,dict) or not isinstance(actual_row,dict):continue
        ident=str(planned.get('framework_id') or '');owner=str(planned.get('generation_owner') or '')
        for key in ('framework_label','framework_function','generation_owner','content_source','previous_framework_id','next_framework_id'):
            if actual_row.get(key)!=planned.get(key):errors.append(f'{ident} 的 {key} 漂移')
        text=str(actual_row.get('text') or '').strip();primary=str(actual_row.get('primary_writing_method') or '').strip();auxiliary=actual_row.get('auxiliary_writing_methods',[]);reason=str(actual_row.get('method_rationale') or '').strip()
        if not text:errors.append(f'{ident} 正文不能为空')
        if primary not in WRITING_METHODS or not method_matches(primary,text):errors.append(f'{ident} 主写作手法缺失或与正文不匹配')
        if not isinstance(auxiliary,list) or any(str(method) not in WRITING_METHODS or str(method)==primary for method in auxiliary):errors.append(f'{ident} 辅写作手法不合格')
        if not reason:errors.append(f'{ident} 缺少写作手法选择理由')
        if owner=='structure-core' and (not str(planned.get('frozen_content') or '').strip() or actual_row.get('frozen_content')!=planned.get('frozen_content')):errors.append(f'{ident} 未锁定用户冻结内容')
        if owner=='final-copy' and (str(actual_row.get('frozen_content') or '').strip() or not str(actual_row.get('generation_instruction') or '').strip()):errors.append(f'{ident} 非核心框架不得伪装为用户冻结内容')
        if owner=='final-copy' and not str(actual_row.get('framework_function') or '').strip():errors.append(f'{ident} 非核心框架缺少功能定义')
    expected_annotations=render_annotations(plan,candidate)
    if not a.annotations.is_file() or a.annotations.read_text(encoding='utf-8')!=expected_annotations:errors.append('段落注释未由当前计划和候选渲染')
    if errors:print('FAIL\n'+'\n'.join('- '+x for x in errors));return 1
    print(f'PASS: {len(expected)} 个完整 FNN 大框架、写作手法与段落注释');return 0
if __name__=='__main__':raise SystemExit(main())
