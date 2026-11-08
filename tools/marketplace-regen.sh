#!/usr/bin/env bash
# Post-merge reconcile of the generated marketplace catalog. Run by
# .github/workflows/marketplace-regen.yml; see tools/marketplace.py.
#
# Each attempt starts from the latest remote branch, folds every fragment into
# marketplace.json, and pushes. A rejected push (someone pushed meanwhile) retries
# from scratch on the new tip instead of rebasing: `apply` is idempotent, so
# re-running it on fresh main is always correct, and there is no half-finished
# rebase that could "push" nothing and report success while dropping the commit.
#
# Env: REGEN_REMOTE (origin), REGEN_BRANCH (main), REGEN_ATTEMPTS (2),
#      REGEN_RETRY_SLEEP seconds between attempts (2).
set -euo pipefail

remote="${REGEN_REMOTE:-origin}"
branch="${REGEN_BRANCH:-main}"
attempts="${REGEN_ATTEMPTS:-2}"
retry_sleep="${REGEN_RETRY_SLEEP:-2}"

catalog=".claude-plugin/marketplace.json"
# The `:(glob)` magic is load-bearing: it makes a leading `**/` match at depth 0
# too. That is how a fragment belonging to a plugin at the repo root
# (.claude-plugin/marketplace-entry.json, beside the catalog) would be seen at
# all -- no plugin lives there now, but drop the magic and such a fragment would
# survive every reconcile. Plain '**/...' matches only depth 1 and below.
fragment_glob=":(glob)**/.claude-plugin/marketplace-entry.json"

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

for attempt in $(seq 1 "$attempts"); do
  git fetch --quiet "$remote" "$branch"
  git checkout --quiet -B "$branch" "$remote/$branch"
  git reset --quiet --hard "$remote/$branch"

  python3 tools/marketplace.py apply --delete-fragments

  if [ -z "$(git status --porcelain -- "$catalog" "$fragment_glob")" ]; then
    echo "Catalog already up to date; nothing to commit."
    exit 0
  fi

  # `git status` tolerates a pathspec that matches nothing, but `git add` exits 128
  # on one ("did not match any files") even when another pathspec did match. The
  # steady state here has no fragments at all -- they are consumed by the first
  # reconcile -- so a catalog-only change (a prune, or a version refreshed from
  # plugin.json) would abort the script under `set -e`. Resolve the fragments from
  # the index instead: they are still tracked there once deleted from the worktree.
  stage=("$catalog")
  while IFS= read -r -d '' f; do stage+=("$f"); done < <(git ls-files -z -- "$fragment_glob")
  git add -A -- "${stage[@]}"

  # The guard above reads the worktree; what actually got staged is decided by the
  # `git ls-files` walk. If those ever disagree, `git commit` fails with the opaque
  # "nothing to commit, working tree clean" and takes the job red. Say why instead.
  if git diff --cached --quiet; then
    echo "Catalog changed in the worktree but nothing was staged; the staging" >&2
    echo "pathspec and the status guard disagree -- refusing an empty commit." >&2
    exit 1
  fi

  # [skip ci] is redundant under GITHUB_TOKEN (whose pushes never trigger workflows)
  # but load-bearing under MARKETPLACE_REGEN_TOKEN: a PAT push DOES trigger them, so
  # without this marker the workflow would re-trigger itself forever.
  git commit --quiet -m "chore(marketplace): reconcile catalog from fragments [skip ci]"

  push_log=$(mktemp)
  if git push "$remote" "HEAD:$branch" 2>&1 | tee "$push_log"; then
    rm -f "$push_log"
    echo "Pushed reconciled catalog (attempt $attempt)."
    exit 0
  fi
  # Not every push failure is a losable race. A read-only Actions token or a
  # protected branch will fail identically on every attempt, so retrying just
  # buries the real cause under "Failed to push after N attempts".
  if grep -qiE 'protected branch|permission to|403|denied|shallow update' "$push_log"; then
    rm -f "$push_log"
    echo "Push refused for permissions, not a race. Check Settings > Actions >" >&2
    echo "General > Workflow permissions = 'Read and write'; if main is protected," >&2
    echo "set the MARKETPLACE_REGEN_TOKEN secret (Contents:write + Workflows:write)." >&2
    exit 1
  fi
  rm -f "$push_log"
  echo "Push rejected (attempt $attempt); retrying on the latest $branch..."
  sleep "$retry_sleep"
done

echo "Failed to push reconciled catalog after $attempts attempts." >&2
exit 1
