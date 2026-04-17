## Context

The release model is documented in `localdev/release.md` and enforced by
three pieces:

- `scripts/create-release-pr.sh` — reads the current version from
  `origin/v0.1:pyproject.toml`, bumps it, creates `release-<next>` off
  `v0.1`, merges `main` with `--no-ff --no-commit`, bumps
  `pyproject.toml`, commits, pushes, opens a PR into `v0.1`, and blocks
  on CI.
- `scripts/release.sh` — wraps the prepare step, merges the PR, waits for
  `release-create.yml`, and cleans up locally.
- `.github/workflows/release-create.yml` — fires on pushes to `v0.1`,
  reads the version from `pyproject.toml`, tags `v<VERSION>` and
  publishes the GitHub Release.

All three hard-code `v0.1`, and all three implicitly rely on `main` and
`v0.1` having the same `version` line at the common ancestor of the
release branch so that the `git merge origin/main` inside the prepare
script stays conflict-free. The 0.2.0 release (PR #36) committed
`version = "0.2.0"` onto `main`, which broke that invariant.

This change cuts a new `v0.2` release branch, re-points the tooling at
it, and replaces the "main never gets the version bump" invariant with
an explicit "main carries a dev sentinel" model that the scripts
actively resolve.

Stakeholders: the single maintainer cutting releases today, plus any
future contributor who runs `./scripts/release.sh` or pins the install
URL to `@v0.2`.

## Goals / Non-Goals

**Goals:**

- `./scripts/release.sh` works end-to-end again, cutting `0.2.x` patches
  against a real `v0.2` branch with a deterministic merge resolution.
- `v0.2.0` is tagged and released (via the normal automated path) as the
  initial release on the new line.
- `main` is explicitly marked non-releasable via `version = "0.0.0-dev"`
  in `pyproject.toml`, so anyone reading the repo can tell at a glance
  that it is not a published version.
- `RELEASE_BRANCH` becomes the one knob that scripts consult, so
  opening a `v0.3` line later is a one-env-var override, not a re-edit.
- `v0.1` is archived in place — existing `@v0.1` pins keep resolving,
  but no new patches flow to it without an explicit opt-in.

**Non-Goals:**

- No support for maintaining `v0.1` in parallel. If a 0.1.x patch ever
  becomes necessary, the operator re-adds `v0.1` to the CI triggers and
  runs the scripts with `RELEASE_BRANCH=v0.1`. That workflow is not
  automated here.
- No change to the `--merge` strategy on release PRs. The signed merge
  commit on `v0.2` is still the artifact that `release-create.yml` tags.
- No change to how `release-create.yml` reads the version or creates the
  tag — only its `push.branches` trigger moves from `v0.1` to `v0.2`.
- No introduction of a shared helper library under `scripts/lib/` —
  `release.sh` continues to shell out to `create-release-pr.sh` (the
  design established by the archived `release-full-cycle-script`
  change). The `RELEASE_BRANCH` variable is duplicated between the two
  scripts with a shared default, which is the smallest change that
  honors the existing boundary.
- No rollback of the 0.2.0 commit on `main`. The breaking CLI restructure
  stays; only the `version` line flips to the dev sentinel.

## Decisions

### Decision 1: Branch `v0.2` from current `main` HEAD and let `release-create.yml` tag `v0.2.0`

**Choice:** `git push origin main:refs/heads/v0.2` (or equivalent) after
the `release-create.yml` trigger has been flipped to `[v0.2]`. The
pushed branch's HEAD already carries `version = "0.2.0"`, so the
existing workflow reads it, tags `v0.2.0`, and creates the GitHub
Release without any manual tagging step.

**Why:** The merge commit of PR #36 (currently `main` HEAD) is already
the canonical "0.2.0 is released" point. Reusing the existing
auto-tagger keeps the release history consistent with every prior
release — same "Verified" merge commit, same auto-generated notes,
same tag format.

**Alternatives considered:**

- *Manual `git tag -a v0.2.0`*: skips the workflow entirely, producing
  an unsigned tag and no GitHub Release notes. Rejected — breaks parity
  with `v0.1` tags.
- *Cut empty `v0.2` then run `./scripts/release.sh`*: would produce a
  `release-0.2.0 → v0.2` merge commit on top of the main HEAD, adding a
  pointless second release commit to the history. Rejected.

### Decision 2: `main` carries `version = "0.0.0-dev"` after the branch cut

**Choice:** Replace `main`'s `pyproject.toml` `version` line with
`version = "0.0.0-dev"` in a standalone `chore:` commit. The dev
sentinel is explicit, PEP 440-parseable, and unambiguously non-release.

**Why:** The old "main stays at the previous release version" invariant
(from `localdev/release.md`) kept the merge conflict-free but left
`main` looking like a released version, which is misleading. A dev
sentinel makes the intent clear and shifts conflict resolution into
the release script (where we can make it deterministic). Any reader
running `pip show localbox` on an editable-install from `main` now
sees `0.0.0-dev`, which correctly signals "not a release."

**Alternatives considered:**

- *Match the latest release on `v0.2` (i.e., keep `main` at `0.2.0`)*:
  reverts to the old conflict-free model. Rejected because the user
  asked for a dev sentinel and because the alternative below (script
  resolver) makes the sentinel model work just as reliably.
- *Use `0.2.0.dev0` (PEP 440 dev release)*: also parseable, but
  numerically close to `0.2.0` and could be confused with a real
  release. Rejected in favor of `0.0.0-dev` which sorts lowest and
  carries the clearest intent.
- *Delete the `version` line on `main`*: breaks `hatchling` builds of
  editable installs. Rejected.

### Decision 3: Resolve the `pyproject.toml` conflict by taking `main`'s side, then `sed`-bumping the version

**Choice:** After `git merge --no-commit --no-ff origin/main` inside
`create-release-pr.sh`, the script inspects `git ls-files -u`:

- If the only conflicted path is `pyproject.toml`, run `git checkout
  --theirs -- pyproject.toml` and let the pre-existing
  `sed -i 's/^version = .*/version = "$NEXT"/' pyproject.toml` line
  re-set the version to the computed next version. Then `git add
  pyproject.toml` and commit as before.
- If any other path is conflicted, exit 1 with a message naming the
  paths and instructing the operator to resolve manually and rerun.

**Why:**

- Taking `main`'s side (`--theirs` during a merge means the side being
  merged in, i.e., `origin/main`) preserves any dependency additions,
  tool config updates, or other `pyproject.toml` edits that landed on
  `main` since the last release. Taking `--ours` (the release branch,
  started from `v0.2`) would silently drop those, which is the worse
  failure mode because the release would ship without them.
