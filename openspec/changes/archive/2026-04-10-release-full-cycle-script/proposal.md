## Why

Cutting a release today is a three-step dance that keeps the operator in the
loop even when nothing interesting is happening:

1. Run `./scripts/create-release-pr.sh` — creates the branch, opens the PR,
   waits for CI.
2. Merge the PR manually (`gh pr merge --merge` or the web UI).
3. Watch `release-create.yml` finish, confirm the tag and GitHub Release, and
   clean up any leftover local branches.

Each step is mostly waiting, but the operator has to stay in the terminal to
move between them. There is no single command that performs the whole release
cycle end-to-end and says "done". Adding one removes three context switches
per release and makes the happy path scriptable (e.g. from a release cron or
a teammate who has never cut a release before).

## What Changes

- Add `./scripts/release.sh` that performs the full release cycle:
  1. Invokes the existing `./scripts/create-release-pr.sh` to prepare the
     release branch, push it, and open a PR into `v0.1`. That script already
     blocks on CI via `gh pr checks --watch`, so by the time it returns the
     checks on the release PR are green.
  2. Derives the release branch name and next version from the current Git
     state (the branch `create-release-pr.sh` checked out) and the PR number
     via `gh pr list --head "$BRANCH"`.
  3. Merges the PR with `gh pr merge --merge --delete-branch` — the "merge
     commit" strategy is required by the release model (no squash, no rebase)
     so that the merge commit on `v0.1` is the signed artifact that
     `release-create.yml` tags.
  4. Waits for the post-merge `release-create.yml` workflow run on `v0.1` to
     finish successfully. The run is identified by matching the workflow's
     `headSha` to the PR's merge commit SHA, so concurrent runs on other
     branches are ignored.
  5. Deletes the local release branch if it still exists (the `--delete-branch`
     flag on `gh pr merge` only deletes the remote), switches the working
     tree back to `main`, and fetches/prunes stale remote refs.
  6. Prints `Version v<NEXT> released.` as the final line on success.
- Fail loudly at every step: if `create-release-pr.sh` exits non-zero, if the
  PR cannot be located, if the merge fails, or if `release-create.yml`
  concludes with anything other than `success`, `release.sh` SHALL exit with
  the same non-zero status and SHALL NOT attempt cleanup. The release branch
  stays around so the operator can inspect state.
- Update `localdev/release.md` to document the new one-shot entry point and
  keep the step-by-step manual flow as a fallback for partial releases.

## Capabilities

### New Capabilities

_None — release tooling is operator scripting, not a spec-level capability._

### Modified Capabilities

_None._

## Impact

- Code:
  - `scripts/release.sh` — new executable bash script (`set -euo pipefail`,
    `#!/usr/bin/env bash`) that orchestrates the steps above.
  - `scripts/create-release-pr.sh` — unchanged in behavior; `release.sh`
    shells out to it rather than duplicating its logic.
- Docs:
  - `localdev/release.md` — add a "Release in one shot" section pointing at
    `./scripts/release.sh` and note that `create-release-pr.sh` remains the
    right entry point when the operator wants to prepare a release but merge
    manually (e.g. waiting for a human reviewer).
- Tests: none. These are operator scripts that shell out to `gh` and `git`
  against live GitHub; they have no unit test coverage in this repo today,
  and the change intentionally does not introduce a new test harness for
  shell scripts.
- Dependencies: no new tools. Already-required `git`, `gh` (authenticated),
  and `python3` cover everything.
