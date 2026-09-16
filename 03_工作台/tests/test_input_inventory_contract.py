from __future__ import annotations

import tempfile
import unittest
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.asset_paths import relative
from workflow.input_inventory import build_inventory, inventory_summary, video_correction_batch, video_refresh_batch


class InputInventoryContractTest(unittest.TestCase):
    def test_work_journal_sample_is_not_a_pending_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "02_资产中心" / relative("input.journals")
            source_root.mkdir(parents=True)
            (source_root / "样板-工作纪实-001.md").write_text("仅展示格式，不是工作记录。", encoding="utf-8")
            (source_root / "真实复盘.md").write_text("这是可进入拆解流程的真实复盘。", encoding="utf-8")

            rows = build_inventory(root)

        journals = [row for row in rows if row["source_type"] == "work-journals"]
        self.assertEqual([row["title"] for row in journals], ["真实复盘"])
        self.assertEqual(journals[0]["status"], "未拆解")

    def test_work_journal_inventory_exposes_formal_case_cards(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "02_资产中心" / relative("input.journals")
            source_root.mkdir(parents=True)
            source = source_root / "真实复盘.md"
            source.write_text("# 真实复盘\n", encoding="utf-8")
            index = root / "02_资产中心" / "02_处理库" / "05_案例_内容模块（会员专享）" / "02_案例卡索引" / "案例卡索引.jsonl"
            index.parent.mkdir(parents=True)
            index.write_text(json.dumps({
                "case_id": "CASE-note-001", "schema_version": "work-journal-case-card-v12",
                "source_title": "真实复盘", "source_path": str(source),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "title": "一条视频别又想两头都要", "card_path": "case.md",
            }, ensure_ascii=False) + "\n", encoding="utf-8")

            rows = build_inventory(root)

        journal = next(row for row in rows if row["source_type"] == "work-journals")
        self.assertEqual(journal["status"], "已拆解")
        self.assertEqual(journal["processing_output_count"], 1)
        self.assertEqual(journal["case_cards"], [{
            "case_id": "CASE-note-001", "title": "一条视频别又想两头都要", "card_path": "case.md",
        }])

    def test_work_journal_no_case_is_processed_not_pending(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "02_资产中心" / relative("input.journals")
            source_root.mkdir(parents=True)
            source = source_root / "纯观点复盘.md"
            source.write_text("# 纯观点复盘\n", encoding="utf-8")
            ledger = root / "02_资产中心" / "02_处理库" / "05_案例_内容模块（会员专享）" / "05_案例卡跳过记录" / "no_case_list.jsonl"
            ledger.parent.mkdir(parents=True)
            ledger.write_text(json.dumps({
                "schema_version": "work-journal-case-card-v12", "release_disposition": "no_case",
                "source_path": str(source), "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }, ensure_ascii=False) + "\n", encoding="utf-8")

            rows = build_inventory(root)

        journal = next(row for row in rows if row["source_type"] == "work-journals")
        self.assertEqual(journal["status"], "已处理")
        self.assertEqual(journal["processing_output_count"], 0)
        self.assertEqual(inventory_summary([journal])["work-journals"]["completed"], 1)
        self.assertEqual(inventory_summary([journal])["work-journals"]["noCase"], 1)

    def test_changed_work_journal_source_invalidates_old_case_index(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "02_资产中心" / relative("input.journals")
            source_root.mkdir(parents=True)
            source = source_root / "会变更的复盘.md"
            source.write_text("# 初版\n", encoding="utf-8")
            old_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            source.write_text("# 新版\n", encoding="utf-8")
            index = root / "02_资产中心" / "02_处理库" / "05_案例_内容模块（会员专享）" / "02_案例卡索引" / "案例卡索引.jsonl"
            index.parent.mkdir(parents=True)
            index.write_text(json.dumps({
                "case_id": "CASE-note-001", "schema_version": "work-journal-case-card-v12",
                "source_title": "会变更的复盘", "source_path": str(source), "source_sha256": old_hash,
                "title": "旧案例", "card_path": "case.md",
            }, ensure_ascii=False) + "\n", encoding="utf-8")
            journal = next(row for row in build_inventory(root) if row["source_type"] == "work-journals")

        self.assertEqual(journal["status"], "未拆解")
        self.assertIn("源文件已变更", journal["status_reason"])

    def test_video_inventory_uses_released_batch_and_next_source_audit_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "02_资产中心" / "01_输入库" / "04_视频文案-源文件（会员专享）" / "00_标准化源文档" / "account"
            source_root.mkdir(parents=True)
            manifest_rows = []
            ledger_sources = []
            for index in range(1, 4):
                source_id = f"VS-test-{index:06d}"
                path = source_root / f"{source_id}.md"
                path.write_text(f"# {source_id}\n", encoding="utf-8")
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                manifest_rows.append({"source_id": source_id, "relative_path": f"account/{source_id}.md", "title": source_id})
                ledger_sources.append({"source_id": source_id, "source_path": str(path), "source_sha256": digest, "status": "approved" if index == 1 else "pending"})
            manifest = source_root.parent / "manifest.jsonl"
            manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest_rows), encoding="utf-8")

            runtime = root / ".runtime" / "video-pain-cards" / "five-source-batches"
            candidate = runtime / "batch-0002" / "校对候选" / "VS-test-000002-校对版候选.md"
            candidate.parent.mkdir(parents=True)
            candidate.write_text("---\nsource_id: VS-test-000002\nsource_variant: corrected_candidate\n---\n", encoding="utf-8")
            receipt = runtime / "batch-0002" / "小审回执" / "VS-test-000002.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({
                "schema": "audit-receipt-v3", "artifactType": "video-source-correction-v1", "status": "approved",
                "subject": {"source_id": "VS-test-000002", "candidate": candidate.relative_to(root).as_posix(), "candidateSha256": hashlib.sha256(candidate.read_bytes()).hexdigest()},
            }, ensure_ascii=False), encoding="utf-8")
            ledger = {
                "schema": "video-pain-batch-ledger-v1", "batch_size": 1, "next_batch_ready": True, "active_batch": None,
                "sources": ledger_sources,
                "completed_batches": [{"batch_number": 1, "source_ids": ["VS-test-000001"], "release_status": "released"}],
            }
            state = runtime / "rebuild-547-state" / "coverage-ledger.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

            rows = {row["source_id"]: row for row in build_inventory(root) if row["source_type"] == "video-sources"}
            batch = video_refresh_batch(root)
            correction_batch = video_correction_batch(root)

        self.assertEqual(rows["VS-test-000001"]["status"], "已拆解")
        self.assertEqual(rows["VS-test-000002"]["status"], "未拆解")
        self.assertEqual(rows["VS-test-000003"]["status"], "待审核")
        self.assertEqual(inventory_summary(list(rows.values()))["video-sources"], {"label": "视频文案", "total": 3, "completed": 1, "pending": 1, "review": 1, "uncertain": 0, "noCase": 0})
        self.assertEqual([item["source_id"] for item in batch], ["VS-test-000002"])
        self.assertTrue(batch[0]["candidate_path"].endswith("VS-test-000002-校对版候选.md"))
        self.assertEqual(correction_batch["batch_number"], 2)
        self.assertEqual([item["source_id"] for item in correction_batch["sources"]], ["VS-test-000002"])

    def test_raw_video_file_is_visible_as_pending_refresh_without_a_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "02_资产中心" / "01_输入库" / "04_视频文案-源文件（会员专享）" / "新复制的视频原始表.xlsx"
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"copied-video-workbook")

            rows = [row for row in build_inventory(root) if row["source_type"] == "video-sources"]

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "新复制的视频原始表")
        self.assertEqual(rows[0]["status"], "未拆解")
        self.assertEqual(rows[0]["source_origin"], "manual-file")
        self.assertIn("用户已确认", rows[0]["status_reason"])

    def test_video_workbench_prefers_v2_rebuild_ledger_over_legacy_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_root = root / "02_资产中心" / "01_输入库" / "04_视频文案-源文件（会员专享）" / "00_标准化源文档" / "account"
            source_root.mkdir(parents=True)
            source_id = "VS-test-000001"
            source = source_root / f"{source_id}.md"
            source.write_text(f"# {source_id}\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (source_root.parent / "manifest.jsonl").write_text(json.dumps({"source_id": source_id, "relative_path": f"account/{source.name}", "title": source_id}, ensure_ascii=False) + "\n", encoding="utf-8")

            correction_root = root / ".runtime" / "video-pain-cards" / "five-source-batches"
            candidate = correction_root / "batch-0001" / "校对候选" / f"{source_id}-校对版候选.md"
            candidate.parent.mkdir(parents=True)
            candidate.write_text(f"---\nsource_id: {source_id}\nsource_variant: corrected_candidate\n---\n", encoding="utf-8")
            receipt = correction_root / "batch-0001" / "小审回执" / f"{source_id}.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({"schema": "audit-receipt-v3", "artifactType": "video-source-correction-v1", "status": "approved", "subject": {"source_id": source_id, "candidate": candidate.relative_to(root).as_posix(), "candidateSha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}}, ensure_ascii=False), encoding="utf-8")
            ledger = {"schema": "video-pain-batch-ledger-v1", "batch_size": 1, "next_batch_ready": True, "active_batch": None, "sources": [{"source_id": source_id, "source_path": str(source), "source_sha256": digest, "status": "pending"}], "completed_batches": []}
            v2 = root / ".runtime" / "video-pain-cards" / "rebuild-547-v2" / "state" / "coverage-ledger.json"
            v2.parent.mkdir(parents=True)
            v2.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
            legacy = correction_root / "rebuild-547-state" / "coverage-ledger.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({**ledger, "sources": [{**ledger["sources"][0], "status": "approved"}], "completed_batches": [{"batch_number": 99, "source_ids": [source_id], "release_status": "released"}]}, ensure_ascii=False), encoding="utf-8")

            batch = video_refresh_batch(root)
            correction_batch = video_correction_batch(root)

        self.assertEqual([item["source_id"] for item in batch], [source_id])
        self.assertEqual(correction_batch["batch_number"], 1)
        self.assertEqual([item["source_id"] for item in correction_batch["sources"]], [source_id])


if __name__ == "__main__":
    unittest.main()
