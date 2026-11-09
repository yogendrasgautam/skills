"""Static checks that the orchestrator prompt carries the team-ready rules."""
import os
import unittest

SKILL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "factory", "SKILL.md")


def read_skill() -> str:
    with open(SKILL, encoding="utf-8") as f:
        return f.read()


class SkillRulesTest(unittest.TestCase):
    def setUp(self):
        self.text = read_skill()

    def test_no_local_counter(self):
        self.assertNotIn("max in", self.text)
        self.assertNotIn("next 3-digit number", self.text)

    def test_issue_first_job_id(self):
        self.assertIn("<issue>-<slug>", self.text)

    def test_status_command(self):
        self.assertIn("/factory status", self.text)

    def test_claim_section_rereads(self):
        start = self.text.index("**Claim.**")
        self.assertIn("re-read", self.text[start:start + 1800])
        self.assertIn("decide_claim_winner", self.text[start:start + 1800])

    def test_issue_url_mentioned(self):
        self.assertIn("issueUrl", self.text)

    def test_rebuilt_board_leaves_blocked_by_to_github(self):
        self.assertIn("leaves `blockedBy`", self.text)
        self.assertIn("dependencies/blocked_by", self.text)


if __name__ == "__main__":
    unittest.main()
