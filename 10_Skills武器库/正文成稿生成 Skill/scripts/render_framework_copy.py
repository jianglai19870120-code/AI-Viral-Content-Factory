#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
if str(Path(__file__).resolve().parent) not in sys.path:sys.path.insert(0,str(Path(__file__).resolve().parent))
from framework_copy_contract import punctuation_lines

ROOT=next(parent for parent in Path(__file__).resolve().parents if (parent / 'workflow' / 'common.py').is_file())
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from workflow.common import append_brand_footer_text

def cell(value:object)->str:
    return str(value or '').replace('\\', '\\\\').replace('|', '\\|').replace('\r\n', '\n').replace('\n', '<br>')

def inline_annotation(item:dict)->str:
    """Render the required reader-facing FNN and writing-method label."""
    auxiliary='、'.join(str(method) for method in item.get('auxiliary_writing_methods',[]) if str(method).strip()) or '无'
    return '【'+str(item['framework_id'])+'｜'+str(item['framework_label'])+'｜主：'+str(item['primary_writing_method'])+'｜辅：'+auxiliary+'】'

def inline_annotation_errors(candidate:dict,preview_text:str)->list[str]:
    """Reject missing, reordered, or drifted inline labels in a rendered preview."""
    expected=[inline_annotation(item) for item in candidate.get('framework_mappings',[]) if isinstance(item,dict)]
    actual=[line.strip() for line in str(preview_text).splitlines() if line.strip().startswith('【') and line.strip().endswith('】')]
    if actual==expected:return []
    return ['正文内联框架/写作手法标注不完整或漂移：期望 '+str(expected)+'，实际 '+str(actual)]

def render(plan:dict,candidate:dict)->str:
    sections=[f"# {candidate['topic']}",""]
    for item in candidate['framework_mappings']:
        sections.append(inline_annotation(item))
        sections.append(punctuation_lines(str(item['text']).strip()))
        sections.append("")
    return append_brand_footer_text('\n'.join(sections).rstrip()+'\n')

def render_annotations(plan:dict,candidate:dict)->str:
    lines=[f"# 正文段落注释｜{candidate['topic']}","","> 正式正文已内联展示 FNN、框架和主/辅写作手法；本文件保留框架功能、内容来源和手法选择理由，供写作与审核追溯。","", "| FNN | 大结构 | 框架功能 | 内容来源 | 主写作手法 | 辅写作手法 | 手法选择理由 | 正文段落 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for number,item in enumerate(candidate['framework_mappings'],1):
        source='结构四人工内容' if str(item.get('content_source') or '').startswith('user-filled') else 'AI按框架功能补足'
        auxiliary='、'.join(item.get('auxiliary_writing_methods') or []) or '无'
        lines.append(f"| {cell(item['framework_id'])} | {cell(item['framework_label'])} | {cell(item['framework_function'])} | {source} | {cell(item['primary_writing_method'])} | {cell(auxiliary)} | {cell(item['method_rationale'])} | 第 {number} 段 |")
    return append_brand_footer_text('\n'.join(lines)+'\n')

def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--annotations',type=Path);a=p.parse_args()
    plan=json.loads(a.plan.read_text(encoding='utf-8'));candidate=json.loads(a.candidate.read_text(encoding='utf-8'))
    formal_root=ROOT/'02_资产中心'/'03_输出库'/'02_正文成稿'
    if a.output.resolve().is_relative_to(formal_root.resolve()):
        raise SystemExit('正文预览不得直接写入正式正文库；请在小审 approved 后调用 publish_framework_final_copy.py')
    a.output.write_text(render(plan,candidate),encoding='utf-8')
    if a.annotations:a.annotations.write_text(render_annotations(plan,candidate),encoding='utf-8')
    return 0
if __name__=='__main__':raise SystemExit(main())
