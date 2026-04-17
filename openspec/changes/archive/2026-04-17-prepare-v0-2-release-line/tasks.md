## 1. CI workflow triggers

- [x] 1.1 Edit `.github/workflows/release-create.yml` line 6: change `branches: [v0.1]` under `push` to `branches: [v0.2]`. Do not touch the rest of the workflow (the version-reader, tag-creator, and release-publisher stay byte-for-byte identical).
- [x] 1.2 Edit `.github/workflows/ci.yml` line 7: change `pull_request.branches` from `[main, v0.1]` to `[main]`. Leave the `push.branches: [main]` trigger alone.

## 2. `pyproject.toml` dev sentinel on `main`

- [x] 2.1 Edit `pyproject.toml` line 8: change `version = "0.2.0"` to `version = "0.0.0-dev"`. Verify the file still parses (no accidental quote mangling) by running `python3 -c 'import tomllib; tomllib.load(open("pyproject.toml","rb"))'` or by running `pip install -e .` in a scratch venv.

## 3. Parameterize `scripts/create-release-pr.sh`

- [x] 3.1 Near the top of the script (after the opening comment block, before the first `git fetch`), add `RELEASE_BRANCH="${RELEASE_BRANCH:-v0.2}"` with a one-line comment explaining it overrides the default target for `v0.3` lines.
- [x] 3.2 Replace the literal `origin/v0.1` on line 12 (`git show origin/v0.1:pyproject.toml | ...`) with `"origin/$RELEASE_BRANCH:pyproject.toml"`.
- [x] 3.3 Replace the literal `origin/v0.1` on line 41 (`git checkout -b "$BRANCH" origin/v0.1`) with `"origin/$RELEASE_BRANCH"`.
- [x] 3.4 Replace the literal `v0.1` on line 51 (`--base v0.1`) in the `gh pr create` invocation with `"$RELEASE_BRANCH"`.
- [x] 3.5 Between the `git merge --no-commit --no-ff origin/main` on line 42 and the existing `sed -i "s/^version = ...` on line 43, insert a deterministic `pyproject.toml` conflict resolver:
  - Check `git ls-files -u` for any unmerged paths.
  - If the only unmerged path is `pyproject.toml`, run `git checkout --theirs -- pyproject.toml` so the `main`-side content (including any dependency additions) is taken.
  - If any other path is unmerged, `echo` a clear error naming the paths and `exit 1` before the `sed` runs.
  - Let the pre-existing `sed` on line 43 overwrite the version line with `$NEXT`.
- [x] 3.6 Manually re-read the script to confirm the error messages on lines 30, 34, 36, and 49 now reference `"$RELEASE_BRANCH"` (or literally `$RELEASE_BRANCH` where the variable expands inside the message). The banner "branch '$BRANCH' already exists on remote" messages should still read naturally.

## 4. Parameterize `scripts/release.sh`

- [x] 4.1 Near the top of the script (alongside the existing `SCRIPT_DIR` setup), add `RELEASE_BRANCH="${RELEASE_BRANCH:-v0.2}"` so the variable is available before the PR lookup.
- [x] 4.2 Replace the literal `--base v0.1` on line 47 (`gh pr list --head "$BRANCH" --base v0.1 ...`) with `--base "$RELEASE_BRANCH"`.
- [x] 4.3 Replace the literal `v0.1` in the error message on line 49 (`"could not find an open PR with head '$BRANCH' into v0.1."`) with `$RELEASE_BRANCH` so the message stays accurate under an override.
- [x] 4.4 Leave the "release-<version> branch" contract check on lines 33-37 untouched — it derives the version from the branch name, which is orthogonal to `RELEASE_BRANCH`.

## 5. Docs: `localdev/release.md`

- [x] 5.1 Rewrite the "Branch model" section (currently lines 3-17). Replace the `v0.1` diagram with a `v0.2`-oriented one, show `main` as `0.0.0-dev`, and note that `RELEASE_BRANCH` overrides the target branch for future major lines.
- [x] 5.2 Remove or rewrite the bullet "main never gets the version bump — it stays at the previous release version." The new invariant is "main carries a `0.0.0-dev` sentinel; the release script resolves the resulting `pyproject.toml` conflict deterministically."
- [x] 5.3 Update Step 1 (lines 28-34) to reference `v0.2` instead of `v0.1` in the prose ("creates `release-<next>` branch from `v0.2`", "opens a PR: `release-<next>` → `v0.2`").
- [x] 5.4 Update Step 3 (lines 49-54) to reference `v0.2` in the `release-create.yml` description.
- [x] 5.5 Add a short "Archived release lines" paragraph noting that `v0.1` is no longer wired into CI, that existing `@v0.1` install URLs still resolve, and that a 0.1.x patch would require explicitly re-adding the CI triggers and running with `RELEASE_BRANCH=v0.1`.

