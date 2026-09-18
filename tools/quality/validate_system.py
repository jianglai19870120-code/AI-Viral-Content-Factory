#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--root',type=Path,required=True); a=p.parse_args(); r=a.root; reg=json.loads((r/'00_系统说明/system-registry.json').read_text(encoding='utf-8')); errors=[]
    if reg.get('pipeline',{}).get('id')!='universal-copy-v1': errors.append('通用流水线未启用')
    for skill in reg.get('skills',[]):
        if skill.get('status')!='active' or not (r/'10_Skills武器库'/skill['sourceDir']/'SKILL.md').is_file(): errors.append('Skill 无效：'+skill['id'])
    # Only the live contracts are a release requirement.  Requiring retired
    # schemas made an otherwise V19/V5-only workflow fail validation.
    for relative in ('10_Skills武器库/文案结构生成 Skill/schemas/copy-structure-v19.schema.json','10_Skills武器库/正文成稿生成 Skill/schemas/final-copy-v5.schema.json'):
        if not (r/relative).is_file(): errors.append('通用文案 schema 缺失：'+relative)
    for path in ('02_资产中心/03_输出库/01_文案结构','02_资产中心/03_输出库/02_正文成稿','02_资产中心/05_案例库/02_对标复刻拆解','01_Agent系统/02_小审-质量审核Agent/00_正式审核回执/benchmark-video-structure'):
        if not (r/path).is_dir(): errors.append('目录缺失：'+path)
    if not (r/'00_系统说明/benchmark-case-registry.json').is_file(): errors.append('案例编号登记表缺失')
    case_registry=json.loads((r/'00_系统说明/benchmark-case-registry.json').read_text(encoding='utf-8'))
    cases=case_registry.get('cases',[]); ids=[]
    for case in cases:
        cid=str(case.get('id') or ''); ids.append(cid)
        breakdown=r/str(case.get('breakdownPath') or '')
        manual_policy=str(case.get('manualEditPolicy') or case_registry.get('manualEditPolicy') or '') == 'owner-approved'
        receipt=(
            r/'01_Agent系统/01_小姜-CEO助理Agent/人工确认回执/benchmark-video-structure'/f'{cid}_人工确认回执.json'
            if manual_policy else r/'01_Agent系统/02_小审-质量审核Agent/00_正式审核回执/benchmark-video-structure'/f'{cid}_审核回执.json'
        )
        valid=re.fullmatch(r'[A-Z]+-\d{3}',cid) and breakdown.is_file() and receipt.is_file()
        if valid:
            try:
                source_title=str(case.get('sourceTitle') or '')
                sources=list((r/'02_资产中心/05_案例库/01_对标视频原文').rglob(f'{source_title}.md'))
                proof=json.loads(receipt.read_text(encoding='utf-8'))
                valid=(len(sources)==1 and proof.get('status')=='approved' and proof.get('benchmark_case_id')==cid
                       and proof.get('source_sha256')==hashlib.sha256(sources[0].read_bytes()).hexdigest()
                       and proof.get('output_sha256')==hashlib.sha256(breakdown.read_bytes()).hexdigest())
            except (OSError, json.JSONDecodeError): valid=False
        if not valid: errors.append('案例编号资产不完整：'+cid)
    if len(ids)!=len(set(ids)): errors.append('案例编号重复')
    print(json.dumps({'status':'passed' if not errors else 'failed','failures':errors},ensure_ascii=False)); return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
