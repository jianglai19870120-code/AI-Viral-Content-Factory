from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.input_inventory import build_inventory

SERVER = ROOT / "03_工作台" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("workbench_folder_sync_video_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FolderSyncVideoContractTest(unittest.TestCase):
    def test_manual_video_workbook_is_a_pending_refresh_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = root / "02_资产中心" / "01_输入库" / "04_视频文案-源文件（会员专享）" / "新复制的视频原始表.xlsx"
            raw.parent.mkdir(parents=True)
            raw.write_bytes(b"copied-video-workbook")
            rows = [row for row in build_inventory(root) if row["source_type"] == "video-sources"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "未拆解")
        self.assertEqual(rows[0]["source_origin"], "manual-file")
        self.assertIn("用户已确认", rows[0]["status_reason"])

    def test_video_refresh_uses_technical_standardization_without_an_extra_confirmation_step(self):
        server = load_server()
        module = server._today_module_index()["video-sources"]
        prompt = server._today_module_prompt(module, ["video-sources-x｜用户确认输入：02_资产中心/输入.xlsx"], video_source_import=[{
            "source_id": "video-sources-x", "source_path": "02_资产中心/输入.xlsx",
        }])
        self.assertIn("$standardize-and-inventory-sources", prompt)
        self.assertIn("$breakdown-video-pain-cards", prompt)
        self.assertNotIn("待入库", prompt)


if __name__ == "__main__":
    unittest.main()
