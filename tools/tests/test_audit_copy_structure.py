from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_SCRIPT = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "scripts" / "audit_copy_structure.py"
SPEC = importlib.util.spec_from_file_location("copy_structure_audit", AUDIT_SCRIPT)
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class CopyStructureAuditNamingTests(unittest.TestCase):
    def test_accepts_topic_first_release_name(self) -> None:
        self.assertTrue(AUDIT.future_release_name_valid("赚钱就是两件事_做对的事和把事情做对_GHX-002_20260906-195747.md"))
        self.assertTrue(AUDIT.future_release_name_valid("选题_GHX-002_20260906-195747_02.md"))

    def test_rejects_legacy_or_invalid_release_name(self) -> None:
        self.assertFalse(AUDIT.future_release_name_valid("GHX-002_选题_20260906-195747.md"))
        self.assertFalse(AUDIT.future_release_name_valid("选题_ABC-002_20260906-195747.md"))
        self.assertFalse(AUDIT.future_release_name_valid("选题_GHX-002_20260906.md"))


if __name__ == "__main__":
    unittest.main()
