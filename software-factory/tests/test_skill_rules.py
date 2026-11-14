"""Static checks: the prompts stay wired to the state script, the guard and each other."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "skills", "factory", "scripts"))
import factory  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class SkillRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.skill = read("skills", "factory", "SKILL.md")

    def test_every_F_command_exists(self):
        sub = factory.build_parser()._subparsers._group_actions[0].choices
        used = set(re.findall(r"`F ([a-z][a-z-]+)", self.skill))
        self.assertTrue(used)
        self.assertEqual(used - set(sub), set(), "SKILL.md uses unknown factory.py commands")

    def test_every_command_documented(self):
        sub = factory.build_parser()._subparsers._group_actions[0].choices
        for name in sub:
            self.assertIn("`F %s" % name, self.skill, name)

    def test_stages_match_script_and_dashboard(self):
        dash = read("skills", "factory", "templates", "dashboard.html")
        for stage in factory.STAGES:
            self.assertIn(stage, self.skill)
            self.assertIn('["%s"' % stage, dash)

    def test_no_hand_written_board(self):
        self.assertNotIn("Rewrite the whole file", self.skill)
        self.assertNotIn("json.tool", self.skill)
        self.assertNotIn("3-digit", self.skill)

    def test_merge_is_pinned(self):
        self.assertIn("--match-head-commit", self.skill)
        self.assertNotIn("`gh pr merge <pr> --squash --delete-branch`", self.skill)

    def test_run_lock_and_andon(self):
        for needle in ("F lock run acquire", "F lock run release", "F halt set", "risk_globs", "no_ci"):
            self.assertIn(needle, self.skill)

    def test_agents_exist_for_every_spawn(self):
        names = set(re.findall(r"`(planner|spec-writer|builder|reviewer-[a-z]+|ux-tester|approver)`", self.skill))
        for n in names:
            self.assertTrue(os.path.exists(os.path.join(ROOT, "agents", n + ".md")), n)
        for r in factory.REVIEWERS:
            self.assertIn("reviewer-" + r, names)

    def test_reviewers_do_not_run_the_suite(self):
        for r in ("code", "security", "ux"):
            text = read("agents", "reviewer-%s.md" % r)
            self.assertIn("tests.txt", text)
            self.assertIn("delta", text)
            self.assertNotIn("you may run tests", text)

    def test_builder_and_approver_contracts(self):
        self.assertIn("SPEC-GAP", read("agents", "builder.md"))
        self.assertIn("SPEC-GAP", self.skill)
        self.assertIn("Commit: <Head sha>", read("agents", "approver.md"))
        self.assertIn("Epic mode", read("agents", "reviewer-adversary.md"))

    def test_conflict_contract(self):
        builder = read("agents", "builder.md")
        self.assertIn('"Resolving conflicts"', self.skill)
        self.assertIn("## Resolving conflicts", builder)
        self.assertIn("conflict fix", builder)
        self.assertIn("zdiff3", builder)
        self.assertIn("conflict fix", read("agents", "reviewer-code.md"))

    def test_plugin_manifest(self):
        m = json.loads(read(".claude-plugin", "plugin.json"))
        self.assertEqual(m["name"], "software-factory")
        self.assertRegex(m["version"], r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
