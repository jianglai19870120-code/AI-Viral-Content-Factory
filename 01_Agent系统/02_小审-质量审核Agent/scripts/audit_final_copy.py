#!/usr/bin/env python3
"""Audit a complete-FNN V3 final copy without reading benchmark prose."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from final_copy_semantic_quality import REQUIRED_CHECK_IDS

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def load_renderer(path:Path):
    spec=importlib.util.spec_from_file_location('framework_renderer',path);module=importlib.util.module_from_spec(spec);assert spec and spec.loader;spec.loader.exec_module(module);return module
def semantic_errors(path:Path,plan:dict,candidate:dict,annotations:Path)->list[str]:
    try:review=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError):return ['独立正文审稿不可读取']
    errors=[];expected=[str(x.get('framework_id') or '') for x in candidate.get('framework_mappings',[]) if isinstance(x,dict)]
    if review.get('schema')!='independent-framework-final-copy-semantic-review-v3' or review.get('status')!='completed':errors.append('独立正文审稿类型或状态错误')
    if review.get('plan_sha256')!=plan.get('__sha256__') or review.get('candidate_sha256')!=candidate.get('__sha256__'):errors.append('独立正文审稿未绑定当前计划或候选')
    if review.get('annotations_sha256')!=digest(annotations):errors.append('独立正文审稿未绑定当前段落注释')
    reviewer=review.get('reviewer') if isinstance(review.get('reviewer'),dict) else {}
    if len(str(reviewer.get('reviewer_id') or '').strip())<3 or len(str(reviewer.get('independence_attestation') or '').strip())<16:errors.append('独立正文审稿缺少审稿人或独立性声明')
    checks=review.get('checks') if isinstance(review.get('checks'),list) else []
    required=set(REQUIRED_CHECK_IDS)
    if {str(x.get('id') or '') for x in checks if isinstance(x,dict)}!=required or any(x.get('status')!='passed' or not str(x.get('summary') or '').strip() or not x.get('evidence') for x in checks if isinstance(x,dict)):errors.append('独立正文审稿缺少完整通过检查项')
    items=review.get('item_reviews') if isinstance(review.get('item_reviews'),list) else []
    if {str(x.get('id') or '') for x in items if isinstance(x,dict)}!=set(expected) or any(x.get('verdict')!='passed' or not str(x.get('reasoning') or '').strip() or not x.get('evidence') for x in items if isinstance(x,dict)):errors.append('独立正文审稿未逐项覆盖完整 FNN')
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
    receipt={'schema':'audit-receipt-v3','artifactType':'final-copy-v3','status':'approved' if result.returncode==0 and not issues else 'rejected','auditor':'xiaoshen','generatedAt':datetime.now(timezone.utc).isoformat(),'subject':{'plan':str(a.plan.resolve()),'candidate':str(a.candidate.resolve()),'preview':str(a.preview.resolve()),'annotations':str(a.annotations.resolve()),'planSha256':digest(a.plan),'candidateSha256':digest(a.candidate),'previewSha256':digest(a.preview),'annotationsSha256':digest(a.annotations) if a.annotations.is_file() else ''},'mechanicalResult':result.stdout.strip() or result.stderr.strip(),'semanticReview':str(a.semantic_review.resolve()),'semanticIssues':issues}
    a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(receipt,ensure_ascii=False));return 0 if receipt['status']=='approved' else 1
if __name__=='__main__':raise SystemExit(main())
