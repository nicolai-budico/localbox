## Context

After a successful build, `_write_last_build(source_dir)` writes `.last-build` into the cloned project's source directory (e.g. `.build/projects/pet_clinic/.last-build`). That directory is a git working tree, so the file appears in `git status` as an untracked file on every developer machine after the first build.

The timestamp is consumed only by `show_project_status` (`projects status`) to display the "Last Build" age column. No other code reads or writes it.

The `.build/` directory is already gitignored at the solution level, making it the natural home for all localbox-generated state.

## Goals / Non-Goals

**Goals:**

- Move timestamp storage out of project git working trees
- Preserve the "Last Build" column in `projects status`
- Clean up any `.last-build` files already written into project repos on the next successful build

**Non-Goals:**

- Changing the format or precision of the timestamp
- Surfacing last-build time anywhere other than `projects status`
- Migrating existing `.last-build` files automatically (stale entries in repos are harmless — `git clean` or the next build handles them)

## Decisions

### New path: `.build/last-build/<project-name>`

Store the marker at `solution.directories.build / "last-build" / project.name` (e.g. `.build/last-build/pet_clinic`).

**Rationale**: `.build/` is already created and gitignored by localbox. A flat `last-build/` subdirectory keeps all build-state metadata together. Using `project.name` as the filename is unambiguous and matches the log file convention (`.build/logs/<project-name>.log`).

Alternative considered: keep the file inside the source dir but add it to the project repo's `.gitignore`. Rejected — it requires mutating the developer's repo, which localbox should not do.

### Old file cleanup on successful build

When writing the new marker, also delete `<source_dir>/.last-build` if it exists.

**Rationale**: Silently cleans up stale files left by earlier localbox versions without requiring a migration step or user action.

## Risks / Trade-offs

- **Loss of history on first run**: existing `.last-build` files inside repos are not migrated to the new location — "Last Build" shows "never" for projects not yet rebuilt after the update. Acceptable: the data is informational only.
- **Multiple solution roots sharing a `.build/`**: unlikely in practice; if it occurs, project names could collide in the `last-build/` dir. Mitigation: same risk already exists for `.build/logs/`; no new action needed.
