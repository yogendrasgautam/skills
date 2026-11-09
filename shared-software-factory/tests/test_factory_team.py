import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "skills", "factory", "scripts"),
)

from factory_team import (  # noqa: E402
    Claim,
    build_board,
    claim_state,
    decide_claim_winner,
    derive_stage,
    job_id,
    markers_from_comments,
    render_status,
)

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


NOW = "2026-11-09T12:00:00Z"


def gh_issue(number=42, title="Rate limiting", state="OPEN", labels=("factory",),
             assignees=(), updated="2026-11-09T10:00:00Z"):
    return {
        "number": number,
        "title": title,
        "url": "https://github.com/o/r/issues/%d" % number,
        "state": state,
        "labels": [{"name": n} for n in labels],
        "assignees": [{"login": a} for a in assignees],
        "updatedAt": updated,
    }


def gh_pr(number=57, state="OPEN", body="Closes #42", updated="2026-11-09T11:00:00Z"):
    return {
        "number": number,
        "url": "https://github.com/o/r/pull/%d" % number,
        "state": state,
        "body": body,
        "updatedAt": updated,
        "headRefName": "factory/42-rate-limiting",
    }


class FactoryTeamBoard(unittest.TestCase):
    def test_markers_from_comments(self):
        bodies = [
            "hi <!-- factory:spec --> there",
            "<!--factory:review round-1-->",
            "<!-- factory:decision -->",
            "no marker",
        ]
        self.assertEqual(
            markers_from_comments(bodies),
            {"spec", "review round-1", "decision"},
        )

    def test_stage_merged_pr_beats_stale_labels(self):
        i = gh_issue(state="CLOSED", labels=("factory", "in-progress"))
        self.assertEqual(derive_stage(i, gh_pr(state="MERGED"), set()), "merged")

    def test_stage_closed_unmerged_pr_is_ignored(self):
        i = gh_issue(labels=("factory", "in-progress"))
        self.assertEqual(derive_stage(i, gh_pr(state="CLOSED"), set()), "spec")
        self.assertEqual(derive_stage(gh_issue(), gh_pr(state="CLOSED"), set()), "blocked")

    def test_stage_needs_human_label_wins_over_review_marker(self):
        i = gh_issue(labels=("factory", "needs-human-review"))
        self.assertEqual(derive_stage(i, gh_pr(), {"review round-1"}), "needs-human")

    def test_stage_ladder(self):
        pr = gh_pr()
        self.assertEqual(
            derive_stage(gh_issue(labels=("factory", "factory-approved")), pr, {"decision"}),
            "pr-open",
        )
        self.assertEqual(derive_stage(gh_issue(), pr, {"decision", "review round-1"}), "approve")
        self.assertEqual(derive_stage(gh_issue(), pr, {"review round-2"}), "review")
        self.assertEqual(derive_stage(gh_issue(), pr, set()), "build")
        self.assertEqual(derive_stage(gh_issue(), None, {"spec"}), "build")
        self.assertEqual(derive_stage(gh_issue(labels=("factory", "in-progress")), None, set()), "spec")
        self.assertEqual(derive_stage(gh_issue(), None, set()), "blocked")

    def test_board_row_without_spec_or_pr_has_empty_links(self):
        board = build_board("o/r", [gh_issue()], [], {}, "me", NOW)
        row = board["jobs"][0]
        self.assertEqual(row["prUrl"], "")
        self.assertIsNone(row["pr"])
        self.assertEqual(row["issueUrl"], "https://github.com/o/r/issues/42")
        self.assertEqual(row["id"], "42-rate-limiting")
        self.assertEqual(row["branch"], "factory/42-rate-limiting")
        self.assertEqual(row["stage"], "blocked")
        self.assertIsNone(row["owner"])
        self.assertFalse(row["stale"])

    def test_board_only_factory_non_epic_issues(self):
        issues = [
            gh_issue(1, labels=("factory",)),
            gh_issue(2, labels=("factory", "epic")),
            gh_issue(3, labels=("bug",)),
        ]
        board = build_board("o/r", issues, [], {}, "me", NOW)
        self.assertEqual([j["issue"] for j in board["jobs"]], [1])

    def test_pr_match_is_exact_issue_number(self):
        prs = [gh_pr(60, body="Closes #421")]
        board = build_board("o/r", [gh_issue(42)], prs, {}, "me", NOW)
        self.assertIsNone(board["jobs"][0]["pr"])

    def test_two_prs_one_issue_latest_wins_and_noted(self):
        prs = [
            gh_pr(57, updated="2026-11-08T10:00:00Z"),
            gh_pr(58, updated="2026-11-09T09:00:00Z"),
        ]
        row = build_board("o/r", [gh_issue()], prs, {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["pr"], 58)
        self.assertIn("#57", row["note"])
        self.assertIn("[#57](https://github.com/o/r/pull/57)", row["note"])

    def test_merged_pr_gives_merged_row(self):
        i = gh_issue(state="CLOSED", labels=("factory", "in-progress"), assignees=["bob"])
        row = build_board("o/r", [i], [gh_pr(state="MERGED")], {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["stage"], "merged")
        self.assertEqual(row["pr"], 57)

    def test_stale_claim_flagged_not_released(self):
        i = gh_issue(assignees=["bob"], labels=("factory", "in-progress"),
                     updated="2026-11-05T11:00:00Z")
        row = build_board("o/r", [i], [], {}, "me", NOW)["jobs"][0]
        self.assertTrue(row["stale"])
        self.assertEqual(row["owner"], "bob")

    def test_recent_or_done_claim_not_stale(self):
        fresh = gh_issue(assignees=["bob"], updated="2026-11-08T12:00:00Z")
        old_merged = gh_issue(43, state="CLOSED", assignees=["bob"], updated="2026-10-01T00:00:00Z")
        board = build_board("o/r", [fresh, old_merged], [gh_pr(44, "MERGED", "Closes #43")], {}, "me", NOW)
        self.assertFalse(board["jobs"][0]["stale"])
        self.assertFalse(board["jobs"][1]["stale"])

    def test_status_table_has_links(self):
        i = gh_issue(assignees=["bob"], updated="2026-11-01T00:00:00Z")
        board = build_board("o/r", [i, gh_issue(7, title="Other")], [gh_pr()], {}, "me", NOW)
        out = render_status(board, "o/r")
        self.assertIn("Job | Stage | Owner | Issue | PR | Note", out)
        self.assertIn("[#42](https://github.com/o/r/issues/42)", out)
        self.assertIn("[#57](https://github.com/o/r/pull/57)", out)
        self.assertIn("(stale)", out)
        self.assertIn(
            "| 7-other | blocked | — | [#7](https://github.com/o/r/issues/7) | — |  |", out
        )


if __name__ == "__main__":
    unittest.main()
