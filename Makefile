PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help marketplace marketplace-preview marketplace-lint marketplace-check test check install-hooks

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_%-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# marketplace.json is written by CI (the regen job on main), never by a PR -- so this
# target is the repair/escape hatch (a bad generated state, --force-prune), not part of
# the normal flow. Do not commit its output in a PR: the guard in the workflow rejects
# a catalog change unless the PR carries the `catalog-override` label.
marketplace: ## Rewrite marketplace.json locally -- repair only; CI does this on main
	$(PYTHON) tools/marketplace.py apply

# What to run before pushing: exactly what regen will do on main, without writing.
# Exits 2 when there is work to do, which is the normal state of a feature branch,
# so the failure is swallowed -- this target reports, it does not judge.
marketplace-preview: ## Show what the regen job will do on main (writes nothing)
	@$(PYTHON) tools/marketplace.py apply --check --delete-fragments || true

marketplace-lint: ## Validate every marketplace-entry.json fragment
	$(PYTHON) tools/marketplace.py lint

# Not part of `check`, and not what a feature branch should satisfy: a branch that adds
# or updates a plugin is *expected* to leave the catalog stale until regen reconciles it
# on main. This is for inspecting main, or debugging the generator.
marketplace-check: ## Fail if marketplace.json is not already up to date (main only)
	$(PYTHON) tools/marketplace.py apply --check

test: ## Run the marketplace tooling's unit tests
	$(PYTHON) -m unittest discover -s tools -p 'test_*.py'

check: test marketplace-lint ## Everything CI checks on a PR, in CI's order

# Opt-in, and deliberately runs marketplace-lint rather than marketplace-check: a
# branch that ships a new fragment legitimately has a stale catalog (regen reconciles
# it on main), so checking the catalog here would block every add and update. Lint is
# the invariant that must hold at commit time -- notably that every plugin has an entry
# or a fragment. It only ever fails; it never rewrites files mid-commit. Hooks are not
# version-controlled, so this is per-clone.
install-hooks: ## Install a pre-commit hook that runs the fragment lint
	@printf '#!/bin/sh\nexec make -s marketplace-lint\n' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Installed .git/hooks/pre-commit (runs make marketplace-lint)."
