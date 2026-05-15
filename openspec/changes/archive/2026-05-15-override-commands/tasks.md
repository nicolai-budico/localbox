## 1. Shared Infrastructure

- [x] 1.1 Expose `load_solution(override=False)` flag (or equivalent) so solution can be loaded without `solution-override.py` to read pristine defaults
- [x] 1.2 Extract a `_find_override_line(lines, identifier)` helper that, given the file lines and a dotted identifier (`env.KEY`, `config.ATTR`, `project.G.N.path`), returns the matching line index (commented or uncommented) using AST-based matching
- [x] 1.3 Define the identifier namespace mapping: `env.KEY` → `solution.config.env.KEY` / `solution.config.env["KEY"]`, `config.ATTR` → `solution.config.ATTR`, `project.G.N.path` → `p.g.n.path`

## 2. `override list` Command

- [x] 2.1 Add `@override.command("list")` Click command in `src/localbox/cli.py`
- [x] 2.2 Load solution without override file to collect defaults (env vars + config attrs + project paths)
- [x] 2.3 Parse existing `solution-override.py` (via `_parse_existing_override`) to collect active overrides; handle missing file gracefully with a notice
- [x] 2.4 Build and render output table: required env vars section first (red/bold, `None` default), then optional env vars, config attributes, project paths — each showing identifier, default, and override (if set)
- [x] 2.5 Write tests for `list` covering: no override file, all-defaults, partial overrides, required fields highlighted

## 3. `override set` Command

- [x] 3.1 Add `@override.command("set")` Click command with `identifier` and `value` arguments
- [x] 3.2 Fail with clear message if `solution-override.py` does not exist (direct to `override init`)
- [x] 3.3 Use `_find_override_line` to locate the line; if not found, fail with unknown-identifier error
- [x] 3.4 Replace the matched line with the uncommented, updated assignment (value verbatim); handle both `= None  # REQUIRED` and commented forms
- [x] 3.5 Write file back; print confirmation (`set env.DB_PASS = "secret"`)
- [x] 3.6 Write tests: set required field, set optional (commented) field, update existing value, unknown identifier error, no override file error

## 4. `override clear` Command

- [x] 4.1 Add `@override.command("clear")` Click command with `identifier` argument
- [x] 4.2 Fail with clear message if `solution-override.py` does not exist (direct to `override init`)
- [x] 4.3 Use `_find_override_line` to locate the line; if not found, fail with unknown-identifier error
- [x] 4.4 If line is already commented out, print notice and exit cleanly (no file change)
- [x] 4.5 If field is required (`None` default), restore to `= None  # REQUIRED — set a value` form (do NOT comment out)
- [x] 4.6 Otherwise comment out the line with `# ` prefix
- [x] 4.7 Write file back; print confirmation
- [x] 4.8 Write tests: clear set value, clear required field (restores None), already-cleared no-op, unknown identifier error, no override file error

## 5. Quality

- [x] 5.1 Run `ruff format src/ tests/`, `ruff check src/ tests/`, `mypy src/localbox/`, `pytest tests/ -q` — all must pass
