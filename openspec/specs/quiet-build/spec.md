# Spec: quiet-build

## Purpose

Defines the default quiet output mode for `localbox projects build` and `localbox services build`, and the `--verbose` flag that restores full streaming output.

## Requirements

### Requirement: Build output is quiet by default
By default, `localbox projects build` and `localbox services build` SHALL suppress per-line Docker container output from the terminal. Instead they SHALL print a single start line when a job begins and a single result line when it completes. Full container output SHALL be written to a log file under `.build/logs/<job-name>.log` (relative to the solution root). The result line on failure SHALL include the log file path.

#### Scenario: Quiet mode start line
- **WHEN** a build job starts in default (quiet) mode
- **THEN** a line matching `[<name>] Building...` is printed to stdout

#### Scenario: Quiet mode success line
- **WHEN** a build job completes successfully in quiet mode
- **THEN** a line matching `[<name>] OK  (<N>s)` is printed to stdout

#### Scenario: Quiet mode failure line
- **WHEN** a build job exits with a non-zero code in quiet mode
- **THEN** a line matching `[<name>] FAILED (<N>s) — log: <path>` is printed to stdout

#### Scenario: Log file written in quiet mode
- **WHEN** a build job runs in quiet mode
- **THEN** a log file is created at `.build/logs/<job-name>.log` containing the full Docker container output

### Requirement: --verbose flag restores full output
`localbox projects build` and `localbox services build` SHALL accept a `--verbose` flag. When passed, all Docker container output SHALL be streamed to stdout and no quiet-mode status lines are printed. Behavior SHALL be identical to the pre-quiet-build output.

#### Scenario: Verbose streams Docker output
- **WHEN** `localbox projects build --verbose` is run
- **THEN** all Docker container output lines are written to stdout as they arrive

#### Scenario: Verbose suppresses status lines
- **WHEN** `localbox projects build --verbose` is run
- **THEN** no `Building...` / `OK` / `FAILED` status lines are printed by the build runner

#### Scenario: Verbose and parallel compatible
- **WHEN** `localbox projects build -j 4 --verbose` is run
- **THEN** all Docker container output from concurrent jobs is streamed to stdout without prefixing; interleaving is expected and acceptable