- The `sed` is already the source of truth for the version line; it
  runs unconditionally after the merge today. Keeping it as the
  final writer means the version conflict is fully absorbed without
  the script needing to parse conflict markers.
- Refusing any other conflict short-circuits the "automate through the
  mess" failure mode. If a real code conflict exists between `main`
  and the release branch, the operator needs to see it.

**Alternatives considered:**

- *`git merge -X theirs`*: applies hunk-level "theirs" to every
  conflict in the merge, not just `pyproject.toml`. Too broad — would
  silently resolve legitimate conflicts in source files. Rejected.
- *A `.gitattributes` merge driver for `pyproject.toml`*: works
  without script changes, but adds a permanent config file that
  future readers would have to understand. Rejected in favor of the
  explicit script-level resolver.
- *Parse conflict markers and surgically rewrite just the version
  line*: fragile; `git merge` does not guarantee the marker format
  across all conflict shapes. Rejected.

### Decision 4: `RELEASE_BRANCH` as a single env var, defaulting to `v0.2`

**Choice:** Both scripts add `RELEASE_BRANCH="${RELEASE_BRANCH:-v0.2}"`
near the top and replace every literal `v0.1` reference with
`"$RELEASE_BRANCH"`. Error messages use `"$RELEASE_BRANCH"` so they
stay accurate when the operator overrides it.

**Why:** One knob, one default, zero ceremony for the common case. A
future `v0.3` release line is cut with `RELEASE_BRANCH=v0.3
./scripts/release.sh` rather than a script edit. The default
guarantees the no-env-var invocation keeps doing the right thing for
the active line.

**Alternatives considered:**

- *CLI flag (e.g., `--branch v0.2`)*: marginally cleaner, but requires
  `getopts` parsing and two new args in two scripts. The env-var shape
  matches how `create-release-pr.sh` already surfaces operator
  controls (or would, if it had any). Rejected for now; trivial to
  add later if needed.
- *Hard-code `v0.2` without a variable*: fine today, one extra touch
  next time a major line opens. Rejected — the variable is a line of
  code and saves a round trip through code review.

### Decision 5: Freeze `v0.1` by removing it from CI triggers; leave the branch alone

**Choice:**

- `.github/workflows/ci.yml`: drop `v0.1` from `pull_request.branches`.
- `.github/workflows/release-create.yml`: change `push.branches` from
  `[v0.1]` to `[v0.2]`.
