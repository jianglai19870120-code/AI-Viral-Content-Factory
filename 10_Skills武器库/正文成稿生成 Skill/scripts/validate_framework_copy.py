#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
from framework_copy_contract import WRITING_METHODS,method_matches
from render_framework_copy import render_annotations

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from workflow.writing_contract import mechanical_checks_for, resolve_contract, rule_ids, validate_guidance_snapshot

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);a=p.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf-8'));candidate=json.loads(a.candidate.read_text(encoding='utf-8'))
    errors=[]
    if (plan.get('schema'),candidate.get('schema')) != ('final-copy-plan-v5','final-copy-v5'):errors.append('新正文必须使用完整 FNN V5 正文合同')
    if candidate.get('plan_sha256')!=digest(a.plan):errors.append('候选未绑定当前人工填写结构四计划')
    contract=None
    if candidate.get('writing_contract')!=plan.get('writing_contract'):errors.append('V5 写作文案表达合同未随正文候选锁定')
    else:
        try:contract=resolve_contract(plan.get('writing_contract') if isinstance(plan.get('writing_contract'),dict) else {})
        except ValueError:errors.append('V5 写作文案表达合同缺失、版本错误或哈希漂移')
    if contract:
        if 'small_framework_context' in plan or 'small_framework_context' in candidate:
            errors.append('新正文计划或候选不得携带小框架上下文')
        expected_rule_ids=rule_ids(plan.get('writing_contract'),'final-copy')
        if plan.get('writing_contract_rule_ids')!=expected_rule_ids or candidate.get('writing_contract_rule_ids')!=expected_rule_ids:
            errors.append('V3 正文未随计划和候选锁定写作文案表达合同规则索引')
        try:
            validate_guidance_snapshot(plan.get('writing_contract_guidance_snapshot'), plan.get('writing_contract'), 'final-copy')
            validate_guidance_snapshot(candidate.get('writing_contract_guidance_snapshot'), plan.get('writing_contract'), 'final-copy')
        except ValueError:
            errors.append('V3 正文未随计划和候选锁定完整口播原文与规则快照')
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
        if contract:
            for check in mechanical_checks_for(plan['writing_contract'], 'final-copy'):
                if check.get('kind')=='forbidden-phrases' and any(str(value) in text for value in check.get('phrases', [])):
                    errors.append(f"{ident}：{check['message']}")
                if check.get('kind')=='isolated-corporate-cliche' and any(__import__('re').search(str(pattern), text) for pattern in check.get('patterns', [])):
                    errors.append(f"{ident}：{check['message']}")
        if primary not in WRITING_METHODS or not method_matches(primary,text):errors.append(f'{ident} 主写作手法缺失或与正文不匹配')
        if not isinstance(auxiliary,list) or any(str(method) not in WRITING_METHODS or str(method)==primary for method in auxiliary):errors.append(f'{ident} 辅写作手法不合格')
        if not reason:errors.append(f'{ident} 缺少写作手法选择理由')
        if owner=='structure-core' and (not str(planned.get('filled_content') or '').strip() or actual_row.get('filled_content')!=planned.get('filled_content')):errors.append(f'{ident} 未锁定用户填写内容')
        if owner=='final-copy' and (str(actual_row.get('filled_content') or '').strip() or not str(actual_row.get('generation_instruction') or '').strip()):errors.append(f'{ident} 非核心框架不得伪装为用户填写内容')
        if owner=='final-copy' and not str(actual_row.get('framework_function') or '').strip():errors.append(f'{ident} 非核心框架缺少功能定义')
        if contract:
            if 'small_framework_context' in planned or 'small_framework_context' in actual_row:errors.append(f'{ident} 新正文不得携带或校验小框架上下文')
            if owner=='structure-core' and actual_row.get('content_source')!='user-filled-structure-four':errors.append(f'{ident} 新正文必须只以结构四大框架内容为核心输入')
    expected_annotations=render_annotations(plan,candidate)
    if not a.annotations.is_file() or a.annotations.read_text(encoding='utf-8')!=expected_annotations:errors.append('段落注释未由当前计划和候选渲染')
    if errors:print('FAIL\n'+'\n'.join('- '+x for x in errors));return 1
    print(f'PASS: {len(expected)} 个完整 FNN 大框架、写作手法与段落注释');return 0
if __name__=='__main__':raise SystemExit(main())
