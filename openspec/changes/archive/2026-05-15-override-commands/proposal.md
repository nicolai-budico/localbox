## Why

The `override` domain has only `init`, leaving no way to inspect or modify individual override values without editing `solution-override.py` by hand. Developers need CLI commands to discover what can be overridden, see required vs optional fields, and set/clear individual values without regenerating the entire file.

## What Changes

- Add `localbox override list` — shows all overridable identifiers (env vars, config attrs, project paths/branches) with default and current overridden value; required (None) fields surfaced at top
- Add `localbox override set <identifier> <value>` — writes a single value into `solution-override.py`
- Add `localbox override clear <identifier>` — resets a single value back to its default (comments the line out)

## Capabilities

### New Capabilities

- `override-list`: Read and display all overridable identifiers with their default value, current override value, and required status
- `override-set`: Write a single override value into `solution-override.py` (env vars, config attrs, project paths/branches)
- `override-clear`: Remove/comment out a single override value in `solution-override.py`, reverting to default

### Modified Capabilities

<!-- No existing spec-level behavior changes -->

## Impact

- New commands added under `@override` Click group in `src/localbox/cli.py`
- Reads solution config (loaded without override file) to discover defaults
- Parses and mutates `solution-override.py` in-place for `set`/`clear`
- Re-uses `_parse_existing_override()` and related helpers; may need to expose or extend them
- No changes to models, builders, or other domains
