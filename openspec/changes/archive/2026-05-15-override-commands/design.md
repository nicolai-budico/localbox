## Context

`solution-override.py` is a Python file that developers fill in manually to set env vars, config attributes, and project path/branch overrides. Currently the only `override` CLI command is `init`, which generates or regenerates that file. There is no CLI surface for reading or modifying individual values.

The file has a well-defined structure with three kinds of overridable identifiers:

| Kind | Line pattern | Example |
|---|---|---|
| Env var | `solution.config.env.KEY = VALUE` or `solution.config.env["KEY"] = VALUE` | `solution.config.env.DB_PASS = "secret"` |
| Config attr | `solution.config.ATTR = VALUE` | `solution.config.build_dir = ".build"` |
| Project attr | `p.group.name.path = VALUE` or `p.group.name.branch = VALUE` | `p.libs.utils.path = "/home/dev/utils"` |

Commented-out lines (prefixed `#`) mean "using default". Uncommented lines with `None` mean "required — not yet set".

The internal `_ParsedOverride` / `_parse_existing_override()` / `_rhs_source()` helpers already extract active values from the file.

## Goals / Non-Goals

**Goals:**

- `override list`: show every overridable identifier, its default, its current override (if any), and flag required fields visibly at the top
- `override set <id> <value>`: write one identifier's value into `solution-override.py` (uncomment the line or update the RHS in-place)
- `override clear <id>`: comment out one identifier's line, reverting to default
- Identifier syntax must be stable, tab-completable, and map 1:1 to the generated template lines

**Non-Goals:**

- Editing project `branch` via `set`/`clear` (deferred — branch is also managed by `switch`)
- Type validation of values (Python `eval`/type coercion is out of scope)
- Creating `solution-override.py` if it doesn't exist — use `override init` first

## Decisions

### Identifier namespace

Use a dot-prefixed namespace that mirrors the Python template lines exactly:

| Namespace | Identifier form | Maps to |
|---|---|---|
| `env` | `env.KEY` | `solution.config.env.KEY` |
| `config` | `config.ATTR` | `solution.config.ATTR` |
| `project` | `project.GROUP.NAME.path` | `p.group.name.path` |

**Rationale**: The generated file already uses these dotted forms. Reusing them avoids inventing a new identifier language, and users can copy-paste from the file.

Alternative considered: colon-syntax (`libs:utils.path`) — rejected because it conflicts with the existing group:name project target syntax, and the `p.*` form is already in the template.

### In-place file mutation for `set`/`clear`

Both commands mutate `solution-override.py` line-by-line (regex + AST) rather than regenerating via `_generate_override_template()`.

**Rationale**: Regeneration would discard manual comments and custom ordering. Line-by-line mutation is surgical and preserves the rest of the file. The file's comment/uncomment convention is already well-defined (`# ` prefix = commented out).

For `set`:
1. Scan for a line (commented or uncommented) whose LHS matches the identifier
2. Replace/uncomment it with the new value
3. If no line found, append to the appropriate section

For `clear`:
1. Find the uncommented line matching the identifier
2. Prefix it with `# ` (add default value comment if it was required/None)

### Default values for `list`

Load the solution **without** the override file (via existing `load_solution(override=False)` or equivalent — may need to expose this flag) to get pristine defaults. Then parse the current override file to show the delta.

**Rationale**: The override file itself doesn't carry the defaults — only the template comments do. Loading without override is authoritative.

### Required fields surfacing in `list`

Env vars whose default is `None` are "required". Display them in a dedicated `[REQUIRED]` section at the top of `list` output, with a clear visual indicator (e.g., red/bold), before optional/config/project sections.

## Risks / Trade-offs

- **Regex fragility on malformed files**: if a user has hand-edited the override file into non-standard shapes, line matching may miss entries. Mitigation: use AST parsing (same as `_rhs_source`) to validate matched lines; fall back to appending if not found.
- **`set` on a required field**: after `set`, the line changes from `= None  # REQUIRED` to `= <value>`. The `# REQUIRED` comment is dropped. Acceptable — the value being set makes the required annotation moot.
- **No solution-override.py present**: `set`/`clear` must fail with a clear message directing user to `override init`.
- **Dict-style env (`env["KEY"]`)**: both `env.KEY` and `env["KEY"]` forms exist in the template. The identifier `env.KEY` should match either form when scanning the file.

## Open Questions

- Should `set` accept quoted strings with spaces? (e.g. `localbox override set env.NAME "my value"`) — Click's argument handling makes this natural; document it.
- Should `clear` on a config attr restore the inline comment (e.g., `# Override to point all projects...`)? For simplicity: no, just comment the line.
