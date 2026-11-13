"""Unit tests for the factory state script (unittest, stdlib only)."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "factory", "scripts"))
import factory  # noqa: E402

SHA1, SHA2 = "a" * 40, "b" * 40


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = os.path.join(self.tmp.name, "factory")
        os.mkdir(self.d)
        with open(os.path.join(self.d, "board.json"), "w") as f:
            f.write('{ "jobs": [] }\n')

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = factory.main(["--dir", self.d] + [str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def ok(self, *args):
        code, out, err = self.run_cli(*args)
        self.assertEqual(code, 0, "%s -> %s %s" % (args, code, err))
        return out

    def job(self, jid):
        with open(os.path.join(self.d, "board.json")) as f:
            return [j for j in json.load(f)["jobs"] if j["id"] == jid][0]

    def add(self, jid="42-rate-limit", **kw):
        args = ["add", "--id", jid, "--title", "t", "--issue", jid.split("-")[0]]
        for k, v in kw.items():
            args += ["--" + k.replace("_", "-"), v]
        self.ok(*args)

    def to_review(self, jid="42-rate-limit", sha=SHA1):
        self.ok("transition", jid, "spec")
        self.ok("transition", jid, "build")
        self.ok("round-start", jid, "--sha", sha)

    def pass_all(self, jid="42-rate-limit"):
        self.ok("round-set", jid, "tests=PASS")
        for r in factory.REVIEWERS:
            self.ok("review", jid, r, "--verdict", "PASS")

    def to_pr_open(self, jid="42-rate-limit", sha=SHA1):
        self.to_review(jid, sha)
        self.pass_all(jid)
        self.ok("round-set", jid, "uxTest=SKIPPED", "ci=PASS")
        self.ok("transition", jid, "approve")
        self.ok("decision", jid, "APPROVE", "--sha", sha)
        self.ok("set", jid, "pr=57")
        self.ok("transition", jid, "pr-open")


class AddTest(Base):
    def test_id_must_be_issue_slug(self):
        code, _, err = self.run_cli("add", "--id", "003-foo", "--title", "t", "--issue", 42)
        self.assertEqual(code, 1)
        self.assertIn("must start with its issue number", err)
        self.assertEqual(self.run_cli("add", "--id", "Foo", "--title", "t")[0], 1)

    def test_duplicate_rejected(self):
        self.add()
        self.assertEqual(self.run_cli("add", "--id", "42-rate-limit", "--title", "t")[0], 1)

    def test_branch_derived(self):
        self.add()
        self.assertEqual(self.job("42-rate-limit")["branch"], "factory/42-rate-limit")


class TransitionTest(Base):
    def test_illegal_edge(self):
        self.add()
        code, _, err = self.run_cli("transition", "42-rate-limit", "approve")
        self.assertEqual(code, 2)
        self.assertIn("illegal transition", err)

    def test_review_only_via_round_start(self):
        self.add()
        self.ok("transition", "42-rate-limit", "spec")
        self.ok("transition", "42-rate-limit", "build")
        code, _, err = self.run_cli("transition", "42-rate-limit", "review")
        self.assertEqual(code, 2)
        self.assertIn("round-start", err)

    def test_needs_human_requires_note(self):
        self.add()
        self.assertEqual(self.run_cli("transition", "42-rate-limit", "needs-human")[0], 1)
        self.ok("transition", "42-rate-limit", "needs-human", "--note", "doubt")
        self.assertEqual(self.job("42-rate-limit")["note"], "doubt")

    def test_approve_needs_four_pass_and_tests(self):
        self.add()
        self.to_review()
        self.ok("round-set", "42-rate-limit", "tests=PASS", "uxTest=SKIPPED")
        for r in ("security", "ux", "code"):
            self.ok("review", "42-rate-limit", r, "--verdict", "PASS")
        self.assertEqual(self.run_cli("transition", "42-rate-limit", "approve")[0], 2)
        self.ok("review", "42-rate-limit", "adversary", "--verdict", "PASS")
        self.ok("transition", "42-rate-limit", "approve")

    def test_ui_job_cannot_skip_ux_test(self):
        self.add()
        self.to_review()
        self.pass_all()
        self.assertEqual(self.run_cli("transition", "42-rate-limit", "approve")[0], 2)
        self.ok("transition", "42-rate-limit", "ux-queue")
        self.assertTrue(self.job("42-rate-limit")["uxQueuedAt"])

    def test_external_merge_from_any_stage(self):
        self.add()
        self.to_review()
        self.assertEqual(self.run_cli("transition", "42-rate-limit", "merged")[0], 2)
        self.ok("transition", "42-rate-limit", "merged", "--external")
        self.assertEqual(self.run_cli("transition", "42-rate-limit", "closed", "--external")[0], 2)

    def test_back_to_build_clears_approval(self):
        self.add()
        self.to_pr_open()
        self.ok("transition", "42-rate-limit", "build", "--note", "CI failed")
        j = self.job("42-rate-limit")
        self.assertIsNone(j["decision"])
        self.assertEqual(j["approvedSha"], "")

    def test_events_logged(self):
        self.add()
        self.ok("transition", "42-rate-limit", "spec")
        with open(os.path.join(self.d, "events.jsonl")) as f:
            events = [json.loads(l) for l in f]
        self.assertEqual([e["event"] for e in events], ["add", "transition"])


class RoundTest(Base):
    def test_round_budget(self):
        self.add()
        self.to_review()
        for sha in ("c" * 40, "d" * 40):
            self.ok("transition", "42-rate-limit", "build")
            self.ok("round-start", "42-rate-limit", "--sha", sha)
        self.ok("transition", "42-rate-limit", "build")
        code, _, err = self.run_cli("round-start", "42-rate-limit", "--sha", "e" * 40)
        self.assertEqual(code, 3)
        self.ok("rework", "42-rate-limit")
        self.ok("round-start", "42-rate-limit", "--sha", "e" * 40)
        self.assertEqual(self.job("42-rate-limit")["round"], 4)

    def test_second_round_is_delta_with_prev_sha(self):
        self.add()
        self.to_review()
        self.assertEqual(self.job("42-rate-limit")["rounds"][0]["mode"], "full")
        self.ok("transition", "42-rate-limit", "build")
        self.ok("round-start", "42-rate-limit", "--sha", SHA2)
        r = self.job("42-rate-limit")["rounds"][1]
        self.assertEqual((r["mode"], r["prevSha"], r["sha"]), ("delta", SHA1, SHA2))

    def test_round_after_rework_is_full(self):
        self.add()
        self.to_review()
        self.ok("rework", "42-rate-limit")
        self.ok("round-start", "42-rate-limit", "--sha", SHA2)
        self.assertEqual(self.job("42-rate-limit")["rounds"][1]["mode"], "full")

    def test_review_from_file(self):
        self.add()
        self.to_review()
        p = os.path.join(self.tmp.name, "review-code.md")
        with open(p, "w") as f:
            f.write("VERDICT: CHANGES\nsummary\n")
        self.ok("review", "42-rate-limit", "code", "--file", p)
        self.assertEqual(self.job("42-rate-limit")["reviews"]["code"], "CHANGES")
        with open(p, "w") as f:
            f.write("Looks good to me\n")
        self.assertEqual(self.run_cli("review", "42-rate-limit", "code", "--file", p)[0], 4)
        self.assertEqual(self.run_cli("review", "42-rate-limit", "code", "--file", p + ".nope")[0], 4)

    def test_round_set_enums(self):
        self.add()
        self.to_review()
        self.assertEqual(self.run_cli("round-set", "42-rate-limit", "uxTest=MAYBE")[0], 1)
        self.assertEqual(self.run_cli("round-set", "42-rate-limit", "bogus=1")[0], 1)

    def test_verdict_kinds(self):
        p = os.path.join(self.tmp.name, "decision.md")
        with open(p, "w") as f:
            f.write("ESCALATE\nreason\n")
        self.assertEqual(self.ok("verdict", p, "--kind", "decision").strip(), "ESCALATE")


class MergeGateTest(Base):
    def test_approve_pinned_to_reviewed_sha(self):
        self.add()
        self.to_review()
        self.pass_all()
        self.ok("round-set", "42-rate-limit", "uxTest=SKIPPED")
        self.ok("transition", "42-rate-limit", "approve")
        code, _, err = self.run_cli("decision", "42-rate-limit", "APPROVE", "--sha", SHA2)
        self.assertEqual(code, 2)
        self.assertIn("not the reviewed sha", err)

    def test_merge_check_happy_path(self):
        self.add()
        self.to_pr_open()
        out = self.ok("merge-check", "42-rate-limit", "--head", SHA1)
        self.assertEqual(out.strip(), "gh pr merge 57 --squash --delete-branch --match-head-commit " + SHA1)

    def test_merge_refused_when_head_moved(self):
        self.add()
        self.to_pr_open()
        code, _, err = self.run_cli("merge-check", "42-rate-limit", "--head", SHA2)
        self.assertEqual(code, 2)
        self.assertIn("new commits need review", err)

    def test_merge_refused_when_stacked(self):
        self.add()
        self.to_pr_open()
        self.ok("set", "42-rate-limit", "base=factory/41-x")
        self.assertEqual(self.run_cli("merge-check", "42-rate-limit", "--head", SHA1)[0], 2)

    def test_risk_paths_need_human(self):
        self.add()
        self.to_pr_open()
        self.ok("set", "42-rate-limit", "risk=.github/workflows/ci.yml")
        self.assertEqual(self.run_cli("merge-check", "42-rate-limit", "--head", SHA1)[0], 2)
        self.ok("decision", "42-rate-limit", "APPROVE", "--human", "--sha", SHA1)
        self.ok("merge-check", "42-rate-limit", "--head", SHA1)

    def test_no_ci_needs_human(self):
        self.add()
        self.to_pr_open()
        self.ok("round-set", "42-rate-limit", "ci=none")
        self.assertEqual(self.run_cli("merge-check", "42-rate-limit", "--head", SHA1)[0], 2)

    def test_halt_blocks_merge_and_promotion(self):
        self.add()
        self.to_pr_open()
        self.add("43-other")
        self.ok("halt", "set", "main is red: ci")
        self.assertEqual(self.run_cli("merge-check", "42-rate-limit", "--head", SHA1)[0], 2)
        r = json.loads(self.ok("ready").strip())
        self.assertEqual(r["action"], "wait")
        self.ok("halt", "clear")
        self.ok("merge-check", "42-rate-limit", "--head", SHA1)

    def test_needs_human_to_pr_open_only_with_human_approve(self):
        self.add()
        self.to_review()
        self.ok("transition", "42-rate-limit", "needs-human", "--note", "doubt")
        self.assertEqual(self.run_cli("transition", "42-rate-limit", "pr-open")[0], 2)
        self.ok("decision", "42-rate-limit", "APPROVE", "--human", "--sha", SHA1)
        self.ok("transition", "42-rate-limit", "pr-open")

    def test_repin_only_when_approved_pr_open(self):
        self.add()
        self.to_review()
        self.assertEqual(self.run_cli("repin", "42-rate-limit", "--sha", SHA2, "--reason", "r")[0], 2)
        self.add("43-b")
        self.to_pr_open("43-b")
        self.ok("repin", "43-b", "--sha", SHA2, "--reason", "restack, patch-id unchanged")
        self.ok("merge-check", "43-b", "--head", SHA2)

    def test_restack_round_from_pr_open_clears_approval(self):
        self.add()
        self.to_pr_open()
        self.ok("round-start", "42-rate-limit", "--sha", SHA2, "--mode", "full")
        j = self.job("42-rate-limit")
        self.assertEqual((j["stage"], j["decision"], j["approvedSha"]), ("review", None, ""))


class ReadyTest(Base):
    def ready(self, *args):
        return dict((r["id"], r) for r in
                    (json.loads(l) for l in self.ok("ready", *args).splitlines()))

    def test_start_stack_wait(self):
        self.add("41-store")
        self.add("42-api", blocked_by="41-store")
        self.add("43-ui", blocked_by="41-store,42-api")
        r = self.ready()
        self.assertEqual(r["41-store"]["action"], "start")
        self.assertEqual(r["42-api"]["action"], "wait")
        self.to_pr_open("41-store")
        r = self.ready()
        self.assertEqual((r["42-api"]["action"], r["42-api"]["base"]), ("stack", "factory/41-store"))
        self.assertEqual(r["43-ui"]["action"], "wait")

    def test_max_parallel(self):
        for i in (1, 2, 3):
            self.add("%d-t" % i)
        acts = [r["action"] for r in self.ready("--max-parallel", 2).values()]
        self.assertEqual(sorted(acts), ["start", "start", "wait"])

    def test_dependents(self):
        self.add("41-store")
        self.add("42-api", blocked_by="41-store")
        self.ok("transition", "42-api", "spec")
        self.ok("set", "42-api", "base=factory/41-store")
        self.assertIn("42-api", self.ok("dependents", "41-store"))


class LockTest(Base):
    def test_acquire_held_release(self):
        self.ok("lock", "run", "acquire", "--owner", "s1")
        self.ok("lock", "run", "acquire", "--owner", "s1")
        self.assertEqual(self.run_cli("lock", "run", "acquire", "--owner", "s2")[0], 6)
        self.assertEqual(self.run_cli("lock", "run", "release", "--owner", "s2")[0], 6)
        self.ok("lock", "run", "release", "--owner", "s1")
        self.ok("lock", "run", "acquire", "--owner", "s2")

    def test_stale(self):
        self.ok("lock", "ux", "acquire", "--owner", "j1")
        old = time.time() - 3 * 3600
        os.utime(os.path.join(self.d, "ux.lock", "owner"), (old, old))
        self.assertEqual(self.run_cli("lock", "ux", "acquire", "--owner", "j2")[0], 5)

    def test_board_write_is_heartbeat(self):
        self.ok("lock", "run", "acquire", "--owner", "s1")
        owner = os.path.join(self.d, "run.lock", "owner")
        old = time.time() - 3 * 3600
        os.utime(owner, (old, old))
        self.add()
        self.assertGreater(os.path.getmtime(owner), old + 3600)


class MiscTest(Base):
    def test_validate(self):
        self.add()
        self.ok("validate")
        with open(os.path.join(self.d, "board.json"), "w") as f:
            json.dump({"jobs": [{"id": "42-x", "stage": "nope", "blockedBy": ["9-y"]}]}, f)
        code, out, _ = self.run_cli("validate")
        self.assertEqual(code, 1)
        self.assertIn("unknown stage", out)
        self.assertIn("unknown job", out)

    def test_epic(self):
        self.add("41-a", epic="40", epic_base=SHA1)
        self.add("42-b", epic="40")
        e = json.loads(self.ok("epic", 40))
        self.assertEqual((e["total"], e["done"], e["base"]), (2, False, SHA1))

    def test_metrics(self):
        self.add()
        self.to_pr_open()
        self.ok("transition", "42-rate-limit", "merged")
        summary = json.loads(self.ok("metrics").splitlines()[0])
        self.assertEqual((summary["merged"], summary["firstPassRate"]), (1, 1.0))
        self.assertTrue(os.path.exists(os.path.join(self.d, "metrics.json")))

    def test_stuck(self):
        self.add()
        self.ok("transition", "42-rate-limit", "spec")
        self.assertEqual(self.ok("stuck", "--minutes", 60), "")
        self.assertIn("42-rate-limit", self.ok("stuck", "--minutes", 0))

    def test_diff_match(self):
        repo = os.path.join(self.tmp.name, "repo")
        os.mkdir(repo)

        def git(*a):
            subprocess.run(("git", "-C", repo, "-c", "user.email=t@t", "-c", "user.name=t") + a,
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init", "-q", "-b", "main")
        open(os.path.join(repo, "a.txt"), "w").close()
        git("add", "."), git("commit", "-qm", "init")
        git("switch", "-qc", "factory/1-x")
        os.makedirs(os.path.join(repo, ".github", "workflows"))
        open(os.path.join(repo, ".github", "workflows", "ci.yml"), "w").close()
        open(os.path.join(repo, "b.txt"), "w").close()
        git("add", "."), git("commit", "-qm", "work")
        profile = os.path.join(self.d, "profile.md")
        with open(profile, "w") as f:
            f.write("risk_globs: .github/**, **/migrations/**   # comment\nui_globs: none\n")
        common = ["--profile", profile, "--base", "main", "--head", "factory/1-x", "--repo", repo]
        code, out, _ = self.run_cli("diff-match", "--key", "risk_globs", *common)
        self.assertEqual((code, out.strip()), (10, ".github/workflows/ci.yml"))
        self.assertEqual(self.run_cli("diff-match", "--key", "ui_globs", *common)[0], 0)


if __name__ == "__main__":
    unittest.main()
