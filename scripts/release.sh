#!/usr/bin/env bash
set -euo pipefail

# Full release cycle in one shot:
#   1. Prepare   — delegates to ./scripts/create-release-pr.sh (creates the
#                  release-<next> branch, pushes, opens a PR into v0.1, and
#                  blocks on CI via `gh pr checks --watch`).
#   2. Merge     — `gh pr merge --merge --delete-branch` on the release PR.
#                  The `--merge` strategy is required so the signed merge
#                  commit on v0.1 is the artifact that release-create.yml
#                  tags.
#   3. Wait      — polls for the release-create.yml workflow run whose
#                  headSha equals the PR's merge commit, then `gh run watch`
#                  until it succeeds.
#   4. Cleanup   — switches back to main, prunes stale remotes, deletes the
#                  local release-<next> branch if it is still around.
#   5. Announce  — prints "Version v<NEXT> released." as the final line.
#
# On any error, the script exits non-zero and leaves the repo state
# untouched for inspection. There is no cleanup trap on purpose — a
# half-merged release is recoverable, a script that rewrote history trying
# to recover is not.
#
# Requirements: git, gh (authenticated), python3.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- 1. Prepare -------------------------------------------------------------

"$SCRIPT_DIR/create-release-pr.sh"

BRANCH="$(git branch --show-current)"
if [[ "$BRANCH" != release-* ]]; then
  echo "Error: expected to be on a release-<version> branch after prepare, but current branch is '$BRANCH'." >&2
  echo "       scripts/create-release-pr.sh may have changed its contract." >&2
  exit 1
fi

NEXT="${BRANCH#release-}"
echo ""
echo "Prepared release branch: $BRANCH"
echo "Next version           : $NEXT"
echo ""

# --- 2. Locate the release PR ----------------------------------------------

PR_NUMBER="$(gh pr list --head "$BRANCH" --base v0.1 --json number --jq '.[0].number // empty')"
if [ -z "$PR_NUMBER" ]; then
  echo "Error: could not find an open PR with head '$BRANCH' into v0.1." >&2
  echo "       Check the PR state on GitHub before re-running this script." >&2
  exit 1
fi

echo "PR #$PR_NUMBER for release $NEXT"
echo ""

# --- 3. Merge and capture the merge commit ---------------------------------

echo "Merging PR #$PR_NUMBER..."
gh pr merge "$PR_NUMBER" --merge --delete-branch

# GitHub takes a moment to record the merge commit on the PR object.
# Poll mergeCommit.oid the same way create-release-pr.sh polls gh pr checks.
MERGE_SHA=""
for _ in $(seq 1 10); do
  MERGE_SHA="$(gh pr view "$PR_NUMBER" --json mergeCommit --jq '.mergeCommit.oid // empty')"
  if [ -n "$MERGE_SHA" ]; then
    break
  fi
  sleep 2
done

if [ -z "$MERGE_SHA" ]; then
  echo "Error: PR #$PR_NUMBER was merged but GitHub did not return a merge commit SHA in time." >&2
  echo "       Check https://github.com and verify the merge before re-running." >&2
  exit 1
fi

echo "Merge commit: $MERGE_SHA"
echo ""

# --- 4. Wait for release-create.yml on that merge commit -------------------

echo "Waiting for release-create.yml run on $MERGE_SHA..."
RUN_ID=""
for _ in $(seq 1 30); do
  RUN_ID="$(
    gh run list \
      --workflow=release-create.yml \
      --limit 10 \
      --json databaseId,headSha \
      --jq ".[] | select(.headSha == \"$MERGE_SHA\") | .databaseId" \
    | head -n1
  )"
  if [ -n "$RUN_ID" ]; then
    break
  fi
  sleep 2
done

if [ -z "$RUN_ID" ]; then
  echo "Error: no release-create.yml run found for merge commit $MERGE_SHA after ~60s." >&2
  echo "       Check the Actions tab on GitHub before re-running." >&2
  exit 1
fi

echo "release-create.yml run: $RUN_ID"
gh run watch "$RUN_ID" --exit-status --interval 2

# --- 5. Local cleanup ------------------------------------------------------

echo ""
echo "Cleaning up local state..."
git checkout main
git fetch origin --prune
git branch -D "$BRANCH" 2>/dev/null || true

# --- 6. Announce ----------------------------------------------------------

echo ""
echo "Version v$NEXT released."
