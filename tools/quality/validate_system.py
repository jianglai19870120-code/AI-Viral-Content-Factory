#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); r=a.root; reg=json.loads((r/'00_系统说明/system-registry.json').read_text(encoding='utf-8')); errors=[]
    if reg.get('pipeline',{}).get('id')!='universal-copy-v1': errors.append('通用流水线未启用')
    for skill in reg.get('skills',[]):
        source_root=r/'10_Skills武器库'/skill['sourceDir']
        source=source_root/'SKILL.md'
        member_placeholder='（会员专享）' in source_root.name and (source_root/'.gitkeep').is_file()
        if skill.get('status')!='active' or (not source.is_file() and not member_placeholder): errors.append('Skill 无效：'+skill['id'])
    for relative in ('schemas/copy-structure-v16.schema.json','schemas/final-copy-v3.schema.json'):
        if not (r/relative).is_file(): errors.append('通用文案 schema 缺失：'+relative)
    for path in ('02_资产中心/03_输出库/01_文案结构','02_资产中心/03_输出库/02_正文成稿','02_资产中心/05_案例库/02_对标复刻拆解'):
        if not (r/path).is_dir(): errors.append('目录缺失：'+path)
    if not (r/'00_系统说明/benchmark-case-registry.json').is_file(): errors.append('案例编号登记表缺失')
    cases=json.loads((r/'00_系统说明/benchmark-case-registry.json').read_text(encoding='utf-8')).get('cases',[]); ids=[]
    for case in cases:
        cid=str(case.get('id') or ''); ids.append(cid)
        breakdown=r/str(case.get('breakdownPath') or '')
        receipt=r/'01_Agent系统/02_小审-质量审核Agent/00_正式审核回执/benchmark-video-structure'/f'{cid}_审核回执.json'
        member_root=next((parent for parent in breakdown.parents if '（会员专享）' in parent.name),None)
        placeholder=member_root is not None and (member_root/'.gitkeep').is_file()
        if not __import__('re').fullmatch(r'[A-Z]{3}-\d{3}',cid) or (not breakdown.is_file() and not placeholder): errors.append('案例编号资产不完整：'+cid)
    if len(ids)!=len(set(ids)): errors.append('案例编号重复')
    print(json.dumps({'status':'passed' if not errors else 'failed','failures':errors},ensure_ascii=False)); return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
