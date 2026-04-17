## Why

The 0.2.0 breaking release just merged into `main`, but the release tooling
can no longer cut a release:

1. `scripts/create-release-pr.sh` and `scripts/release.sh` are hard-coded to
   `v0.1`. They start `release-<next>` from `origin/v0.1` and run
   `git merge --no-commit --no-ff origin/main`. With `origin/v0.1` at
   `0.1.28` and `origin/main` at `0.2.0`, both sides modified the
   `version = "…"` line in `pyproject.toml` since the common ancestor, so
   every merge hits a conflict on that one line.
2. `localdev/release.md` documents the invariant "main never gets the
   version bump — it stays at the previous release version," and the old
   scripts relied on that invariant to stay conflict-free. Bumping `main`
   to `0.2.0` as part of the domain-first CLI release broke it.
3. `v0.1` as the active release target is now behind `main` by a breaking
   release and cannot receive further patches without contradicting
   semver. There is no `v0.2` branch yet, so `release-create.yml` has
   nothing to tag against.

We fix it by cutting a dedicated `v0.2` release branch from `main`, freezing
`v0.1` in place, parameterizing the release scripts, and reverting `main`'s
`pyproject.toml` version to a dev sentinel (`0.0.0-dev`) so that `main` is
explicitly non-releasable. The release script is hardened to resolve the
`pyproject.toml` conflict that the dev-sentinel model produces deterministically
— the existing `sed` that sets the version is promoted to the single source of
truth for release-branch version bumps, and the script takes `main`'s side for
everything else in `pyproject.toml` to preserve dependency changes.

Outcome: `./scripts/release.sh` works again for cutting `0.2.x` patches
against `v0.2`, `v0.1` is archived in place on GitHub but no longer wired
into CI or the release scripts, and the release docs describe the new
single-active-line model with a `RELEASE_BRANCH` override for the future.

## What Changes

### Branch model

- Create `v0.2` from the current `main` HEAD (the merge commit of PR #36,
  which already carries `version = "0.2.0"`). Push to `origin`.
- Change `pyproject.toml` on `main` from `version = "0.2.0"` to
  `version = "0.0.0-dev"` in a standalone commit so `main` is explicitly
  non-releasable and future release-branch merges resolve deterministically.

### Scripts

- `scripts/create-release-pr.sh` and `scripts/release.sh` SHALL accept a
  `RELEASE_BRANCH` environment variable (default: `v0.2`) instead of the
  current hard-coded `v0.1`. Every literal reference to `v0.1` /
  `origin/v0.1` becomes `"$RELEASE_BRANCH"` / `"origin/$RELEASE_BRANCH"`.
- `scripts/create-release-pr.sh` SHALL resolve the expected
  `pyproject.toml` conflict after `git merge --no-commit --no-ff origin/main`
  by taking `main`'s version of the file (`git checkout --theirs --
  pyproject.toml`), so any main-side dependency changes survive. The
  existing `sed -i 's/^version = .*/version = "$NEXT"/' pyproject.toml`
  then overwrites the version line with the computed next version. If
  any file other than `pyproject.toml` is in a conflicted state, the
  script SHALL abort with a message naming the file.

### CI

- `.github/workflows/ci.yml` SHALL drop `v0.1` from its
  `pull_request.branches` list. CI triggers become `push: [main]` and
  `pull_request: [main]` only.
- `.github/workflows/release-create.yml` SHALL change its `push.branches`
  trigger from `[v0.1]` to `[v0.2]`, so pushing to `v0.2` is what
  produces the tag + GitHub Release.
- `origin/v0.1` stays on GitHub as an archived branch. No branch
  protection changes, no deletion. Restoring maintenance on `v0.1` would
  require explicitly setting `RELEASE_BRANCH=v0.1` and re-adding the CI
  triggers.

### Docs

- `localdev/release.md`: rewrite the branch-model section for the
  single-active-line `v0.2` world. Replace the "main never gets the
  version bump" note with the `0.0.0-dev` sentinel explanation. Add a
  brief note about the `RELEASE_BRANCH` override for future major lines
  (`v0.3` etc.).
- `README.md`: update install URLs from
  `git+https://github.com/nicolai-budico/localbox.git@v0.1` to `@v0.2`,
  and the specific-pin example from `@v0.1.0` to `@v0.2.0`.
- `docs/getting-started.md`, `docs/developer-guide.md`: same install-URL
  substitution; refresh any branch-diagram prose that names `v0.1` as
  the release target.

## Capabilities

### New Capabilities

_None — release tooling is operator scripting, not a spec-level
capability._

### Modified Capabilities

_None._

## Impact

- Code:
  - `scripts/create-release-pr.sh` — parameterize `RELEASE_BRANCH`, add
    pyproject-conflict resolver, reject unexpected conflicts.
  - `scripts/release.sh` — parameterize `RELEASE_BRANCH` in the PR-lookup
    and error messages.
- Config:
  - `pyproject.toml` on `main` only — `0.2.0` → `0.0.0-dev`.
  - `.github/workflows/ci.yml` — drop `v0.1` from `pull_request.branches`.
  - `.github/workflows/release-create.yml` — `v0.1` → `v0.2` trigger.
- Branch state:
  - New `origin/v0.2` pointing at current `origin/main` HEAD.
  - First push of `v0.2` triggers `release-create.yml`, which tags
    `v0.2.0` and publishes the GitHub Release.
- Docs:
  - `localdev/release.md` — rewritten branch model section.
  - `README.md`, `docs/getting-started.md`, `docs/developer-guide.md` —
    install URL & version pin refreshes.
- Tests: none. These are operator scripts that shell out to `gh` and
  `git` against live GitHub; the repo has no shell-script test harness.
- Dependencies: no new tools. `git`, `gh` (authenticated), `python3` are
  already required.
- Rollback: revert the change commits; re-cut `origin/v0.2` if it was
  pushed. `origin/v0.1` is untouched so no maintenance state is lost.
