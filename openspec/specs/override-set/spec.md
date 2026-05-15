# Spec: override-set

## Purpose

Defines the behaviour of `localbox override set <identifier> <value>`, which writes a single override value into `solution-override.py` by updating or uncommenting the matching line in-place while leaving the rest of the file untouched.

## Requirements

### Requirement: Set a single override value
`localbox override set <identifier> <value>` SHALL write the given value for the identified field into `solution-override.py`, either by uncommenting and replacing an existing commented line or by updating an already-uncommented line in-place. The rest of the file SHALL remain unchanged.

#### Scenario: Setting a required env var (currently None)
- **WHEN** `localbox override set env.DB_PASS "secret"` is run
- **AND** `solution-override.py` contains `solution.config.env.DB_PASS = None  # REQUIRED — set a value`
- **THEN** that line SHALL become `solution.config.env.DB_PASS = "secret"`
- **AND** the `# REQUIRED` comment SHALL be removed

#### Scenario: Setting an optional env var (currently commented out)
- **WHEN** `localbox override set env.LOG_LEVEL "debug"` is run
- **AND** `solution-override.py` contains `# solution.config.env.LOG_LEVEL = "info"`
- **THEN** that line SHALL become `solution.config.env.LOG_LEVEL = "debug"`

#### Scenario: Updating an already-set value
- **WHEN** `localbox override set config.build_dir ".dist"` is run
- **AND** `solution-override.py` contains `solution.config.build_dir = ".build"`
- **THEN** that line SHALL become `solution.config.build_dir = ".dist"`

#### Scenario: Setting a project path override
- **WHEN** `localbox override set project.libs.utils.path "/home/dev/utils"` is run
- **THEN** the matching `p.libs.utils.path` line in `solution-override.py` SHALL be updated or uncommented with that value

#### Scenario: Identifier not found in override file
- **WHEN** `localbox override set env.UNKNOWN_KEY "x"` is run
- **AND** no matching line exists in `solution-override.py`
- **THEN** the command SHALL fail with a clear error naming the unknown identifier

### Requirement: Require override file before set
`set` SHALL fail with a clear error if `solution-override.py` does not exist, directing the user to run `localbox override init` first.

#### Scenario: No override file present
- **WHEN** `localbox override set env.KEY "val"` is run and no `solution-override.py` exists
- **THEN** the command SHALL exit with a non-zero status and print a message directing the user to `localbox override init`

### Requirement: Value is stored verbatim as Python literal
The value argument SHALL be written to the file exactly as provided, without additional quoting by the tool. The user is responsible for passing a valid Python literal (string in quotes, int, bool, etc.).

#### Scenario: String value with quotes
- **WHEN** the user runs `localbox override set env.HOST '"localhost"'` (shell-quoted to preserve inner quotes)
- **THEN** the written line SHALL contain `= "localhost"` (a valid Python string literal)

#### Scenario: Integer value
- **WHEN** `localbox override set config.build_workers 4` is run
- **THEN** the written line SHALL contain `= 4`
