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


if __name__ == "__main__":
    unittest.main()
