from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "03_工作台" / "server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("workbench_folder_sync_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FolderSyncContractTest(unittest.TestCase):
    def test_failed_refresh_does_not_commit_the_scan_baseline(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            payload = {"rows": [{
                "source_type": "video-sources", "source_path": "02_资产中心/01_输入库/原始.xlsx",
                "source_sha256": "raw-v1", "status": "未拆解",
            }], "summary": {}}
            originals = {
                "runtime": server.RUNTIME_ROOT,
                "inventory": server._input_inventory_payload,
                "modules": server._today_module_index,
                "refresh": server.refresh_data_center,
                "dashboard": server.dashboard_page,
            }
            try:
                server.RUNTIME_ROOT = runtime
                server._input_inventory_payload = lambda: payload
                server._today_module_index = lambda: {}
                server.refresh_data_center = lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("数据中心暂不可用"))
                server.dashboard_page = lambda page: {"page": page}

                with self.assertRaisesRegex(RuntimeError, "数据中心暂不可用"):
                    server.sync_workbench_folders("today")
                self.assertFalse((runtime / "folder-sync-state.json").exists())

                server.refresh_data_center = lambda **_kwargs: {"generatedAt": "now"}
                retry = server.sync_workbench_folders("today")
                self.assertEqual(retry["sync"]["changes"]["video-sources"]["added"], 1)
            finally:
                server.RUNTIME_ROOT = originals["runtime"]
                server._input_inventory_payload = originals["inventory"]
                server._today_module_index = originals["modules"]
                server.refresh_data_center = originals["refresh"]
                server.dashboard_page = originals["dashboard"]

    def test_sync_reports_new_changed_and_removed_files_without_writing_sources(self):
        server = load_server()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime = root / "runtime"
            topics = root / "topics"
            cases = root / "cases"
            topics.mkdir()
            cases.mkdir()
            topic = topics / "账号A.md"
            case = cases / "案例A.md"
            topic.write_text("初版", encoding="utf-8")
            case.write_text("初版", encoding="utf-8")
            payload = {"rows": [{
                "source_type": "video-sources", "source_path": "02_资产中心/01_输入库/原始.xlsx",
                "source_sha256": "raw-v1", "status": "未拆解",
            }], "summary": {}}
            originals = {
                "runtime": server.RUNTIME_ROOT,
                "inventory": server._input_inventory_payload,
                "modules": server._today_module_index,
                "module_root": server._module_root,
                "refresh": server.refresh_data_center,
                "dashboard": server.dashboard_page,
            }
            try:
                server.RUNTIME_ROOT = runtime
                server._input_inventory_payload = lambda: payload
                server._today_module_index = lambda: {
                    "topics": {"id": "topics", "sourceRoot": "topics"},
                    "cases": {"id": "cases", "sourceRoot": "cases"},
                }
                server._module_root = lambda module, _key="root": topics if module["id"] == "topics" else cases
                server.refresh_data_center = lambda **_kwargs: {"generatedAt": "now"}
                server.dashboard_page = lambda page: {"page": page}

                first = server.sync_workbench_folders("today")
                self.assertEqual(first["sync"]["changes"]["video-sources"]["added"], 1)
                self.assertEqual(first["sync"]["changes"]["topics"]["added"], 1)
                self.assertEqual(first["sync"]["changes"]["cases"]["added"], 1)
                self.assertEqual(case.read_text(encoding="utf-8"), "初版")

                payload["rows"][0]["source_sha256"] = "raw-v2"
                topic.write_text("已变更", encoding="utf-8")
                case.unlink()
                second = server.sync_workbench_folders("today")
                self.assertEqual(second["sync"]["changes"]["video-sources"]["changed"], 1)
                self.assertEqual(second["sync"]["changes"]["topics"]["changed"], 1)
                self.assertEqual(second["sync"]["changes"]["cases"]["removed"], 1)
            finally:
                server.RUNTIME_ROOT = originals["runtime"]
                server._input_inventory_payload = originals["inventory"]
                server._today_module_index = originals["modules"]
                server._module_root = originals["module_root"]
                server.refresh_data_center = originals["refresh"]
                server.dashboard_page = originals["dashboard"]


if __name__ == "__main__":
    unittest.main()
