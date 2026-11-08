"""Tests for the generated marketplace catalog (tools/marketplace.py).

Run with `make test`, i.e. `python3 -m unittest discover -s tools -p 'test_*.py'`.
Deliberately unittest, not pytest: the system interpreter has no pytest, and the
whole point of this tooling is that it needs no installs.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import marketplace  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)

    # --- fixtures -----------------------------------------------------------

    def write_catalog(self, plugins: list) -> Path:
        path = self.repo / ".claude-plugin" / "marketplace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"name": "engineering-skills", "owner": {"name": "Test"}, "plugins": plugins}
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path

    def write_plugin(
        self,
        source: str,
        name: str,
        version: str = "0.1.0",
        fragment: dict | None = None,
    ) -> Path | None:
        """Create a plugin manifest at ``source`` and optionally its fragment."""
        plugin_dir = marketplace._plugin_dir_for(self.repo, source)
        claude_dir = plugin_dir / ".claude-plugin"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "plugin.json").write_text(
            json.dumps({"name": name, "version": version}), encoding="utf-8"
        )
        if fragment is None:
            return None
        frag_path = claude_dir / marketplace.FRAGMENT_NAME
        frag_path.write_text(json.dumps(fragment), encoding="utf-8")
        return frag_path

    def entry(self, name: str = "", version: str = "0.1.0", source: str = "./x") -> dict:
        # Shaped like a real generated entry, `category` included -- lint flags a
        # live plugin whose entry has lost its curated category.
        return {
            "name": name or "x",
            "source": source,
            "description": "d",
            "version": version,
            "category": "Engineering",
        }

    # --- reads --------------------------------------------------------------

    @property
    def catalog_path(self) -> Path:
        return self.repo / ".claude-plugin" / "marketplace.json"

    def entries(self) -> list:
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))["plugins"]


class TestSourceDerivation(_Base):
    def test_root_fragment_yields_dot_slash(self) -> None:
        """The repo root is itself a plugin; its source must be "./", not "./.".

        A fragment at the top-level .claude-plugin/ sits beside the catalog, so
        this also proves the discovery glob matches at depth 0.
        """
        self.write_catalog([])
        self.write_plugin(
            "./",
            "engineering-pipeline",
            fragment={"category": "Engineering", "description": "The pipeline."},
        )

        result = marketplace.apply(self.repo)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.added, ["./"])
        self.assertEqual(self.entries()[0]["source"], "./")

    def test_subdir_fragment_yields_relative_source(self) -> None:
        self.write_catalog([])
        self.write_plugin(
            "./diagram-studio",
            "diagram-studio",
            version="0.1.1",
            fragment={"category": "Engineering", "description": "Diagrams."},
        )

        result = marketplace.apply(self.repo)

        self.assertEqual(result.added, ["./diagram-studio"])
        self.assertEqual(self.entries()[0]["source"], "./diagram-studio")

    def test_entry_key_order_is_stable(self) -> None:
        self.write_catalog([])
        self.write_plugin(
            "./p", "p", fragment={"category": "Data", "description": "d"}
        )

        marketplace.apply(self.repo)

        self.assertEqual(
            list(self.entries()[0].keys()),
            ["name", "source", "description", "version", "category"],
        )

    def test_unnormalized_existing_source_upserts_not_duplicates(self) -> None:
        """A hand-written "." or trailing slash must match the derived source."""
        for written in (".", "./", ""):
            with self.subTest(written=written):
                self.setUp()
                self.write_catalog(
                    [
                        {
                            "name": "engineering-pipeline",
                            "source": written,
                            "description": "old",
                            "version": "0.1.0",
                        }
                    ]
                )
                self.write_plugin(
                    "./",
                    "engineering-pipeline",
                    version="0.2.0",
                    fragment={"category": "Engineering", "description": "new"},
                )

                result = marketplace.apply(self.repo)

                self.assertEqual(result.errors, [])
                self.assertEqual(result.added, [])
                self.assertEqual(len(self.entries()), 1, "should upsert, not append")
                self.assertEqual(self.entries()[0]["description"], "new")

    def test_trailing_slash_source_upserts_not_duplicates(self) -> None:
        self.write_catalog(
            [
                {
                    "name": "diagram-studio",
                    "source": "./diagram-studio/",
                    "description": "old",
                    "version": "0.1.0",
                }
            ]
        )
        self.write_plugin(
            "./diagram-studio",
            "diagram-studio",
            fragment={"category": "Engineering", "description": "new"},
        )

        marketplace.apply(self.repo)

        self.assertEqual(len(self.entries()), 1)


class TestDerivedVersion(_Base):
    def test_version_comes_from_the_manifest(self) -> None:
        self.write_catalog([self.entry("p", version="0.1.0", source="./p")])
        self.write_plugin(
            "./p", "p", version="9.9.9", fragment={"category": "Data", "description": "d"}
        )

        marketplace.apply(self.repo)

        self.assertEqual(self.entries()[0]["version"], "9.9.9")

    def test_version_refreshes_with_no_fragment_present(self) -> None:
        """The post-bootstrap steady state: fragments are consumed, bumps still land.

        Without this the generator would re-create exactly the drift it exists to
        prevent (catalog 0.1.0 vs plugin.json 0.1.1).
        """
        self.write_catalog([self.entry("p", version="0.1.0", source="./p")])
        self.write_plugin("./p", "p", version="0.1.1")  # no fragment

        result = marketplace.apply(self.repo)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.updated, ["./p"])
        self.assertEqual(self.entries()[0]["version"], "0.1.1")

    def test_refresh_leaves_curated_fields_alone(self) -> None:
        self.write_catalog(
            [
                {
                    "name": "p",
                    "source": "./p",
                    "description": "curated",
                    "version": "0.1.0",
                    "category": "Data",
                }
            ]
        )
        self.write_plugin("./p", "p", version="0.2.0")

        marketplace.apply(self.repo)

        entry = self.entries()[0]
        self.assertEqual(entry["description"], "curated")
        self.assertEqual(entry["category"], "Data")
        self.assertEqual(entry["version"], "0.2.0")


class TestIdempotenceAndFormat(_Base):
    def test_apply_twice_is_a_no_op(self) -> None:
        self.write_catalog([])
        self.write_plugin("./p", "p", fragment={"category": "Data", "description": "d"})
        marketplace.apply(self.repo)
        before = self.catalog_path.read_bytes()

        result = marketplace.apply(self.repo)

        self.assertEqual(result.added, [])
        self.assertEqual(result.updated, [])
        self.assertFalse(result.root_changed)
        self.assertEqual(self.catalog_path.read_bytes(), before)

    def test_preserves_unicode_and_formatting(self) -> None:
        self.write_catalog([])
        self.write_plugin(
            "./p",
            "p",
            fragment={"category": "Data", "description": "em—dash and café →"},
        )

        marketplace.apply(self.repo)

        text = self.catalog_path.read_text(encoding="utf-8")
        self.assertIn("em—dash and café →", text)
        self.assertTrue(text.endswith("\n"))
        self.assertIn("\n  ", text)

    def test_preserves_top_level_keys(self) -> None:
        self.write_catalog([])
        self.write_plugin("./p", "p", fragment={"category": "Data", "description": "d"})

        marketplace.apply(self.repo)

        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "engineering-skills")
        self.assertEqual(data["owner"], {"name": "Test"})

    def test_real_catalog_round_trips_byte_identically(self) -> None:
        """Locks indent=2 + ensure_ascii=False + trailing newline against the real file.

        The committed catalog contains non-ASCII, so a stray ensure_ascii default
        would rewrite the whole file on the next regen.
        """
        path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(marketplace._dump_catalog(json.loads(text)), text)


class TestPrune(_Base):
    def test_prunes_entry_when_manifest_disappears(self) -> None:
        self.write_catalog(
            [
                self.entry("stay", source="./stay"),
                self.entry("gone", source="./gone"),
            ]
        )
        self.write_plugin("./stay", "stay")

        result = marketplace.apply(self.repo)

        self.assertEqual(result.pruned, ["./gone"])
        self.assertEqual([e["name"] for e in self.entries()], ["stay"])

    def test_prunes_dir_that_exists_but_is_no_longer_a_plugin(self) -> None:
        """Liveness is "has a plugin.json", not "the directory exists"."""
        self.write_catalog(
            [
                self.entry("stay", source="./stay"),
                self.entry("husk", source="./husk"),
            ]
        )
        self.write_plugin("./stay", "stay")
        (self.repo / "husk").mkdir()  # dir exists, no manifest

        result = marketplace.apply(self.repo)

        self.assertEqual(result.pruned, ["./husk"])

    def test_root_plugin_moved_to_subdir_does_not_collide(self) -> None:
        """Regression: an is_dir() liveness check made this a dead end.

        The root's directory always exists, so the stale "./" entry looked live and
        hard-failed the name-uniqueness check against the moved plugin.
        """
        self.write_catalog(
            [
                self.entry("engineering-pipeline", source="./"),
                self.entry("keep", source="./keep"),
            ]
        )
        self.write_plugin("./keep", "keep")
        self.write_plugin(
            "./engineering-pipeline",
            "engineering-pipeline",
            fragment={"category": "Engineering", "description": "moved"},
        )

        self.assertEqual(marketplace.lint(self.repo), [])
        result = marketplace.apply(self.repo)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.pruned, ["./"])
        self.assertEqual(
            sorted(e["source"] for e in self.entries()),
            ["./engineering-pipeline", "./keep"],
        )

    def test_guard_refuses_to_prune_every_entry(self) -> None:
        self.write_catalog(
            [self.entry("a", source="./a"), self.entry("b", source="./b")]
        )
        self.write_plugin("./c", "c")  # a manifest exists, so not a "bad checkout"
        before = self.catalog_path.read_bytes()

        result = marketplace.apply(self.repo)

        self.assertEqual(len(result.errors), 1)
        self.assertIn("refusing to prune every entry", str(result.errors[0]))
        self.assertEqual(self.catalog_path.read_bytes(), before)

    def test_guard_refuses_when_no_manifests_anywhere(self) -> None:
        self.write_catalog(
            [
                self.entry("a", source="./a"),
                self.entry("b", source="./b"),
                self.entry("c", source="./c"),
            ]
        )
        before = self.catalog_path.read_bytes()

        result = marketplace.apply(self.repo)

        self.assertEqual(len(result.errors), 1)
        self.assertIn("no plugin manifests found", str(result.errors[0]))
        self.assertEqual(self.catalog_path.read_bytes(), before)

    def test_never_prunes_an_externally_hosted_entry(self) -> None:
        """An object `source` has no local directory; it must survive a reconcile.

        This is what the isinstance(str) guards in apply() are actually for -- a
        "simplification" that dropped them would silently delete every third-party
        entry on the next run.
        """
        external = {"name": "ext", "source": {"source": "github", "repo": "o/n"}}
        self.write_catalog([external, self.entry("stay", source="./stay")])
        self.write_plugin("./stay", "stay")

        result = marketplace.apply(self.repo)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.pruned, [])
        self.assertIn(external, self.entries())

    def test_force_prune_overrides_the_guard(self) -> None:
        self.write_catalog([self.entry("a", source="./a")])

        result = marketplace.apply(self.repo, force_prune=True)

        self.assertEqual(result.errors, [])
        self.assertEqual(result.pruned, ["./a"])
        self.assertEqual(self.entries(), [])


class TestCheckMode(_Base):
    def test_check_reports_without_writing(self) -> None:
        self.write_catalog([])
        frag = self.write_plugin(
            "./p", "p", fragment={"category": "Data", "description": "d"}
        )
        before = self.catalog_path.read_bytes()

        result = marketplace.apply(self.repo, delete_fragments=True, check=True)

        self.assertTrue(result.root_changed)
        self.assertTrue(result.would_change())
        self.assertEqual(self.catalog_path.read_bytes(), before)
        assert frag is not None
        self.assertTrue(frag.exists(), "check must not delete fragments")

    def test_check_is_quiet_when_up_to_date(self) -> None:
        self.write_catalog([])
        marketplace.apply(self.repo)

        result = marketplace.apply(self.repo, check=True)

        self.assertFalse(result.would_change())

    def test_cli_exit_codes(self) -> None:
        self.write_catalog([])
        self.write_plugin("./p", "p", fragment={"category": "Data", "description": "d"})
        root = ["--repo-root", str(self.repo)]

        def run(argv: list) -> int:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                return marketplace.main(argv + root)

        self.assertEqual(run(["apply", "--check"]), marketplace.EXIT_WOULD_CHANGE)
        self.assertEqual(run(["apply"]), 0)
        self.assertEqual(run(["apply", "--check"]), 0)
        self.assertEqual(run(["lint"]), 0)

    def test_cli_gate_signal_for_ci(self) -> None:
        """`apply --check --delete-fragments` is the CI gate; exit 2 means "reconcile".

        The marketplace workflow decides whether to run the regen job from this one
        exit code, so it must report BOTH kinds of pending work. Plain `--check` is
        deliberately not enough: a fragment that is already folded in leaves the
        catalog unchanged, yet regen still has to consume it.
        """
        self.write_catalog([])
        self.write_plugin("./p", "p", fragment={"category": "Data", "description": "d"})
        root = ["--repo-root", str(self.repo)]

        def run(argv: list) -> int:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                return marketplace.main(argv + root)

        # Folded but not consumed: the catalog is current, the fragment is not.
        self.assertEqual(run(["apply"]), 0)
        self.assertEqual(run(["apply", "--check"]), 0)
        self.assertEqual(
            run(["apply", "--check", "--delete-fragments"]),
            marketplace.EXIT_WOULD_CHANGE,
            "a lingering fragment must still schedule a reconcile",
        )

        # Consumed: steady state, and the gate must stay quiet.
        self.assertEqual(run(["apply", "--delete-fragments"]), 0)
        self.assertEqual(run(["apply", "--check", "--delete-fragments"]), 0)

        # Catalog drift with no fragment anywhere (a plugin.json version bump) must
        # schedule a reconcile too, otherwise the bump never reaches the catalog.
        self.write_plugin("./p", "p", version="0.2.0")
        self.assertEqual(
            run(["apply", "--check", "--delete-fragments"]),
            marketplace.EXIT_WOULD_CHANGE,
        )


class TestFragmentDeletion(_Base):
    def test_fragments_are_removed_after_folding(self) -> None:
        self.write_catalog([])
        root_frag = self.write_plugin(
            "./", "engineering-pipeline", fragment={"category": "Engineering", "description": "p"}
        )
        sub_frag = self.write_plugin(
            "./diagram-studio",
            "diagram-studio",
            fragment={"category": "Engineering", "description": "d"},
        )

        result = marketplace.apply(self.repo, delete_fragments=True)

        assert root_frag is not None and sub_frag is not None
        self.assertFalse(root_frag.exists(), "the ROOT fragment must be deleted too")
        self.assertFalse(sub_frag.exists())
        self.assertEqual(len(result.deleted_fragments), 2)


class TestUncataloguedPlugins(_Base):
    """A live plugin with neither an entry nor a fragment must not pass silently.

    apply() can never fix this one: it only upserts from fragments and refreshes or
    prunes entries that already exist, and `category`/`description` are curated, so
    the entry cannot be derived. Without this rule a new plugin -- or one whose entry
    a hand edit deleted -- is simply invisible in the marketplace, on green CI.
    """

    def test_plugin_with_neither_entry_nor_fragment_is_flagged(self) -> None:
        self.write_catalog([])
        self.write_plugin("./newplug", "newplug")

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        message = str(errors[0])
        self.assertIn("./newplug", message)
        self.assertIn(marketplace.FRAGMENT_NAME, message)

    def test_hand_edit_that_drops_a_live_entry_is_flagged(self) -> None:
        """The same hole from the other side: the entry was there and got deleted."""
        self.write_catalog([self.entry("keep", source="./keep")])
        self.write_plugin("./keep", "keep")
        self.write_plugin("./dropped", "dropped")

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("./dropped", str(errors[0]))

    def test_fragment_without_an_entry_yet_is_not_flagged(self) -> None:
        """The normal pre-`make marketplace` state; apply --check reports that."""
        self.write_catalog([])
        self.write_plugin(
            "./p", "p", fragment={"category": "Data", "description": "d"}
        )

        self.assertEqual(marketplace.lint(self.repo), [])

    def test_entry_without_a_fragment_is_not_flagged(self) -> None:
        """The steady state: fragments are consumed by the reconcile."""
        self.write_catalog([self.entry("p", source="./p")])
        self.write_plugin("./p", "p")

        self.assertEqual(marketplace.lint(self.repo), [])

    def test_invalid_fragment_does_not_also_report_uncatalogued(self) -> None:
        """One broken file, one error -- not a second, misleading one."""
        self.write_catalog([])
        self.write_plugin("./p", "p", fragment={"category": "Nope", "description": "d"})

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("category", str(errors[0]))

    def test_root_plugin_is_matched_through_the_source_key(self) -> None:
        """A root plugin's entry may be written "." or "./"; neither is uncatalogued."""
        self.write_catalog([self.entry("root", source=".")])
        self.write_plugin("./", "root")

        self.assertEqual(marketplace.lint(self.repo), [])

    def test_cli_exits_invalid(self) -> None:
        self.write_catalog([])
        self.write_plugin("./newplug", "newplug")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            rc = marketplace.main(["lint", "--repo-root", str(self.repo)])

        self.assertEqual(rc, marketplace.EXIT_INVALID)


