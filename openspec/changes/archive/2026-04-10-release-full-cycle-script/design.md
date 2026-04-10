## Context

The release model is documented in `localdev/release.md` and enforced by two
pieces:

- `scripts/create-release-pr.sh` — computes the next patch version from
  `origin/v0.1:pyproject.toml`, creates `release-<next>` off `v0.1`, merges
  `main` with `--no-ff --no-commit`, bumps `pyproject.toml`, commits, pushes,
  opens a PR into `v0.1`, and blocks on `gh pr checks --watch` until CI either
  passes (exit 0) or fails (exit 1).
- `.github/workflows/release-create.yml` — fires on pushes to `v0.1`, reads
  the version from `pyproject.toml`, creates an annotated tag, and publishes
  the GitHub Release with auto-generated notes.

Between those two, the operator does three things by hand: merges the PR,
waits for `release-create.yml`, and deletes any local leftovers. All three are
mechanical and can be scripted from the existing `gh` CLI surface. The
scripting is the subject of this change.

Stakeholders: anyone cutting a release of this repo. Today that is a single
maintainer, but the one-shot script makes it safe for anyone on the team to
run the release without memorizing the multi-step flow.

## Goals / Non-Goals

**Goals:**

- A single command — `./scripts/release.sh` — that drives the full release
  cycle end-to-end and exits 0 only when the GitHub Release exists and the
  local/remote branches are clean.
- Reuse `scripts/create-release-pr.sh` as the "prepare" stage so the two
  scripts cannot drift in how they compute the version, create the branch,
  or wait for the release PR's CI.
- Identify the post-merge `release-create.yml` run unambiguously (by the PR's
  merge commit SHA) so concurrent pushes to other branches cannot confuse it.
- Fail fast and leave the repo inspectable on any error — do not attempt
  cleanup when a step fails.

**Non-Goals:**

- No change to `create-release-pr.sh` itself. Its behavior and output stay
  byte-for-byte the same so direct invocations keep working.
- No change to the branch model, merge strategy, or `release-create.yml`.
  The merge strategy stays `--merge` (no squash, no rebase) because the
  signed merge commit on `v0.1` is what gets tagged.
- No support for skipping CI, forcing a merge, or overriding the next
  version. Operators who need any of that can still use the manual flow
  documented in `localdev/release.md`.
- No retry/backoff logic beyond what `gh run watch` provides. If GitHub is
  flaky, the operator re-runs the script.
- No test coverage for the shell scripts. They shell out to `gh` and `git`
  against live GitHub and are outside the Python test surface.

## Decisions

### Decision 1: Shell out to `create-release-pr.sh` instead of extracting shared logic

**Choice:** `release.sh` invokes `"$SCRIPT_DIR/create-release-pr.sh"` as a
subprocess. It does not source the script, does not copy its logic, and does
not extract a shared helper library.

**Why:** The prepare logic is already well-tested in place and exits
non-zero on every failure mode we care about. Sourcing would mix shell state
(variables, `set -e` interactions) between the two scripts; a sub-shell gives
us a clean boundary. Extracting a `lib/release.sh` helper is overkill for
two scripts with one caller relationship and would force a second review
round on changes that only affect prepare.

**Alternatives considered:**
- *Source `create-release-pr.sh`*: inherits shell state, including the
  trailing `gh pr checks --watch` call, but exposes us to `set -euox`
  interactions and makes the merge step read variables set by a different
  file. Rejected.
- *Extract `scripts/lib/release-common.sh`*: cleaner in the abstract, but the
  only two consumers are these two scripts, and one of them (`release.sh`)
  is brand new. Premature abstraction.

### Decision 2: Derive the PR and version from Git state after prepare returns

**Choice:** After `create-release-pr.sh` exits successfully, `release.sh`
reads:

- `BRANCH=$(git branch --show-current)` — `create-release-pr.sh` leaves the
  working tree on `release-<next>`, so this is the release branch.
