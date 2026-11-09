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
    def section(self, title: str) -> str:
        start = self.text.index(title)
        nxt = self.text.find("\n### ", start + len(title))
        return self.text[start:] if nxt == -1 else self.text[start:nxt]

    def test_marker_comments_present(self):
        for marker in ("<!-- factory:review round-N -->", "<!-- factory:build -->",
                       "<!-- factory:decision -->", "<!-- factory:spec -->"):
            self.assertIn(marker, self.text)

    def test_posting_updates_existing_comment(self):
        block = self.section("### Posting shared history")
        self.assertIn("update the existing comment", block)
        self.assertIn("-X PATCH", block)
        self.assertIn("comments --paginate", block)

    def test_rebuild_section(self):
        block = self.section("### Rebuilding a job from GitHub")
        for needle in ("ticket.md", "spec.md", "build.md", "decision.md", "round-N/review-",
                       "git fetch origin", "git worktree add .worktrees/<id> -b factory/<id> origin/factory/<id>",
                       "shared-software-factory:builder", "builder-<id>", "read build.md"):
            self.assertIn(needle, block)

    def test_approve_rework_cross_clone(self):
        for title in ("### `approve <job-id>`", "### `rework <job-id> <note>`"):
            block = self.section(title)
            self.assertIn("needs-human", block)
            self.assertIn("Rebuilding a job from GitHub", block)
            self.assertIn("the PR is the target", block)
        approve = self.section("### `approve <job-id>`")
        self.assertIn("/factory approve 123", approve)
        self.assertIn("issue number", approve)
        self.assertIn("pr-open", approve)

    def test_hard_rule_5_exempts_approve_rework(self):
        rule = self.text[self.text.index("5. GitHub is the board"):self.text.index("## Files")]
        self.assertIn("approve", rule)
        self.assertIn("rework", rule)


if __name__ == "__main__":
    unittest.main()
