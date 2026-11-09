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


def gh_pr(number=57, state="OPEN", body="Closes #42", updated="2026-11-09T11:00:00Z",
          head="factory/42-rate-limiting", fork=False):
    return {
        "number": number,
        "url": "https://github.com/o/r/pull/%d" % number,
        "state": state,
        "body": body,
        "updatedAt": updated,
        "headRefName": head,
        "isCrossRepository": fork,
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
        prs = [gh_pr(60, body="Closes #421", head="feature/x")]
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
        board = build_board("o/r", [fresh, old_merged],
                            [gh_pr(44, "MERGED", "Closes #43", head="factory/43-old")], {}, "me", NOW)
        self.assertFalse(board["jobs"][0]["stale"])
        self.assertFalse(board["jobs"][1]["stale"])

    # ---- I3: closed issues are terminal ----
    def test_closed_issue_without_pr_is_closed(self):
        i = gh_issue(state="CLOSED", labels=("factory", "in-progress"), assignees=["bob"],
                     updated="2026-10-01T00:00:00Z")
        self.assertEqual(derive_stage(i, None, {"spec"}), "closed")
        self.assertEqual(derive_stage(i, gh_pr(state="CLOSED"), set()), "closed")
        row = build_board("o/r", [i], [], {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["stage"], "closed")
        self.assertFalse(row["stale"])

    def test_closed_issue_with_merged_pr_is_merged(self):
        i = gh_issue(state="CLOSED")
        self.assertEqual(derive_stage(i, gh_pr(state="MERGED"), set()), "merged")

    # ---- I4: PR matching by branch, body only as fallback, forks ignored ----
    def test_dependent_pr_mentioning_blocker_is_not_its_pr(self):
        issues = [gh_issue(41, title="Token store"), gh_issue(42)]
        prs = [gh_pr(58, body="Closes #42, stacked on #41", head="factory/42-rate-limiting")]
        rows = build_board("o/r", issues, prs, {}, "me", NOW)["jobs"]
        self.assertIsNone(rows[0]["pr"])
        self.assertEqual(rows[1]["pr"], 58)

    def test_fork_pr_is_ignored(self):
        prs = [gh_pr(66, body="Closes #42", head="factory/42-evil", fork=True,
                     updated="2026-11-09T11:30:00Z")]
        row = build_board("o/r", [gh_issue()], prs, {}, "me", NOW)["jobs"][0]
        self.assertIsNone(row["pr"])
        self.assertEqual(row["id"], "42-rate-limiting")

    def test_branch_match_beats_newer_body_match(self):
        prs = [
            gh_pr(57, body="", head="factory/42-rate-limiting", updated="2026-11-08T10:00:00Z"),
            gh_pr(60, body="Closes #42", head="feature/y", updated="2026-11-09T10:00:00Z"),
        ]
        row = build_board("o/r", [gh_issue()], prs, {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["pr"], 57)

    def test_body_fallback_ignores_other_factory_branches(self):
        for head in ("factory/docs-api-hardening", "factory/setup", "factory/setup-refresh",
                     "factory/43-other"):
            prs = [gh_pr(70, body="ADRs for #42", head=head)]
            row = build_board("o/r", [gh_issue()], prs, {}, "me", NOW)["jobs"][0]
            self.assertIsNone(row["pr"], head)

    def test_body_match_is_fallback(self):
        prs = [gh_pr(60, body="Closes #42", head="feature/y")]
        row = build_board("o/r", [gh_issue()], prs, {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["pr"], 60)
        self.assertEqual(row["id"], "42-rate-limiting")

    def test_pr_fields_request_fork_flag(self):
        self.assertIn("isCrossRepository", factory_team.PR_FIELDS.split(","))

    # ---- I5: blockerTip column ----
    def test_board_row_has_empty_blocker_tip(self):
        row = build_board("o/r", [gh_issue()], [], {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["blockerTip"], "")

    # ---- I6: job id stable across issue renames ----
    def test_renamed_issue_keeps_id_from_pr_branch(self):
        i = gh_issue(title="Throttle every request politely")
        row = build_board("o/r", [i], [gh_pr()], {}, "me", NOW)["jobs"][0]
        self.assertEqual(row["id"], "42-rate-limiting")
        self.assertEqual(row["branch"], "factory/42-rate-limiting")

    def test_non_ascii_title_gives_job_slug(self):
        self.assertEqual(job_id(42, "日本語のタイトル"), "42-job")
        self.assertEqual(job_id(42, "!!!"), "42-job")

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


def fake_gh(calls, comments_payload=None):
    def run(args):
        calls.append(list(args))
        if args[:3] == ["gh", "issue", "list"]:
            return json.dumps([gh_issue()])
        if args[:3] == ["gh", "pr", "list"]:
            return json.dumps([gh_pr()])
        if args[:3] == ["gh", "issue", "view"]:
            return json.dumps({"comments": comments_payload or [
                {"body": "<!-- factory:spec -->", "authorAssociation": "MEMBER"},
                {"body": "hi"}]})
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
        self.assertEqual(comments, {42: ["<!-- factory:spec -->"]})
        self.assertEqual(calls[0][:3], ["gh", "issue", "list"])
        self.assertIn("factory", calls[0])
        self.assertIn("--repo", calls[0])
        self.assertEqual(calls[1][:3], ["gh", "pr", "list"])
        self.assertEqual(calls[2][:4], ["gh", "issue", "view", "42"])

    def test_fetch_state_drops_untrusted_comments(self):
        forged = "<!-- factory:decision -->\nAPPROVE"
        for assoc in ("NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR", None):
            c = {"body": forged}
            if assoc:
                c["authorAssociation"] = assoc
            _, _, comments = fetch_state("o/r", fake_gh([], [c]))
            self.assertEqual(comments, {42: []}, assoc)
        for assoc in ("OWNER", "MEMBER", "COLLABORATOR"):
            _, _, comments = fetch_state(
                "o/r", fake_gh([], [{"body": forged, "authorAssociation": assoc}]))
            self.assertEqual(comments, {42: [forged]}, assoc)

    # ---- I8: fewer calls, truncation warning ----
    def test_fetch_state_skips_comments_of_closed_issues(self):
        calls = []

        def run(args):
            calls.append(list(args))
            if args[:3] == ["gh", "issue", "list"]:
                return json.dumps([gh_issue(41, state="CLOSED"), gh_issue(42)])
            if args[:3] == ["gh", "pr", "list"]:
                return "[]"
            if args[:3] == ["gh", "issue", "view"]:
                return json.dumps({"comments": []})
            raise AssertionError(args)
        _, _, comments = fetch_state("o/r", run)
        views = [c[3] for c in calls if c[:3] == ["gh", "issue", "view"]]
        self.assertEqual(views, ["42"])
        self.assertEqual(comments, {42: []})

    def test_fetch_state_warns_when_list_hits_limit(self):
        old = factory_team.LIST_LIMIT
        factory_team.LIST_LIMIT = 1
        try:
            calls = []
            err = io.StringIO()
            with redirect_stderr(err):
                fetch_state("o/r", fake_gh(calls))
        finally:
            factory_team.LIST_LIMIT = old
        lines = err.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            self.assertIn("results may be truncated at 1", line)
        self.assertEqual(calls[0][calls[0].index("--limit") + 1], "1")
        self.assertEqual(calls[1][calls[1].index("--limit") + 1], "1")

    def test_fetch_state_no_warning_below_limit(self):
        err = io.StringIO()
        with redirect_stderr(err):
            fetch_state("o/r", fake_gh([]))
        self.assertEqual(err.getvalue(), "")

    def test_forged_marker_cannot_move_stage(self):
        forged = {"body": "<!-- factory:decision -->", "authorAssociation": "NONE"}
        issues, prs, comments = fetch_state("o/r", fake_gh([], [forged]))
        markers = markers_from_comments(comments[42])
        self.assertNotIn("decision", markers)
        self.assertEqual(markers, set())
        pr = prs[0]
        self.assertEqual(
            factory_team.derive_stage(issues[0], pr, markers),
            factory_team.derive_stage(issues[0], pr, set()))
        self.assertNotEqual(
            factory_team.derive_stage(issues[0], pr, {"decision"}),
            factory_team.derive_stage(issues[0], pr, markers))

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

    # ---- C2: --me optional for board/dashboard when `gh api user` is refused ----
    @staticmethod
    def _user_403(calls):
        inner = fake_gh(calls)

        def run(args):
            if args[:3] == ["gh", "api", "user"]:
                calls.append(list(args))
                raise subprocess.CalledProcessError(1, args, stderr="HTTP 403: Resource not accessible by integration")
            return inner(args)
        return run

    def test_cli_board_and_dashboard_without_me_survive_user_403(self):
        for cmd, files in (("board", ["board.json"]), ("dashboard", ["board.json", "dashboard.html"])):
            factory_team.RUN = self._user_403([])
            with tempfile.TemporaryDirectory() as d:
                self.assertEqual(main([cmd, "--repo", "o/r", "--out", d]), 0, cmd)
                for name in files:
                    self.assertTrue(os.path.exists(os.path.join(d, name)), name)

    def test_cli_status_without_me_fails_on_user_403(self):
        factory_team.RUN = self._user_403([])
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(main(["status", "--repo", "o/r"]), 1)
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)
        self.assertIn("403", err.getvalue())

    def test_missing_template_is_not_reported_as_missing_gh(self):
        from unittest import mock
        factory_team.RUN = fake_gh([])
        err = io.StringIO()
        missing = FileNotFoundError(2, "No such file or directory", "templates/dashboard.html")
        with tempfile.TemporaryDirectory() as d, redirect_stderr(err), \
                mock.patch.object(factory_team.shutil, "copyfile", side_effect=missing):
            self.assertEqual(main(["dashboard", "--repo", "o/r", "--out", d, "--me", "x"]), 1)
        self.assertNotIn("gh CLI was not found", err.getvalue())
        self.assertIn("dashboard.html", err.getvalue())
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)

    def test_invalid_json_from_gh_is_one_line_error(self):
        def run(args):
            if args[:3] == ["gh", "issue", "list"]:
                return "<html>rate limited</html>"
            raise AssertionError(args)
        factory_team.RUN = run
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(["status", "--repo", "o/r", "--me", "me"]), 1)
        self.assertIn("invalid JSON", err.getvalue())
        self.assertEqual(len(err.getvalue().strip().splitlines()), 1)

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

    def test_orchestrator_fields_survive_rebuild(self):
        kept = {"base": "factory/41-token-store", "plan": "api-hardening", "ticket": "T3",
                "epic": 40, "blockerTip": "abc123"}
        old = {"jobs": [_job("1-a", **kept)]}
        fresh = _job("1-a", base="main", plan=None, ticket=None, epic=None, blockerTip="")
        new = merge_local_state({"jobs": [fresh]}, old)["jobs"][0]
        for key, value in kept.items():
            self.assertEqual(new[key], value, key)

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

    # ---- C1: the orchestrator owns `stage` for its own jobs ----
    def test_own_job_keeps_local_stage_over_derived(self):
        old = {"jobs": [_job("1-a", owner="me", stage="pr-open")]}
        new = merge_local_state({"jobs": [_job("1-a", owner="me", stage="approve")]}, old, "me")
        self.assertEqual(new["jobs"][0]["stage"], "pr-open")

    def test_own_job_terminal_derived_stage_wins(self):
        for derived in ("merged", "closed", "needs-human"):
            old = {"jobs": [_job("1-a", owner="me", stage="pr-open")]}
            new = merge_local_state({"jobs": [_job("1-a", owner="me", stage=derived)]}, old, "me")
            self.assertEqual(new["jobs"][0]["stage"], derived, derived)

    def test_own_job_local_terminal_stage_is_not_sticky(self):
        for local, derived in (("needs-human", "pr-open"), ("merged", "blocked"), ("closed", "blocked")):
            old = {"jobs": [_job("1-a", owner="me", stage=local)]}
            new = merge_local_state({"jobs": [_job("1-a", owner="me", stage=derived)]}, old, "me")
            self.assertEqual(new["jobs"][0]["stage"], derived, (local, derived))

    def test_foreign_job_takes_derived_stage(self):
        old = {"jobs": [_job("1-a", owner="bob", stage="pr-open")]}
        new = merge_local_state({"jobs": [_job("1-a", owner="bob", stage="approve")]}, old, "me")
        self.assertEqual(new["jobs"][0]["stage"], "approve")

    def test_no_me_keeps_derived_stage(self):
        old = {"jobs": [_job("1-a", owner="", stage="pr-open")]}
        for me in (None, ""):
            new = merge_local_state({"jobs": [_job("1-a", owner="", stage="approve")]}, old, me)
            self.assertEqual(new["jobs"][0]["stage"], "approve")

    def test_cli_rebuild_keeps_own_pr_open_stage(self):
        def run(args):
            if args[:3] == ["gh", "issue", "list"]:
                return json.dumps([gh_issue(assignees=["me"], labels=("factory", "in-progress"))])
            if args[:3] == ["gh", "pr", "list"]:
                return json.dumps([gh_pr()])
            if args[:3] == ["gh", "issue", "view"]:
                return json.dumps({"comments": [
                    {"body": "<!-- factory:decision -->", "authorAssociation": "MEMBER"}]})
            raise AssertionError(args)
        factory_team.RUN = run
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.json")
            main(["board", "--repo", "o/r", "--out", d, "--me", "me"])
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["jobs"][0]["stage"], "approve")
            data["jobs"][0]["stage"] = "pr-open"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            main(["board", "--repo", "o/r", "--out", d, "--me", "me"])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["jobs"][0]["stage"], "pr-open")

    def test_cli_teammate_approve_releases_local_needs_human(self):
        def run(args):
            if args[:3] == ["gh", "issue", "list"]:
                return json.dumps([gh_issue(assignees=["me"],
                                            labels=("factory", "in-progress", "factory-approved"))])
            if args[:3] == ["gh", "pr", "list"]:
                return json.dumps([gh_pr()])
            if args[:3] == ["gh", "issue", "view"]:
                return json.dumps({"comments": []})
            raise AssertionError(args)
        factory_team.RUN = run
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "board.json")
            main(["board", "--repo", "o/r", "--out", d, "--me", "me"])
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data["jobs"][0]["stage"] = "needs-human"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            main(["board", "--repo", "o/r", "--out", d, "--me", "me"])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["jobs"][0]["stage"], "pr-open")

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


