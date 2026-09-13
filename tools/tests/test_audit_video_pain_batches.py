from __future__ import annotations

import hashlib, importlib.util, json, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SCRIPT=ROOT/'01_Agent系统'/'02_小审-质量审核Agent'/'scripts'/'audit_video_pain_batches.py'
SPEC=importlib.util.spec_from_file_location('audit_video_pain_batches',SCRIPT); assert SPEC and SPEC.loader
MOD=importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name]=MOD; SPEC.loader.exec_module(MOD)

class BatchAuditTests(unittest.TestCase):
    def make_batch(self) -> tuple[Path,Path]:
        root=Path(tempfile.mkdtemp()); sources=root/'sources'; sources.mkdir(); rows=[]; manifest=[]
        for n in range(5):
            sid=f'VID-{n:03d}'; raw=sources/f'{sid}.md'; raw.write_text(f'---\nsource_id: {sid}\n---\n\n## 全文\n\n正文{n}\n',encoding='utf-8')
            manifest.append({'source_id':sid,'relative_path':raw.name,'full_text_sha256':hashlib.sha256(f'正文{n}'.encode()).hexdigest(),'account':'经纬'})
            correction=root/f'{sid}-corrected.md'; correction.write_text(f'校对{n}',encoding='utf-8')
            audit=root/f'{sid}-audit.json'; audit.write_text(json.dumps({'status':'approved','subject':{'source_id':sid,'candidateSha256':hashlib.sha256(correction.read_bytes()).hexdigest()}},ensure_ascii=False),encoding='utf-8')
            rows.append({'source_id':sid,'original_source_path':str(raw),'correction_candidate_path':str(correction),'correction_candidate_sha256':hashlib.sha256(correction.read_bytes()).hexdigest(),'correction_audit_receipt':str(audit),'correction_audit_sha256':hashlib.sha256(audit.read_bytes()).hexdigest(),'status':'approved'})
        (sources/'manifest.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in manifest),encoding='utf-8')
        ledger=root/'batch-source-ledger.json'; ledger.write_text(json.dumps({'schema':'video-pain-batch-source-ledger-v1','sources':rows},ensure_ascii=False),encoding='utf-8')
        machine=root/'machine-evidence'; machine.mkdir(); bundle=root/'bundle.json'; bundle.write_text(json.dumps({'sources':[{'source_id':f'VID-{n:03d}','full_text':f'正文{n}'} for n in range(5)]},ensure_ascii=False),encoding='utf-8'); index=machine/'candidate-module-index.jsonl'; index.write_text('',encoding='utf-8'); (machine/'routed-modules.json').write_text(json.dumps({'schema':'video-module-machine-candidates-v2','pain_cards':[],'micro_modules':[]}),encoding='utf-8')
        m=root/'batch-machine-manifest.json'; m.write_text(json.dumps({'schema':'video-pain-batch-machine-v1','batch_number':1,'source_ledger_path':str(ledger),'source_ledger_sha256':hashlib.sha256(ledger.read_bytes()).hexdigest(),'approved_source_ids':[x['source_id'] for x in rows],'machine_candidate_root':str(machine),'machine_candidate_sha256':MOD.tree_sha(machine),'bundle_path':str(bundle),'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'machine_index_path':str(index),'machine_index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'module_types':['pain']},ensure_ascii=False),encoding='utf-8')
        return m,sources
    def test_batch_accepts_exact_five_approved_sources_and_rejects_short_batch(self)->None:
        manifest,sources=self.make_batch(); checks,_=MOD.batch(manifest,sources); self.assertTrue(all(x['status']=='passed' for x in checks),checks)
        payload=json.loads(manifest.read_text(encoding='utf-8')); ledger=Path(payload['source_ledger_path']); item=json.loads(ledger.read_text(encoding='utf-8')); item['sources'].pop(); ledger.write_text(json.dumps(item),encoding='utf-8'); payload['source_ledger_sha256']=hashlib.sha256(ledger.read_bytes()).hexdigest(); manifest.write_text(json.dumps(payload),encoding='utf-8')
        checks,_=MOD.batch(manifest,sources); self.assertEqual('failed',checks[0]['status'])

    def test_batch_binds_active_master_ledger_to_approved_source_manifest(self)->None:
        manifest,sources=self.make_batch(); payload=json.loads(manifest.read_text(encoding='utf-8'))
        approved=Path(payload['source_ledger_path']); master=manifest.parent/'coverage-ledger.json'
        master_payload={'schema':'video-pain-batch-ledger-v1','status':'active','batch_size':5,'expected_count':547,
                        'completed_batches':[],'next_batch_ready':False,
                        'active_batch':{'batch_number':1,'source_ids':payload['approved_source_ids'],
                                        'source_manifest':str(approved),'source_manifest_sha256':hashlib.sha256(approved.read_bytes()).hexdigest()}}
        master.write_text(json.dumps(master_payload),encoding='utf-8')
        payload.update({'schema':'video-pain-batch-machine-manifest-v1','source_ledger_path':str(master),
                        'source_ledger_sha256':hashlib.sha256(master.read_bytes()).hexdigest(),'status':'awaiting_batch_audit'})
        machine=Path(payload['machine_candidate_root']); (machine/'routed-modules.json').write_text(json.dumps({'schema':'video-module-machine-candidates-v2','pain_cards':[],'micro_modules':[]}),encoding='utf-8')
        payload['machine_candidate_sha256']=MOD.tree_sha(machine)
        manifest.write_text(json.dumps(payload),encoding='utf-8')
        checks,_=MOD.batch(manifest,sources); self.assertTrue(all(x['status']=='passed' for x in checks),checks)

    def test_coverage_rejects_incomplete_rebuild_before_release(self)->None:
        root=Path(tempfile.mkdtemp()); sources=root/'sources'; sources.mkdir()
        (sources/'manifest.jsonl').write_text(json.dumps({'source_id':'VID-001','relative_path':'VID-001.md','account':'经纬'},ensure_ascii=False)+'\n',encoding='utf-8')
        ledger=root/'coverage.json'; ledger.write_text(json.dumps({'schema':'video-pain-rebuild-coverage-v1','batches':[],'account_counts':{'经纬':1}},ensure_ascii=False),encoding='utf-8')
        checks,_=MOD.coverage(ledger,sources); self.assertEqual('failed',checks[0]['status'])

    def test_batch_release_rejects_missing_prior_approved_contribution(self)->None:
        root=Path(tempfile.mkdtemp()); master=root/'master.json'; master.write_text(json.dumps({'schema':'video-pain-batch-ledger-v1','active_batch':{'batch_number':2},'next_batch_ready':False}),encoding='utf-8')
        registry=root/'registry.json'; registry.write_text(json.dumps({'schema':'video-pain-approved-contribution-registry-v1','contributions':[{'batch_number':2}]}),encoding='utf-8')
        manifest=root/'release.json'; manifest.write_text(json.dumps({'schema':'video-pain-batch-release-v1','batch_number':2,'coverage_ledger_path':str(master),'coverage_ledger_sha256':hashlib.sha256(master.read_bytes()).hexdigest(),'approved_contribution_registry':str(registry),'approved_contribution_registry_sha256':hashlib.sha256(registry.read_bytes()).hexdigest()}),encoding='utf-8')
        checks,_=MOD.batch_release(manifest); self.assertEqual('failed',checks[0]['status']); self.assertIn('连续聚合',checks[0]['detail'])

if __name__=='__main__': unittest.main()
