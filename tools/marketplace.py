#!/usr/bin/env python3
"""Generate the root ``marketplace.json`` catalog from per-plugin fragments.

The root ``.claude-plugin/marketplace.json`` is a *generated* catalog. Nobody
should edit it directly: one hand-maintained array means every change appends an
entry at the same spot, so two changes in flight collide, and the catalog quietly
drifts from the plugin manifests it is supposed to describe.

Instead each plugin ships a transient *fragment* at
``<plugin>/.claude-plugin/marketplace-entry.json`` carrying only its curated
catalog fields::

    { "category": "Engineering", "description": "<catalog-facing description>" }

A change adds (or, for a delete, removes) files only inside its own plugin
directory, so two changes can never conflict. After the PR merges to ``main``,
the ``marketplace-regen`` workflow runs :func:`apply` with
``delete_fragments=True``:

- **refresh** the derived fields (``name``, ``version``) of every surviving entry
  from its ``plugin.json`` -- fragments are consumed, so without this a later
  version bump could never reach the catalog again;
- **upsert** each fragment's entry into the catalog (match by ``source``; replace
  in place if present, else append) -- order is preserved, never re-sorted;
- **prune** any entry whose plugin is gone (this is how a delete or a move takes
  effect), guarded against wiping the catalog from a broken checkout;
- **delete** the merged fragment files.

Between reconciles, :func:`lint` holds the invariant the reconcile cannot restore
on its own: every live plugin must be described by a catalog entry or by a fragment
about to become one. A plugin added with neither is invisible in the marketplace,
and ``category``/``description`` are curated, so nothing can derive the missing
entry for it.

``name`` and ``version`` come from the sibling ``plugin.json`` and ``source`` from
the plugin's directory path, so the fragment holds only what cannot be derived:
the curated ``category`` and catalog ``description``.

A plugin may live at the repo root itself (``source: "./"``, a fragment in the
top-level ``.claude-plugin/`` beside the catalog); this repo had that arrangement
until ``engineering-pipeline`` moved into ``engineering-skills/``. Two consequences
are baked in and still hold: ``source`` for the root is ``"./"`` (not ``"./."``),
and liveness is decided by "does a ``plugin.json`` still live here", never by "does
this directory exist" -- the repo root always exists, so a directory check would
make a root entry permanently unprunable, and moving that plugin into a
subdirectory would collide with its own stale entry instead of relocating.

Stdlib only, and kept compatible with Python 3.9 (the system interpreter, where
``make marketplace`` runs) through 3.12+ (CI).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

FRAGMENT_NAME = "marketplace-entry.json"
_PLUGIN_MANIFEST = "plugin.json"
_CLAUDE_DIR = ".claude-plugin"
_ROOT_MANIFEST = (_CLAUDE_DIR, "marketplace.json")

# Directories the fragment walk must not descend into. pathlib's `**` happily
# enters hidden and vendored trees, and an unpacked build artifact can carry a
# whole second copy of a plugin -- which would then look like a duplicate.
_SKIP_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "__MACOSX",
        ".playwright-mcp",
    }
)

# The marketplace category vocabulary, Title Case and verbatim -- matches the list
# the share-playlist-plugin skill offers when publishing.
ALLOWED_CATEGORIES: frozenset = frozenset(
    {
        "Product",
        "Design",
        "Engineering",
        "Business Intelligence",
        "Security",
        "Research",
        "Marketing",
        "Sales",
        "Finance",
        "Data",
        "CX",
        "Support",
        "Other",
    }
)

# Exit codes: 1 = something is invalid, 2 = --check found work to do.
EXIT_INVALID = 1
EXIT_WOULD_CHANGE = 2


class MarketplaceError(ValueError):
    """A fragment or the root catalog is malformed, or a reconcile is unsafe."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


@dataclass(frozen=True)
class Fragment:
    """A validated per-plugin catalog fragment plus its derived entry fields."""

    path: Path  # the marketplace-entry.json file
    plugin_dir: Path  # the directory holding .claude-plugin/
    name: str  # from the sibling plugin.json
    source: str  # "./<repo-relative-posix>" of plugin_dir, or "./" for the root
    version: str  # from the sibling plugin.json
    category: str
    description: str

    def entry(self) -> dict:
        """The catalog entry, keyed in the same order as existing entries."""
        return {
            "name": self.name,
            "source": self.source,
            "description": self.description,
            "version": self.version,
            "category": self.category,
        }


