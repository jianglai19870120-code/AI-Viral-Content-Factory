"""小审：547 篇视频痛点卡重建的批次、覆盖与切换前门禁。

只审不改。批次产物必须先经本脚本 approved，下一批才可启动；全量
覆盖、浏览卡暂存、索引暂存和归档清单均完整前，不会放行正式库切换。
"""
from __future__ import annotations

import argparse, hashlib, json, math, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_TOTAL, LAST_BATCH_SIZE = 547, 2

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def tree_sha(root: Path) -> str:
    digest=hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0"); digest.update(sha(path).encode("ascii")); digest.update(b"\n")
    return digest.hexdigest()
def now() -> str: return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
def read(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def rel(path: Path) -> str:
    try: return path.resolve().relative_to(ROOT).as_posix()
    except ValueError: return str(path.resolve())
def resolved(value: str) -> Path:
    p=Path(value); return p.resolve() if p.is_absolute() else (ROOT/p).resolve()

def check_file(value: Any, expected_sha: Any, label: str, issues: list[str]) -> Path | None:
    if not value: issues.append(f"缺 {label} 路径"); return None
    p=resolved(str(value))
    if not p.is_file(): issues.append(f"{label} 不存在：{p}"); return None
    if expected_sha and str(expected_sha) != sha(p): issues.append(f"{label} 哈希不匹配")
    return p

def receipt(path: Path, task_id: str, status: str, checks: list[dict[str, Any]], subject: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema":"audit-receipt-v3","artifactType":"video-module-assets-v1","status":status,"task_id":task_id,"attempt":1,"auditor":"xiaoshen","auditor_skill_id":"xiaoshen-audit","generatedAt":now(),"subject":subject,"required_check_ids":[x["id"] for x in checks],"checks":checks,"note":"只审核，未改写校对、机器候选、暂存卡或正式库。"},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def batch(manifest_path: Path, source_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    m=read(manifest_path); issues: list[str]=[]; n=m.get("batch_number")
    if m.get("schema") not in {"video-pain-batch-machine-v1","video-pain-batch-machine-manifest-v1"}: issues.append("batch-machine-manifest schema 不正确")
    if not isinstance(n,int) or n<1 or n>math.ceil(EXPECTED_TOTAL/5): issues.append("batch_number 越界")
    source_ledger=check_file(m.get("source_ledger_path"),m.get("source_ledger_sha256"),"source ledger",issues)
    rows=[]; master=None
    if source_ledger:
        ledger=read(source_ledger)
        if ledger.get("schema") in {"video-pain-batch-source-ledger-v1","video-source-correction-approved-batch-v1"}:
            rows=ledger.get("sources",[]) if isinstance(ledger.get("sources"),list) else []
        elif ledger.get("schema")=="video-pain-batch-ledger-v1":
            master=ledger; active=ledger.get("active_batch",{}) if isinstance(ledger.get("active_batch"),dict) else {}
            if ledger.get("expected_count")!=EXPECTED_TOTAL or ledger.get("batch_size")!=5: issues.append("总台账的 547 篇或每批 5 篇约束不正确")
            if active.get("batch_number")!=n: issues.append("总台账 active_batch 未绑定当前批次")
            if ledger.get("next_batch_ready") is not False: issues.append("当前批未审核，不得预先解锁下一批")
            completed=ledger.get("completed_batches",[]) if isinstance(ledger.get("completed_batches"),list) else []
            if any(isinstance(item,dict) and item.get("batch_number",0)>=n for item in completed): issues.append("当前批尚未审核却已被标记完成")
            if n and n>1:
                prior=[item for item in completed if isinstance(item,dict) and item.get("batch_number")==n-1]
                if len(prior)!=1 or prior[0].get("release_status")!="released": issues.append("上一批未在总台账中绑定 released 状态，禁止启动当前批")
                else:
                    prior_release=check_file(prior[0].get("release_audit_receipt"),prior[0].get("release_audit_sha256"),"上一批发布审核回执",issues)
                    if prior_release and read(prior_release).get("status")!="approved": issues.append("上一批发布审核回执未 approved")
            source_manifest=check_file(active.get("source_manifest"),active.get("source_manifest_sha256"),"已审核校对源批次清单",issues)
            if source_manifest:
                approved_ledger=read(source_manifest)
                if approved_ledger.get("schema") not in {"video-pain-batch-source-ledger-v1","video-source-correction-approved-batch-v1"}: issues.append("已审核校对源批次清单 schema 不正确")
                rows=approved_ledger.get("sources",[]) if isinstance(approved_ledger.get("sources"),list) else []
        else: issues.append("source ledger schema 不正确")
    expected=LAST_BATCH_SIZE if n==math.ceil(EXPECTED_TOTAL/5) else 5
    ids=[str(x.get("source_id") or "") for x in rows if isinstance(x,dict)]
    if len(rows)!=expected or len(set(ids))!=expected or any(not x for x in ids): issues.append(f"本批必须恰有 {expected} 个唯一来源")
    for row in rows:
        if not isinstance(row,dict): continue
        cp=check_file(row.get("correction_candidate_path"),row.get("correction_candidate_sha256"),f"{row.get('source_id')} 校对候选",issues)
        rp=check_file(row.get("correction_audit_receipt"),row.get("correction_audit_sha256"),f"{row.get('source_id')} 校对回执",issues)
        if rp:
            r=read(rp); subj=r.get("subject",{}) if isinstance(r.get("subject"),dict) else {}
            if r.get("status")!="approved" or subj.get("source_id")!=row.get("source_id") or (cp and subj.get("candidateSha256")!=sha(cp)): issues.append(f"{row.get('source_id')} 校对回执未连续绑定 approved 候选")
    machine=resolved(str(m.get("machine_candidate_root") or ""))
    if not machine.is_dir() or list(machine.rglob("*.md")): issues.append("机器候选根不存在或混入 Markdown 浏览卡")
    elif m.get("machine_candidate_sha256")!=tree_sha(machine): issues.append("机器候选根哈希不匹配")
    bundle_file=check_file(m.get("bundle_path"),m.get("bundle_sha256"),"bundle",issues); check_file(m.get("machine_index_path"),m.get("machine_index_sha256"),"machine index",issues)
    approved=m.get("approved_source_ids") if isinstance(m.get("approved_source_ids"),list) else []
    if set(approved)!=set(ids): issues.append("approved_source_ids 与已审核校对清单不一致")
    routed=machine/"routed-modules.json"
    if not routed.is_file(): issues.append("机器候选缺 routed-modules.json")
    else:
        try:
            route=read(routed)
            if route.get("schema")!="video-module-machine-candidates-v2" or not isinstance(route.get("pain_cards"),list) or route.get("micro_modules") not in ([],None): issues.append("机器候选不是仅 pain 路由")
            if bundle_file:
                bundle=read(bundle_file); bundle_sources=bundle.get("sources",[]) if isinstance(bundle.get("sources"),list) else []
                source_text={str(item.get("source_id") or ""):str(item.get("full_text") or "").strip() for item in bundle_sources if isinstance(item,dict)}
                if set(source_text)!=set(approved): issues.append("证据包来源未与本批 approved_source_ids 完整对应")
                evidence_sources={str(ev.get("source_id") or "") for card in route.get("pain_cards",[]) if isinstance(card,dict) for angle in card.get("angles",[]) if isinstance(angle,dict) for ev in angle.get("evidence",[]) if isinstance(ev,dict)}
                invalid_empty={sid for sid,text in source_text.items() if text in {"","-","—"}} & evidence_sources
                if invalid_empty: issues.append("空白或 '-' 原文被强行产出痛点证据："+"、".join(sorted(invalid_empty)))
        except (OSError,json.JSONDecodeError): issues.append("routed-modules.json 无法读取")
    if m.get("module_types") not in (None,["pain"]): issues.append("批次 module_types 只能为 [pain]")
    if m.get("status") not in (None,"awaiting_batch_audit"): issues.append("批次 manifest 状态必须为 awaiting_batch_audit")
    if n and n>1:
        prev=check_file(m.get("previous_batch_audit_receipt"),m.get("previous_batch_audit_sha256"),"上一批审核回执",issues)
        if prev and read(prev).get("status")!="approved": issues.append("上一批未 approved，禁止启动本批")
    checks=[{"id":"batch-contract","status":"passed" if not issues else "failed","detail":"；".join(issues) or "通过"}]
    return checks,{"batch_number":n,"source_ids":ids,"machine_candidate_root":rel(machine) if machine else ""}

def source_ledger(ledger_path: Path, source_root: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    ledger=read(ledger_path); issues=[]; n=ledger.get("batch_number"); rows=ledger.get("sources",[]) if isinstance(ledger.get("sources"),list) else []
    expected=LAST_BATCH_SIZE if n==math.ceil(EXPECTED_TOTAL/5) else 5
    if ledger.get("schema") not in {"video-pain-batch-source-ledger-v1","video-source-correction-approved-batch-v1"}: issues.append("source ledger schema 不正确")
    if not isinstance(n,int) or len(rows)!=expected: issues.append(f"校对批次必须恰有 {expected} 篇")
    ids=[]
    for row in rows:
        sid=str(row.get("source_id") or ""); ids.append(sid)
        original=source_root/str(row.get("original_source_path") or "")
        if not sid or not original.is_file(): issues.append(f"{sid or '<空>'} 原识别源不存在")
        cp=check_file(row.get("correction_candidate_path"),row.get("correction_candidate_sha256"),f"{sid} 校对候选",issues)
        rp=check_file(row.get("correction_audit_receipt"),row.get("correction_audit_sha256"),f"{sid} 校对回执",issues)
        if row.get("status")!="approved": issues.append(f"{sid} 校对状态非 approved")
        if rp:
            r=read(rp); subj=r.get("subject",{}) if isinstance(r.get("subject"),dict) else {}
            if r.get("status")!="approved" or subj.get("source_id")!=sid or (cp and subj.get("candidateSha256")!=sha(cp)): issues.append(f"{sid} 校对回执未连续绑定")
    if len(set(ids))!=len(rows): issues.append("校对清单 source_id 重复")
    return [{"id":"per-source-correction-continuity","status":"passed" if not issues else "failed","detail":"；".join(issues) or "通过"}],{"batch_number":n,"source_ids":ids}

def legacy_cleanup_scope(card_root: Path, index_path: Path, sample_card: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    """Read-only confirmation for the explicitly-authorized legacy cleanup set."""
    issues=[]; legacy=[]
    for path in card_root.rglob("*.md"):
        text=path.read_text(encoding="utf-8",errors="ignore")
        if "schema: video-pain-card-v1" not in text: continue
        fields={}
        for line in text.splitlines()[:30]:
            if ": " in line:
                key,value=line.split(": ",1); fields[key.strip()]=value.strip()
        pain_id=fields.get("pain_id") or fields.get("card_id")
        if not pain_id: issues.append(f"旧格式卡缺 pain_id：{rel(path)}")
        legacy.append((pain_id,path.resolve()))
    ids=[item[0] for item in legacy]
    if len(legacy)!=15 or len(set(ids))!=15 or any(not item for item in ids): issues.append("待清理范围必须恰为 15 张唯一的 video-pain-card-v1 卡")
    if not index_path.is_file(): issues.append("视频模块索引不存在"); rows=[]
    else:
        try: rows=[json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except json.JSONDecodeError: issues.append("视频模块索引含非 JSON 行"); rows=[]
    matches=[row for row in rows if isinstance(row,dict) and row.get("pain_id") in set(ids)]
    for pain_id,path in legacy:
        same=[row for row in matches if row.get("pain_id")==pain_id]
        if len(same)!=1: issues.append(f"{pain_id} 未恰好对应一条索引")
        elif resolved(str(same[0].get("module_path") or ""))!=path: issues.append(f"{pain_id} 索引路径未精确对应旧格式卡")
    if len(matches)!=15: issues.append("待清理索引范围必须恰为 15 条")
    sample_rows=[row for row in rows if isinstance(row,dict) and row.get("pain_id")=="PAIN-A02-VIDEO-SELF-EXPRESSION"]
    if not sample_card.is_file() or "video-pain-card-v1" in sample_card.read_text(encoding="utf-8",errors="ignore"): issues.append("新格式样本卡不存在或误被判入旧格式")
    if len(sample_rows)!=1 or resolved(str(sample_rows[0].get("module_path") or ""))!=sample_card.resolve(): issues.append("新格式样本索引不存在、重复或未指向样本卡")
    return [{"id":"legacy-cleanup-exact-scope","status":"passed" if not issues else "failed","detail":"；".join(issues) or "15 张旧卡、15 条精确索引行，且新格式样本卡/索引均已排除"}],{"legacy_card_ids":sorted(ids),"legacy_card_count":len(legacy),"matching_index_count":len(matches),"preserved_sample":"PAIN-A02-VIDEO-SELF-EXPRESSION"}

def legacy_cleanup_plan(plan_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    plan=read(plan_path); issues=[]
    if plan.get("schema")!="video-pain-legacy-cleanup-plan-v1" or plan.get("status")!="awaiting_cleanup_audit": issues.append("清理计划 schema 或状态不正确")
    cards=plan.get("legacy_cards",[]) if isinstance(plan.get("legacy_cards"),list) else []
    plan_ids=plan.get("legacy_pain_ids",[]) if isinstance(plan.get("legacy_pain_ids"),list) else []
    if len(cards)!=15 or len(plan_ids)!=15 or len(set(plan_ids))!=15: issues.append("清理计划必须列出 15 张唯一旧卡及 15 个 pain_id")
    listed_paths=set()
    for item in cards:
        if not isinstance(item,dict): issues.append("清理计划 legacy_cards 含非对象"); continue
        path=resolved(str(item.get("path") or "")); listed_paths.add(path)
        if not path.is_file() or sha(path)!=item.get("sha256"): issues.append(f"旧格式卡不存在或哈希漂移：{rel(path)}")
        elif "schema: video-pain-card-v1" not in path.read_text(encoding="utf-8",errors="ignore"): issues.append(f"清理计划含非旧格式卡：{rel(path)}")
    index=check_file(plan.get("index_path"),plan.get("index_sha256"),"待清理视频索引",issues)
    sample=resolved(str(plan.get("preserve_card") or ""))
    if not sample.is_file() or sha(sample)!=plan.get("preserve_card_sha256") or "video-pain-card-v1" in sample.read_text(encoding="utf-8",errors="ignore"): issues.append("保留的新格式样本卡不存在、哈希漂移或被误列为旧格式")
    if sample in listed_paths or plan.get("preserve_pain_id") in plan_ids: issues.append("新格式样本被误列入清理计划")
    card_root=ROOT/"02_资产中心"/"02_处理库"/"02_痛点_内容模块（会员专享）"
    scope_checks,subject=legacy_cleanup_scope(card_root,index or resolved(str(plan.get("index_path") or "")),sample)
    actual_ids=set(subject.get("legacy_card_ids",[])); actual_paths={path.resolve() for path in card_root.rglob("*.md") if "schema: video-pain-card-v1" in path.read_text(encoding="utf-8",errors="ignore")}
    if actual_ids!=set(plan_ids) or actual_paths!=listed_paths: issues.append("清理计划与当前全部旧格式卡范围不完全一致")
    if scope_checks[0]["status"]!="passed": issues.append(scope_checks[0]["detail"])
    return [{"id":"legacy-cleanup-plan-binding","status":"passed" if not issues else "failed","detail":"；".join(issues) or "计划精确绑定 15 张旧格式卡、15 条索引行，并保留新格式样本"}],{**subject,"cleanup_plan":rel(plan_path)}

def batch_release(manifest_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    """Gate staged human cards before a controller unlocks the next source batch."""
    m=read(manifest_path); issues=[]; n=m.get("batch_number")
    if m.get("schema")!="video-pain-batch-release-v1" or not isinstance(n,int): issues.append("batch release manifest schema 或 batch_number 不正确")
    master_path=check_file(m.get("coverage_ledger_path"),m.get("coverage_ledger_sha256"),"总台账",issues)
    if master_path:
        master=read(master_path); active=master.get("active_batch",{}) if isinstance(master.get("active_batch"),dict) else {}
        if master.get("schema")!="video-pain-batch-ledger-v1" or active.get("batch_number")!=n or master.get("next_batch_ready") is not False: issues.append("正式落盘前总台账必须锁定当前批，且不得预先解锁下一批")
    for path_key,hash_key,label in (("source_ledger_audit_receipt","source_ledger_audit_sha256","校对清单审核回执"),("machine_audit_receipt","machine_audit_sha256","机器候选审核回执"),("batch_gate_audit_receipt","batch_gate_audit_sha256","批次门禁审核回执")):
        p=check_file(m.get(path_key),m.get(hash_key),label,issues)
        if p and read(p).get("status")!="approved": issues.append(f"{label} 未 approved")
    registry_path=check_file(m.get("approved_contribution_registry"),m.get("approved_contribution_registry_sha256"),"已批准贡献登记簿",issues)
    if registry_path:
        registry=read(registry_path); contributions=registry.get("contributions",[]) if isinstance(registry.get("contributions"),list) else []
        numbers=[item.get("batch_number") for item in contributions if isinstance(item,dict)]
        if registry.get("schema")!="video-pain-approved-contribution-registry-v1" or numbers!=list(range(1,n+1)): issues.append("贡献登记簿必须连续聚合 1 至当前批的已批准证据")
        for item in contributions:
            if not isinstance(item,dict): continue
            p=check_file(item.get("machine_audit_receipt"),item.get("machine_audit_sha256"),f"贡献批次 {item.get('batch_number')} 机器回执",issues)
            if p and read(p).get("status")!="approved": issues.append(f"贡献批次 {item.get('batch_number')} 未 approved")
    merge=check_file(m.get("merge_receipt"),m.get("merge_receipt_sha256"),"合并去重回执",issues)
    merge_payload={}; affected_ids:set[str]=set()
    if merge:
        merge_payload=read(merge)
        if merge_payload.get("schema")!="video-pain-batch-merge-v1" or merge_payload.get("status")!="staged" or merge_payload.get("batch_number")!=n: issues.append("合并去重回执 schema、状态或批次不正确")
        affected=merge_payload.get("affected_pain_ids",[]) if isinstance(merge_payload.get("affected_pain_ids"),list) else []
        affected_ids={str(item) for item in affected if item}
        zero_batch=merge_payload.get("zero_pain_evidence") is True
        if (not affected_ids and not zero_batch) or len(affected_ids)!=len(affected): issues.append("合并去重回执必须列出本批唯一 affected_pain_ids；零卡批次须显式标记 zero_pain_evidence")
    stage=resolved(str(m.get("staging_card_root") or "")); index=check_file(m.get("staging_index"),m.get("staging_index_sha256"),"暂存索引",issues)
    cards=list(stage.rglob("*.md")) if stage.is_dir() else []
    if not stage.is_dir() or (affected_ids and not cards) or (not affected_ids and cards): issues.append("人读卡暂存目录与本批受影响痛点卡不一致")
    staged_rows=[]
    if index:
        try: staged_rows=[json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
        except json.JSONDecodeError: issues.append("暂存索引含非 JSON 行")
    pain_rows=[row for row in staged_rows if isinstance(row,dict) and row.get("pain_id") and (row.get("angle_id") or row.get("module_type")=="pain")]
    ids={str(row.get("pain_id") or "") for row in pain_rows}
    angle_keys=[(str(row.get("pain_id") or ""),str(row.get("angle_id") or "")) for row in pain_rows]
    if not pain_rows or not ids or any(not pain_id or not angle_id for pain_id,angle_id in angle_keys) or len(angle_keys)!=len(set(angle_keys)):
        issues.append("暂存专用角度索引必须含唯一 pain_id + angle_id")
    if not affected_ids <= ids: issues.append("暂存专用角度索引遗漏本批 affected_pain_ids")
    staged_paths=set(); formal_pain_root=(ROOT/"02_资产中心"/"02_处理库"/"02_痛点_内容模块（会员专享）").resolve()
    for row in pain_rows:
        pain_id=str(row.get("pain_id") or row.get("card_id") or ""); final_path=resolved(str(row.get("card_path") or row.get("module_path") or ""))
        if formal_pain_root not in final_path.parents: issues.append(f"暂存索引正式目标不在痛点库：{row.get('card_id')}"); continue
        staged_path=stage/final_path.relative_to(formal_pain_root)
        path=staged_path if pain_id in affected_ids else final_path
        if pain_id in affected_ids: staged_paths.add(staged_path.resolve())
        if not path.is_file(): issues.append(f"暂存或既有卡不存在：{row.get('card_id')}"); continue
        primary, secondary, title = str(row.get("primary_category") or ""), str(row.get("secondary_keyword") or ""), str(row.get("pain_title") or "")
        relative = final_path.relative_to(formal_pain_root) if formal_pain_root in final_path.parents else Path("__invalid__")
        expected_name = f"{secondary}_{title}_{pain_id}.md"
        if not primary or not secondary or any(token in secondary for token in ("、", "/", "-", "_", " ")) or len(relative.parts) != 2 or relative.parts[0] != primary or relative.name != expected_name:
            issues.append(f"{pain_id} 未使用一级目录和二级词_标题_PAIN-ID 新命名")
        text=path.read_text(encoding="utf-8",errors="ignore")
        forbidden=("video-pain-card-v1","待小审","痛点 ID","来源定位","哈希","基于原文整理")
        if not text.startswith("# 痛点卡｜") or "来源：" not in text or "我是姜来已来" not in text or any(word in text for word in forbidden): issues.append(f"{row.get('card_id')} 人读卡格式不合规")
    actual_pain_cards={path.resolve() for path in cards if path.read_text(encoding="utf-8",errors="ignore").startswith("# 痛点卡｜")}
    if actual_pain_cards!=staged_paths: issues.append("本批暂存 pain 卡与 affected_pain_ids 未一一对应")
    if merge:
        if index is None or merge_payload.get("staging_index_sha256")!=sha(index): issues.append("合并去重回执未绑定当前暂存索引")
    return [{"id":"batch-formal-staging-and-merge","status":"passed" if not issues else "failed","detail":"；".join(issues) or "已连续聚合批准证据；人读卡暂存、索引去重合并与回执均通过，可由调度器解锁下一批"}],{"batch_number":n,"staging_card_root":rel(stage) if stage else ""}

def replacement_release(manifest_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    """Gate an atomic replacement of one already-released batch contribution."""
    m=read(manifest_path); issues=[]
    if m.get("schema")!="video-pain-batch-replacement-release-v1" or m.get("status")!="awaiting_replacement_audit": issues.append("replacement release manifest schema 或状态不正确")
    operation=str(m.get("operation") or "replace")
    if operation not in {"replace","add"}: issues.append("replacement release operation 只能为 replace 或 add")
    lineage_path=check_file(m.get("lineage_path"),m.get("lineage_sha256"),"重建谱系",issues); lineage={}; rebuilt={}; root=None
    if lineage_path:
        lineage=read(lineage_path); rebuilt=lineage.get("rebuilt_contribution",{}) if isinstance(lineage.get("rebuilt_contribution"),dict) else {}; scope=lineage.get("replacement_scope",{}) if isinstance(lineage.get("replacement_scope"),dict) else {}
        if lineage.get("schema")!="video-pain-rebuilt-contribution-lineage-v1" or lineage.get("status")!="approved_rebuild_awaiting_release": issues.append("重建谱系 schema 或状态不正确")
        root=resolved(str(rebuilt.get("machine_root") or "")); audit=check_file(rebuilt.get("machine_audit_receipt"),rebuilt.get("machine_audit_sha256"),"重建机器审核回执",issues)
        if not root.is_dir() or rebuilt.get("machine_root_sha256")!=tree_sha(root): issues.append("重建谱系 machine_root 哈希与当前机器候选不一致")
        if audit:
            receipt_payload=read(audit); candidate=(receipt_payload.get("subject",{}) or {}).get("candidateSha256") if isinstance(receipt_payload.get("subject"),dict) else None
            if receipt_payload.get("status")!="approved" or candidate!=tree_sha(root): issues.append("重建机器审核回执未 approved 或未绑定当前机器候选")
        affected=scope.get("pain_ids",[]) if isinstance(scope.get("pain_ids"),list) else []
    else: affected=[]
    if set(m.get("affected_pain_ids",[]) if isinstance(m.get("affected_pain_ids"),list) else [])!=set(affected) or not affected: issues.append("replacement manifest affected_pain_ids 必须与重建谱系完全一致")
    current_index=check_file(m.get("current_index_path"),m.get("current_index_sha256"),"当前正式索引快照",issues); old_cards=m.get("old_cards",[]) if isinstance(m.get("old_cards"),list) else []
    if operation=="replace" and len(old_cards)!=len(affected): issues.append("replace 的 old_cards 必须与受影响 pain_id 一一对应")
    if operation=="add" and old_cards: issues.append("add 不得携带 old_cards，避免误覆盖既有正式卡")
    old_paths=set()
    for item in old_cards:
        if not isinstance(item,dict): issues.append("old_cards 含非对象"); continue
        path=resolved(str(item.get("path") or "")); old_paths.add(path)
        if item.get("pain_id") not in affected or not path.is_file() or sha(path)!=item.get("sha256"): issues.append("旧正式卡路径、pain_id 或哈希不匹配")
    rows=[]; current_rows=[]
    if current_index:
        rows=current_index.read_text(encoding="utf-8").splitlines()
        try: current_rows=[json.loads(line) for line in rows if line.strip()]
        except json.JSONDecodeError: issues.append("当前正式索引含非 JSON 行")
        for pain_id in affected:
            matched=[line for line in rows if json.loads(line).get("pain_id")==pain_id]
            if operation=="replace" and len(matched)!=1: issues.append(f"旧正式索引未恰好命中 {pain_id} 一行")
            if operation=="add" and matched: issues.append(f"新增卡 {pain_id} 已存在正式索引，不能作为 add")
    preserved=m.get("preserved_assets",[]) if isinstance(m.get("preserved_assets"),list) else []
    if not preserved: issues.append("replacement manifest 必须列出保留资产（至少样本与既有其他批卡）")
    for item in preserved:
        if not isinstance(item,dict): issues.append("preserved_assets 含非对象"); continue
        path=resolved(str(item.get("path") or ""))
        if path in old_paths or not path.is_file() or sha(path)!=item.get("sha256"): issues.append("保留资产被误列为替换项、缺失或哈希漂移")
    staged_root=resolved(str(m.get("staging_card_root") or "")); staged_index=check_file(m.get("staging_index"),m.get("staging_index_sha256"),"替换后暂存索引",issues)
    staged_cards=list(staged_root.rglob("*.md")) if staged_root.is_dir() else []
    if not staged_cards: issues.append("替换后暂存人读卡不存在")
    if staged_index:
        try: next_rows=[json.loads(line) for line in staged_index.read_text(encoding="utf-8").splitlines() if line.strip()]
        except json.JSONDecodeError: next_rows=[]; issues.append("替换后暂存索引含非 JSON 行")
        ids=[row.get("pain_id") for row in next_rows if isinstance(row,dict) and row.get("module_type")=="pain"]
        if len(ids)!=len(set(ids)) or not set(affected)<=set(ids): issues.append("替换后暂存索引 pain_id 重复或遗漏受影响卡")
        current_by_id={row.get("pain_id"):row for row in current_rows if isinstance(row,dict) and row.get("pain_id")}
        next_by_id={row.get("pain_id"):row for row in next_rows if isinstance(row,dict) and row.get("pain_id")}
        for item in preserved:
            if isinstance(item,dict):
                path=resolved(str(item.get("path") or "")); matched=[key for key,row in current_by_id.items() if resolved(str(row.get("module_path") or ""))==path]
                if len(matched)!=1 or next_by_id.get(matched[0])!=current_by_id[matched[0]]: issues.append("保留资产对应索引行被替换暂存意外改写")
        if root and root.is_dir():
            try: rebuilt_cards={str(card.get("pain_id") or ""):card for card in read(root/"routed-modules.json").get("pain_cards",[]) if isinstance(card,dict)}
            except (OSError,json.JSONDecodeError): rebuilt_cards={}; issues.append("重建机器候选 routed-modules 无法读取")
            formal_root=(ROOT/"02_资产中心"/"02_处理库"/"02_痛点_内容模块（会员专享）").resolve()
            for pain_id in affected:
                old=next((item for item in old_cards if isinstance(item,dict) and item.get("pain_id")==pain_id),{})
                final_path=resolved(str(old.get("path") or "")) if operation=="replace" else resolved(str(next_by_id.get(pain_id,{}).get("module_path") or ""))
                staged_path=staged_root/final_path.relative_to(formal_root) if formal_root in final_path.parents else staged_root/"__invalid__"
                card=rebuilt_cards.get(pain_id); rendered=staged_path.read_text(encoding="utf-8",errors="ignore") if staged_path.is_file() else ""
                if not card or not rendered or not rendered.startswith("# 痛点卡｜") or "来源：" not in rendered or "我是姜来已来" not in rendered or any(token in rendered for token in ("video-pain-card-v1","待小审","痛点 ID","哈希","基于原文整理")):
                    issues.append(f"{pain_id} 暂存人读卡格式或路径不合规")
                    continue
                for angle in card.get("angles",[]) if isinstance(card.get("angles"),list) else []:
                    if isinstance(angle,dict) and str(angle.get("short_video_expression") or "") not in rendered: issues.append(f"{pain_id} 暂存人读卡未逐字使用新机器候选表达")
                if next_by_id.get(pain_id,{}).get("module_path")!=str(final_path): issues.append(f"{pain_id} 替换后索引未指向计划正式卡路径")
                if operation=="add" and final_path.exists(): issues.append(f"新增卡 {pain_id} 的正式目标已存在，拒绝覆盖")
    replacement_receipt=check_file(m.get("replacement_merge_receipt"),m.get("replacement_merge_receipt_sha256"),"原子替换合并回执",issues)
    if replacement_receipt:
        payload=read(replacement_receipt)
        if payload.get("schema")!="video-pain-batch-replacement-merge-v1" or payload.get("status")!="staged" or set(payload.get("affected_pain_ids",[]))!=set(affected) or str(payload.get("operation") or "replace")!=operation: issues.append("原子替换合并回执未精确绑定操作类型和受影响卡")
        if staged_index and payload.get("staging_index_sha256")!=sha(staged_index): issues.append("原子替换合并回执未绑定暂存索引")
    no_pain=check_file(m.get("no_pain_coverage_path"),m.get("no_pain_coverage_sha256"),"无痛点覆盖记录",issues) if m.get("no_pain_coverage_path") else None
    if no_pain:
        payload=read(no_pain)
        source_ids: list[str]=[]
        if payload.get("schema")!="video-pain-no-pain-coverage-v1":
            issues.append("无痛点覆盖记录 schema 不正确")
        elif isinstance(payload.get("no_pain_sources"),list):
            # A batch may have several readable sources that legitimately contain
            # no independently supportable pain scenario. Each needs an explicit
            # reason; do not incorrectly require every such source to be blank.
            entries=payload["no_pain_sources"]
            source_ids=[str(item.get("source_id") or "") for item in entries if isinstance(item,dict)]
            if (not entries or len(source_ids)!=len(entries) or len(set(source_ids))!=len(source_ids)
                    or any(not source_id or not str(item.get("reason") or "").strip() for source_id,item in zip(source_ids,entries) if isinstance(item,dict))):
                issues.append("批次无痛点覆盖记录必须逐篇给出唯一 source_id 与明确理由")
        else:
            source_id=str(payload.get("source_id") or "")
            if payload.get("status")!="no_pain" or not source_id:
                issues.append("无痛点覆盖记录状态或 source_id 不正确")
            else:
                source_ids=[source_id]
        if source_ids and root and root.is_dir():
            try:
                bundle=read(resolved(str(rebuilt.get("bundle") or rebuilt.get("bundle_path") or ""))); source_text={str(item.get("source_id") or ""):str(item.get("full_text") or "").strip() for item in bundle.get("sources",[]) if isinstance(item,dict)}
                routed=read(root/"routed-modules.json"); evidence_sources={str(ev.get("source_id") or "") for card in routed.get("pain_cards",[]) if isinstance(card,dict) for angle in card.get("angles",[]) if isinstance(angle,dict) for ev in angle.get("evidence",[]) if isinstance(ev,dict)}
                missing=[source_id for source_id in source_ids if source_id not in source_text]
                reused=[source_id for source_id in source_ids if source_id in evidence_sources]
                if missing or reused:
                    issues.append("无痛点覆盖记录未与证据包来源或机器证据排除状态一致")
            except (OSError,json.JSONDecodeError): issues.append("无法读取无痛点覆盖所绑定的证据包或路由")
    return [{"id":"rebuild-replacement-atomicity","status":"passed" if not issues else "failed","detail":"；".join(issues) or "新机器证据、旧卡/索引快照、受影响范围、保留资产和替换后暂存索引均精确绑定，可原子替换"}],{"batch_number":lineage.get("batch_number"),"affected_pain_ids":affected}

def post_release(index_path: Path, source_root: Path, coverage_ledger: Path, added_ids: set[str], expected_total: int, expected_prior: int, active_batch: int, no_pain_coverage: Path | None=None, expected_no_pain_ids: set[str] | None=None, commit_receipt: Path | None=None, prior_replace_receipt: Path | None=None) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    """Read-only formal verification after an approved atomic add/replace."""
    issues=[]
    try: rows=[json.loads(line) for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError: rows=[]; issues.append("正式索引含非 JSON 行")
    pain_rows=[row for row in rows if isinstance(row,dict) and row.get("module_type")=="pain"]
    ids=[str(row.get("pain_id") or "") for row in pain_rows]
    if len(rows)!=expected_total or len(pain_rows)!=expected_total or len(set(ids))!=expected_total or any(not item for item in ids): issues.append(f"正式库必须恰有 {expected_total} 张唯一 pain 卡及 {expected_total} 条索引行")
    if not added_ids <= set(ids) or len(set(ids)-added_ids)!=expected_prior: issues.append(f"新增卡或此前 {expected_prior} 张保留卡数量不正确")
    manifest={}
    source_manifest=source_root/"manifest.jsonl"
    if source_manifest.is_file(): manifest={item.get("source_id"):item for item in (json.loads(line) for line in source_manifest.read_text(encoding="utf-8").splitlines() if line.strip())}
    else: issues.append("标准化来源 manifest 不存在")
    for row in pain_rows:
        path=resolved(str(row.get("module_path") or "")); text=path.read_text(encoding="utf-8",errors="ignore") if path.is_file() else ""
        forbidden=("video-pain-card-v1","待小审","痛点 ID","来源定位","哈希","基于原文整理")
        if not path.is_file() or not text.startswith("# 痛点卡｜") or "来源：" not in text or "我是姜来已来" not in text or any(token in text for token in forbidden): issues.append(f"{row.get('pain_id')} 正式人读卡格式不合规"); continue
        expressions=re.findall(r"#### 表达方式\s*\n\s*(.*?)(?=\n\n来源：)",text,re.S)
        source_texts=[]
        for source_id in row.get("source_ids",[]) if isinstance(row.get("source_ids"),list) else []:
            item=manifest.get(source_id,{}); p=source_root/str(item.get("relative_path") or "")
            if p.is_file(): source_texts.append(p.read_text(encoding="utf-8",errors="ignore"))
        if not expressions or not source_texts or any(not any(expr in source for source in source_texts) for expr in expressions): issues.append(f"{row.get('pain_id')} 人读表达未逐字回到索引来源全文")
    if no_pain_coverage is not None:
        expected_no_pain_ids=expected_no_pain_ids or set()
        try:
            payload=read(no_pain_coverage)
            entries=payload.get("no_pain_sources",[]) if isinstance(payload.get("no_pain_sources"),list) else []
            actual={str(item.get("source_id") or "") for item in entries if isinstance(item,dict)}
            if payload.get("schema")!="video-pain-no-pain-coverage-v1" or actual!=expected_no_pain_ids or any(not str(item.get("reason") or "").strip() for item in entries if isinstance(item,dict)):
                issues.append("本批无痛点覆盖记录的 schema、来源范围或理由不正确")
            indexed_sources={source_id for row in pain_rows for source_id in (row.get("source_ids",[]) if isinstance(row.get("source_ids"),list) else [])}
            if actual & indexed_sources: issues.append("本批标记为无痛点的来源被正式 pain 卡错误使用")
        except (OSError,json.JSONDecodeError):
            issues.append("无法读取本批无痛点覆盖记录")
    if commit_receipt is not None:
        try:
            payload=read(commit_receipt)
            if (payload.get("schema")!="video-pain-batch-commit-receipt-v1" or payload.get("status")!="committed_awaiting_post_release"
                    or str(payload.get("operation") or "")!="add" or set(payload.get("affected_pain_ids",[]))!=added_ids
                    or payload.get("post_commit_card_count")!=expected_total or payload.get("post_commit_unique_index_rows")!=expected_total):
                issues.append("提交回执 schema、状态、操作、受影响卡或提交后数量不正确")
            commit_index=resolved(str(payload.get("formal_index") or ""))
            if commit_index!=index_path or not commit_index.is_file() or payload.get("formal_index_sha256")!=sha(commit_index):
                issues.append("提交回执未精确绑定当前正式索引")
            commit_manifest=resolved(str(payload.get("manifest") or ""))
            if not commit_manifest.is_file() or payload.get("manifest_sha256")!=sha(commit_manifest):
                issues.append("提交回执未精确绑定发布清单")
            audit_path=resolved(str(payload.get("audit_receipt") or ""))
            if not audit_path.is_file() or payload.get("audit_receipt_sha256")!=sha(audit_path) or read(audit_path).get("status")!="approved":
                issues.append("提交回执未精确绑定 approved 预审回执")
            committed={resolved(str(path)) for path in payload.get("committed_cards",[]) if str(path)}
            current_added={resolved(str(row.get("module_path") or "")) for row in pain_rows if row.get("pain_id") in added_ids}
            if committed!=current_added or len(committed)!=len(added_ids) or any(not path.is_file() for path in committed):
                issues.append("提交回执的新增正式卡未与当前索引一一对应")
            preserved=payload.get("preserved_assets",[]) if isinstance(payload.get("preserved_assets"),list) else []
            if len(preserved)!=expected_prior:
                issues.append("提交回执的保留资产数量不正确")
            for item in preserved:
                path=resolved(str(item.get("path") or "")) if isinstance(item,dict) else Path()
                if not isinstance(item,dict) or not path.is_file() or item.get("sha256")!=sha(path):
                    issues.append("提交回执所列既有正式资产发生漂移")
        except (OSError,json.JSONDecodeError):
            issues.append("无法读取提交回执或其绑定文件")
    if prior_replace_receipt is not None:
        try:
            payload=read(prior_replace_receipt)
            replaced=set(payload.get("affected_pain_ids",[]) if isinstance(payload.get("affected_pain_ids"),list) else [])
            if (payload.get("schema")!="video-pain-batch-operation-commit-receipt-v1" or payload.get("status")!="committed_awaiting_operation_02"
                    or payload.get("operation")!="replace" or len(replaced)!=1):
                issues.append("前置替换提交回执 schema、状态或替换范围不正确")
            manifest_path=resolved(str(payload.get("manifest") or "")); audit_path=resolved(str(payload.get("audit_receipt") or ""))
            if not manifest_path.is_file() or payload.get("manifest_sha256")!=sha(manifest_path): issues.append("前置替换提交回执未绑定替换清单")
            if not audit_path.is_file() or payload.get("audit_receipt_sha256")!=sha(audit_path) or read(audit_path).get("status")!="approved": issues.append("前置替换提交回执未绑定 approved 预审")
            archive=resolved(str(payload.get("archive") or "")); old_cards=list(archive.rglob("*.md")) if archive.is_dir() else []
            replaced_id=next(iter(replaced),""); current_row=next((row for row in pain_rows if row.get("pain_id")==replaced_id),{})
            current_path=resolved(str(current_row.get("module_path") or "")); current_text=current_path.read_text(encoding="utf-8",errors="ignore") if current_path.is_file() else ""
            if len(old_cards)!=1 or not current_text: issues.append("替换前归档卡或当前替换卡不存在")
            else:
                old_text=old_cards[0].read_text(encoding="utf-8",errors="ignore")
                old_expr=re.findall(r"#### 表达方式\s*\n\s*(.*?)(?=\n\n来源：)",old_text,re.S)
                current_expr=re.findall(r"#### 表达方式\s*\n\s*(.*?)(?=\n\n来源：)",current_text,re.S)
                if not old_expr or len(current_expr)<=len(old_expr) or any(expression not in current_text for expression in old_expr):
                    issues.append("替换卡未完整保留旧角度表达，或未追加新完整原话")
        except (OSError,json.JSONDecodeError):
            issues.append("无法读取前置替换提交回执或旧版本归档")
    ledger=read(coverage_ledger) if coverage_ledger.is_file() else {}
    active=ledger.get("active_batch")
    active_number=active.get("batch_number") if isinstance(active,dict) else active if isinstance(active,int) else None
    if ledger.get("next_batch_ready") is not False or active_number!=active_batch: issues.append(f"batch{active_batch + 1} 已被提前解锁或当前台账未锁定 batch{active_batch}")
    next_batch=coverage_ledger.parent/"batches"/f"batch-{active_batch + 1:04d}"
    if next_batch.exists(): issues.append(f"batch-{active_batch + 1:04d} 已启动")
    return [{"id":"post-release-formal-integrity","status":"passed" if not issues else "failed","detail":"；".join(issues) or f"{expected_total} 张唯一 pain 卡/索引、{len(added_ids)} 张本批新增、{expected_prior} 张保留卡、替换旧角度保留、提交回执、原文直引人读格式、无痛点覆盖及下一批锁定均通过"}],{"formal_index":rel(index_path),"added_pain_ids":sorted(added_ids),"active_batch":active_batch,"no_pain_source_ids":sorted(expected_no_pain_ids or set()),"commit_receipt":rel(commit_receipt) if commit_receipt else "","prior_replace_receipt":rel(prior_replace_receipt) if prior_replace_receipt else ""}

def coverage(ledger_path: Path, source_root: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    ledger=read(ledger_path); issues=[]
    manifest=source_root/"manifest.jsonl"; expected=[]
    if not manifest.is_file(): issues.append("标准化源 manifest.jsonl 不存在")
    else: expected=[json.loads(x)["source_id"] for x in manifest.read_text(encoding="utf-8").splitlines() if x.strip()]
    batches=ledger.get("batches",[]) if isinstance(ledger.get("batches"),list) else []
    ids=[]
    for b in batches:
        p=check_file(b.get("batch_audit_receipt"),b.get("batch_audit_sha256"),f"批次 {b.get('batch_number')} 审核回执",issues)
        if p and read(p).get("status")!="approved": issues.append(f"批次 {b.get('batch_number')} 未 approved")
        ids += b.get("source_ids",[]) if isinstance(b.get("source_ids"),list) else []
    if ledger.get("schema")!="video-pain-rebuild-coverage-v1": issues.append("coverage ledger schema 不正确")
    if len(expected)!=EXPECTED_TOTAL or set(ids)!=set(expected) or len(ids)!=len(expected): issues.append("未完成 547 篇无重无漏覆盖")
    # 单批只校验其连续校对源链；四账号分布属于全量覆盖审核，不能引用
    # 未传入的 manifest 变量而把每个批次都变成运行时 NameError。
    accounts=ledger.get("account_counts") if isinstance(ledger.get("account_counts"),dict) else {}
    return [{"id":"full-coverage-and-batch-chain","status":"passed" if not issues else "failed","detail":"；".join(issues) or "通过"}],{"expected_source_count":expected,"account_counts":accounts}

def release(manifest_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    m=read(manifest_path); issues=[]
    if m.get("schema")!="video-pain-rebuild-release-v1": issues.append("release manifest schema 不正确")
    for path_key,hash_key,label in (("coverage_audit_receipt","coverage_audit_sha256","覆盖审核回执"),("staging_card_root",None,"人读卡暂存目录"),("staging_index","staging_index_sha256","索引暂存"),("archive_manifest","archive_manifest_sha256","旧库归档清单")):
        p=check_file(m.get(path_key),m.get(hash_key),label,issues) if hash_key else (resolved(str(m.get(path_key))) if m.get(path_key) else None)
        if not hash_key and (p is None or not p.is_dir() or not list(p.rglob("*.md"))): issues.append(f"{label} 不存在或不含人读卡")
        if label=="覆盖审核回执" and p and read(p).get("status")!="approved": issues.append("547 篇覆盖审核未 approved")
    if m.get("formal_switched") is not False: issues.append("切换前复核 manifest 不得声明 formal_switched")
    return [{"id":"pre-switch-staging-integrity","status":"passed" if not issues else "failed","detail":"；".join(issues) or "通过"}],{"manifest":rel(manifest_path)}

def definition_repair(plan_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    """Audit a metadata-only repair; it must never alter evidence or expressions."""
    plan=read(plan_path); issues=[]
    if plan.get("schema")!="video-pain-definition-repair-plan-v1" or plan.get("status")!="awaiting_audit": issues.append("定义修复计划 schema 或状态不正确")
    evidence=check_file(plan.get("approved_evidence_path"),plan.get("approved_evidence_sha256"),"已通过证据总库",issues)
    registry=check_file(plan.get("registry_path"),plan.get("registry_sha256"),"已批准痛点登记簿",issues)
    repairs=plan.get("repairs",[]) if isinstance(plan.get("repairs"),list) else []
    if not repairs: issues.append("定义修复计划为空")
    evidence_by_id={}
    if evidence:
        try:
            evidence_by_id={str(row.get("item",{}).get("evidence_id") or ""):row.get("item",{}) for row in (json.loads(line) for line in evidence.read_text(encoding="utf-8").splitlines() if line.strip()) if isinstance(row,dict) and row.get("kind")=="evidence" and isinstance(row.get("item"),dict)}
        except json.JSONDecodeError: issues.append("已通过证据总库含非 JSON 行")
    registry_by_id={}
    if registry:
        try: registry_by_id={str(row.get("pain_id") or ""):row for row in read(registry).get("entries",[]) if isinstance(row,dict)}
        except (OSError,json.JSONDecodeError): issues.append("已批准痛点登记簿无法读取")
    seen=set()
    for repair in repairs:
        if not isinstance(repair,dict): issues.append("定义修复项必须为对象"); continue
        evidence_id=str(repair.get("evidence_id") or ""); item=evidence_by_id.get(evidence_id); pain_id=str(repair.get("pain_id") or "")
        if not evidence_id or evidence_id in seen or not item: issues.append("定义修复项 evidence_id 缺失、重复或未命中"); continue
        seen.add(evidence_id); canonical=registry_by_id.get(pain_id)
        if item.get("pain_id")!=pain_id or item.get("source_id")!=repair.get("source_id") or item.get("pain_definition")!=repair.get("old_definition"): issues.append(f"{evidence_id} 的原始定义或来源已漂移"); continue
        if not canonical or canonical.get("pain_title")!=item.get("pain_title") or canonical.get("taxonomy_id")!=item.get("taxonomy_id") or canonical.get("pain_definition")!=repair.get("new_definition"): issues.append(f"{evidence_id} 未严格对齐已批准同 pain_id 标题、分类和定义")
    return [{"id":"definition-repair-scope-and-identity","status":"passed" if not issues else "failed","detail":"；".join(issues) or "仅统一已批准同 pain_id 的定义文本；原文证据、表达、标题和分类均未改写"}],{"definition_repair_plan":rel(plan_path)}

def coverage_order_repair(plan_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    plan=read(plan_path); issues=[]
    if plan.get("schema")!="video-pain-coverage-order-repair-plan-v1" or plan.get("status")!="awaiting_audit": issues.append("覆盖顺序修复计划 schema 或状态不正确")
    ledger=check_file(plan.get("coverage_ledger_path"),plan.get("coverage_ledger_sha256"),"覆盖台账",issues)
    pre=check_file(plan.get("coverage_preflight_path"),plan.get("coverage_preflight_sha256"),"冻结覆盖预检",issues)
    if ledger and pre:
        l,p=read(ledger),read(pre); protected=int(plan.get("protected_source_count",-1)); rows=l.get("sources",[]); bindings=p.get("source_bindings",[])
        if l.get("active_batch") is not None or protected!=len(l.get("completed_batches",[]))*5: issues.append("活动批次或已完成范围不符合计划")
        if len(rows)!=len(bindings) or [x.get("source_id") for x in rows[:protected]]!=[x.get("source_id") for x in bindings[:protected]]: issues.append("已处理来源顺序或覆盖范围漂移")
        if {x.get("source_id") for x in rows}!={x.get("source_id") for x in bindings}: issues.append("修复会改变来源集合")
    return [{"id":"coverage-order-repair-scope-and-identity","status":"passed" if not issues else "failed","detail":"；".join(issues) or "仅允许按冻结预检重排未处理来源；已完成来源与正式资产不变"}],{"coverage_order_repair_plan":rel(plan_path)}

def library_cleanup_v2(plan_path: Path) -> tuple[list[dict[str,Any]],dict[str,Any]]:
    """Audit the one-way v2 cleanup before any active asset is deleted."""
    plan=read(plan_path); issues=[]
    if plan.get("schema")!="video-pain-library-cleanup-plan-v2" or plan.get("status")!="awaiting_cleanup_audit": issues.append("v2 清理计划 schema 或状态不正确")
    cards=plan.get("legacy_cards",[]) if isinstance(plan.get("legacy_cards"),list) else []
    rows=plan.get("legacy_index_rows",[]) if isinstance(plan.get("legacy_index_rows"),list) else []
    if len(cards)!=plan.get("expected_active_card_count") or len(cards)!=48: issues.append("清理计划必须精确列出 48 张活跃正式卡")
    if len(rows)!=plan.get("expected_angle_index_row_count") or len(rows)!=53: issues.append("清理计划必须精确列出 53 条专用角度索引")
    root=resolved(str(plan.get("pain_root") or "")); index=check_file(plan.get("index_path"),plan.get("index_sha256"),"专用角度索引",issues)
    listed=set()
    for item in cards:
        if not isinstance(item,dict): issues.append("旧卡清单含非对象"); continue
        path=resolved(str(item.get("path") or "")); listed.add(path)
        if root not in path.parents or "00_审核样例" in path.parts or not path.is_file() or sha(path)!=item.get("sha256") or not path.read_text(encoding="utf-8",errors="ignore").startswith("# 痛点卡｜"):
            issues.append(f"清理卡不在活跃会员库或已漂移：{rel(path)}")
    taxonomy=plan.get("legacy_taxonomy") if isinstance(plan.get("legacy_taxonomy"),dict) else {}
    check_file(taxonomy.get("path"),taxonomy.get("sha256"),"旧分类法",issues)
    if index:
        try:
            actual=[json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
            actual_rows=[hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode("utf-8")).hexdigest() for row in actual]
            if actual_rows != [str(item.get("sha256") or "") for item in rows]: issues.append("专用角度索引 53 条内容或顺序已漂移")
        except json.JSONDecodeError: issues.append("专用角度索引含非 JSON 行")
    sample=plan.get("preserve_sample") if isinstance(plan.get("preserve_sample"),dict) else {}
    sample_src=resolved(str(sample.get("source_path") or "")); sample_target=resolved(str(sample.get("target_path") or ""))
    if not sample_src.is_file() or sha(sample_src)!=sample.get("source_sha256") or sample_target.exists() or sample_src in listed or index and any(str(row.get("card_path") or "") == str(sample_src) for row in actual):
        issues.append("审核样例必须保留、不得在清理清单或正式索引中，且新命名目标必须空闲")
    if not sample_target.name.startswith(str(sample.get("secondary_keyword") or "")+"_") or not sample_target.name.endswith("_"+str(sample.get("pain_id") or "")+".md"):
        issues.append("审核样例目标文件名不符合二级词_标题_PAIN-ID")
    if any(".runtime" not in str(path) for path in (plan.get("excluded_paths") or [])) or not any(".runtime" in str(path) for path in (plan.get("excluded_paths") or [])):
        issues.append("清理计划必须明确排除 .runtime 历史证据与回执")
    return [{"id":"member-pain-library-cleanup-v2","status":"passed" if not issues else "failed","detail":"；".join(issues) or "精确绑定 48 张活跃卡、旧分类法、53 条专用角度索引；样例和 .runtime 均已排除"}],{"cleanup_plan":rel(plan_path)}

def main() -> int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    for name in ("batch","coverage","source-ledger"):
        x=sub.add_parser(name); x.add_argument("--manifest",required=True); x.add_argument("--source-root",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("legacy-cleanup-scope"); x.add_argument("--card-root",required=True); x.add_argument("--index",required=True); x.add_argument("--preserved-sample",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("legacy-cleanup-plan"); x.add_argument("--manifest",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("library-cleanup-v2"); x.add_argument("--manifest",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("batch-release"); x.add_argument("--manifest",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("replacement-release"); x.add_argument("--manifest",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("definition-repair"); x.add_argument("--plan",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("coverage-order-repair"); x.add_argument("--plan",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("post-release"); x.add_argument("--index",required=True); x.add_argument("--source-root",required=True); x.add_argument("--coverage-ledger",required=True); x.add_argument("--added-pain-ids",required=True); x.add_argument("--expected-pain-count",required=True,type=int); x.add_argument("--expected-prior-count",required=True,type=int); x.add_argument("--active-batch",required=True,type=int); x.add_argument("--no-pain-coverage"); x.add_argument("--no-pain-source-ids",default=""); x.add_argument("--commit-receipt"); x.add_argument("--prior-replace-receipt"); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    x=sub.add_parser("release"); x.add_argument("--manifest",required=True); x.add_argument("--receipt",required=True); x.add_argument("--task-id",default="")
    a=p.parse_args()
    if a.cmd=="legacy-cleanup-scope":
        path=resolved(a.card_root); checks,subject=legacy_cleanup_scope(path,resolved(a.index),resolved(a.preserved_sample))
    elif a.cmd=="definition-repair":
        path=resolved(a.plan); checks,subject=definition_repair(path)
    elif a.cmd=="coverage-order-repair":
        path=resolved(a.plan); checks,subject=coverage_order_repair(path)
    elif a.cmd=="post-release":
        path=resolved(a.index); checks,subject=post_release(path,resolved(a.source_root),resolved(a.coverage_ledger),{item for item in a.added_pain_ids.split(",") if item},a.expected_pain_count,a.expected_prior_count,a.active_batch,resolved(a.no_pain_coverage) if a.no_pain_coverage else None,{item for item in a.no_pain_source_ids.split(",") if item},resolved(a.commit_receipt) if a.commit_receipt else None,resolved(a.prior_replace_receipt) if a.prior_replace_receipt else None)
    else:
        path=resolved(a.manifest); checks,subject=(batch(path,resolved(a.source_root)) if a.cmd=="batch" else coverage(path,resolved(a.source_root)) if a.cmd=="coverage" else source_ledger(path,resolved(a.source_root)) if a.cmd=="source-ledger" else legacy_cleanup_plan(path) if a.cmd=="legacy-cleanup-plan" else library_cleanup_v2(path) if a.cmd=="library-cleanup-v2" else batch_release(path) if a.cmd=="batch-release" else replacement_release(path) if a.cmd=="replacement-release" else release(path))
    status="approved" if all(x["status"]=="passed" for x in checks) else "rejected"; task=a.task_id or hashlib.sha256(rel(path).encode()).hexdigest()[:16]
    receipt(resolved(a.receipt),task,status,checks,{**subject,"manifest":rel(path)}); print(json.dumps({"status":status,"checks":checks},ensure_ascii=False)); return 0 if status=="approved" else 2
if __name__=="__main__": raise SystemExit(main())
