## ADDED Requirements

### Requirement: projects fetch accepts force flag
`localbox projects fetch` SHALL accept a `--force` flag. When provided, each project SHALL be reset to a clean copy of `origin/<configured-branch>` via the sequence: `git fetch --all`, `git reset --hard origin/<branch>`, `git clean -fd`. When omitted, existing `git pull --rebase` behaviour is unchanged.

`<configured-branch>` is `project.git.branch` if set, otherwise `solution.default_branch`.

#### Scenario: Force fetch on dirty working tree
- **WHEN** `localbox projects fetch --force` is run with modified tracked files present
- **THEN** modifications are discarded and repo HEAD matches `origin/<configured-branch>`

#### Scenario: Force fetch on detached HEAD
- **WHEN** `localbox projects fetch --force` is run on a repo in detached HEAD state (e.g., left by `switch --manifest`)
- **THEN** repo is reset to `origin/<configured-branch>` and is no longer in detached HEAD state

#### Scenario: Force fetch removes untracked artifacts
- **WHEN** `localbox projects fetch --force` is run with untracked build artifacts present
- **THEN** untracked files are deleted by `git clean -fd`

#### Scenario: No-force fetch is unchanged
- **WHEN** `localbox projects fetch` is run without `--force`
- **THEN** behaviour is identical to before this change (git pull --rebase)
