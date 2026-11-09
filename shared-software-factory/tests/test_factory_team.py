import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "skills", "factory", "scripts"),
)

import factory_team  # noqa: E402
from factory_team import (  # noqa: E402
    Claim,
    build_board,
    claim_state,
    decide_claim_winner,
    derive_stage,
    detect_dashboard_mode,
    fetch_state,
    job_id,
    main,
    markers_from_comments,
    merge_local_state,
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


def fake_gh(calls):
    def run(args):
        calls.append(list(args))
        if args[:3] == ["gh", "issue", "list"]:
            return json.dumps([gh_issue()])
        if args[:3] == ["gh", "pr", "list"]:
            return json.dumps([gh_pr()])
        if args[:3] == ["gh", "issue", "view"]:
            return json.dumps({"comments": [{"body": "<!-- factory:spec -->"}, {"body": "hi"}]})
        if args[:3] == ["gh", "api", "user"]:
            return "me\n"
        raise AssertionError(args)
    return run


class CliTests(unittest.TestCase):
    def tearDown(self):
        factory_team.RUN = None

    def test_fetch_state_uses_injected_runner(self):
        calls = []
        issues, prs, comments = fetch_state("o/r", fake_gh(calls))
        self.assertEqual(issues[0]["number"], 42)
        self.assertEqual(prs[0]["number"], 57)
        self.assertEqual(comments, {42: ["<!-- factory:spec -->", "hi"]})
        self.assertEqual(calls[0][:3], ["gh", "issue", "list"])
        self.assertIn("factory", calls[0])
        self.assertIn("--repo", calls[0])
        self.assertEqual(calls[1][:3], ["gh", "pr", "list"])
        self.assertEqual(calls[2][:4], ["gh", "issue", "view", "42"])

    def test_cli_board_writes_valid_json(self):
        calls = []
        factory_team.RUN = fake_gh(calls)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["board", "--repo", "o/r", "--out", d]), 0)
            with open(os.path.join(d, "board.json"), encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(data["repo"], "o/r")
        self.assertEqual(data["jobs"][0]["issue"], 42)
        self.assertTrue(any(c[:3] == ["gh", "api", "user"] for c in calls))

    def test_cli_dashboard_copies_html(self):
        factory_team.RUN = fake_gh([])
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["dashboard", "--repo", "o/r", "--out", d, "--me", "x"]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "board.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "dashboard.html")))

    def test_cli_status_prints_table(self):
        factory_team.RUN = fake_gh([])
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["status", "--repo", "o/r", "--me", "me"]), 0)
        self.assertIn("Job | Stage | Owner", out.getvalue())

    def test_cli_exits_1_when_gh_missing(self):
        def boom(args):
            raise FileNotFoundError("gh")
        factory_team.RUN = boom
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(["status", "--repo", "o/r", "--me", "me"]), 1)
        self.assertIn("gh", err.getvalue())
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)


def _job(jid, **kw):
    j = {"id": jid, "round": 0, "reviews": {}, "rounds": [], "decision": None, "blockedBy": []}
    j.update(kw)
    return j


