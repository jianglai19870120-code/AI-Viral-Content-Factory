from __future__ import annotations

import unittest

from workflow.benchmark_structure_v3 import (
    normalize_portable_case_markdown,
    parse_markdown_text,
    repair_table_divider,
    validate_portable_case_markdown,
    validate_table_layout,
)


HEADER = "| 编号 | 大框架 | 小框架 | 小框架原文内容 |"
DIVIDER = "| --- | --- | --- | --- |"


class BenchmarkStructureV3LayoutTests(unittest.TestCase):
    def test_missing_divider_is_inserted_without_losing_the_first_real_row(self) -> None:
        source = "\n".join([HEADER, "| F01 | 观点 | 判断 | 内容 |", ""])
        repaired = repair_table_divider(source)
        self.assertEqual(repaired.splitlines()[:3], [HEADER, DIVIDER, "| F01 | 观点 | 判断 | 内容 |"]) 
        validate_table_layout(repaired)

    def test_legacy_serialized_last_row_is_replaced_not_duplicated(self) -> None:
        source = "\n".join([
            HEADER,
            "| F02 | 行动 | 收尾 | 最后一段 |",
            "| F01 | 观点 | 判断 | 第一段 |",
            "| F02 | 行动 | 收尾 | 最后一段 |",
            "",
        ])
        repaired = repair_table_divider(source)
        self.assertEqual(repaired.splitlines()[:4], [
            HEADER, DIVIDER, "| F01 | 观点 | 判断 | 第一段 |", "| F02 | 行动 | 收尾 | 最后一段 |",
        ])
        validate_table_layout(repaired)

    def test_layout_rejects_a_table_without_a_divider(self) -> None:
        with self.assertRaisesRegex(ValueError, "分隔行"):
            validate_table_layout(HEADER + "\n| F01 | 观点 | 判断 | 内容 |\n")

    def test_standalone_html_spacers_become_portable_blank_lines(self) -> None:
        source = "\n".join([
            "# 标题",
            "<br>",
            "## 结构总表",
            "<BR />",
            HEADER,
            DIVIDER,
            "| F01 | 观点 | 判断 | 第一段<br>第二行 |",
            "<br>",
            "---",
            "",
        ])
        normalized = normalize_portable_case_markdown(source)
        self.assertNotRegex(normalized, r"(?im)^\s*<br\s*/?>\s*$")
        self.assertIn("第一段<br>第二行", normalized)
        validate_table_layout(normalized)

    def test_portable_gate_rejects_unconverted_standalone_html_spacer(self) -> None:
        source = "\n".join(["# 标题", "<br>", HEADER, DIVIDER, "| F01 | 观点 | 核心判断 | 内容 |", ""])
        with self.assertRaisesRegex(ValueError, "独立 <br>"):
            validate_portable_case_markdown(source)

    def test_small_framework_names_must_be_functional_and_unique_per_fnn(self) -> None:
        accepted = "\n".join([HEADER, DIVIDER, "| F01 | 痛点 | 痛点观点 | 先提出问题。 |", "| F01 | 痛点 | 痛点场景描述 | 再描述场景。 |", ""])
        self.assertEqual(len(parse_markdown_text(accepted)), 2)
        duplicate = accepted.replace("痛点场景描述", "痛点观点")
        with self.assertRaisesRegex(ValueError, "不得重复"):
            parse_markdown_text(duplicate)
        copied = accepted.replace("痛点场景描述", "再描述场景。")
        with self.assertRaisesRegex(ValueError, "直接照搬"):
            parse_markdown_text(copied)
        version = accepted.replace("痛点场景描述", "2.0 方法论")
        with self.assertRaisesRegex(ValueError, "方法版本"):
            parse_markdown_text(version)


if __name__ == "__main__":
    unittest.main()
