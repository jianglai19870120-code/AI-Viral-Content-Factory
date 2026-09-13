from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "query" / "search_video_modules.py"
MODULE = None
if SCRIPT.is_file():
    SPEC = importlib.util.spec_from_file_location("search_video_modules", SCRIPT)
    assert SPEC and SPEC.loader
    MODULE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MODULE)


@unittest.skipIf(MODULE is None, "公开包未分发仅本机查询脚本")
class SearchVideoModulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.card = root / "card.md"
        self.card.write_text("# card\n", encoding="utf-8")
        self.record = {
            "schema": "video-module-index-v1", "card_id": "PAIN-A03-X", "pain_id": "PAIN-A03-X",
            "module_type": "pain", "module_path": str(self.card),
            "classification_path": "内容与流量/流量/起号", "target_people": ["短视频创作者"],
            "scene_tags": ["播放量", "没流量"], "source_ids": ["VS-1"],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def args(self, **changes):
        values = {"query": "", "module_type": None, "classification": "", "audience": "", "scene": "", "limit": 20}
        values.update(changes)
        return type("Args", (), values)()

    def test_query_and_filters_locate_existing_card(self) -> None:
        results = MODULE.search([self.record], self.args(query="没流量", module_type="pain", audience="短视频", scene="播放"))
        self.assertEqual([item["card_id"] for item in results], ["PAIN-A03-X"])

    def test_missing_card_is_not_returned(self) -> None:
        self.card.unlink()
        self.assertEqual(MODULE.search([self.record], self.args(query="流量")), [])

    def test_natural_language_flow_query_prefers_traffic_category(self) -> None:
        broad = dict(self.record, card_id="PAIN-A01-X", pain_id="PAIN-A01-X", classification_path="内容与流量/定位/人群/方向")
        direct = dict(self.record, card_id="PAIN-A03-X", pain_id="PAIN-A03-X", classification_path="内容与流量/流量/起号")
        self.assertEqual("PAIN-A03-X", MODULE.search([broad, direct], self.args(query="没流量"))[0]["card_id"])


if __name__ == "__main__":
    unittest.main()
