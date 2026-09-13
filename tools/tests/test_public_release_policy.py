from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.release.public_policy import classify, registered_member_roots


class PublicReleasePolicyTests(unittest.TestCase):
    def test_content_asset_is_never_public(self) -> None:
        self.assertEqual(classify(Path("02_资产中心/03_输出库/02_正文成稿/01_干货型/示例.md"))[0], "private")

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

    def test_registered_member_roots_accept_relative_directories_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "03_工作台" / "config"
            config.mkdir(parents=True)
            (config / "content-types.json").write_text(
                '{"types":[{"memberOnly":true,"roots":{"input":"01_输入库/自定义","process":"02_处理库/自定义","output":"03_输出库/自定义"}}]}',
                encoding="utf-8",
            )
            roots, error = registered_member_roots(root)
            self.assertIsNone(error)
            self.assertIn(Path("02_资产中心/03_输出库/自定义"), roots)

    def test_registered_member_roots_reject_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "03_工作台" / "config"
            config.mkdir(parents=True)
            (config / "content-types.json").write_text(
                '{"types":[{"memberOnly":true,"roots":{"input":"01_输入库/x","process":"02_处理库/x","output":"../private"}}]}',
                encoding="utf-8",
            )
            roots, error = registered_member_roots(root)
            self.assertEqual(roots, set())
            self.assertIn("相对路径", error or "")