- `NEXT="${BRANCH#release-}"` — strip the prefix to get the version string.
- `PR_NUMBER=$(gh pr list --head "$BRANCH" --base v0.1 --json number --jq '.[0].number')`
  — look up the PR by head + base. The head branch name is unique on the
  remote (guarded by `create-release-pr.sh`'s pre-flight check), so this
  returns exactly one PR.

**Why:** This avoids having to parse `create-release-pr.sh`'s stdout or
teach it a new machine-readable output mode. The script's observable side
effects (checked-out branch, pushed remote branch, created PR) are already
stable contracts; we lean on them.

**Alternatives considered:**
- *Parse `create-release-pr.sh` output*: fragile; the script currently uses
  `set -x` so stderr is noisy, and stdout format is human-facing. Rejected.
- *Pass arguments through*: would require `create-release-pr.sh` to accept
  flags like `--print-pr`. Not worth the API surface.
- *Re-derive `NEXT` independently*: possible (read `pyproject.toml` on the
  checked-out branch) but duplicates logic; the branch name is simpler.

### Decision 3: Wait for `release-create.yml` by matching the merge commit SHA

**Choice:** Immediately after `gh pr merge`, fetch the merge commit SHA:

```
MERGE_SHA=$(gh pr view "$PR_NUMBER" --json mergeCommit --jq '.mergeCommit.oid')
```

Then poll `gh run list --workflow=release-create.yml --limit 10 --json databaseId,headSha,status,conclusion`
until a row with `headSha == $MERGE_SHA` appears. Hand its `databaseId` to
`gh run watch --exit-status` so the script exits non-zero if the run fails.

**Why:** `release-create.yml` is triggered by a push to `v0.1`, and the
merge commit is what `v0.1` advances to. The `headSha` match is the only
reliable way to identify the specific run that corresponds to our release —
matching by branch + timestamp would be racy if someone else pushes to
`v0.1` in the same window (rare, but not impossible).

**Alternatives considered:**
- *Watch the newest run on `v0.1` unconditionally*: racy. Rejected.
- *Use `gh run watch` without knowing the run ID*: `gh run watch` requires
  a run ID; it does not accept filters.
- *Sleep N seconds then check*: brittle; release workflow runtime varies.
- *Use `gh api` with a GraphQL query*: more targeted, but the REST polling
  loop is simpler and already matches the style of `create-release-pr.sh`.

### Decision 4: `gh pr merge --merge --delete-branch`, then prune locally

**Choice:** Merge with `--merge` (explicit, even though it is the default on
this repo) and `--delete-branch` to let GitHub delete the remote head.
Afterwards, `release.sh`:

1. `git checkout main`
2. `git fetch origin --prune` (drops any stale `origin/release-<next>` ref)
3. `git branch -D "$BRANCH" 2>/dev/null || true` (drops the local branch,
   tolerating the case where it was already gone because the user had
   `branch.autoSetupMerge` tricks configured)

**Why:** `--delete-branch` is the documented way to ask GitHub to clean up
the remote branch on merge and is idempotent. The local cleanup is separate
because `gh pr merge` only touches the remote. Switching to `main` before
deleting the local branch avoids the "cannot delete the currently checked-out
branch" failure mode.

**Alternatives considered:**
- *Leave the branch behind*: the whole point is to finish clean.
- *Use `git worktree remove`*: overkill; no worktree is involved.

### Decision 5: Fail fast, do not attempt cleanup on error

**Choice:** The script runs under `set -euo pipefail`. Every step that can
fail does so without a trap or cleanup handler. The release branch, local
checkout, and any partial state are left for the operator to inspect.

**Why:** Cleanup handlers on release scripts are the classic way to turn a
recoverable problem into a destroyed branch. If the merge fails, the PR
still exists and can be merged manually. If `release-create.yml` fails, the
merge already happened and the release is half-done — the operator needs to
see that state, not a script that rewrote history trying to be helpful.

**Alternatives considered:**
- *`trap` on `ERR` that deletes the branch*: risks destroying a partially
  merged release. Rejected.
- *Prompt the operator on each step*: turns a one-shot script back into a
  guided flow, defeating the purpose.

## Risks / Trade-offs

- **Risk:** `gh pr list --head "$BRANCH"` returns zero rows if the PR was
  closed or the remote branch was deleted between `create-release-pr.sh` and
  the lookup. **Mitigation:** if the lookup returns empty, exit with a clear
  error that names the branch and tells the operator to check the PR state.
  The prepare script just pushed and opened the PR, so this should only
  happen if a human actively intervened.

- **Risk:** Someone else pushes to `v0.1` in the same window and triggers
  a concurrent `release-create.yml` run. **Mitigation:** matching the run by
  the PR's merge commit SHA, not by "latest run on branch", isolates us
  from concurrent pushes.

- **Risk:** `gh pr merge` succeeds but `gh pr view --json mergeCommit`
  returns an empty/null SHA because GitHub hasn't finished recording the
  merge. **Mitigation:** retry the `mergeCommit` read a few times (e.g. up
  to 10 iterations of 2-second sleeps) before giving up. This is the same
  pattern `create-release-pr.sh` already uses when waiting for CI to start.

- **Risk:** `release-create.yml` takes longer than the operator expects and
  the script appears to hang. **Mitigation:** `gh run watch` prints progress
  lines as steps complete, which is enough feedback. We document the
  expected runtime in `localdev/release.md`.

- **Trade-off:** Shelling out to `create-release-pr.sh` means two layers of
  `bash -e` and therefore two stack traces on failure. The alternative
  (sourcing) is worse because it blurs error boundaries. Accept the extra
  log noise.

- **Trade-off:** The script assumes `main` is a valid checkout target after
  merge. If the operator has uncommitted changes on `release-<next>`, the
  `git checkout main` will fail — but by that point the release has already
  happened, so the only damage is a noisy exit. Document this in
  `localdev/release.md`.

## Migration Plan

No migration. The new script is additive and does not touch any existing
tooling. `create-release-pr.sh` remains the right entry point when:

- The operator wants to prepare a release but have a human review and merge
  the PR manually.
- CI is red on `main` and the operator wants to prepare the branch, fix
  forward, and only later come back to merge.

After this change lands, the default path in `localdev/release.md` points at
`release.sh`; the old step-by-step stays below it as the "manual fallback"
section.

Rollback is a single revert commit (delete `scripts/release.sh` and the
`localdev/release.md` edit).

## Open Questions

- Should `release.sh` accept a `--dry-run` flag that stops after prepare (no
  merge, no wait)? Leaning no — that is exactly what running
  `create-release-pr.sh` directly already gives you.
- Should we print a link to the published GitHub Release in the final
  "released" message? Cheap to add (`gh release view v$NEXT --json url`);
  worth doing if the operator uses that link often.
