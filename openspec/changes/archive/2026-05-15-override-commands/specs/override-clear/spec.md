## ADDED Requirements

### Requirement: Clear a single override value
`localbox override clear <identifier>` SHALL revert a single overridden field in `solution-override.py` back to its default by commenting out the active line. The rest of the file SHALL remain unchanged.

#### Scenario: Clearing a set env var
- **WHEN** `localbox override clear env.DB_PASS` is run
- **AND** `solution-override.py` contains `solution.config.env.DB_PASS = "secret"`
- **THEN** that line SHALL become `# solution.config.env.DB_PASS = "secret"`

#### Scenario: Clearing a config attribute
- **WHEN** `localbox override clear config.build_dir` is run
- **AND** `solution-override.py` contains `solution.config.build_dir = ".dist"`
- **THEN** that line SHALL become `# solution.config.build_dir = ".dist"`

#### Scenario: Clearing an already-commented identifier
- **WHEN** `localbox override clear env.LOG_LEVEL` is run
- **AND** the line is already commented out in `solution-override.py`
- **THEN** the command SHALL succeed with a notice that the identifier was already at its default (no file change)

#### Scenario: Identifier not found in override file
- **WHEN** `localbox override clear env.UNKNOWN_KEY` is run
- **AND** no matching line exists in `solution-override.py`
- **THEN** the command SHALL fail with a clear error naming the unknown identifier

### Requirement: Require override file before clear
`clear` SHALL fail with a clear error if `solution-override.py` does not exist, directing the user to run `localbox override init` first.

#### Scenario: No override file present
- **WHEN** `localbox override clear env.KEY` is run and no `solution-override.py` exists
- **THEN** the command SHALL exit with a non-zero status and print a message directing the user to `localbox override init`

### Requirement: Clearing a required field restores REQUIRED annotation
If a field was originally generated as `= None  # REQUIRED — set a value` and has since been set, `clear` SHALL restore it to the `= None  # REQUIRED — set a value` form rather than commenting it out, because commenting it out would silently suppress the required warning.

#### Scenario: Clearing a previously-required env var
- **WHEN** `localbox override clear env.DB_PASS` is run
- **AND** `env.DB_PASS` has a `None` default (required field)
- **THEN** the line SHALL become `solution.config.env.DB_PASS = None  # REQUIRED — set a value`
- **AND** SHALL NOT be commented out
