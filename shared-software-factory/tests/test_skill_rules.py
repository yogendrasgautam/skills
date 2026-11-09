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

    def claim_block(self) -> str:
        start = self.text.index("**Claim.**")
        end = self.text.index("Workspace:", start)
        return self.text[start:end]

    def test_no_local_counter(self):
        self.assertNotIn("next 3-digit number", self.text)
        self.assertNotIn("(max in", self.text)

    def test_issue_first_job_id(self):
        self.assertIn("<issue>-<slug>", self.text)
        self.assertIn("kebab-case, at most 4 words", self.text)

    def test_status_command(self):
        self.assertIn("/factory status", self.text)

    def test_claim_section_rereads_and_uses_cli(self):
        block = self.claim_block()
        self.assertIn("re-read", block)
        self.assertIn("decide_claim_winner", block)
        self.assertIn("claim check", block)
        self.assertIn("claim verify", block)

    def test_claim_loser_path(self):
        self.assertIn("--remove-assignee", self.claim_block())

    def test_capacity_checked_before_claim(self):
        promote = self.text[self.text.index("2. **Promote.**"):self.text.index("**Claim.**")]
        self.assertIn("max_parallel", promote)
        self.assertIn("first", promote)

    def test_never_drive_other_owners(self):
        self.assertIn("Never drive a job whose", self.text)

    def test_links_required(self):
        self.assertIn("give it as a markdown link", self.text)

    def test_issue_url_mentioned(self):
        self.assertIn("issueUrl", self.text)

    def test_rebuilt_board_leaves_blocked_by_to_github(self):
        self.assertIn("leaves `blockedBy`", self.text)
        self.assertIn("dependencies/blocked_by", self.text)
        self.assertIn("preserves them", self.text)


if __name__ == "__main__":
    unittest.main()