## 6. Docs: `README.md`

- [x] 6.1 Replace every install-URL occurrence of `git+https://github.com/nicolai-budico/localbox.git@v0.1` with `@v0.2`. Specifically check around lines 41, 44, and 60 (per the exploration report) but grep the whole file to be safe.
- [x] 6.2 Replace the `@v0.1.0` specific-pin example with `@v0.2.0`.
- [x] 6.3 Grep the README for any prose that names `v0.1` as "the release branch" and update it to `v0.2`.

## 7. Docs: `docs/getting-started.md` and `docs/developer-guide.md`

- [x] 7.1 In `docs/getting-started.md`, replace install URLs (`@v0.1` → `@v0.2`) and update any prose describing the release branch.
- [x] 7.2 In `docs/developer-guide.md`, update the branch diagram (if present) and any prose referring to `v0.1` as the active release target; note the `v0.1` archive status briefly.
- [x] 7.3 Grep the entire `docs/` tree for `v0.1` one final time. Any remaining reference should either update to `v0.2` or explicitly acknowledge that `v0.1` is archived.

## 8. Release gate

- [x] 8.1 `ruff format src/ tests/` — clean (no formatter changes, since the edits are script/config/docs, not Python).
- [x] 8.2 `ruff check src/ tests/` — clean.
- [x] 8.3 `mypy src/localbox/` — clean.
- [x] 8.4 `pytest tests/ -q` — all existing tests pass (this change does not add new tests).
- [x] 8.5 `bash -n scripts/create-release-pr.sh` and `bash -n scripts/release.sh` — syntax check.

## 9. Open PR, merge, then cut `v0.2`

- [x] 9.1 Push a feature branch with all of the above changes. Open a PR into `main` with a descriptive title (e.g., `chore: prepare v0.2 release line and retire v0.1`) and a body summarizing Sections 1-7 above. Wait for CI green.
- [x] 9.2 Merge the PR with `gh pr merge --merge` (the default strategy for this repo; preserves the Verified merge commit).
- [x] 9.3 After merge, from a clean checkout of the updated `main`, run `git push origin main:refs/heads/v0.2`. This pushes the `main` HEAD to a new `v0.2` branch and triggers `.github/workflows/release-create.yml` (now listening on `v0.2`), which tags `v0.2.0` and publishes the GitHub Release.
- [x] 9.4 Verify: `gh release view v0.2.0` shows a release with auto-generated notes; `git ls-remote --tags origin v0.2.0` lists the tag; `gh run list --workflow=release-create.yml --limit 1` shows the run completed successfully.

## 10. Smoke-test the release scripts against `v0.2`

- [x] 10.1 From a clean tree on the updated `main`, run `./scripts/create-release-pr.sh`. Expected: the script reads `0.2.0` from `origin/v0.2`, computes `NEXT=0.2.1`, creates `release-0.2.1`, merges `main` (resolving the `pyproject.toml` conflict automatically), bumps the version to `0.2.1`, pushes the branch, opens a PR into `v0.2`, and blocks on CI until green.
- [x] 10.2 Confirm the PR exists (`gh pr list --base v0.2 --head release-0.2.1`) with CI passing.
- [x] 10.3 **Close the PR without merging** — this is a smoke test, not a real release. Delete the remote branch with `git push origin --delete release-0.2.1` and the local branch with `git branch -D release-0.2.1` after switching back to `main`.
- [x] 10.4 Document the smoke-test result in the PR that landed Section 1-7 (as a follow-up comment) so future readers can see the mechanism was validated.

## 11. Archive the OpenSpec change

- [x] 11.1 After Sections 1-10 are complete and the smoke test has been confirmed, move `openspec/changes/prepare-v0-2-release-line/` to `openspec/changes/archive/2026-MM-DD-prepare-v0-2-release-line/` using the date of archival. Matches the archive pattern used for `2026-04-10-release-full-cycle-script` and other completed changes.
