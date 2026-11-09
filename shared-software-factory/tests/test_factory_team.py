import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "skills", "factory", "scripts"),
)

from factory_team import Claim, claim_state, decide_claim_winner, job_id  # noqa: E402

URL = "https://github.com/o/r/issues/123"


def issue(assignees=(), labels=()):
    return {
        "number": 123,
        "url": URL,
        "assignees": [{"login": a} for a in assignees],
        "labels": [{"name": n} for n in labels],
    }


class FactoryTeamIdsAndClaims(unittest.TestCase):
    def test_job_id_uses_issue_number_and_four_word_slug(self):
        self.assertEqual(
            job_id(123, "Rate limiting on the public API now"),
            "123-rate-limiting-on-the",
        )

    def test_claim_free_when_no_assignee_and_no_label(self):
        c = claim_state(issue(), "me")
        self.assertIsInstance(c, Claim)
        self.assertEqual(c.state, "free")
        self.assertIsNone(c.holder)

    def test_claim_mine_when_me_is_sole_assignee(self):
        c = claim_state(issue(["me"]), "me")
        self.assertEqual(c.state, "mine")
        self.assertEqual(c.holder, "me")

    def test_claim_other_with_multiple_assignees_links_issue(self):
        c = claim_state(issue(["bob", "me"]), "me")
        self.assertEqual(c.state, "other")
        self.assertEqual(c.holder, "bob")
        self.assertEqual(c.url, URL)

    def test_claim_other_when_label_in_progress_but_no_assignee(self):
        c = claim_state(issue([], ["in-progress"]), "me")
        self.assertEqual(c.state, "other")
        self.assertIsNone(c.holder)

    def test_race_loser_backs_off(self):
        after = issue(["bob", "me"])
        self.assertFalse(decide_claim_winner(after, "me"))
        self.assertTrue(decide_claim_winner(after, "bob"))


if __name__ == "__main__":
    unittest.main()
