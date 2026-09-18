from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "03_工作台" / "server.py"
APP = ROOT / "03_工作台" / "frontend" / "app.js"
STYLES = ROOT / "03_工作台" / "frontend" / "today-v9.css"


def load_server():
    spec = importlib.util.spec_from_file_location("structure_editor_direct_save_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def structure_markdown(value: str = "人工填写内容") -> str:
    return "\n".join([
        "# 测试结构",
        "",
        "## 结构四",
        "",
        "| 编号 | 大框架 | 核心内容 |",
        "| --- | --- | --- |",
        f"| F01 | 开场 | {value} |",
        "",
    ])


class StructureEditorDirectSaveAndDeleteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.structures = self.assets / "structures"
        self.copies = self.assets / "copies"
        self.structures.mkdir(parents=True)
        self.copies.mkdir(parents=True)
        self.server = load_server()
        self.server.ASSET_ROOT = self.assets
        self.server.STRUCTURE_ROOT = self.structures
        self.server.COPY_ROOT = self.copies
        self.server.TODAY_CANDIDATE_ROOT = self.root / "candidates"
        self.server.TODAY_EDITOR_SURFACES = {
            **self.server.TODAY_EDITOR_SURFACES,
            "structure": {**self.server.TODAY_EDITOR_SURFACES["structure"], "root": self.structures},
            "copy": {**self.server.TODAY_EDITOR_SURFACES["copy"], "root": self.copies},
        }
        self.server.append_data_event = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        self.temp.cleanup()

    def catalog_item(self, path: Path, surface: str = "structure") -> dict:
        return next(item for item in self.server.today_editor_catalog(surface)["files"] if item["relativePath"] == path.name)

    def copy_binding(self, output: Path, *, topic: str = "测试选题", case: str = "SCHX-001") -> dict:
        structure_candidate = self.root / "structure-candidate.md"
        return {
            "topic": topic,
            "benchmark_case_id": case,
            "candidate_path": str(structure_candidate),
            "candidate_sha256": "same-structure-sha",
            "final_copy": {
                "output_path": str(output),
                "candidate_path": str(self.root / f"{output.stem}-final-candidate.md"),
                "audit_receipt_path": str(self.root / f"{output.stem}-audit.json"),
            },
        }

    def test_structure_four_direct_save_updates_formal_file_and_clears_candidate(self) -> None:
        path = self.structures / "结构四.md"
        path.write_text(structure_markdown("修改前"), encoding="utf-8")
        self.server.verified_release_bindings = lambda: {}
        frozen_calls: list[Path] = []
        self.server.record_owner_frozen_structure = lambda **kwargs: frozen_calls.append(kwargs["structure_markdown"])
        item = self.catalog_item(path)
        candidate = self.server._candidate_path("structure", path)
        candidate.parent.mkdir(parents=True)
        candidate.write_text("{}", encoding="utf-8")

        result = self.server.save_today_editor_file(
            "structure", item["id"], item["sha256"], {"content": structure_markdown("人工修改后")}
        )

        self.assertTrue(result["formalUpdated"])
        self.assertEqual(path.read_text(encoding="utf-8"), structure_markdown("人工修改后"))
        self.assertFalse(candidate.exists())
        self.assertEqual(frozen_calls, [])
        self.assertTrue(result["structureFourFilled"])
        self.assertFalse(result["structureFourFrozen"])
        self.assertFalse(result["workbenchEligible"])
        self.assertEqual(result["structureFourStatus"], "已填写，待冻结")
        self.assertIn("添加 √", result["structureFourReason"])

    def test_deleting_current_binding_selects_remaining_verifiable_version(self) -> None:
        fallback = self.structures / "历史结构.md"
        current = self.structures / "当前结构.md"
        fallback.write_text(structure_markdown(), encoding="utf-8")
        current.write_text(structure_markdown(), encoding="utf-8")
        key = ("测试选题", "SCHX-001")

        def bindings():
            output = current if current.exists() else fallback
            return {key: {"output_path": str(output)}}

        self.server.verified_release_bindings = bindings
        item = self.catalog_item(current)
        candidate = self.server._candidate_path("structure", current)
        candidate.parent.mkdir(parents=True)
        candidate.write_text("{}", encoding="utf-8")
        result = self.server.delete_today_structure_file("structure", item["id"], item["sha256"])

        self.assertFalse(current.exists())
        self.assertFalse(candidate.exists())
        self.assertTrue(fallback.exists())
        self.assertTrue(result["currentBindingDeleted"])
        self.assertEqual(result["fallbackId"], self.server._today_editor_file_id("structure", fallback))
        self.assertEqual(result["currentStructureState"], "fallback")

    def test_deleting_current_without_fallback_marks_structure_pending_generation(self) -> None:
        current = self.structures / "当前结构.md"
        current.write_text(structure_markdown(), encoding="utf-8")
        key = ("测试选题", "SCHX-001")
        self.server.verified_release_bindings = lambda: {key: {"output_path": str(current)}} if current.exists() else {}
        item = self.catalog_item(current)

        result = self.server.delete_today_structure_file("structure", item["id"], item["sha256"])

        self.assertFalse(current.exists())
        self.assertTrue(result["currentBindingDeleted"])
        self.assertEqual(result["fallbackId"], "")
        self.assertEqual(result["currentStructureState"], "pending-generation")

    def test_delete_rejects_stale_hash_and_non_structure_surface(self) -> None:
        path = self.structures / "结构.md"
        path.write_text(structure_markdown(), encoding="utf-8")
        self.server.verified_release_bindings = lambda: {}
        item = self.catalog_item(path)
        path.write_text(structure_markdown("外部更新"), encoding="utf-8")

        with self.assertRaises(self.server.EditorConflictError):
            self.server.delete_today_structure_file("structure", item["id"], item["sha256"])
        with self.assertRaises(ValueError):
            self.server.delete_today_structure_file("copy", item["id"], item["sha256"])
        self.assertTrue(path.exists())

    def test_deleting_current_copy_restores_same_structure_history_and_cleans_candidate(self) -> None:
        fallback = self.copies / "历史正文.md"
        current = self.copies / "当前正文.md"
        fallback.write_text("# 历史正文\n", encoding="utf-8")
        current.write_text("# 当前正文\n", encoding="utf-8")
        key = ("测试选题", "SCHX-001")
        current_binding = self.copy_binding(current)
        fallback_binding = self.copy_binding(fallback)
        self.server.verified_release_bindings = lambda: {key: current_binding}
        self.server.verified_final_copy = lambda entry: Path(str(entry["final_copy"]["output_path"])).is_file()
        self.server.load_release_index = lambda: {"entries": [fallback_binding, current_binding]}
        appended: list[dict] = []
        self.server.append_final_copy_binding = lambda **kwargs: appended.append(kwargs)
        candidate = self.server._candidate_path("copy", current)
        candidate.parent.mkdir(parents=True)
        candidate.write_text("{}", encoding="utf-8")
        item = self.catalog_item(current, "copy")

        result = self.server.delete_today_editor_file("copy", item["id"], item["sha256"])

        self.assertFalse(current.exists())
        self.assertFalse(candidate.exists())
        self.assertTrue(fallback.exists())
        self.assertTrue(result["currentBindingDeleted"])
        self.assertEqual(result["fallbackId"], self.server._today_editor_file_id("copy", fallback))
        self.assertEqual(result["currentCopyState"], "fallback")
        self.assertEqual(appended[0]["output_path"].resolve(), fallback.resolve())

    def test_deleting_current_copy_without_history_marks_copy_pending_generation(self) -> None:
        current = self.copies / "当前正文.md"
        current.write_text("# 当前正文\n", encoding="utf-8")
        key = ("测试选题", "SCHX-001")
        current_binding = self.copy_binding(current)
        self.server.verified_release_bindings = lambda: {key: current_binding}
        self.server.verified_final_copy = lambda entry: Path(str(entry["final_copy"]["output_path"])).is_file()
        self.server.load_release_index = lambda: {"entries": [current_binding]}
        self.server.append_final_copy_binding = lambda **kwargs: self.fail("不应追加不存在的历史正文")
        item = self.catalog_item(current, "copy")

        result = self.server.delete_today_editor_file("copy", item["id"], item["sha256"])

        self.assertFalse(current.exists())
        self.assertTrue(result["currentBindingDeleted"])
        self.assertEqual(result["fallbackId"], "")
        self.assertEqual(result["currentCopyState"], "pending-generation")

    def test_deleting_noncurrent_copy_keeps_current_binding_and_rejects_wrong_copy_id(self) -> None:
        current = self.copies / "当前正文.md"
        historic = self.copies / "历史正文.md"
        structure = self.structures / "结构.md"
        current.write_text("# 当前正文\n", encoding="utf-8")
        historic.write_text("# 历史正文\n", encoding="utf-8")
        structure.write_text(structure_markdown(), encoding="utf-8")
        key = ("测试选题", "SCHX-001")
        current_binding = self.copy_binding(current)
        self.server.verified_release_bindings = lambda: {key: current_binding}
        self.server.verified_final_copy = lambda entry: Path(str(entry["final_copy"]["output_path"])).is_file()
        self.server.load_release_index = lambda: {"entries": [current_binding]}
        self.server.append_final_copy_binding = lambda **kwargs: self.fail("删除非当前正文不应修改当前绑定")
        historic_item = self.catalog_item(historic, "copy")

        result = self.server.delete_today_editor_file("copy", historic_item["id"], historic_item["sha256"])

        self.assertFalse(historic.exists())
        self.assertTrue(current.exists())
        self.assertFalse(result["currentBindingDeleted"])
        self.assertEqual(result["currentCopyState"], "unchanged")
        with self.assertRaises(ValueError):
            self.server.delete_today_editor_file("topics", historic_item["id"], historic_item["sha256"])
        with self.assertRaises(FileNotFoundError):
            self.server.delete_today_editor_file("copy", self.catalog_item(structure)["id"], "not-used")

    def test_copy_delete_rejects_stale_hash(self) -> None:
        path = self.copies / "正文.md"
        path.write_text("# 正文\n", encoding="utf-8")
        item = self.catalog_item(path, "copy")
        path.write_text("# 外部更新\n", encoding="utf-8")

        with self.assertRaises(self.server.EditorConflictError):
            self.server.delete_today_editor_file("copy", item["id"], item["sha256"])
        self.assertTrue(path.exists())

    def test_frontend_exposes_direct_save_message_and_delete_control(self) -> None:
        app = APP.read_text(encoding="utf-8")
        styles = STYLES.read_text(encoding="utf-8")
        self.assertIn("确认直接保存正式结构吗？不会送小审，也不会自动冻结正文。", app)
        self.assertIn("已保存，待冻结；请在文件名添加 √ 后进入正文生成。", app)
        self.assertIn("data-editor-file-delete", app)
        self.assertIn("(isStructure||isCopy)", app)
        self.assertIn("expectedSha256:item.sha256", app)
        self.assertIn("JSON.stringify({surface:editor.surface,id:fileId,expectedSha256:item.sha256})", app)
        self.assertIn("currentCopyState", app)
        self.assertIn("正文成稿文件及其临时编辑候选，不会删除审核回执或发布历史", app)
        self.assertIn("已回退到最近可核验历史正文", app)
        self.assertIn(".today-editor-file-delete", styles)


if __name__ == "__main__":
    unittest.main()
