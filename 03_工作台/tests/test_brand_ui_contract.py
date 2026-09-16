from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKBENCH = ROOT / "03_工作台"
BRAND = WORKBENCH / "01_品牌设计系统"
SERVER = WORKBENCH / "server.py"
FRONTEND = WORKBENCH / "frontend"
TOKENS = BRAND / "品牌规范" / "tokens.css"
ICON_MANIFEST = BRAND / "图标" / "manifest.json"
PORTRAIT_MANIFEST = BRAND / "人物头像" / "portrait-manifest.json"
CATALOG = BRAND / "组件目录" / "index.html"


def load_server():
    spec = importlib.util.spec_from_file_location("brand_ui_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BrandUiContractTest(unittest.TestCase):
    def test_brand_manifests_only_register_real_assets(self):
        icons = json.loads(ICON_MANIFEST.read_text(encoding="utf-8"))["icons"]
        self.assertEqual(len(icons), 47)
        self.assertEqual([item for item in icons if not (BRAND / "图标" / f"{item}.svg").is_file()], [])
        portraits = json.loads(PORTRAIT_MANIFEST.read_text(encoding="utf-8"))["portraits"]
        self.assertEqual([item for item in portraits.values() if not (BRAND / "人物头像" / item).is_file()], [])

    def test_component_catalog_matches_the_icon_manifest(self):
        source = CATALOG.read_text(encoding="utf-8")
        match = re.search(r"const icons = \[(.*?)\];", source, flags=re.DOTALL)
        self.assertIsNotNone(match)
        catalog_icons = re.findall(r"'([a-z0-9-]+)'", match.group(1))
        manifest_icons = json.loads(ICON_MANIFEST.read_text(encoding="utf-8"))["icons"]
        self.assertEqual(catalog_icons, manifest_icons)

    def test_canonical_tokens_and_frontend_compatibility_boundary(self):
        payload = json.loads((BRAND / "品牌规范" / "brand-tokens.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["color"]["orange"], "#FF7900")
        self.assertEqual(payload["typography"]["light"]["fontWeight"], 300)
        token_source = TOKENS.read_text(encoding="utf-8")
        self.assertIn('url("/brand-assets/fonts/OPPOSans-Variable.ttf")', token_source)
        self.assertIn("--aip-orange: #ff7900", token_source)
        frontend_source = (FRONTEND / "design-system.css").read_text(encoding="utf-8")
        self.assertTrue(frontend_source.startswith('@import url("/brand-assets/tokens.css");'))
        self.assertIn("--orange:#ff7200", frontend_source)

    def test_brand_asset_route_exposes_only_registered_runtime_assets(self):
        server = load_server()
        permitted = [
            "logo.png",
            "tokens.css",
            "fonts/OPPOSans-Variable.ttf",
            "fonts/OPPOSans-Regular.ttf",
            "fonts/OPPOSans-Medium.ttf",
            "fonts/OPPOSans-Bold.ttf",
            "fonts/OPPOSans-Heavy.ttf",
            "icons/nav-dashboard.svg",
            "portraits/xiaojiang-master.png",
            "status/running.svg",
        ]
        for relative in permitted:
            self.assertTrue(server._safe_brand_asset_path(relative).is_file(), relative)
        with self.assertRaises(ValueError):
            server._safe_brand_asset_path("品牌规范/brand-tokens.json")

    def test_status_assets_use_the_canonical_orange(self):
        status = json.loads((BRAND / "人物头像" / "状态徽标" / "status-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(status["running"]["color"], "#FF7900")
        self.assertEqual(status["auditing"]["color"], "#FF7900")
        self.assertNotIn("#ff7200", (BRAND / "人物头像" / "状态徽标" / "running.svg").read_text(encoding="utf-8").lower())
        self.assertNotIn("#ff7200", (BRAND / "人物头像" / "状态徽标" / "auditing.svg").read_text(encoding="utf-8").lower())

    def test_mistaken_page_identity_layer_is_not_present(self):
        self.assertNotIn("factoryStatus", (FRONTEND / "index.html").read_text(encoding="utf-8"))
        self.assertNotIn("renderPageBrandContext", (FRONTEND / "app.js").read_text(encoding="utf-8"))
        self.assertNotIn(".factory-context", (FRONTEND / "app-pages-v10.css").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
