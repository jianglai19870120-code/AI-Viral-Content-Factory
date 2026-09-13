from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = ROOT / "10_Skills武器库" / "文案结构生成 Skill" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from structure_v16 import validate_case_card_binding  # noqa: E402


class CaseCardV12StructureBindingTest(unittest.TestCase):
    def test_case_copy_must_be_used_verbatim(self):
        cards = list((ROOT / "02_资产中心" / "02_处理库" / "05_案例_内容模块（会员专享）" / "01_案例卡").rglob("CASE-*.md"))
        if not cards:
            self.skipTest("公开包不分发会员案例卡正文")
        card = cards[0]
        text = card.read_text(encoding="utf-8")
        case_copy = re.search(r"^##\s*可直接调用案例\s*\n+(.+?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(case_copy)
        relative = card.relative_to(ROOT).as_posix()
        row = {
            "formal_framework_type": "案例",
            "core_claim": case_copy.group(1).strip(),
            "processing_sources": [{"path": relative, "section": "原文依据"}],
        }
        self.assertEqual(validate_case_card_binding(row), [])
        row["core_claim"] = "我把案例改成了一句概念解释。"
        self.assertIn("逐字等于", validate_case_card_binding(row)[0])


if __name__ == "__main__":
    unittest.main()