@dataclass
class ApplyResult:
    added: list = field(default_factory=list)  # sources newly inserted
    updated: list = field(default_factory=list)  # sources replaced in place
    pruned: list = field(default_factory=list)  # sources removed (plugin gone)
    deleted_fragments: list = field(default_factory=list)
    root_changed: bool = False
    errors: list = field(default_factory=list)

    def would_change(self) -> bool:
        return bool(self.root_changed or self.deleted_fragments)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_string(manifest_data: object, key: str) -> str | None:
    """The non-empty string at ``key``, or None (a non-string is *not* accepted)."""
    if not isinstance(manifest_data, dict):
        return None
    value = manifest_data.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _source_for(plugin_dir: Path, repo_root: Path) -> str:
    """Catalog ``source`` for a plugin dir. The repo root is ``"./"``, not ``"./."``."""
    rel = plugin_dir.relative_to(repo_root).as_posix()
    return "./" if rel == "." else "./" + rel


def _source_key(source: str) -> str:
    """Canonical matching key for a ``source`` string.

    ``"./"``, ``"."`` and ``""`` all collapse to ``""`` (the repo root), and a
    trailing slash is insignificant, so a hand-written ``"./x/"`` upserts the same
    entry as a derived ``"./x"`` instead of silently appending a duplicate.
    """
    s = source.strip()
    if s in (".", "./"):
        return ""
    if s.startswith("./"):
        s = s[2:]
    return s.strip("/")


def _plugin_dir_for(repo_root: Path, source: str) -> Path:
    key = _source_key(source)
    return repo_root.joinpath(*key.split("/")) if key else repo_root


def _manifest_for(repo_root: Path, source: str) -> Path:
    return _plugin_dir_for(repo_root, source) / _CLAUDE_DIR / _PLUGIN_MANIFEST


def _is_live_plugin(repo_root: Path, source: str) -> bool:
    """A source is live when it still holds a plugin manifest.

    Deliberately not ``is_dir()``: see the module docstring on the root plugin.
    """
    return _manifest_for(repo_root, source).is_file()


def _skipped(path: Path, repo_root: Path) -> bool:
    return bool(_SKIP_DIRS & set(path.relative_to(repo_root).parts))


def _load_fragment(path: Path, repo_root: Path) -> Fragment:
    """Parse and validate one ``marketplace-entry.json``.

    Raises :class:`MarketplaceError` describing the first problem found.
    """
    try:
        data = _read_json(path)
    except json.JSONDecodeError as exc:
        raise MarketplaceError(path, f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise MarketplaceError(path, "must be a JSON object")

    category = data.get("category")
    if not isinstance(category, str) or not category.strip():
        raise MarketplaceError(path, "'category' is required and must be a non-empty string")
    if category not in ALLOWED_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_CATEGORIES))
        raise MarketplaceError(path, f"'category' {category!r} is not one of: {allowed}")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise MarketplaceError(path, "'description' is required and must be a non-empty string")

    plugin_dir = path.parent.parent
    manifest = plugin_dir / _CLAUDE_DIR / _PLUGIN_MANIFEST
    if not manifest.is_file():
        raise MarketplaceError(path, f"no sibling plugin manifest at {manifest}")
    try:
        manifest_data = _read_json(manifest)
    except json.JSONDecodeError as exc:
        raise MarketplaceError(manifest, f"invalid JSON: {exc}") from exc

    name = _manifest_string(manifest_data, "name")
    if name is None:
        raise MarketplaceError(manifest, "plugin manifest is missing a non-empty 'name'")
    version = _manifest_string(manifest_data, "version")
    if version is None:
        raise MarketplaceError(
            manifest, "plugin manifest is missing a non-empty 'version' string"
        )

    return Fragment(
        path=path,
        plugin_dir=plugin_dir,
        name=name,
        source=_source_for(plugin_dir, repo_root),
        version=version,
        category=category,
        description=description,
    )


