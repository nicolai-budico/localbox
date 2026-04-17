#!/usr/bin/env bash
set -euox pipefail

# Creates a release branch from $RELEASE_BRANCH (default: v0.2), merges main,
# bumps the patch version, and opens a PR into $RELEASE_BRANCH. Run from
# anywhere inside the repo.
#
# Requirements: git, gh (authenticated), python3

# Override to target a different release line (e.g., RELEASE_BRANCH=v0.3).
RELEASE_BRANCH="${RELEASE_BRANCH:-v0.2}"

git fetch origin

# Read current version from $RELEASE_BRANCH
CURRENT=$(git show "origin/$RELEASE_BRANCH:pyproject.toml" | python3 -c "
import re, sys
m = re.search(r'^version\s*=\s*\"([^\"]+)\"', sys.stdin.read(), re.MULTILINE)
print(m.group(1))
")

# Compute next patch version
IFS='.' read -ra P <<< "$CURRENT"
P[2]=$(( P[2] + 1 ))
NEXT="${P[0]}.${P[1]}.${P[2]}"

echo "Current version : $CURRENT"
echo "Next version    : $NEXT"
echo ""

BRANCH="release-$NEXT"

if git ls-remote --exit-code origin "refs/heads/$BRANCH" > /dev/null 2>&1; then
  echo "Error: branch '$BRANCH' already exists on remote." >&2
  exit 1
fi

# Also guard against a stale local branch left behind by a previous aborted run.
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  echo "Error: local branch '$BRANCH' already exists (likely from a previous aborted run)." >&2
  echo "       Delete it with: git branch -D $BRANCH" >&2
  exit 1
fi

git checkout -b "$BRANCH" "origin/$RELEASE_BRANCH"
git merge --no-commit --no-ff origin/main

# Resolve the expected pyproject.toml conflict deterministically: take main's
# side so dependency additions and tool config survive; the sed below then
# re-sets the version line to $NEXT. Any other unmerged path is a real
# conflict and must be resolved manually.
UNMERGED="$(git ls-files -u | awk '{print $4}' | sort -u)"
if [ -n "$UNMERGED" ]; then
  OTHER="$(printf '%s\n' "$UNMERGED" | grep -v '^pyproject\.toml$' || true)"
  if [ -n "$OTHER" ]; then
    echo "Error: unexpected merge conflict(s) in:" >&2
    printf '  %s\n' $OTHER >&2
    echo "Resolve manually, then rerun the script." >&2
    exit 1
  fi
  git checkout --theirs -- pyproject.toml
fi

sed -i "s/^version = \".*\"/version = \"$NEXT\"/" pyproject.toml
git add pyproject.toml
git commit -m "Release $NEXT"
git push origin "$BRANCH"

PR_URL=$(gh pr create \
  --title "Release $NEXT" \
  --body "Automated release PR for v$NEXT" \
  --base "$RELEASE_BRANCH" \
  --head "$BRANCH")

PR_NUMBER=$(basename "$PR_URL")
echo "PR #$PR_NUMBER: $PR_URL"
echo ""

echo "Waiting for CI to start..."
while true; do
  CHECKS=$(gh pr checks "$PR_NUMBER" 2>/dev/null || true)
  if [ -n "$CHECKS" ]; then
    break
  fi
  sleep 2
done

echo "CI started. Waiting for checks to complete..."
if gh pr checks "$PR_NUMBER" --watch --interval 2; then
  echo ""
  echo "CI passed. Review and merge: $PR_URL"
else
  echo ""
  echo "CI failed. Check details: $PR_URL" >&2
  exit 1
fi
