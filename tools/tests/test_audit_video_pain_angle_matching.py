from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "audit_video_pain_angle_matching.py"
SPEC = importlib.util.spec_from_file_location("audit_video_pain_angle_matching", SCRIPT); assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = MOD; SPEC.loader.exec_module(MOD)


class PainAngleMatchingTests(unittest.TestCase):
    def fixture(self) -> tuple[Path, Path, Path, Path, dict[str, object]]:
        root = Path(tempfile.mkdtemp()); source_root = root / "sources"; source_root.mkdir(); pain_root = root / "pain"; pain_root.mkdir()
        full = "小李晚上回家，事情太多很焦虑，后来失眠。"
        source = source_root / "source.md"; source.write_text(f"---\nsource_id: VID-1\n---\n\n## 全文\n\n{full}\n", encoding="utf-8")
        expression = full
        card = pain_root / "PAIN-X.md"; card.write_text(f"# 痛点卡｜测试\n\n### 角度 1｜夜晚事情太多\n\n#### 表达方式\n\n{expression}\n\n来源：测试｜测试选题\n\n---\n\n• 我是姜来已来\n", encoding="utf-8")
        pain_index = root / "pain-index.jsonl"; pain_index.write_text(json.dumps({"module_type":"pain","pain_id":"PAIN-X","module_path":str(card)}, ensure_ascii=False) + "\n", encoding="utf-8")
        row = {"schema":"video-pain-angle-index-v1","status":"active","angle_id":"ANGLE-X-001","pain_id":"PAIN-X","card_path":str(card),"card_sha256":MOD.sha(card),"angle_ordinal":1,"angle_title":"夜晚事情太多","expression_sha256":hashlib.sha256(expression.encode()).hexdigest(),"source_anchor":{"source_id":"VID-1","original_source_path":str(source),"original_full_text_sha256":hashlib.sha256(full.encode()).hexdigest(),"start_offset":0,"end_offset":len(full),"original_excerpt":full},"target_people":["独居上班族"],"scene_tags":["晚上回家"],"core_contradiction":"事情太多很焦虑"}
        angle_index = root / "angles.jsonl"; angle_index.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        return root, source_root, pain_root, pain_index, row

    def test_rejects_utf16_missing_anchor_and_archive_mix(self) -> None:
        root, source_root, pain_root, pain_index, row = self.fixture(); angle_index = root / "angles.jsonl"
        self.assertEqual([], MOD.angle_index_checks(angle_index, pain_index, pain_root, source_root))
        card = Path(str(row["card_path"])); card.write_text(card.read_text(encoding="utf-8"), encoding="utf-16")
        issues = MOD.angle_index_checks(angle_index, pain_index, pain_root, source_root); self.assertTrue(any("UTF-8" in item for item in issues))
        card.write_text("# 痛点卡｜测试\n\n### 角度 1｜夜晚事情太多\n\n#### 表达方式\n\n小李晚上回家，事情太多很焦虑，后来失眠。\n\n来源：测试｜测试选题\n", encoding="utf-8")
        row["card_sha256"] = MOD.sha(card); row.pop("source_anchor"); angle_index.write_text(json.dumps(row, ensure_ascii=False)+"\n", encoding="utf-8")
        issues = MOD.angle_index_checks(angle_index, pain_index, pain_root, source_root); self.assertTrue(any("source_anchor" in item for item in issues))
        archive = root / "99_归档" / "PAIN-X.md"; archive.parent.mkdir(); archive.write_text(card.read_text(encoding="utf-8"), encoding="utf-8")
        row["source_anchor"] = {"source_id":"VID-1","original_source_path":str(source_root / "source.md"),"original_full_text_sha256":hashlib.sha256("小李晚上回家，事情太多很焦虑，后来失眠。".encode()).hexdigest(),"start_offset":0,"end_offset":21,"original_excerpt":"小李晚上回家，事情太多很焦虑，后来失眠。"}; row["card_path"] = str(archive); row["card_sha256"] = MOD.sha(archive); angle_index.write_text(json.dumps(row, ensure_ascii=False)+"\n", encoding="utf-8")
        issues = MOD.angle_index_checks(angle_index, pain_index, pain_root, source_root); self.assertTrue(any("归档" in item or "非正式" in item for item in issues))

    def test_rejects_angle_id_drift_and_vague_structure_reason(self) -> None:
        root, _, _, _, row = self.fixture(); previous = root / "prior.jsonl"; current = root / "current.jsonl"
        previous.write_text(json.dumps(row, ensure_ascii=False)+"\n", encoding="utf-8"); changed = dict(row); changed["card_sha256"] = "baseline-hash-drift"; changed["source_anchor"] = dict(row["source_anchor"]); changed["source_anchor"]["start_offset"] = 1
        current.write_text(json.dumps(changed, ensure_ascii=False)+"\n", encoding="utf-8")
        self.assertTrue(MOD.release_checks(previous, current, set()))
        candidate = root / "candidate.json"; candidate.write_text(json.dumps({"small_structures":[{"replication_function":"痛点圈人","structure_three":{"angle_id":"ANGLE-X-001","module_path":row["card_path"],"source_anchor":row["source_anchor"],"selection_reason":{"target_people":"相关","scene":"适合","core_contradiction":"痛点明显","functional_fit":"痛点圈人"}}}]}, ensure_ascii=False), encoding="utf-8")
        angles = root / "angles.jsonl"; angles.write_text(json.dumps(row, ensure_ascii=False)+"\n", encoding="utf-8")
        issues = MOD.structure_checks(candidate, angles); self.assertGreaterEqual(len(issues), 3)


if __name__ == "__main__":
    unittest.main()