def discover_fragments(repo_root: Path) -> tuple:
    """Every valid fragment under ``repo_root``, plus errors for invalid ones.

    Sorted by ``source`` for stable output. The glob also matches a fragment at
    the repo root, because the root directory *may* itself be a plugin -- this
    repo no longer has that arrangement; see the module docstring.

    Symlinked directories are not descended into (pathlib's recursive ``**``
    skips them on 3.9-3.12, and 3.13+ defaults ``recurse_symlinks=False``), so a
    symlinked plugin is silently invisible here.
    """
    repo_root = repo_root.resolve()
    fragments = []
    errors = []
    for path in sorted(repo_root.glob("**/" + _CLAUDE_DIR + "/" + FRAGMENT_NAME)):
        if _skipped(path, repo_root):
            continue
        try:
            fragments.append(_load_fragment(path, repo_root))
        except MarketplaceError as exc:
            errors.append(exc)
    fragments.sort(key=lambda f: f.source)
    return fragments, errors


def discover_plugin_sources(repo_root: Path) -> list:
    """Catalog ``source`` for every live plugin under ``repo_root``, sorted.

    The mirror image of :func:`discover_fragments`: that one finds what *wants* an
    entry, this one finds what *needs* one. Same skip list, and the same glob, so a
    plugin at the repo root is included as ``"./"``.
    """
    repo_root = repo_root.resolve()
    sources = []
    for path in sorted(repo_root.glob("**/" + _CLAUDE_DIR + "/" + _PLUGIN_MANIFEST)):
        if _skipped(path, repo_root):
            continue
        sources.append(_source_for(path.parent.parent, repo_root))
    sources.sort()
    return sources


def _has_any_plugin_manifest(repo_root: Path) -> bool:
    return bool(discover_plugin_sources(repo_root))


