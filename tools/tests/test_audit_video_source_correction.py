from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "audit_video_source_correction.py"
SPEC = importlib.util.spec_from_file_location("audit_video_source_correction", SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class AuditVideoSourceCorrectionTests(unittest.TestCase):
    def make_candidate(self) -> tuple[Path, Path]:
        temp = Path(tempfile.mkdtemp())
        source = temp / "source.md"
        original = "老板做账号，不要只讲产品。"
        source.write_text(f"---\nsource_id: VS-test-001\n---\n\n## 全文\n\n{original}\n", encoding="utf-8")
        start = original.index("，")
        corrected = original.replace("，", "。", 1)
        runtime = ROOT / ".runtime" / "test-video-source-correction"
        runtime.mkdir(parents=True, exist_ok=True)
        candidate = runtime / "candidate.md"
        change = {"change_id": "C-001", "type": "标点", "original_start": start, "original_end": start + 1, "original_text": "，", "corrected_text": "。", "reason": "句子在此处结束", "status": "applied"}
        candidate.write_text(
            "---\n"
            "schema: video-source-correction-candidate-v1\n"
            "source_id: VS-test-001\n"
            f"original_source_path: {source.as_posix()}\n"
            f"original_source_sha256: {hashlib.sha256(source.read_bytes()).hexdigest()}\n"
            f"original_full_text_sha256: {hashlib.sha256(original.encode()).hexdigest()}\n"
            f"corrected_full_text_sha256: {hashlib.sha256(corrected.encode()).hexdigest()}\n"
            "---\n\n## 校对后全文\n\n" + corrected + "\n\n## 修改清单\n\n```jsonl\n" + json.dumps(change, ensure_ascii=False) + "\n```\n",
            encoding="utf-8",
        )
        return candidate, source

    def test_approves_replayable_correction_and_v3_receipt(self) -> None:
        candidate, _ = self.make_candidate()
        checks, notes = AUDIT.audit_candidate(candidate)
        self.assertTrue(all(item.status == "passed" for item in checks), [item.detail for item in checks])
        receipt = candidate.with_name("audit-receipt.json")
        payload = AUDIT.write_receipt(receipt, "0123456789abcdef", 1, candidate, checks, notes)
        schema = json.loads((ROOT / "schemas" / "audit-receipt-v3.schema.json").read_text(encoding="utf-8"))
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(payload)))
        self.assertEqual("approved", payload["status"])

    def test_rejects_unrecorded_rewrite(self) -> None:
        candidate, _ = self.make_candidate()
        text = candidate.read_text(encoding="utf-8").replace("老板做账号。不要只讲产品。", "老板做账号。别只讲产品。")
        candidate.write_text(text, encoding="utf-8")
        checks, _ = AUDIT.audit_candidate(candidate)
        by_id = {item.id: item for item in checks}
        self.assertEqual("failed", by_id["corrected-text-hash"].status)
        self.assertEqual("failed", by_id["replay-without-unrecorded-rewrite"].status)

    def test_rejects_disallowed_or_mutating_pending_item(self) -> None:
        candidate, _ = self.make_candidate()
        text = candidate.read_text(encoding="utf-8").replace('"type": "标点"', '"type": "润色"').replace('"status": "applied"', '"status": "pending"').replace('"corrected_text": "。"', '"corrected_text": "！"')
        candidate.write_text(text, encoding="utf-8")
        checks, _ = AUDIT.audit_candidate(candidate)
        by_id = {item.id: item for item in checks}
        self.assertEqual("failed", by_id["change-ledger-shape-and-types"].status)
        self.assertEqual("failed", by_id["pending-isolation"].status)


if __name__ == "__main__":
    unittest.main()
