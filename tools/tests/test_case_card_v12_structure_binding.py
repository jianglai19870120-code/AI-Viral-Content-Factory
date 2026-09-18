from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = ROOT / "10_Skills武器库" / "文案结构生成 Skill" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from structure_v19 import validate_v19  # noqa: E402


class CaseCardV19StructureContractTest(unittest.TestCase):
    def test_retired_structure_contract_cannot_enter_current_validator(self):
        errors = validate_v19(
            {"schema": "copy-structure-handoff-v16"},
            {"schema": "copy-structure-v16"},
        )
        self.assertEqual(errors, ["handoff/candidate 必须同时为 V19"])


if __name__ == "__main__":
    unittest.main()