def _load_catalog(repo_root: Path) -> tuple:
    root_path = repo_root / _ROOT_MANIFEST[0] / _ROOT_MANIFEST[1]
    if not root_path.is_file():
        return None, MarketplaceError(root_path, "root marketplace.json not found")
    try:
        data = _read_json(root_path)
    except json.JSONDecodeError as exc:
        return None, MarketplaceError(root_path, f"invalid JSON: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
        return None, MarketplaceError(root_path, "must be an object with a 'plugins' array")
    return data, None


def _existing_entries(catalog: dict) -> list:
    return [e for e in catalog["plugins"] if isinstance(e, dict)]


def _entry_shape_errors(repo_root: Path, catalog: dict) -> list:
    """Catalog entries that would otherwise fail silently forever.

    An entry that is not an object, or has no usable ``source``, is skipped by
    every guard in :func:`apply`: it is never pruned, never counted toward the
    prune total, and never reported -- it just survives. And because a consumed
    fragment leaves only ``name``/``version`` being refreshed, an entry whose
    curated ``category`` was lost can never regain one on its own.

    A non-string ``source`` is fine (see the escape-hatch comment in
    :func:`apply`): an externally hosted plugin has an object there. Only a
    *missing* or *blank* source is wrong.
    """
    root_path = repo_root / _ROOT_MANIFEST[0] / _ROOT_MANIFEST[1]
    errors = []
    for i, entry in enumerate(catalog["plugins"]):
        if not isinstance(entry, dict):
            errors.append(MarketplaceError(root_path, f"plugins[{i}] is not an object"))
            continue
        if "source" not in entry:
            errors.append(MarketplaceError(root_path, f"plugins[{i}] has no 'source'"))
            continue
        source = entry["source"]
        if isinstance(source, str) and not source.strip():
            errors.append(MarketplaceError(root_path, f"plugins[{i}] has a blank 'source'"))
            continue
        # Only local plugins can have a category restored from a fragment, so only
        # flag those -- an externally hosted entry is not ours to fix.
        if (
            isinstance(source, str)
            and _is_live_plugin(repo_root, source)
            and not entry.get("category")
        ):
            errors.append(
                MarketplaceError(
                    root_path,
                    f"entry {source!r} has no 'category'; ship a "
                    f"{FRAGMENT_NAME} for it and run `make marketplace`",
                )
            )
    return errors


def _duplicate_sources(repo_root: Path, entries: list) -> list:
    """Two entries whose ``source`` normalizes to the same plugin."""
    root_path = repo_root / _ROOT_MANIFEST[0] / _ROOT_MANIFEST[1]
    seen = {}
    errors = []
    for entry in entries:
        source = entry.get("source")
        if not isinstance(source, str):
            continue
        key = _source_key(source)
        if key in seen:
            errors.append(
                MarketplaceError(
                    root_path,
                    f"duplicate catalog entries for the same plugin: "
                    f"{seen[key]!r} and {source!r}",
                )
            )
        else:
            seen[key] = source
    return errors


def _name_collisions(repo_root: Path, fragments: list, entries: list) -> list:
    """A plugin ``name`` must be unique across the catalog.

    The catalog keys on ``source``, but Claude Code's marketplace needs unique
    plugin names, so flag a fragment whose name already belongs to a *different*
    plugin (an existing entry or another fragment).

    Entries that are no longer live are ignored: the reconcile prunes them, so a
    plugin moved to a new path (manifest gone from the old one, fragment at the
    new one) keeps its name rather than colliding with its own stale entry.
    """
    name_to_source = {}
    for entry in entries:
        name = entry.get("name")
        source = entry.get("source")
        if (
            isinstance(name, str)
            and isinstance(source, str)
            and _is_live_plugin(repo_root, source)
        ):
            name_to_source[name] = source

    errors = []
    for frag in fragments:
        owner = name_to_source.get(frag.name)
        if owner is not None and _source_key(owner) != _source_key(frag.source):
            errors.append(
                MarketplaceError(
                    frag.path,
                    f"plugin name {frag.name!r} already used by {owner}; names must be unique",
                )
            )
        else:
            name_to_source[frag.name] = frag.source
    return errors


def _uncatalogued_plugins(repo_root: Path, entries: list) -> list:
    """A live plugin that no entry describes and no fragment is about to describe.

    Nothing else catches this. :func:`apply` only upserts from fragments and
    refreshes or prunes entries that already exist, so a plugin directory added
    with neither leaves the catalog untouched -- no entry, no error, and a plugin
    nobody can install. The same hole swallows a hand edit that deletes a live
    plugin's entry.

    The generator cannot simply invent the entry: ``category`` and the catalog
    ``description`` are curated, not derivable from ``plugin.json``. So this is a
    lint error, and it is what makes the fragment a real prerequisite rather than
    a convention.

    A plugin that merely *has* a fragment is never flagged: not one that has not
    been folded in yet (`apply --check`'s job, reported far more precisely), and
    not one whose fragment is invalid (already reported by
    :func:`discover_fragments`, and a second error for the same file would only
    mislead). So the signal here is the fragment file's existence, not its
    validity.
    """
    known = set()
    for entry in entries:
        source = entry.get("source")
        # A non-string source is an externally hosted plugin: not a local directory,
        # so it can neither satisfy nor mask a local plugin's missing entry.
        if isinstance(source, str):
            known.add(_source_key(source))

    errors = []
    for source in discover_plugin_sources(repo_root):
        if _source_key(source) in known:
            continue
        plugin_dir = _plugin_dir_for(repo_root, source)
        if (plugin_dir / _CLAUDE_DIR / FRAGMENT_NAME).is_file():
            continue
        manifest = _manifest_for(repo_root, source)
        name = None
        try:
            name = _manifest_string(_read_json(manifest), "name")
        except (OSError, json.JSONDecodeError):
            # A manifest too broken to name itself is still an uncatalogued plugin;
            # report it by path rather than swallowing it.
            pass
        label = f"plugin {name!r}" if name else "plugin"
        errors.append(
            MarketplaceError(
                manifest,
                f"{label} at {source!r} is in no catalog entry and has no "
                f"{FRAGMENT_NAME}; ship one (category + description) -- the regen "
                "job writes the catalog entry on main after the merge",
            )
        )
    return errors


def lint(repo_root: Path) -> list:
    """Validate every fragment (shape + name uniqueness) and the catalog's sources.

    Returns an empty list when everything is well-formed. A repo with no fragments
    is valid.
    """
    repo_root = repo_root.resolve()
    fragments, errors = discover_fragments(repo_root)
    # Propagate the catalog error rather than silently treating a missing or
    # malformed marketplace.json as "no entries" -- otherwise `lint` reports
    # everything valid while `apply` refuses to run at all.
    catalog, catalog_error = _load_catalog(repo_root)
    if catalog_error is not None:
        errors.append(catalog_error)
    if catalog is not None:
        entries = _existing_entries(catalog)
        errors.extend(_entry_shape_errors(repo_root, catalog))
        errors.extend(_duplicate_sources(repo_root, entries))
        errors.extend(_name_collisions(repo_root, fragments, entries))
        errors.extend(_uncatalogued_plugins(repo_root, entries))
    return errors


def _dump_catalog(data: dict) -> str:
    # Match the committed file exactly: 2-space indent, raw (non-escaped) unicode,
    # trailing newline. The catalog contains non-ASCII, so ensure_ascii=False is
    # load-bearing, not cosmetic.
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _refresh_derived(entry: dict, repo_root: Path) -> bool:
    """Re-derive ``name`` and ``version`` for an existing entry from its manifest.

    Fragments are consumed after merge, so without this a version bump in
    ``plugin.json`` could never reach the catalog again -- which is the very drift
    this generator exists to prevent. ``category`` and ``description`` are left
    alone: those are curated, not derived.
    """
    source = entry.get("source")
    if not isinstance(source, str):
        return False
    manifest = _manifest_for(repo_root, source)
    if not manifest.is_file():
        return False
    try:
        data = _read_json(manifest)
    except json.JSONDecodeError:
        return False
    changed = False
    for key in ("name", "version"):
        value = _manifest_string(data, key)
        if value is not None and entry.get(key) != value:
            entry[key] = value
            changed = True
    return changed


def apply(
    repo_root: Path,
    delete_fragments: bool = False,
    check: bool = False,
    force_prune: bool = False,
) -> ApplyResult:
    """Fold every fragment into the catalog and prune entries for removed plugins.

    Derived fields are refreshed on every surviving entry, fragments are upserted
    by ``source`` (existing replaced in place, new appended), and any entry whose
    plugin is gone is pruned. With ``delete_fragments`` the merged fragment files
    are removed. With ``check`` nothing is written or deleted and
    :attr:`ApplyResult.root_changed` reports whether it would have been. If any
    fragment is invalid, names collide, or a prune guard trips, nothing is written
    and the errors are returned.
    """
    repo_root = repo_root.resolve()
    result = ApplyResult()

    fragments, load_errors = discover_fragments(repo_root)
    if load_errors:
        result.errors = load_errors
        return result

    catalog, catalog_error = _load_catalog(repo_root)
    if catalog is None:
        result.errors = [catalog_error] if catalog_error is not None else []
        return result

    entries = _existing_entries(catalog)
    guard_errors = _duplicate_sources(repo_root, entries)
    guard_errors.extend(_name_collisions(repo_root, fragments, entries))
    if guard_errors:
        result.errors = guard_errors
        return result

    root_path = repo_root / _ROOT_MANIFEST[0] / _ROOT_MANIFEST[1]
    original_text = root_path.read_text(encoding="utf-8")
    plugins = [dict(e) if isinstance(e, dict) else e for e in catalog["plugins"]]

    # Refresh derived fields on entries that have no fragment this round. Track the
    # canonical key, not the raw string: a committed `"."` and a derived `"./"` are
    # the same plugin, and comparing raw strings would report it as updated twice.
    updated_keys = set()
    for entry in plugins:
        if isinstance(entry, dict) and _refresh_derived(entry, repo_root):
            source = entry.get("source")
            if isinstance(source, str):
                updated_keys.add(_source_key(source))
                result.updated.append(source)

    # Upsert fragments by source, preserving existing order.
    index_by_source = {}
    for i, entry in enumerate(plugins):
        if isinstance(entry, dict) and isinstance(entry.get("source"), str):
            index_by_source[_source_key(entry["source"])] = i
    for frag in fragments:
        entry = frag.entry()
        key = _source_key(frag.source)
        pos = index_by_source.get(key)
        if pos is None:
            index_by_source[key] = len(plugins)
            plugins.append(entry)
            result.added.append(frag.source)
        else:
            if plugins[pos] != entry and key not in updated_keys:
                updated_keys.add(key)
                result.updated.append(frag.source)
            plugins[pos] = entry

    # Prune entries whose plugin is gone (delete / move away).
    #
    # `isinstance(..., str)` is NOT defensive noise -- it is the escape hatch for
    # plugins hosted outside this repo, whose `source` is an object rather than a
    # path (e.g. {"source": "github", "repo": "owner/name"}). Those have no local
    # directory to check, so they must pass through untouched. Simplify this away
    # and every third-party entry gets silently pruned on the next reconcile.
    prune_sources = [
        e["source"]
        for e in plugins
        if isinstance(e, dict)
        and isinstance(e.get("source"), str)
        and not _is_live_plugin(repo_root, e["source"])
    ]
    if prune_sources and not force_prune:
        total = sum(
            1 for e in plugins if isinstance(e, dict) and isinstance(e.get("source"), str)
        )
        # A broken or partial checkout reports every plugin as missing. Its
        # signature is direct: no plugin manifest anywhere in the tree.
        if not _has_any_plugin_manifest(repo_root):
            result.errors = [
                MarketplaceError(
                    root_path,
                    "refusing to prune: no plugin manifests found anywhere under "
                    f"{repo_root}; likely a bad checkout, not real deletes "
                    "(pass --force-prune to override)",
                )
            ]
            return result
        if len(prune_sources) == total:
            result.errors = [
                MarketplaceError(
                    root_path,
                    f"refusing to prune every entry ({total} of {total}); "
                    "pass --force-prune if the catalog really should be empty",
                )
            ]
            return result
    if prune_sources:
        # Match on the canonical key so an entry written as "./x/" is pruned by a
        # prune_source of "./x" -- and so a refresh reported for one spelling is
        # dropped when the other spelling is pruned.
        pruned_keys = {_source_key(s) for s in prune_sources}
        plugins = [
            e
            for e in plugins
            if not (
                isinstance(e, dict)
                and isinstance(e.get("source"), str)
                and _source_key(e["source"]) in pruned_keys
            )
        ]
        result.pruned = prune_sources
        result.updated = [s for s in result.updated if _source_key(s) not in pruned_keys]

    catalog["plugins"] = plugins
    new_text = _dump_catalog(catalog)
    if new_text != original_text:
        result.root_changed = True
        if not check:
            root_path.write_text(new_text, encoding="utf-8")

    if delete_fragments:
        for frag in fragments:
            if not check:
                frag.path.unlink()
            result.deleted_fragments.append(frag.path)

    return result


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Defaults to the current working directory.",
    )