class TestLint(_Base):
    def _lint_one(self, fragment: dict) -> str:
        self.write_catalog([])
        self.write_plugin("./p", "p", fragment=fragment)
        errors = marketplace.lint(self.repo)
        self.assertEqual(len(errors), 1)
        return str(errors[0])

    def test_rejects_bad_fragments(self) -> None:
        cases = [
            ({"category": "engineering", "description": "d"}, "category"),
            ({"category": "Nope", "description": "d"}, "category"),
            ({"description": "d"}, "category"),
            ({"category": "Data", "description": "  "}, "description"),
            ({"category": "Data"}, "description"),
        ]
        for fragment, expected in cases:
            with self.subTest(fragment=fragment):
                self.setUp()
                self.assertIn(expected, self._lint_one(fragment))

    def test_rejects_manifest_without_version(self) -> None:
        self.write_catalog([])
        claude_dir = self.repo / "p" / ".claude-plugin"
        claude_dir.mkdir(parents=True)
        (claude_dir / "plugin.json").write_text(json.dumps({"name": "p"}), encoding="utf-8")
        (claude_dir / marketplace.FRAGMENT_NAME).write_text(
            json.dumps({"category": "Data", "description": "d"}), encoding="utf-8"
        )

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("'version'", str(errors[0]))

    def test_rejects_non_string_version(self) -> None:
        self.write_catalog([])
        claude_dir = self.repo / "p" / ".claude-plugin"
        claude_dir.mkdir(parents=True)
        (claude_dir / "plugin.json").write_text(
            json.dumps({"name": "p", "version": 1.0}), encoding="utf-8"
        )
        (claude_dir / marketplace.FRAGMENT_NAME).write_text(
            json.dumps({"category": "Data", "description": "d"}), encoding="utf-8"
        )

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("'version'", str(errors[0]))

    def test_rejects_fragment_without_plugin_manifest(self) -> None:
        self.write_catalog([])
        claude_dir = self.repo / "orphan" / ".claude-plugin"
        claude_dir.mkdir(parents=True)
        (claude_dir / marketplace.FRAGMENT_NAME).write_text(
            json.dumps({"category": "Data", "description": "d"}), encoding="utf-8"
        )

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("plugin manifest", str(errors[0]))

    def test_rejects_name_collision_with_live_plugin(self) -> None:
        self.write_catalog([self.entry("dup", source="./dup")])
        self.write_plugin("./dup", "dup")
        self.write_plugin(
            "./other", "dup", fragment={"category": "Data", "description": "d"}
        )

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("unique", str(errors[0]))

    def test_rejects_duplicate_catalog_sources(self) -> None:
        self.write_catalog(
            [self.entry("a", source="./a"), self.entry("a2", source="./a/")]
        )
        self.write_plugin("./a", "a")

        errors = marketplace.lint(self.repo)

        self.assertTrue(any("duplicate catalog entries" in str(e) for e in errors))

    def test_passes_with_no_fragments(self) -> None:
        self.write_catalog([])
        self.assertEqual(marketplace.lint(self.repo), [])

    def test_reports_missing_catalog(self) -> None:
        """lint and apply must agree: neither can treat a missing catalog as empty."""
        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("not found", str(errors[0]))

    def test_reports_malformed_catalog(self) -> None:
        path = self.repo / ".claude-plugin" / "marketplace.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("invalid JSON", str(errors[0]))

    def test_reports_entry_without_source(self) -> None:
        """Sourceless entries are invisible to every guard in apply(); flag them."""
        self.write_catalog([{"name": "x", "description": "d", "version": "0.1.0"}])

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("no 'source'", str(errors[0]))

    def test_reports_non_object_entry(self) -> None:
        self.write_catalog(["just a string"])

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("not an object", str(errors[0]))

    def test_reports_live_entry_that_lost_its_category(self) -> None:
        self.write_catalog(
            [{"name": "p", "source": "./p", "description": "d", "version": "0.1.0"}]
        )
        self.write_plugin("./p", "p")

        errors = marketplace.lint(self.repo)

        self.assertEqual(len(errors), 1)
        self.assertIn("no 'category'", str(errors[0]))

    def test_allows_externally_hosted_entry_with_object_source(self) -> None:
        """An object `source` is a plugin hosted elsewhere -- not ours to validate."""
        self.write_catalog(
            [
                {"name": "ext", "source": {"source": "github", "repo": "o/n"}},
                self.entry("local", source="./local"),
            ]
        )
        self.write_plugin("./local", "local")

        self.assertEqual(marketplace.lint(self.repo), [])

    def test_skips_noise_directories(self) -> None:
        """A fragment inside .git or an unpacked artifact must not be discovered."""
        self.write_catalog([])
        for noise in (".git", "__MACOSX", "node_modules"):
            claude_dir = self.repo / noise / "copy" / ".claude-plugin"
            claude_dir.mkdir(parents=True)
            (claude_dir / "plugin.json").write_text(
                json.dumps({"name": "copy", "version": "0.1.0"}), encoding="utf-8"
            )
            (claude_dir / marketplace.FRAGMENT_NAME).write_text(
                json.dumps({"category": "Data", "description": "d"}), encoding="utf-8"
            )

        fragments, errors = marketplace.discover_fragments(self.repo)

        self.assertEqual(fragments, [])
        self.assertEqual(errors, [])

    def test_allowed_categories_cover_expected_values(self) -> None:
        self.assertLessEqual(
            {"Engineering", "Product", "Data", "Other"}, marketplace.ALLOWED_CATEGORIES
        )


if __name__ == "__main__":
    unittest.main()
