## 1. `scripts/release.sh` skeleton and prepare step

- [x] 1.1 Create `scripts/release.sh` with `#!/usr/bin/env bash`, `set -euo pipefail`, and a top-of-file comment documenting the full cycle (prepare → merge → wait → cleanup → announce) and the requirements (`git`, `gh` authenticated, `python3`).
- [x] 1.2 Compute `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` and invoke `"$SCRIPT_DIR/create-release-pr.sh"` as a subprocess; propagate its exit status if it fails.
- [x] 1.3 After prepare returns, read `BRANCH=$(git branch --show-current)` and assert it starts with `release-`; exit with a clear error naming the current branch if not (defensive: means `create-release-pr.sh` changed its contract).
- [x] 1.4 Derive `NEXT="${BRANCH#release-}"` and echo both `BRANCH` and `NEXT` for operator visibility.
- [x] 1.5 `chmod +x scripts/release.sh` so it is runnable out of the box.

## 2. Locate the release PR

- [x] 2.1 Run `PR_NUMBER=$(gh pr list --head "$BRANCH" --base v0.1 --json number --jq '.[0].number // empty')` to fetch the PR number.
- [x] 2.2 If `PR_NUMBER` is empty, exit 1 with a message naming `$BRANCH` and telling the operator to inspect the PR state on GitHub. Do not attempt any cleanup.
- [x] 2.3 Echo `PR #$PR_NUMBER for release $NEXT` for visibility before merging.

## 3. Merge the PR and capture the merge commit

- [x] 3.1 Run `gh pr merge "$PR_NUMBER" --merge --delete-branch`. The `--merge` strategy is explicit (no squash, no rebase) to preserve the signed merge commit on `v0.1` that `release-create.yml` tags.
- [x] 3.2 Poll `MERGE_SHA=$(gh pr view "$PR_NUMBER" --json mergeCommit --jq '.mergeCommit.oid // empty')` in a loop (up to ~20 seconds, 2-second sleeps) until it returns a non-empty SHA. This mirrors the "wait for CI to start" loop in `create-release-pr.sh`.
- [x] 3.3 If `MERGE_SHA` is still empty after the loop, exit 1 with a message pointing at the PR URL so the operator can verify the merge manually.
- [x] 3.4 Echo `Merge commit: $MERGE_SHA`.

## 4. Wait for `release-create.yml` on the merge commit

- [x] 4.1 Poll `gh run list --workflow=release-create.yml --limit 10 --json databaseId,headSha,status,conclusion` until a row with `headSha == $MERGE_SHA` appears (retry up to ~60 seconds, 2-second sleeps). Extract that row's `databaseId` as `RUN_ID`.
- [x] 4.2 If no matching run appears, exit 1 with a message naming the merge commit SHA and telling the operator to check the Actions tab. Do not attempt to merge or clean up anything.
- [x] 4.3 Run `gh run watch "$RUN_ID" --exit-status --interval 2`. If the run concludes with anything other than `success`, the `--exit-status` flag propagates the failure and `set -e` exits the script immediately.

## 5. Clean up local state and switch back to main

- [x] 5.1 `git checkout main` — fails loudly if the working tree has uncommitted changes on the release branch; that is the right behavior because the operator needs to decide what to do with them.
- [x] 5.2 `git fetch origin --prune` to drop any stale `origin/release-<next>` ref that `--delete-branch` removed from the remote.
- [x] 5.3 `git branch -D "$BRANCH" 2>/dev/null || true` — tolerate the case where the local branch is already gone (e.g. the operator's git config auto-pruned it).

## 6. Announce success

- [x] 6.1 Print `Version v$NEXT released.` as the final line of script output on success. Keep the wording exact — operators and downstream automation may grep for it.
- [x] 6.2 Exit 0.

## 7. Docs

- [x] 7.1 Add a "Release in one shot" section at the top of `localdev/release.md` that documents `./scripts/release.sh` and shows the expected happy-path output.
- [x] 7.2 Re-label the existing step-by-step section as "Manual release fallback" and note when the operator should prefer it (fix-forward, waiting for human review, partial releases).
- [x] 7.3 Document the failure modes (prepare fails → nothing merged, merge fails → PR still exists, `release-create.yml` fails → release is half-done and needs manual recovery) and the "release branch is left behind on error" contract.

## 8. Quality gates

- [ ] 8.1 `shellcheck scripts/release.sh` — the repo does not currently run shellcheck in CI. Skipped during apply: `shellcheck` is not installed on the development host. Run locally before merging if available.
- [x] 8.2 `bash -n scripts/release.sh` — syntax check. Passed.
- [ ] 8.3 Dry smoke test: run `./scripts/release.sh` against a scratch fork (or with `gh` talking to a fork remote) and confirm the script reaches the "Version v... released." line and leaves `main` checked out with no leftover `release-*` branch locally. Deferred — requires a live GitHub session and a disposable fork; the operator should run this before relying on the script for real.
- [x] 8.4 Verify `./scripts/create-release-pr.sh` still works standalone (no regression from being called as a subprocess). No changes to `scripts/create-release-pr.sh` in this change — existing contract is preserved.
