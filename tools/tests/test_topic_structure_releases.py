from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow import topic_structure_releases as releases
from importlib.util import module_from_spec, spec_from_file_location

_migration_spec = spec_from_file_location("migrate_topic_tables_v42", ROOT / "10_Skills武器库" / "爆款选题分类Skill" / "scripts" / "migrate_topic_tables_v42.py")
assert _migration_spec and _migration_spec.loader
migration = module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(migration)
_refresh_spec = spec_from_file_location("refresh_topic_stats", ROOT / "10_Skills武器库" / "爆款选题分类Skill" / "scripts" / "refresh_topic_stats.py")
assert _refresh_spec and _refresh_spec.loader
refresh = module_from_spec(_refresh_spec)
_refresh_spec.loader.exec_module(refresh)


class TopicStructureReleaseTests(unittest.TestCase):
    def make_owner_freeze_bundle(self, root: Path) -> tuple[Path, Path]:
        candidate = root / "candidate.json"
        receipt = root / "receipt.json"
        handoff = root / "handoff.json"
        plan = root / "release-plan.json"
        index = root / "index.json"
        binding = {
            "topic_table_path": "topics.md", "topic_table_relative_path": "topics.md",
            "topic_table_line": 5, "row_fingerprint": "a" * 64,
            "topic": "人工冻结选题", "benchmark_case_id": "TJX-001",
        }
        candidate.write_text(json.dumps({
            "schema": "copy-structure-v19", "topic": "人工冻结选题", "benchmark_case_id": "TJX-001",
            "topic_table_binding": binding,
            "structures": {"structure_four": {"core_frameworks": [
                {"framework_block_id": "F02", "framework_label": "第一点：案例"},
                {"framework_block_id": "F03", "framework_label": "第二点：误区"},
            ]}},
        }, ensure_ascii=False), encoding="utf-8")
        handoff.write_text(json.dumps({"schema": "copy-structure-handoff-v19"}), encoding="utf-8")
        candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
        handoff_sha = hashlib.sha256(handoff.read_bytes()).hexdigest()
        old_output = root / "旧正式结构.md"
        plan.write_text(json.dumps({
            "schema": "copy-structure-release-plan-v1", "topic_table_binding": binding,
            "topic": "人工冻结选题", "benchmark_case_id": "TJX-001",
            "candidate_path": str(candidate.resolve()), "candidate_sha256": candidate_sha,
            "handoff_path": str(handoff.resolve()), "handoff_sha256": handoff_sha,
            "planned_output_path": str(old_output.resolve()),
        }, ensure_ascii=False), encoding="utf-8")
        receipt.write_text(json.dumps({
            "schema": "audit-receipt-v3", "artifactType": "copy-structure-v19", "status": "approved",
            "subject": {"candidateSha256": candidate_sha, "handoffSha256": handoff_sha,
                        "releasePlanSha256": hashlib.sha256(plan.read_bytes()).hexdigest()},
        }, ensure_ascii=False), encoding="utf-8")
        entry = {**binding, "output_path": str(old_output.resolve()), "output_sha256": "obsolete",
                 "candidate_path": str(candidate.resolve()), "candidate_sha256": candidate_sha,
                 "audit_receipt_path": str(receipt.resolve()), "release_plan_path": str(plan.resolve()),
                 "release_plan_sha256": hashlib.sha256(plan.read_bytes()).hexdigest()}
        releases.write_release_index_entry(entry, index)
        return index, candidate

    @staticmethod
    def write_owner_structure(path: Path, content_a: str = "人工案例", content_b: str = "人工误区") -> None:
        path.write_text("\n".join([
            "# 文案结构｜人工冻结选题", "", "对标复刻拆解：TJX-001", "", "## 结构四", "",
            "| 编号 | 核心大框架 | 核心内容 |", "| --- | --- | --- |",
            f"| F02 | 第一点：案例 | {content_a} |", f"| F03 | 第二点：误区 | {content_b} |", "",
        ]), encoding="utf-8")

    def test_owner_frozen_structure_four_survives_old_output_relocation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index, _candidate = self.make_owner_freeze_bundle(root)
            owner = root / "√人工冻结选题_TJX-001.md"
            self.write_owner_structure(owner)
            releases.record_owner_frozen_structure(structure_markdown=owner, path=index)
            binding = releases.verified_release_bindings(index)[("人工冻结选题", "TJX-001")]
            self.assertEqual(binding["structure_input_authority"], "owner-frozen")
            self.assertEqual(Path(binding["output_path"]), owner.resolve())
            self.assertEqual(binding["output_sha256"], hashlib.sha256(owner.read_bytes()).hexdigest())

    def test_owner_structure_freeze_requires_complete_matching_structure_four(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index, _candidate = self.make_owner_freeze_bundle(root)
            owner = root / "√人工冻结选题_TJX-001.md"
            self.write_owner_structure(owner, content_b="")
            with self.assertRaisesRegex(ValueError, "非空核心内容"):
                releases.record_owner_frozen_structure(structure_markdown=owner, path=index)
            self.write_owner_structure(owner)
            releases.record_owner_frozen_structure(structure_markdown=owner, path=index)
            self.write_owner_structure(owner, content_a="下一版人工案例")
            self.assertNotIn(("人工冻结选题", "TJX-001"), releases.verified_release_bindings(index))
            releases.record_owner_frozen_structure(structure_markdown=owner, path=index)
            refreshed = releases.verified_release_bindings(index)[("人工冻结选题", "TJX-001")]
            self.assertEqual(refreshed["owner_structure_four"]["structure_markdown_sha256"], hashlib.sha256(owner.read_bytes()).hexdigest())

    def write_table(self, root: Path, filename: str, rows: list[list[str]]) -> None:
        lines = [
            "# test",
            "",
            "| " + " | ".join(releases.TOPIC_HEADER) + " |",
            "| " + " | ".join(["---"] * len(releases.TOPIC_HEADER)) + " |",
        ]
        lines += ["| " + " | ".join(row) + " |" for row in rows]
        (root / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def make_tables(self, root: Path, rows: list[list[str]]) -> None:
        for index, filename in enumerate(releases.TOPIC_FILES):
            self.write_table(root, filename, rows if index == 0 else [])

    def test_fingerprint_ignores_derived_status(self) -> None:
        base = dict(zip(releases.TOPIC_HEADER, ["关键词", "选题", "元素", "博主", "1", "", "是", "GHX-002", ""]))
        base["topic_table_relative_path"] = "a.md"
        changed = dict(base, **{"状态": "已生成结构"})
        self.assertEqual(releases.row_fingerprint(base), releases.row_fingerprint(changed))

    def test_selected_topic_requires_one_selected_audited_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tables(root, [["关键词", "唯一选题", "元素", "博主", "1", "", "是", "GHX-002", ""]])
            with patch("workflow.benchmark_cases.approved_case", return_value={"id": "GHX-002"}):
                row = releases.resolve_selected_topic("唯一选题", root)
            self.assertEqual(row["对标复刻拆解编号"], "GHX-002")
            self.write_table(root, releases.TOPIC_FILES[1], [["关键词", "唯一选题", "元素", "博主", "1", "", "是", "GHX-002", ""]])
            with self.assertRaisesRegex(ValueError, "多个候选"):
                releases.resolve_selected_topic("唯一选题", root)

    def test_selected_topic_accepts_every_registered_case_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tables(root, [["关键词", "推荐型唯一选题", "元素", "博主", "1", "", "是", "TJX-001", ""]])
            with patch("workflow.benchmark_cases.approved_case", return_value={"id": "TJX-001"}) as approved:
                row = releases.resolve_selected_topic("推荐型唯一选题", root)
            self.assertEqual(row["对标复刻拆解编号"], "TJX-001")
            approved.assert_called_once_with("TJX-001")

    def test_selected_topic_can_lock_one_of_multiple_case_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_tables(root, [["关键词", "多结构选题", "元素", "博主", "1", "", "是", "GHX-002<br>TJX-001", ""]])
            with patch("workflow.benchmark_cases.approved_case", return_value={"id": "TJX-001"}) as approved:
                row = releases.resolve_selected_topic("多结构选题", root, "TJX-001")
            self.assertEqual(row["selected_benchmark_case_id"], "TJX-001")
            self.assertEqual(row["benchmark_case_ids"], ["GHX-002", "TJX-001"])
            self.assertEqual(releases.handoff_binding(row)["benchmark_case_id"], "TJX-001")
            approved.assert_called_once_with("TJX-001")
            with self.assertRaisesRegex(ValueError, "显式指定"):
                releases.resolve_selected_topic("多结构选题", root)

    def test_index_requires_hashes_receipt_and_candidate_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "candidate.json"
            output = root / "正式结构.md"
            receipt = root / "receipt.json"
            index = root / "index.json"
            binding = {"topic_table_path": "a", "topic_table_relative_path": "a.md", "topic_table_line": 5, "row_fingerprint": "a" * 64, "topic": "唯一选题", "benchmark_case_id": "GHX-002"}
            candidate.write_text(json.dumps({"schema": "copy-structure-v19", "topic": "唯一选题", "benchmark_case_id": "GHX-002", "topic_table_binding": binding}), encoding="utf-8")
            output.write_text("正式内容", encoding="utf-8")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            handoff = root / "handoff.json"; handoff.write_text(json.dumps({"schema": "copy-structure-handoff-v19"}), encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(json.dumps({"schema": "copy-structure-release-plan-v1", "topic_table_binding": binding, "topic": "唯一选题", "benchmark_case_id": "GHX-002", "candidate_path": str(candidate.resolve()), "candidate_sha256": digest, "handoff_path": str(handoff.resolve()), "handoff_sha256": hashlib.sha256(handoff.read_bytes()).hexdigest(), "planned_output_path": str(output.resolve())}), encoding="utf-8")
            receipt.write_text(json.dumps({"schema": "audit-receipt-v3", "artifactType": "copy-structure-v19", "status": "approved", "subject": {"candidateSha256": digest, "handoffSha256": hashlib.sha256(handoff.read_bytes()).hexdigest(), "releasePlanSha256": hashlib.sha256(plan.read_bytes()).hexdigest()}}), encoding="utf-8")
            entry = releases.build_release_entry(binding=binding, output_path=output, candidate_path=candidate, audit_receipt_path=receipt, release_plan_path=plan)
            releases.write_release_index_entry(entry, index)
            self.assertIn(("唯一选题", "GHX-002"), releases.verified_release_bindings(index))
            output.write_text("被篡改", encoding="utf-8")
            self.assertNotIn(("唯一选题", "GHX-002"), releases.verified_release_bindings(index))

    def test_index_rejects_plan_or_receipt_without_full_handoff_binding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate.json"; output = root / "out.md"; receipt = root / "receipt.json"; plan = root / "plan.json"; handoff = root / "handoff.json"; index = root / "index.json"
            binding = {"topic_table_path": "a", "topic_table_relative_path": "a.md", "topic_table_line": 5, "row_fingerprint": "a" * 64, "topic": "唯一选题", "benchmark_case_id": "GHX-002"}
            candidate.write_text(json.dumps({"schema":"copy-structure-v19","topic":"唯一选题","benchmark_case_id":"GHX-002","topic_table_binding":binding}), encoding="utf-8"); output.write_text("out",encoding="utf-8"); handoff.write_text("{}",encoding="utf-8")
            candidate_sha=hashlib.sha256(candidate.read_bytes()).hexdigest(); handoff_sha=hashlib.sha256(handoff.read_bytes()).hexdigest()
            plan.write_text(json.dumps({"schema":"copy-structure-release-plan-v1","topic_table_binding":binding,"topic":"唯一选题","benchmark_case_id":"GHX-002","candidate_path":str(candidate.resolve()),"candidate_sha256":candidate_sha,"handoff_path":str(handoff.resolve()),"handoff_sha256":handoff_sha,"planned_output_path":str(output.resolve())}),encoding="utf-8")
            plan_sha=hashlib.sha256(plan.read_bytes()).hexdigest(); receipt.write_text(json.dumps({"schema":"audit-receipt-v3","artifactType":"copy-structure-v19","status":"approved","subject":{"candidateSha256":candidate_sha,"handoffSha256":handoff_sha,"releasePlanSha256":"bad"}}),encoding="utf-8")
            entry={"topic_table_path":"a","topic_table_relative_path":"a.md","topic_table_line":5,"row_fingerprint":"a"*64,"topic":"唯一选题","benchmark_case_id":"GHX-002","output_path":str(output.resolve()),"output_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"candidate_path":str(candidate.resolve()),"candidate_sha256":candidate_sha,"audit_receipt_path":str(receipt.resolve()),"release_plan_path":str(plan.resolve()),"release_plan_sha256":plan_sha}
            releases.write_release_index_entry(entry,index)
            self.assertNotIn(("唯一选题","GHX-002"),releases.verified_release_bindings(index))

    def test_v19_candidate_uses_v19_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate.json"; receipt = root / "receipt.json"
            candidate.write_text(json.dumps({"schema": "copy-structure-v19"}), encoding="utf-8")
            candidate_sha = hashlib.sha256(candidate.read_bytes()).hexdigest()
            receipt.write_text(json.dumps({"schema": "audit-receipt-v3", "artifactType": "copy-structure-v19", "status": "approved", "subject": {"candidateSha256": candidate_sha}}), encoding="utf-8")
            self.assertTrue(releases._receipt_approves_candidate(receipt, candidate))

    def test_migration_drops_only_retired_last_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "表.md"
            legacy = releases.TOPIC_HEADER + ["文案结构"]
            path.write_text("\n".join([
                "# test", "", "| " + " | ".join(legacy) + " |",
                "| " + " | ".join(["---"] * len(legacy)) + " |",
                "| 关键词 | 选题 | 元素 | 博主 | 1 | 链接 | 是 | GHX-002 | 已生成结构 | [[历史文件]] |", "",
            ]), encoding="utf-8")
            self.assertTrue(migration.migrate(path))
            rendered = path.read_text(encoding="utf-8")
            self.assertIn("| " + " | ".join(releases.TOPIC_HEADER) + " |", rendered)
            self.assertNotIn("文案结构", rendered)
            self.assertIn("| 关键词 | 选题 | 元素 | 博主 | 1 | 链接 | 是 | GHX-002 | 已生成结构 |", rendered)

    def test_refresh_only_updates_status_and_never_merges_or_deletes_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "表.md"
            rows = [
                "| A | 重复选题 | 元素 | 博主 | 1 | 链接一 | 否 |  |  |",
                "| B | 重复选题 | 元素 | 博主 | 2 | 链接二 | 是 | GHX-002 | 旧状态 |",
            ]
            path.write_text("\n".join(["# 表", "", "| " + " | ".join(releases.TOPIC_HEADER) + " |", "| " + " | ".join(["---"] * 9) + " |", *rows, ""]) + "\n", encoding="utf-8")
            with patch.object(refresh, "verified_release_bindings", return_value={}):
                self.assertTrue(refresh.rebuild_file(path))
            rendered = path.read_text(encoding="utf-8")
            self.assertIn("| A | 重复选题 | 元素 | 博主 | 1 | 链接一 | 否 |  |  |", rendered)
            self.assertIn("| B | 重复选题 | 元素 | 博主 | 2 | 链接二 | 是 | GHX-002 | 待生成结构 |", rendered)

    def test_multi_case_status_counts_only_verified_bound_releases(self) -> None:
        fingerprint = "f" * 64
        entries = {
            ("多结构选题", "GHX-002"): {"row_fingerprint": fingerprint},
            ("多结构选题", "TJX-001"): {"row_fingerprint": fingerprint},
        }
        with patch.object(refresh, "verified_release_bindings", return_value=entries):
            self.assertEqual(refresh.derive_status("多结构选题", True, "GHX-002<br>TJX-001", fingerprint), "已生成二")
        with patch.object(refresh, "verified_release_bindings", return_value={("多结构选题", "TJX-001"): {"row_fingerprint": fingerprint}}):
            self.assertEqual(refresh.derive_status("多结构选题", True, "GHX-002<br>TJX-001", fingerprint), "已生成一")


if __name__ == "__main__":
    unittest.main()