class MergeLocalStateTests(unittest.TestCase):
    def tearDown(self):
        factory_team.RUN = None

    def test_preserved_fields_survive(self):
        old = {"jobs": [_job("1-a", round=2, reviews={"ui": "PASS"}, rounds=[{"n": 1}],
                             decision="APPROVE", blockedBy=["0-x"])]}
        new = merge_local_state({"jobs": [_job("1-a")]}, old)["jobs"][0]
        self.assertEqual(new["reviews"], {"ui": "PASS"})
        self.assertEqual(new["rounds"], [{"n": 1}])
        self.assertEqual(new["decision"], "APPROVE")
        self.assertEqual(new["blockedBy"], ["0-x"])
        self.assertEqual(new["round"], 2)

    def test_round_kept_from_new_when_nonzero(self):
        new = merge_local_state({"jobs": [_job("1-a", round=3)]}, {"jobs": [_job("1-a", round=1)]})
        self.assertEqual(new["jobs"][0]["round"], 3)

    def test_job_removed_on_github_disappears_and_new_job_has_defaults(self):
        old = {"jobs": [_job("1-a", decision="APPROVE"), _job("2-b", decision="ESCALATE")]}
        new = merge_local_state({"jobs": [_job("2-b"), _job("3-c")]}, old)
        self.assertEqual([j["id"] for j in new["jobs"]], ["2-b", "3-c"])
        self.assertEqual(new["jobs"][0]["decision"], "ESCALATE")
        self.assertIsNone(new["jobs"][1]["decision"])

    def test_corrupt_old_file_is_ignored(self):
        factory_team.RUN = fake_gh([])
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "board.json"), "w") as f:
                f.write("{not json")
            self.assertEqual(main(["board", "--repo", "o/r", "--out", d, "--me", "x"]), 0)
            with open(os.path.join(d, "board.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["jobs"][0]["issue"], 42)

    def test_cli_board_twice_keeps_hand_edited_decision(self):
        factory_team.RUN = fake_gh([])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.json")
            main(["board", "--repo", "o/r", "--out", d, "--me", "x"])
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["jobs"][0]["decision"] = "APPROVE"
            data["jobs"][0]["reviews"] = {"ui": "PASS"}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            main(["board", "--repo", "o/r", "--out", d, "--me", "x"])
            with open(path, encoding="utf-8") as f:
                job = json.load(f)["jobs"][0]
        self.assertEqual(job["decision"], "APPROVE")
        self.assertEqual(job["reviews"], {"ui": "PASS"})


def fake_issue_gh(assignees, labels=()):
    def run(args):
        if args[:3] == ["gh", "api", "user"]:
            return "me\n"
        if args[:3] == ["gh", "issue", "view"]:
            return json.dumps({"number": 5, "url": "https://github.com/o/r/issues/5",
                               "assignees": [{"login": a} for a in assignees],
                               "labels": [{"name": l} for l in labels]})
        raise AssertionError(args)
    return run


class ClaimCliTests(unittest.TestCase):
    def tearDown(self):
        factory_team.RUN = None

    def _run(self, action, assignees, labels=(), extra=()):
        factory_team.RUN = fake_issue_gh(assignees, labels)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["claim", action, "--repo", "o/r", "--issue", "5"] + list(extra))
        self.assertEqual(rc, 0)
        return out.getvalue().strip()

    def test_check_free(self):
        self.assertEqual(self._run("check", []), "free")

    def test_check_mine(self):
        self.assertEqual(self._run("check", ["me"]), "mine")

    def test_check_other(self):
        self.assertEqual(self._run("check", ["bob"]), "other bob https://github.com/o/r/issues/5")

    def test_check_other_without_assignee(self):
        self.assertEqual(self._run("check", [], ["in-progress"]),
                         "other none https://github.com/o/r/issues/5")

    def test_check_me_override(self):
        self.assertEqual(self._run("check", ["bob"], extra=["--me", "bob"]), "mine")

    def test_verify_won_and_lost(self):
        self.assertEqual(self._run("verify", ["me", "bob"]), "won")
        self.assertEqual(self._run("verify", ["bob", "me"]), "lost")
        self.assertEqual(self._run("verify", []), "lost")


def fake_mode_gh(owner_type="Organization", private=True, plan="enterprise", fail_plan=False):
    def run(args):
        if args[:3] == ["gh", "api", "repos/o/r"]:
            return "%s\n%s\n" % (owner_type, "true" if private else "false")
        if args[:3] in (["gh", "api", "orgs/o"], ["gh", "api", "user"]):
            if fail_plan:
                raise subprocess.CalledProcessError(403, args, stderr="HTTP 403")
            return plan + "\n"
        raise AssertionError(args)
    return run


class DashboardModeTests(unittest.TestCase):
    def tearDown(self):
        factory_team.RUN = None

    def test_enterprise_gives_pages(self):
        self.assertEqual(detect_dashboard_mode("enterprise", True), "pages")
        self.assertEqual(detect_dashboard_mode("Enterprise", False), "pages")

    def test_free_pro_team_give_projects(self):
        for plan in ("free", "pro", "team", "Team"):
            self.assertEqual(detect_dashboard_mode(plan, True), "projects")

    def test_unknown_gives_ask(self):
        self.assertEqual(detect_dashboard_mode(None, True), "ask")
        self.assertEqual(detect_dashboard_mode(None, False), "ask")
        self.assertEqual(detect_dashboard_mode("weird", True), "ask")

    def _mode(self, **kw):
        factory_team.RUN = fake_mode_gh(**kw)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["mode", "--repo", "o/r"]), 0)
        return out.getvalue()

    def test_cli_mode_org_enterprise(self):
        self.assertEqual(self._mode(), "pages\n")

    def test_cli_mode_user_free(self):
        self.assertEqual(self._mode(owner_type="User", plan="free"), "projects\n")

    def test_403_from_org_lookup_gives_ask(self):
        self.assertEqual(self._mode(fail_plan=True), "ask\n")


if __name__ == "__main__":
    unittest.main()
