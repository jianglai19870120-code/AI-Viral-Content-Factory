from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "10_Skills武器库" / "文案结构生成 Skill" / "scripts" / "prepare_structure_task.py"
SPEC = importlib.util.spec_from_file_location("prepare_structure_task_under_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class FormalFrameworkTypeTests(unittest.TestCase):
    def test_numbered_point_prefix_preserves_formal_family(self):
        self.assertEqual(MODULE.formal_framework_type("第一点：案例一"), "案例")
        self.assertEqual(MODULE.formal_framework_type("第三点：误区"), "误区")
        self.assertEqual(MODULE.formal_framework_type("第五点：解决方案"), "解决方案")

    def test_support_label_stays_support_only(self):
        self.assertIsNone(MODULE.formal_framework_type("开场引导"))


if __name__ == "__main__":
    unittest.main()
