## ADDED Requirements

### Requirement: List all overridable identifiers
The `localbox override list` command SHALL display every overridable identifier in the current solution: env vars (class-based and dict-based), config attributes (build_dir, project_dir, default_branch, registry), and project path overrides. For each identifier it SHALL show the default value (from solution loaded without override) and the current override value (from solution-override.py, if set).

#### Scenario: No override file exists
- **WHEN** `localbox override list` is run and no `solution-override.py` exists
- **THEN** the command SHALL display all identifiers with only default values and a notice that no override file is present

#### Scenario: Override file exists with some values set
- **WHEN** `localbox override list` is run and `solution-override.py` exists
- **THEN** each identifier with an active override SHALL show both the default and the overridden value
- **AND** identifiers using their default SHALL show only the default

#### Scenario: Identifiers grouped by type
- **WHEN** `localbox override list` is run
- **THEN** output SHALL be grouped into sections: required env vars, optional env vars, config attributes, project paths

### Requirement: Required env vars displayed prominently
Env vars whose default value is `None` (marked `# REQUIRED`) SHALL be surfaced at the top of the output, visually distinct from optional fields, so that developers immediately see what must be set before the solution is usable.

#### Scenario: Solution has required env vars
- **WHEN** `localbox override list` is run and some env vars have a `None` default
- **THEN** those identifiers SHALL appear first under a `Required` or `[REQUIRED]` heading
- **AND** SHALL be visually highlighted (e.g., red or bold) to distinguish them from optional fields

#### Scenario: All required env vars are set in the override
- **WHEN** all env vars with `None` defaults have values set in `solution-override.py`
- **THEN** they SHALL still appear in the required section but WITHOUT a missing-value warning

#### Scenario: No required env vars
- **WHEN** no env var has a `None` default
- **THEN** the required section SHALL be omitted from the output

### Requirement: Identifier syntax matches set/clear commands
Each identifier shown by `list` SHALL use the same dotted namespace form accepted by `set` and `clear` (`env.KEY`, `config.ATTR`, `project.GROUP.NAME.path`), so that users can copy-paste from list output directly into a `set` or `clear` invocation.

#### Scenario: Output identifiers are copy-pasteable
- **WHEN** `localbox override list` shows identifier `env.DB_PASS`
- **THEN** `localbox override set env.DB_PASS "secret"` SHALL work without modification
