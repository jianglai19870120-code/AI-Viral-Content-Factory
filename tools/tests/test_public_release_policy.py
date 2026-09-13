from __future__ import annotations

import unittest
from pathlib import Path

from tools.release.public_policy import classify


class PublicReleasePolicyTests(unittest.TestCase):
    def test_non_member_content_asset_is_public(self) -> None:
        self.assertEqual(classify(Path("02_资产中心/03_输出库/02_正文成稿/01_干货型/示例.md"))[0], "public")

    def test_type_membership_does_not_hide_non_member_directory(self) -> None:
        book = Path("02_资产中心/01_输入库/01_推荐好书-源文件/01_科学创业/示例.md")
        self.assertEqual(classify(book)[0], "public")

    def test_font_is_public_and_node_modules_is_private(self) -> None:
        self.assertEqual(classify(Path("03_工作台/01_品牌设计系统/字体/OPPOSans/OPPOSans-Regular.ttf"))[0], "public")
        self.assertEqual(classify(Path("03_工作台/vendor/codex-cli/node_modules/@openai/codex/bin/codex.js"))[0], "private")

    def test_asset_contract_readme_remains_public(self) -> None:
        self.assertEqual(classify(Path("02_资产中心/README.md"))[0], "public")

    def test_member_content_is_private_but_placeholder_is_public(self) -> None:
        member = Path("02_资产中心/01_输入库/资料（会员专享）/私有资料.md")
        placeholder = Path("02_资产中心/01_输入库/资料（会员专享）/.gitkeep")
        self.assertEqual(classify(member)[0], "private")
        self.assertEqual(classify(placeholder)[0], "public")

    def test_runtime_is_never_public(self) -> None:
        self.assertEqual(classify(Path("03_工作台/runtime/workbench.db"))[0], "private")
        self.assertEqual(classify(Path(".runtime/state/task.json"))[0], "private")

    def test_data_center_events_and_temporary_scripts_are_private(self) -> None:
        event = Path("04_数据中心/02_事件流水/by-date/2026-08-31.jsonl")
        temporary = Path("tools/tmp_rehash_formal_baseline_v3.py")
        self.assertEqual(classify(event)[0], "private")
        self.assertEqual(classify(temporary)[0], "private")

    def test_member_file_name_does_not_hide_non_member_directory(self) -> None:
        named_file = Path("02_资产中心/01_输入库/公开资料/示例（会员专享）.md")
        self.assertEqual(classify(named_file)[0], "public")
