# cli-structure Specification

## Purpose

Defines the top-level structure and grammar of the `localbox` CLI: which command groups (domains) exist, how sub-commands are organized under them, how target arguments are parsed under each domain, and how shell completion reflects this structure.

## Requirements

### Requirement: Top-level CLI uses domain-first grammar

The `localbox` CLI SHALL accept commands in the form `localbox <domain> <command> [args…]`, where `<domain>` is one of `projects`, `services`, `compose`, `override`, `solution`. The previous shape `localbox <command> <domain>[:path]` SHALL NOT be accepted; invoking a legacy verb at the top level SHALL produce a Click "no such command" error with a non-zero exit status.

#### Scenario: Domain help lists sub-commands
- **WHEN** the user runs `localbox projects --help`
- **THEN** the CLI SHALL print a help block listing `clone`, `fetch`, `switch`, `build`, `status`, `clean`, `list` as sub-commands and exit 0

#### Scenario: Legacy top-level verb is rejected
- **WHEN** the user runs `localbox clone projects:api`
- **THEN** the CLI SHALL exit with a non-zero status and print a Click "No such command 'clone'" error

#### Scenario: Unknown domain is rejected
- **WHEN** the user runs `localbox widgets list`
- **THEN** the CLI SHALL exit with a non-zero status and print a Click "No such command 'widgets'" error

### Requirement: Utility commands remain top-level

Commands that are not scoped to a domain SHALL remain at the top level: `doctor`, `config`, `completion`, `purge`, `prune`, and the domain-groups themselves. `prune` SHALL keep its existing sub-verbs (`caches`, `builders`, `images`, `all`). `completion` SHALL keep its positional shell argument.

#### Scenario: Doctor runs at top level
- **WHEN** the user runs `localbox doctor`
- **THEN** the CLI SHALL execute the system-requirements check and exit 0 when all checks pass

#### Scenario: Prune keeps its sub-verb shape
- **WHEN** the user runs `localbox prune caches`
- **THEN** the CLI SHALL remove builder cache directories under `.build/` and exit 0

#### Scenario: Completion keeps shell argument
- **WHEN** the user runs `localbox completion bash`
- **THEN** the CLI SHALL print the bash completion script to stdout and exit 0

### Requirement: Targets under a domain group use short-form paths

When a command lives under a domain group, its target arguments SHALL be parsed within that domain. Targets SHALL be given as `<group>[:<name>]` (or `<name>` for ungrouped items), without the redundant `projects:` or `services:` domain prefix. A command SHALL accept multiple target arguments, and each argument SHALL be resolved independently within the command's domain.

#### Scenario: Single short-form target
- **WHEN** the user runs `localbox projects build api`
- **THEN** the CLI SHALL resolve `api` against the projects domain and build the matching project

#### Scenario: Multiple short-form targets across groups
- **WHEN** the user runs `localbox projects build be:api fe:api workers`
- **THEN** the CLI SHALL resolve each token independently within the projects domain (`be:api`, `fe:api`, and the whole group `workers`) and build the union of matched projects

#### Scenario: Omitted target defaults to whole domain
- **WHEN** the user runs `localbox projects build` with no positional arguments
- **THEN** the CLI SHALL build all projects defined in the solution

#### Scenario: Domain-prefixed target is rejected under a domain group
- **WHEN** the user runs `localbox projects build projects:api`
- **THEN** the CLI SHALL exit with a non-zero status and print an error indicating that targets under `projects` must be given as `<group>[:<name>]`, not `projects:…`

### Requirement: `projects` domain group

The `projects` domain SHALL expose the sub-commands `clone`, `fetch`, `switch`, `build`, `status`, `clean`, `list`. Each SHALL operate on projects resolved from its positional target arguments, using the short-form path rules above. `build` SHALL keep its `--no-cache` and `--keep-going/-k` flags. `switch` SHALL keep its `--branch/-b` flag. `list` SHALL render the projects tree (equivalent to the legacy `localbox list projects`).

#### Scenario: Projects build with flags
- **WHEN** the user runs `localbox projects build api --no-cache -k`
- **THEN** the CLI SHALL build the `api` project with Docker layer cache disabled and continue past individual failures

#### Scenario: Projects switch with branch flag
- **WHEN** the user runs `localbox projects switch api -b feature-x`
- **THEN** the CLI SHALL switch the `api` project's working tree to branch `feature-x`

#### Scenario: Projects list renders tree
- **WHEN** the user runs `localbox projects list`
- **THEN** the CLI SHALL render a rich tree of all projects grouped by their `group` attribute

### Requirement: `services` domain group

The `services` domain SHALL expose the sub-commands `build` and `list`. `build` SHALL build service Docker images from their configured `DockerImage` definitions and SHALL keep its `--no-cache` flag. `list` SHALL render the services tree (equivalent to the legacy `localbox list services`). The `services build` command SHALL accept multiple short-form target arguments just like `projects build`.

