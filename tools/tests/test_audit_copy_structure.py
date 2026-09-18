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


class CopyStructureAuditContractTests(unittest.TestCase):
    def test_accepts_only_current_v19_handoff_and_candidate(self) -> None:
        self.assertTrue(AUDIT.uses_current_contract(
            {"schema": "copy-structure-handoff-v19"}, {"schema": "copy-structure-v19"}
        ))

    def test_rejects_retired_contracts(self) -> None:
        self.assertFalse(AUDIT.uses_current_contract(
            {"schema": "copy-structure-handoff-v16"}, {"schema": "copy-structure-v16"}
        ))


if __name__ == "__main__":
    unittest.main()
