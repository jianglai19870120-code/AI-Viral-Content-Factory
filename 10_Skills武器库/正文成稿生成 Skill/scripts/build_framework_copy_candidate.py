#!/usr/bin/env python3
"""Bind V5 authored FNN sections and render their companion annotations."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from framework_copy_contract import WRITING_METHODS
from render_framework_copy import render_annotations

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--texts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);a=p.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf-8'));texts=json.loads(a.texts.read_text(encoding='utf-8'))
    schema=str(plan.get('schema') or '')
    if schema != 'final-copy-plan-v5' or not isinstance(texts,dict):raise SystemExit('新正文只接受完整 FNN 的 V5 正文计划与 JSON 段落映射')
    expected=[x['framework_id'] for x in plan['frameworks']]
    if set(texts)!=set(expected):raise SystemExit('texts 必须且只能为每个 FNN 大框架提供一段正文')
    mappings=[]
    for framework in plan['frameworks']:
        ident=framework['framework_id'];authored=texts.get(ident)
        if not isinstance(authored,dict):raise SystemExit(f'{ident} 必须提供正文、主写作手法、辅手法和选择理由')
        text=str(authored.get('text') or '').strip();primary=str(authored.get('primary_writing_method') or '').strip()
        auxiliary=authored.get('auxiliary_writing_methods',[]);reason=str(authored.get('method_rationale') or '').strip()
        if not text or primary not in WRITING_METHODS or not isinstance(auxiliary,list) or any(str(x) not in WRITING_METHODS or str(x)==primary for x in auxiliary) or not reason:
            raise SystemExit(f'{ident} 的正文或写作手法元数据不合格')
        mappings.append({**framework,'text':text,'primary_writing_method':primary,'auxiliary_writing_methods':[str(x) for x in auxiliary],'method_rationale':reason})
    payload={'schema':'final-copy-v5','topic':plan['topic'],'benchmark_case_id':plan['benchmark_case_id'],'plan_sha256':digest(a.plan),'framework_mappings':mappings,'writing_contract':plan.get('writing_contract'),'writing_contract_rule_ids':plan.get('writing_contract_rule_ids'),'writing_contract_guidance_snapshot':plan.get('writing_contract_guidance_snapshot')}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    a.annotations.parent.mkdir(parents=True,exist_ok=True);a.annotations.write_text(render_annotations(plan,payload),encoding='utf-8')
    print(json.dumps({'status':'built','frameworks':len(expected),'annotations':str(a.annotations)},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