- `origin/v0.1` is not deleted, not renamed, not protection-changed.

**Why:** The branch itself needs to remain on GitHub so that existing
`pip install ...@v0.1` pins keep resolving. Removing it from CI
prevents accidental 0.1.x patch PRs from looking supported. If a
real security fix ever needs backporting, re-adding the triggers is
cheap; the ceremony is a feature, not a bug.

**Alternatives considered:**

- *Delete `origin/v0.1`*: breaks the existing install URL. Rejected
  unless we also redirect from a future `@v0.1` pin somehow, which we
  do not.
- *Keep CI triggers for v0.1 but mark the branch read-only via a
  GitHub rule*: adds administrative surface area for a branch we are
  not actively maintaining. Rejected.

## Risks / Trade-offs

- **Risk:** Pushing `v0.2` before `release-create.yml` has been flipped
  to `[v0.2]` means no tag is created. **Mitigation:** the task order
  in `tasks.md` updates the workflow first, merges that change to
  `main`, and only then pushes `v0.2`. If the push lands first anyway,
  the fix is trivial — update the workflow, then `git push --force
  origin <same-sha>:refs/heads/v0.2` to re-trigger. (No history is
  rewritten; the branch already points where it needs to.)

- **Risk:** Reverting `main`'s version to `0.0.0-dev` confuses
  downstream automation that greps `pyproject.toml` for "the current
  release." **Mitigation:** the only such automation in this repo is
  `release-create.yml`, which reads `pyproject.toml` on the release
  branch (`v0.2`), not on `main`. External automation is out of scope;
  the dev sentinel is a signal, not a break.

- **Risk:** `git checkout --theirs -- pyproject.toml` inside the
  release script silently drops a legitimate `main`-side version bump
  if someone edits `main`'s version line manually. **Mitigation:** the
  `sed` that follows sets the version to the computed next value
  regardless, so the "drop" is exactly what we want for that one line.
  Operators who bump the version by hand on `main` should not — that's
  what the dev sentinel and this script exist to prevent.

- **Trade-off:** Duplicating the `RELEASE_BRANCH` default in both
  scripts (vs. a shared helper) is a small DRY violation. Accepted on
  the same reasoning as the archived `release-full-cycle-script`
  change — two scripts, one caller relationship, no third consumer
  coming. If that ever changes, extract `scripts/lib/release-common.sh`.

- **Trade-off:** Freezing `v0.1` loses a channel for fast 0.1.x
  security patches. Given the repo is pre-1.0 and has a single
  maintainer, the cost of maintaining parallel lines outweighs the
  benefit.

## Migration Plan

Order of operations (mirrors task ordering in `tasks.md`):

1. On a feature branch: update `release-create.yml` to trigger on
   `[v0.2]`, update `ci.yml` to drop `v0.1` from pull-request
   branches, parameterize both scripts with `RELEASE_BRANCH`, add the
   conflict resolver, flip `main`'s `pyproject.toml` version to
   `0.0.0-dev`, update all docs. Open a PR into `main`, merge.
2. After the PR is merged: cut `origin/v0.2` from the updated `main`
   HEAD. Pushing the branch triggers `release-create.yml`, which
   tags `v0.2.0` and publishes the GitHub Release.
3. Smoke-test: run `./scripts/create-release-pr.sh` locally, confirm
   it produces a clean `release-0.2.1` PR with the version bumped to
   `0.2.1` and no merge conflict. Close the PR without merging.

Rollback:

- Revert the "prepare v0.2 release line" PR on `main`.
- Delete `origin/v0.2` (the branch, not the tag; the `v0.2.0` tag
  stays because it's legitimate).
- Restore `version = "0.2.0"` on `main` if downstream pins require it.
- The `v0.1` CI triggers can be restored from git history.

No database, no user data, no third-party systems are affected.

## Open Questions

- Should `scripts/release.sh` gain a `--dry-run` flag that stops after
  `create-release-pr.sh` returns (no merge, no wait, no tag)? Leaning
  no; running `create-release-pr.sh` directly already gives that, and
  the current `release.sh` explicitly treats the manual-fallback case
  as "use the prepare script alone." Reconsider if operators start
  asking for it.
- Should `README.md` show both `@v0.1` (archived, last release
  `0.1.28`) and `@v0.2` (active) install URLs, or just `@v0.2`? Current
  plan: just `@v0.2`. Document the `@v0.1` archive state briefly in
  `localdev/release.md` instead, so the top-of-funnel README stays
  uncluttered.
