#!/usr/bin/env bash
set -euox pipefail

# Creates a release branch from v0.1, merges main, bumps the patch version,
# and opens a PR into v0.1. Run from anywhere inside the repo.
#
# Requirements: git, gh (authenticated), python3

git fetch origin

# Read current version from v0.1
CURRENT=$(git show origin/v0.1:pyproject.toml | python3 -c "
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

git checkout -b "$BRANCH" origin/v0.1
git merge --no-commit --no-ff origin/main
sed -i "s/^version = \".*\"/version = \"$NEXT\"/" pyproject.toml
git add pyproject.toml
git commit -m "Release $NEXT"
git push origin "$BRANCH"

PR_URL=$(gh pr create \
  --title "Release $NEXT" \
  --body "Automated release PR for v$NEXT" \
  --base v0.1 \
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
