from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "03_工作台" / "frontend" / "app.js"


class CaseStructureRenderContractTests(unittest.TestCase):
    def test_cases_use_a_dedicated_four_column_rowspan_renderer(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("function isCaseStructureTable(block)", source)
        self.assertIn("编号|大框架|小框架|小框架原文内容", source)
        self.assertIn("rowspan=", source)
        self.assertIn("today-case-structure-table", source)

    def test_table_round_trip_keeps_the_markdown_divider(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("divider:markdownTableCells(lines[dividerIndex])", source)
        self.assertNotIn("divider:markdownTableCells(lines[index-1])", source)

    def test_confirmation_recaptures_the_visible_case_draft_before_saving(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn("function captureTodayDocumentDraft()", source)
        self.assertIn("document.querySelectorAll('[data-structure-cell]')", source)
        self.assertIn("document.querySelectorAll('[data-structure-filename]')", source)
        finish = source.index("async function finishTodayEditorEdit")
        self.assertIn("captureTodayDocumentDraft();", source[finish:finish + 360])

    def test_case_save_normalizes_then_validates_portable_markdown(self) -> None:
        server = (ROOT / "03_工作台" / "server.py").read_text(encoding="utf-8")
        save = server.index("def save_today_editor_file")
        fragment = server[save:save + 2200]
        self.assertIn("normalize_portable_case_markdown(repair_table_divider(content))", fragment)
        self.assertIn("validate_owner_approved_case_edit", fragment)


if __name__ == "__main__":
    unittest.main()