#### Scenario: Services build across groups
- **WHEN** the user runs `localbox services build db:primary cache`
- **THEN** the CLI SHALL build the image for `db:primary` and the images for every service in group `cache`

#### Scenario: Services list renders tree
- **WHEN** the user runs `localbox services list`
- **THEN** the CLI SHALL render a rich tree of all services grouped by their `group` attribute

### Requirement: `compose` domain group

The `compose` domain SHALL expose the sub-command `generate`, which SHALL write `docker-compose.yml` from the solution's service definitions. The domain SHALL remain a Click group (not a standalone command) so future compose-related sub-verbs can be added without re-shaping the CLI.

#### Scenario: Compose generate writes docker-compose.yml
- **WHEN** the user runs `localbox compose generate` inside a solution
- **THEN** the CLI SHALL write a valid `docker-compose.yml` at the solution root and exit 0

### Requirement: `override` domain group

The `override` domain SHALL expose the sub-command `init`, which SHALL replace the legacy top-level `init-override` command. `override init` SHALL keep the `--force/-f` flag and the existing merge-and-backup behavior of `init-override`. The domain SHALL be structured as a Click group so future sub-verbs (`show`, `set`, `clear`) can be added without further restructuring; those sub-verbs are out of scope for this change.

#### Scenario: Override init creates template
- **WHEN** the user runs `localbox override init` inside a solution with no existing `solution-override.py`
- **THEN** the CLI SHALL write a new `solution-override.py` based on the loaded solution and exit 0

#### Scenario: Override init without --force refuses to overwrite
- **WHEN** `solution-override.py` already exists and the user runs `localbox override init` without `--force`
- **THEN** the CLI SHALL print a warning and exit with a non-zero status, leaving the existing file untouched

#### Scenario: Override init --force merges existing values
- **WHEN** `solution-override.py` already exists and the user runs `localbox override init --force`
- **THEN** the CLI SHALL back up the existing file to `solution-override-<timestamp>.py`, regenerate the template, and preserve values that had been set in the old file

### Requirement: `solution` domain group

The `solution` domain SHALL expose the sub-command `init`, which SHALL replace the legacy top-level `init` command. `solution init` SHALL keep the `--force/-f` flag and the existing behavior of creating `solution.py`, the `assets/` and `patches/` directories, and updating `.gitignore`.

#### Scenario: Solution init creates scaffold
- **WHEN** the user runs `localbox solution init` in an empty directory
- **THEN** the CLI SHALL create `solution.py`, `assets/`, `patches/`, and update `.gitignore` with `.logs/`, the override filename, and `.build/`

#### Scenario: Solution init without --force refuses to overwrite
- **WHEN** `solution.py` already exists and the user runs `localbox solution init` without `--force`
- **THEN** the CLI SHALL print a warning and exit with a non-zero status, leaving the existing file untouched

### Requirement: Shell completion reflects the new grammar

Shell completion (bash, zsh, fish) SHALL be updated so that:
- At the top level, completion suggests the domain groups (`projects`, `services`, `compose`, `override`, `solution`) alongside the utility commands (`doctor`, `config`, `completion`, `purge`, `prune`).
- After typing a domain group, completion suggests that domain's sub-commands.
- For commands that take targets under a domain group, completion suggests short-form tokens (`<group>`, `<group>:<name>`, or ungrouped `<name>`) — it SHALL NOT suggest domain-prefixed tokens like `projects:<group>` there.

#### Scenario: Top-level completion lists domains
- **WHEN** the user types `localbox <TAB>`
- **THEN** completion SHALL include at minimum `projects`, `services`, `compose`, `override`, `solution`, `doctor`, `config`, `completion`, `purge`, `prune`

#### Scenario: Sub-command completion under domain
- **WHEN** the user types `localbox projects <TAB>`
- **THEN** completion SHALL include `clone`, `fetch`, `switch`, `build`, `status`, `clean`, `list`

#### Scenario: Target completion is short-form under a domain
- **WHEN** the user types `localbox projects build <TAB>` in a solution with groups `be`, `fe` and project `be:api`
- **THEN** completion SHALL include `be`, `fe`, `be:api` and SHALL NOT include `projects:be` or `projects:be:api`

### Requirement: `build` no longer sniffs the first target for the domain

The implementation of `build` SHALL live under its domain group (`projects build` and `services build`) and SHALL NOT inspect the first positional argument to decide whether to dispatch to project-build or service-build logic. Each domain's `build` command SHALL call only its own resolver and its own build entry point.

#### Scenario: Projects build does not fall through to services
- **WHEN** the user runs `localbox projects build db` in a solution where `db` is a service group but not a project group
- **THEN** the CLI SHALL fail target resolution with a `TargetError` scoped to the projects domain and SHALL NOT attempt to build services

#### Scenario: Services build does not fall through to projects
- **WHEN** the user runs `localbox services build api` in a solution where `api` is a project but not a service
- **THEN** the CLI SHALL fail target resolution with a `TargetError` scoped to the services domain and SHALL NOT attempt to build projects