def main(argv: list = None) -> int:
    parser = argparse.ArgumentParser(
        prog="marketplace",
        description="Generate/validate the marketplace.json catalog from per-plugin fragments.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    lint_parser = sub.add_parser(
        "lint", help="Validate every marketplace-entry.json fragment (shape + name uniqueness)."
    )
    _add_common(lint_parser)

    apply_parser = sub.add_parser(
        "apply",
        help="Fold fragments into marketplace.json and prune entries for removed plugins.",
    )
    _add_common(apply_parser)
    apply_parser.add_argument(
        "--delete-fragments",
        action="store_true",
        help="Remove each fragment after folding it into the catalog (post-merge use).",
    )
    apply_parser.add_argument(
        "--check",
        action="store_true",
        help="Write nothing; exit 2 if the catalog is not already up to date.",
    )
    apply_parser.add_argument(
        "--force-prune",
        action="store_true",
        help="Prune stale entries even when a safety guard would refuse.",
    )

    args = parser.parse_args(argv)
    repo_root = args.repo_root if args.repo_root is not None else Path.cwd()
    if not repo_root.is_dir():
        print(f"{repo_root}: not a directory", file=sys.stderr)
        return EXIT_INVALID

    if args.command == "lint":
        errors = lint(repo_root)
        if not errors:
            print("All marketplace fragments valid.")
            return 0
        for err in errors:
            print(str(err), file=sys.stderr)
        return EXIT_INVALID

    result = apply(
        repo_root,
        delete_fragments=args.delete_fragments,
        check=args.check,
        force_prune=args.force_prune,
    )
    if result.errors:
        for err in result.errors:
            print(str(err), file=sys.stderr)
        return EXIT_INVALID

    for source in result.added:
        print(f"added   {source}")
    for source in result.updated:
        print(f"updated {source}")
    for source in result.pruned:
        print(f"pruned  {source}")
    for frag in result.deleted_fragments:
        print(f"removed {frag}")

    if not result.would_change():
        print("marketplace.json already up to date.")
        return 0
    if args.check:
        print(
            "marketplace.json is out of date; run `make marketplace` and commit the result.",
            file=sys.stderr,
        )
        return EXIT_WOULD_CHANGE
    return 0


if __name__ == "__main__":
    sys.exit(main())
