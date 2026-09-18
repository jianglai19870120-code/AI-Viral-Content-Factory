from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow import case_output_directories as directories


class CaseOutputDirectoriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.breakdown_root = self.root / "cases" / "breakdowns"
        self.structure_root = self.root / "outputs" / "structures"
        self.copy_root = self.root / "outputs" / "copies"
        self.breakdown = self.breakdown_root / "04_晒成果型拆解（会员专享）" / "案例.md"
        self.breakdown.parent.mkdir(parents=True); self.breakdown.write_text("x", encoding="utf-8")
        self.patches = [
            patch.object(directories, "BREAKDOWN_ROOT", self.breakdown_root),
            patch.object(directories, "STRUCTURE_ROOT", self.structure_root),
            patch.object(directories, "FINAL_COPY_ROOT", self.copy_root),
            patch.object(directories, "get_case", return_value={"breakdownPath": str(self.breakdown)}),
        ]
        for item in self.patches: item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def test_mirrors_breakdown_name_and_creates_only_target_leaf(self) -> None:
        structure = directories.resolve_case_output_directory("SCHX-001", "structure", create=True)
        final_copy = directories.resolve_case_output_directory("SCHX-001", "final_copy", create=True)
        self.assertEqual(structure.name, "04_晒成果型文案结构（会员专享）")
        self.assertEqual(final_copy.name, "04_晒成果型（会员专享）")
        self.assertTrue(structure.is_dir()); self.assertTrue(final_copy.is_dir())
        with self.assertRaisesRegex(ValueError, "必须直接写入"):
            directories.assert_case_output_path("SCHX-001", "structure", self.structure_root / "错误.md")

    def test_non_member_suffix_is_not_invented(self) -> None:
        plain = self.breakdown_root / "01_干货型拆解" / "案例.md"
        plain.parent.mkdir(parents=True); plain.write_text("x", encoding="utf-8")
        with patch.object(directories, "get_case", return_value={"breakdownPath": str(plain)}):
            self.assertEqual(directories.resolve_case_output_directory("GHX-001", "structure").name, "01_干货型文案结构")
            self.assertEqual(directories.resolve_case_output_directory("GHX-001", "final_copy").name, "01_干货型")


if __name__ == "__main__":
    unittest.main()
