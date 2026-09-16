from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "03_工作台" / "server.py"
APP = ROOT / "03_工作台" / "frontend" / "app.js"
STYLES = ROOT / "03_工作台" / "frontend" / "today-v9.css"


def load_server():
    spec = importlib.util.spec_from_file_location("case_editor_type_filter_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaseEditorTypeFilterTests(unittest.TestCase):
    def test_case_catalog_exposes_registered_types_including_sun_results(self) -> None:
        server = load_server()
        catalog = server.today_editor_catalog("cases")
        self.assertEqual(catalog["surface"], "cases")
        self.assertTrue({"干货型", "获客型", "推荐型", "晒成果型"}.issubset(set(catalog["caseTypes"])))
        self.assertTrue(all("caseType" in item and item["caseType"] for item in catalog["files"]))

    def test_unregistered_legacy_filename_has_a_type_fallback(self) -> None:
        server = load_server()
        self.assertEqual(server._case_editor_type_from_title(Path("√新类型_历史案例【观点】X-001.md")), "新类型")
        self.assertEqual(server._case_editor_type_from_title(Path("无前缀历史案例.md")), "未归类")

    def test_frontend_uses_combined_status_and_dynamic_type_filters(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("caseTypes:[],caseType:'all'", source)
        self.assertIn("data-editor-case-type", source)
        self.assertIn("全部类型", source)
        self.assertIn("const matchesStatus=editor.filter==='filled'?!item.pending:Boolean(item.pending);", source)
        self.assertNotIn("['干货型','获客型','推荐型']", source)
        case_filters = source[source.index("const filters=isCases?"):].split("</select>`:", 1)[0]
        self.assertNotIn(">全部</button>", case_filters)
        self.assertNotIn("<span>类型</span>", case_filters)

    def test_case_filter_layout_has_a_separate_type_select(self) -> None:
        styles = STYLES.read_text(encoding="utf-8")
        self.assertIn(".today-case-editor-filters { align-items: center; flex-wrap: nowrap; }", styles)
        self.assertIn(".today-case-editor-type-filter { flex: 1 1 auto;", styles)


if __name__ == "__main__":
    unittest.main()
