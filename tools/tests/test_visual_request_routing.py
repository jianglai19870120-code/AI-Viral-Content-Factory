from pathlib import Path
import runpy
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]


class VisualRequestRoutingContractTests(unittest.TestCase):
    def test_visual_entrypoints_keep_visual_work_separate_from_copy_audit(self) -> None:
        paths = [
            ROOT / ".agents" / "skills" / "generate-ip-ppt" / "SKILL.md",
            ROOT / "10_Skills武器库" / "IP视觉PPT生成Skill" / "SKILL.md",
            ROOT / "01_Agent系统" / "08_小图-视觉生产Agent" / "AGENT.md",
            ROOT / "10_Skills武器库" / "01_小姜调度Skill" / "SKILL.md",
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.strip(), path)
            self.assertNotIn("copy_run_manifest", text, path)

    def test_visual_skill_declares_its_only_pre_render_gate(self) -> None:
        text = (
            ROOT / "10_Skills武器库" / "IP视觉PPT生成Skill" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertIn("唯一需要触发的小审门禁是 `audit_visual_work_package.py`", text)
        self.assertIn("不替代或触发 `audit_dry_goods_v6.py`", text)

    def test_visible_labels_do_not_split_chinese_comma_or_colon_clauses(self) -> None:
        scripts_dir = ROOT / "10_Skills武器库" / "IP视觉PPT生成Skill" / "scripts"
        sys.path.insert(0, str(scripts_dir))
        try:
            module = runpy.run_path(str(scripts_dir / "build_ip_ppt.py"))
        finally:
            sys.path.pop(0)
        split_complete_source_phrases = module["split_complete_source_phrases"]
        self.assertEqual(
            split_complete_source_phrases("真正的衡量标准是：你完成的事，能帮你接下来省多少时间，赚多少钱。"),
            ["真正的衡量标准是：你完成的事，能帮你接下来省多少时间，赚多少钱"],
        )


if __name__ == "__main__":
    unittest.main()
