"""Tests for tools/marketplace-regen.sh, the only code that can rewrite `main`.

Drives the real script against a real temporary bare remote via subprocess. The
script does `reset --hard`, `git add -A`, `commit` and `push`, and every claim in
its comment block was previously asserted in prose and verified nowhere.

The case that matters most is `test_catalog_only_change_with_no_fragments`: after
the first reconcile consumes the fragments, that is this repo's steady state, and
it is the exact shape that a naive `git add -- <pathspec that matches nothing>`
aborts on with exit 128 under `set -e`.

unittest + stdlib only, like the rest of tools/. Skipped where git or bash is
missing.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SCRIPT = TOOLS / "marketplace-regen.sh"
CATALOG = ".claude-plugin/marketplace.json"

_HAVE_TOOLS = bool(shutil.which("git")) and bool(shutil.which("bash"))


def _env() -> dict:
    """Isolate git from the developer's global/system config and identity."""
    env = dict(os.environ)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "REGEN_ATTEMPTS": "2",
            "REGEN_RETRY_SLEEP": "0",
        }
    )
    return env


@unittest.skipUnless(_HAVE_TOOLS, "needs git and bash on PATH")
class RegenScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.origin = self.root / "origin.git"
        self.seed = self.root / "seed"
        self.ci = self.root / "ci"
        self.env = _env()

        self.git("init", "-q", "--bare", "-b", "main", str(self.origin), cwd=self.root)
        self.git("clone", "-q", str(self.origin), str(self.seed), cwd=self.root)
        self.git("config", "user.name", "t", cwd=self.seed)
        self.git("config", "user.email", "t@t", cwd=self.seed)

    # --- helpers ------------------------------------------------------------

    def git(self, *args: str, cwd: Path) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"git {' '.join(args)} failed:\n{proc.stderr}")
        return proc.stdout

    def write_repo(self, *, with_fragment: bool, version: str = "0.1.0") -> None:
        """Seed the remote with the tooling, one plugin, and a matching catalog."""
        (self.seed / "tools").mkdir(parents=True, exist_ok=True)
        for name in ("marketplace.py", "marketplace-regen.sh"):
            shutil.copy2(TOOLS / name, self.seed / "tools" / name)
        os.chmod(self.seed / "tools" / "marketplace-regen.sh", 0o755)

        claude = self.seed / "plug" / ".claude-plugin"
        claude.mkdir(parents=True, exist_ok=True)
        (claude / "plugin.json").write_text(
            json.dumps({"name": "plug", "version": version}), encoding="utf-8"
        )
        if with_fragment:
            (claude / "marketplace-entry.json").write_text(
                json.dumps({"category": "Engineering", "description": "a plugin"}),
                encoding="utf-8",
            )

        entry = {
            "name": "plug",
            "source": "./plug",
            "description": "a plugin",
            "version": version,
            "category": "Engineering",
        }
        catalog = {
            "name": "test-marketplace",
            "owner": {"name": "t"},
            # A fragment means the catalog is deliberately stale until reconciled.
            "plugins": [] if with_fragment else [entry],
        }
        path = self.seed / CATALOG
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        self.git("add", "-A", cwd=self.seed)
        self.git("commit", "-q", "-m", "seed", cwd=self.seed)
        self.git("push", "-q", "origin", "main", cwd=self.seed)

        self.git("clone", "-q", str(self.origin), str(self.ci), cwd=self.root)
        self.git("config", "user.name", "t", cwd=self.ci)
        self.git("config", "user.email", "t@t", cwd=self.ci)

    def run_script(self, expect_ok: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["bash", "tools/marketplace-regen.sh"],
            cwd=str(self.ci),
            env=self.env,
            capture_output=True,
            text=True,
        )
        if expect_ok:
            self.assertEqual(
                proc.returncode, 0, f"script failed:\n{proc.stdout}\n{proc.stderr}"
            )
        return proc

    def remote_tip(self) -> str:
        return self.git("rev-parse", "main", cwd=self.origin).strip()

    def remote_tree(self) -> list:
        return self.git("ls-tree", "-r", "--name-only", "main", cwd=self.origin).split()

    def remote_catalog(self) -> dict:
        return json.loads(self.git("show", "main:" + CATALOG, cwd=self.origin))

    # --- the cases ----------------------------------------------------------

    def test_catalog_only_change_with_no_fragments(self) -> None:
        """A version bump with zero fragments must still reach the catalog.

        Regression for two bugs at once: `git add` exits 128 on a pathspec that
        matches nothing (so the script aborted under `set -e` once the fragments
        were consumed), and derived fields must be refreshed even with no fragment
        present, or version bumps silently stop reaching the catalog -- the exact
        drift this feature exists to prevent.
        """
        self.write_repo(with_fragment=False)
        self.assertEqual(
            [f for f in self.remote_tree() if "marketplace-entry" in f],
            [],
            "precondition: no fragments in the tree",
        )
        manifest = self.seed / "plug" / ".claude-plugin" / "plugin.json"
        manifest.write_text(
            json.dumps({"name": "plug", "version": "0.2.0"}), encoding="utf-8"
        )
        self.git("commit", "-q", "-am", "bump to 0.2.0", cwd=self.seed)
        self.git("push", "-q", "origin", "main", cwd=self.seed)

        before = self.remote_tip()
        proc = self.run_script()

        self.assertNotEqual(self.remote_tip(), before, "expected a reconcile commit")
        self.assertIn("updated ./plug", proc.stdout)
        self.assertEqual(self.remote_catalog()["plugins"][0]["version"], "0.2.0")

    def test_folds_fragment_and_deletes_it(self) -> None:
        self.write_repo(with_fragment=True)
        before = self.remote_tip()

        self.run_script()

        self.assertNotEqual(self.remote_tip(), before)
        self.assertEqual(
            [f for f in self.remote_tree() if "marketplace-entry" in f],
            [],
            "the fragment must be deleted from the pushed tree",
        )
        plugins = self.remote_catalog()["plugins"]
        self.assertEqual([p["name"] for p in plugins], ["plug"])
        self.assertEqual(plugins[0]["category"], "Engineering")
        subject = self.git("log", "-1", "--pretty=%s", "main", cwd=self.origin)
        self.assertIn("[skip ci]", subject)

    def test_steady_state_makes_no_commit(self) -> None:
        """No fragments and a current catalog: the bot must not commit at all."""
        self.write_repo(with_fragment=False)
        before = self.remote_tip()

        proc = self.run_script()

        self.assertIn("already up to date", proc.stdout)
        self.assertEqual(self.remote_tip(), before, "must not push an empty reconcile")

    def _install_pre_receive(self, script: str) -> None:
        hook = self.origin / "hooks" / "pre-receive"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text(script, encoding="utf-8")
        os.chmod(hook, 0o755)

    def test_retries_a_rejected_push(self) -> None:
        """A losable race: reject once, succeed on the retry."""
        self.write_repo(with_fragment=True)
        counter = self.root / "reject-count"
        self._install_pre_receive(
            "#!/bin/sh\n"
            f'c="{counter}"\n'
            'n=$(cat "$c" 2>/dev/null || echo 0)\n'
            'echo $((n + 1)) > "$c"\n'
            '[ "$n" -ge 1 ] && exit 0\n'
            'echo "rejecting once" >&2\n'
            "exit 1\n"
        )

        proc = self.run_script()

        self.assertIn("attempt 2", proc.stdout)
        self.assertEqual([p["name"] for p in self.remote_catalog()["plugins"]], ["plug"])

    def test_permission_failure_fails_fast_without_retrying(self) -> None:
        """A 403/protected-branch refusal is not a race; say so and stop."""
        self.write_repo(with_fragment=True)
        self._install_pre_receive(
            '#!/bin/sh\necho "remote: permission to push denied (403)" >&2\nexit 1\n'
        )

        proc = self.run_script(expect_ok=False)

        self.assertNotEqual(proc.returncode, 0)
        combined = proc.stdout + proc.stderr
        self.assertIn("Workflow permissions", combined)
        self.assertNotIn("attempt 2", proc.stdout, "must not retry a permissions refusal")


if __name__ == "__main__":
    unittest.main()