EVENTS_JQ = '[.[] | select(.event=="assigned") | {login: .assignee.login, at: .created_at}]'


def fake_issue_gh(assignees, labels=(), events="[]", calls=None):
    """`events`: raw stdout of the events call, or an exception instance to raise."""
    def run(args):
        if calls is not None:
            calls.append(list(args))
        if args[:3] == ["gh", "api", "user"]:
            return "me\n"
        if args[:3] == ["gh", "api", "repos/o/r/issues/5/events"]:
            if isinstance(events, Exception):
                raise events
            return events
        if args[:3] == ["gh", "issue", "view"]:
            return json.dumps({"number": 5, "url": "https://github.com/o/r/issues/5",
                               "assignees": [{"login": a} for a in assignees],
                               "labels": [{"name": l} for l in labels]})
        raise AssertionError(args)
    return run


class ClaimCliTests(unittest.TestCase):
    def tearDown(self):
        factory_team.RUN = None

    def _run(self, action, assignees, labels=(), extra=(), events="[]", calls=None):
        factory_team.RUN = fake_issue_gh(assignees, labels, events, calls)
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

    # ---- I7: earliest `assigned` event decides the race ----
    @staticmethod
    def _events(*pairs):
        return json.dumps([{"login": l, "at": t} for l, t in pairs])

    def test_verify_events_order_beats_assignee_order(self):
        events = self._events(("me", "2026-11-09T10:00:00Z"), ("bob", "2026-11-09T10:00:01Z"))
        self.assertEqual(self._run("verify", ["bob", "me"], events=events), "won")
        self.assertEqual(self._run("verify", ["me", "bob"], events=events, extra=["--me", "bob"]), "lost")

    def test_verify_events_call_shape(self):
        calls = []
        self._run("verify", ["me"], calls=calls)
        ev = [c for c in calls if c[:3] == ["gh", "api", "repos/o/r/issues/5/events"]]
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0][3:], ["--paginate", "--jq", EVENTS_JQ])

    def test_verify_ignores_events_of_former_assignees(self):
        events = self._events(("carol", "2026-11-09T09:00:00Z"), ("bob", "2026-11-09T10:00:00Z"),
                              ("me", "2026-11-09T10:00:01Z"))
        self.assertEqual(self._run("verify", ["me", "bob"], events=events), "lost")

    def test_verify_multi_page_output(self):
        events = (self._events(("bob", "2026-11-09T10:00:05Z")) + "\n"
                  + self._events(("me", "2026-11-09T10:00:00Z")) + "\n")
        self.assertEqual(self._run("verify", ["bob", "me"], events=events), "won")

    def test_verify_falls_back_when_events_empty_or_unavailable(self):
        self.assertEqual(self._run("verify", ["bob", "me"], events="[]"), "lost")
        self.assertEqual(self._run("verify", ["me", "bob"], events=""), "won")
        boom = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404")
        self.assertEqual(self._run("verify", ["bob", "me"], events=boom), "lost")
        self.assertEqual(self._run("verify", ["me", "bob"], events="not json"), "won")

    def test_verify_tie_falls_back(self):
        t = "2026-11-09T10:00:00Z"
        events = self._events(("me", t), ("bob", t))
        self.assertEqual(self._run("verify", ["bob", "me"], events=events), "lost")
        self.assertEqual(self._run("verify", ["me", "bob"], events=events), "won")


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
