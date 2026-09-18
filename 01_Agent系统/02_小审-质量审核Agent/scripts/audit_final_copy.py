#!/usr/bin/env python3
"""Audit a V5 final copy against the one V3 writing contract."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from final_copy_semantic_quality import required_check_ids
ROOT=Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from workflow.writing_contract import guidance_snapshot, validate_guidance_snapshot

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def load_renderer(path:Path):
    spec=importlib.util.spec_from_file_location('framework_renderer',path);module=importlib.util.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(module);return module
def semantic_errors(path:Path,plan:dict,candidate:dict,annotations:Path)->list[str]:
    try:review=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError):return ['独立正文审稿不可读取']
    errors=[];expected=[str(x.get('framework_id') or '') for x in candidate.get('framework_mappings',[]) if isinstance(x,dict)]
    expected_schema='independent-framework-final-copy-semantic-review-v5'
    if review.get('schema')!=expected_schema or review.get('status')!='completed':errors.append('独立正文审稿类型或状态错误')
    if review.get('plan_sha256')!=plan.get('__sha256__') or review.get('candidate_sha256')!=candidate.get('__sha256__'):errors.append('独立正文审稿未绑定当前计划或候选')
    if review.get('annotations_sha256')!=digest(annotations):errors.append('独立正文审稿未绑定当前段落注释')
    reviewer=review.get('reviewer') if isinstance(review.get('reviewer'),dict) else {}
    if len(str(reviewer.get('reviewer_id') or '').strip())<3 or len(str(reviewer.get('independence_attestation') or '').strip())<16:errors.append('独立正文审稿缺少审稿人或独立性声明')
    checks=review.get('checks') if isinstance(review.get('checks'),list) else []
    binding = plan.get("writing_contract") if isinstance(plan.get("writing_contract"), dict) else None
    try: required=set(required_check_ids(binding))
    except ValueError: errors.append('正文计划缺少有效的 V3 写作文案表达合同'); required=set()
    try: validate_guidance_snapshot(review.get('writing_contract_guidance_snapshot'),binding,'final-copy')
    except ValueError: errors.append('独立正文审稿未锁定完整口播原文与规则快照')
    by_id={rule['id']:rule for rule in guidance_snapshot(binding,'final-copy')['rules']} if isinstance(binding,dict) else {}
    if {str(x.get('id') or '') for x in checks if isinstance(x,dict)}!=required or any(x.get('status')!='passed' or x.get('source_anchors')!=by_id.get(str(x.get('id') or ''),{}).get('source_anchors') or x.get('rule_text')!=by_id.get(str(x.get('id') or ''),{}).get('directive') or x.get('original_guidance')!=by_id.get(str(x.get('id') or ''),{}).get('original_guidance') or not str(x.get('summary') or '').strip() or not x.get('evidence') for x in checks if isinstance(x,dict)):errors.append('独立正文审稿缺少完整通过检查项')
    items=review.get('item_reviews') if isinstance(review.get('item_reviews'),list) else []
    if {str(x.get('id') or '') for x in items if isinstance(x,dict)}!=set(expected) or any(x.get('verdict')!='passed' or not str(x.get('reasoning') or '').strip() or not x.get('evidence') for x in items if isinstance(x,dict)):errors.append('独立正文审稿未逐项覆盖完整 FNN')
    if candidate.get('schema')=='final-copy-v5' and plan.get('schema')=='final-copy-plan-v5':
        text_by_id={str(row.get('framework_id') or ''):str(row.get('text') or '') for row in candidate.get('framework_mappings',[]) if isinstance(row,dict)}
        if any(not str(item.get('candidate_quote') or '').strip() or str(item.get('candidate_quote') or '') not in text_by_id.get(str(item.get('id') or ''),'') or len(str(item.get('specificness_evidence') or '').strip())<12 for item in items if isinstance(item,dict)):
            errors.append('V5 独立正文审稿必须逐段引用候选原句并说明具体性')
        for check in checks:
            evidence=check.get('evidence') if isinstance(check,dict) else []
            if not isinstance(evidence,list) or not evidence or any(not isinstance(row,dict) or str(row.get('item_id') or '') not in text_by_id or not str(row.get('candidate_quote') or '').strip() or str(row.get('candidate_quote') or '') not in text_by_id[str(row.get('item_id'))] or not str(row.get('reasoning') or '').strip() for row in evidence):
                errors.append('V3 写作文案表达合同审核必须逐规则定位候选段和原句');break
    else: errors.append('独立正文审稿只接受 final-copy-plan-v5/final-copy-v5')
    return errors
def main()->int:
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--preview',type=Path,required=True);p.add_argument('--annotations',type=Path,required=True);p.add_argument('--semantic-review',type=Path,required=True);p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[3]
    plan=json.loads(a.plan.read_text(encoding='utf-8'));candidate=json.loads(a.candidate.read_text(encoding='utf-8'));plan['__sha256__']=digest(a.plan);candidate['__sha256__']=digest(a.candidate)
    validator=root/'10_Skills武器库'/'正文成稿生成 Skill'/'scripts'/'validate_framework_copy.py';result=subprocess.run([sys.executable,'-X','utf8',str(validator),'--plan',str(a.plan),'--candidate',str(a.candidate),'--annotations',str(a.annotations)],text=True,capture_output=True,encoding='utf-8',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    renderer=load_renderer(root/'10_Skills武器库'/'正文成稿生成 Skill'/'scripts'/'render_framework_copy.py');issues=[]
    if not a.preview.is_file():issues.append('正文预览未由当前完整 FNN 计划和候选渲染')
    else:
        preview_text=a.preview.read_text(encoding='utf-8')
        if preview_text!=renderer.render(plan,candidate):issues.append('正文预览未由当前完整 FNN 计划和候选渲染')
        if hasattr(renderer,'inline_annotation_errors'):issues.extend(renderer.inline_annotation_errors(candidate,preview_text))
    if not a.annotations.is_file() or a.annotations.read_text(encoding='utf-8')!=renderer.render_annotations(plan,candidate):issues.append('段落注释未由当前完整 FNN 计划和候选渲染')
    issues.extend(semantic_errors(a.semantic_review,plan,candidate,a.annotations))
    receipt={'schema':'audit-receipt-v3','artifactType':candidate.get('schema'),'status':'approved' if result.returncode==0 and not issues else 'rejected','auditor':'xiaoshen','generatedAt':datetime.now(timezone.utc).isoformat(),'subject':{'plan':str(a.plan.resolve()),'candidate':str(a.candidate.resolve()),'preview':str(a.preview.resolve()),'annotations':str(a.annotations.resolve()),'planSha256':digest(a.plan),'candidateSha256':digest(a.candidate),'previewSha256':digest(a.preview),'annotationsSha256':digest(a.annotations) if a.annotations.is_file() else ''},'mechanicalResult':result.stdout.strip() or result.stderr.strip(),'semanticReview':str(a.semantic_review.resolve()),'semanticIssues':issues}
    a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False));return 0 if receipt['status']=='approved' else 1
if __name__=='__main__':raise SystemExit(main())
