## Why

After a successful build, localbox writes `.last-build` into the cloned project's source directory. Because that directory is a git working tree, the file shows up in `git status` as an untracked file, making every repo appear dirty after the first build. This is confusing and interferes with scripts that check for a clean working tree.

## What Changes

- Remove `_write_last_build` / `_read_last_build` from writing into the project source directory
- Store the timestamp in `.build/last-build/<project-name>` (inside the solution build directory, which is already gitignored) instead
- `projects status` "Last Build" column continues to work — only the storage location changes
- Remove any `.last-build` file that already exists inside project repos (on the next build)

## Capabilities

### New Capabilities

<!-- None — this is a relocation, not a new user-facing capability -->

### Modified Capabilities

- `quiet-build`: build completion tracking changes storage path — the timestamp is written outside the project repo instead of inside it

## Impact

- `src/localbox/commands/project.py` — `_write_last_build`, `_read_last_build`, `_LAST_BUILD_FILE`
- Storage path: `<project_source_dir>/.last-build` → `<solution.directories.build>/last-build/<project_name>`
- No CLI interface changes; no model changes
- `.gitignore` in project repos: no longer needs to mention `.last-build` (though existing entries are harmless)
