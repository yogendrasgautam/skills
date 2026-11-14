"""Unit tests for the PreToolUse guard hook."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "..", "hooks", "guard.py")
sys.path.insert(0, os.path.dirname(GUARD))
import guard  # noqa: E402

SHA = "a" * 40


class CheckTest(unittest.TestCase):
    def blocked(self, cmd, agent=True):
        return guard.check(cmd, agent) is not None

    def test_push_to_main(self):
        for cmd in ("git push origin main", "git push -u origin main",
                    "git -C .worktrees/1-x push origin HEAD:main",
                    "cd x && git push origin +factory/1-x:refs/heads/main",
                    "git push origin master"):
            self.assertTrue(self.blocked(cmd), cmd)

    def test_branch_push_allowed(self):
        for cmd in ("git -C .worktrees/1-x push -u origin factory/1-x",
                    "git push --force-with-lease", "git push origin factory/1-main-page",
                    "git push origin factory-evidence", "git log main..factory/1-x"):
            self.assertFalse(self.blocked(cmd), cmd)

    def test_force_and_no_verify(self):
        for cmd in ("git push --force", "git push -f origin factory/1-x",
                    "git commit --no-verify -m x", "git commit -n -m x",
                    "git push --no-verify origin factory/1-x"):
            self.assertTrue(self.blocked(cmd), cmd)

    def test_agents_never_merge(self):
        cmd = "gh pr merge 5 --squash --delete-branch --match-head-commit " + SHA
        self.assertTrue(self.blocked(cmd, agent=True))
        self.assertFalse(self.blocked(cmd, agent=False))

    def test_orchestrator_merge_must_be_pinned(self):
        self.assertTrue(self.blocked("gh pr merge 5 --squash --delete-branch", agent=False))
        self.assertTrue(self.blocked("gh pr merge 5 --merge --match-head-commit " + SHA, agent=False))
        self.assertTrue(self.blocked(
            "gh pr merge 5 --squash --admin --match-head-commit " + SHA, agent=False))

    def test_conflicts_resolved_by_intent(self):
        for cmd in ("git checkout --ours src/a.py", "git -C .worktrees/1-x checkout --theirs .",
                    "git restore --theirs src/a.py", "git rebase -X theirs origin/main",
                    "git rebase -Xours origin/main", "git merge -s ours origin/main",
                    "git pull --strategy-option=theirs", "git rebase --skip"):
            self.assertTrue(self.blocked(cmd), cmd)
        for cmd in ("git rebase origin/main", "git rebase --continue", "git rebase --abort",
                    "git checkout factory/1-x", "git log -p origin/main -- src/a.py",
                    "git rerere status"):
            self.assertFalse(self.blocked(cmd), cmd)

    def test_api_bypass(self):
        self.assertTrue(self.blocked("gh api -X PUT repos/o/r/pulls/5/merge"))
        self.assertTrue(self.blocked("gh api -X DELETE repos/o/r/branches/main/protection"))
        self.assertFalse(self.blocked("gh api repos/o/r/branches/main/protection"))
        self.assertFalse(self.blocked("gh pr view 5 --json state"))


class ScopeTest(unittest.TestCase):
    def run_hook(self, payload, project=None):
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        if project:
            env["CLAUDE_PROJECT_DIR"] = project
        p = subprocess.run([sys.executable, GUARD], input=json.dumps(payload), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return p.returncode, p.stderr

    def payload(self, cmd, **extra):
        d = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/nonexistent"}
        d.update(extra)
        return d

    def test_out_of_scope_session_untouched(self):
        self.assertEqual(self.run_hook(self.payload("git push origin main"))[0], 0)
        self.assertEqual(self.run_hook(self.payload("git push origin main", agent_type="other:builder"))[0], 0)

    def test_factory_agent_blocked(self):
        code, err = self.run_hook(self.payload("git push origin main", agent_type="software-factory:builder"))
        self.assertEqual(code, 2)
        self.assertIn("software-factory guard", err)

    def test_main_session_blocked_only_during_a_run(self):
        with tempfile.TemporaryDirectory() as proj:
            self.assertEqual(self.run_hook(self.payload("gh pr merge 5 --squash"), proj)[0], 0)
            os.makedirs(os.path.join(proj, "factory", "run.lock"))
            self.assertEqual(self.run_hook(self.payload("gh pr merge 5 --squash"), proj)[0], 2)

    def test_fails_open_on_garbage(self):
        p = subprocess.run([sys.executable, GUARD], input="not json", stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(p.returncode, 0)

    def test_hooks_json_points_at_guard(self):
        with open(os.path.join(os.path.dirname(GUARD), "hooks.json")) as f:
            cfg = json.load(f)
        entry = cfg["hooks"]["PreToolUse"][0]
        self.assertEqual(entry["matcher"], "Bash")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/guard.py", entry["hooks"][0]["command"])


if __name__ == "__main__":
    unittest.main()
