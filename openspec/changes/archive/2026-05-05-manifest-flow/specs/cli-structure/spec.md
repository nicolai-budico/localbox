## MODIFIED Requirements

### Requirement: Top-level CLI uses domain-first grammar

The `localbox` CLI SHALL accept commands in the form `localbox <domain> <command> [args…]`, where `<domain>` is one of `projects`, `services`, `compose`, `override`, `solution`, `manifest`. The previous shape `localbox <command> <domain>[:path]` SHALL NOT be accepted; invoking a legacy verb at the top level SHALL produce a Click "no such command" error with a non-zero exit status.

#### Scenario: Domain help lists sub-commands
- **WHEN** the user runs `localbox projects --help`
- **THEN** the CLI SHALL print a help block listing `clone`, `fetch`, `switch`, `build`, `status`, `clean`, `list` as sub-commands and exit 0

#### Scenario: Legacy top-level verb is rejected
- **WHEN** the user runs `localbox clone projects:api`
- **THEN** the CLI SHALL exit with a non-zero status and print a Click "No such command 'clone'" error

#### Scenario: Unknown domain is rejected
- **WHEN** the user runs `localbox widgets list`
- **THEN** the CLI SHALL exit with a non-zero status and print a Click "No such command 'widgets'" error

### Requirement: `projects` domain group

The `projects` domain SHALL expose the sub-commands `clone`, `fetch`, `switch`, `build`, `status`, `clean`, `list`. Each SHALL operate on projects resolved from its positional target arguments, using the short-form path rules above. `build` SHALL keep its `--no-cache` and `--keep-going/-k` flags. `switch` SHALL keep its `--branch/-b` flag and SHALL additionally accept `--manifest=<path>`, which is mutually exclusive with `[targets]` and `-b`. `list` SHALL render the projects tree.

#### Scenario: Projects build with flags
- **WHEN** the user runs `localbox projects build api --no-cache -k`
- **THEN** the CLI SHALL build the `api` project with Docker layer cache disabled and continue past individual failures

#### Scenario: Projects switch with branch flag
- **WHEN** the user runs `localbox projects switch api -b feature-x`
- **THEN** the CLI SHALL switch the `api` project's working tree to branch `feature-x`

#### Scenario: Projects switch with manifest flag
- **WHEN** the user runs `localbox projects switch --manifest assembles/v1.json`
- **THEN** the CLI SHALL check out the recorded commit for each repository listed in the manifest

#### Scenario: Projects list renders tree
- **WHEN** the user runs `localbox projects list`
- **THEN** the CLI SHALL render a rich tree of all projects grouped by their `group` attribute

### Requirement: `services` domain group

The `services` domain SHALL expose the sub-commands `build`, `push`, and `list`. `build` SHALL build service Docker images from their configured `DockerImage` definitions, SHALL keep its `--no-cache` flag, and SHALL additionally accept `--manifest=<path>`. `push` SHALL push service images to a registry using coordinates from a required `--manifest=<path>` option. `list` SHALL render the services tree. The `services build` command SHALL accept multiple short-form target arguments just like `projects build`.

#### Scenario: Services build across groups
- **WHEN** the user runs `localbox services build db:primary cache`
- **THEN** the CLI SHALL build the image for `db:primary` and the images for every service in group `cache`

#### Scenario: Services build with manifest
- **WHEN** the user runs `localbox services build --manifest assembles/v1.json`
- **THEN** the CLI SHALL build all service images and apply remote tags using coordinates from the manifest

#### Scenario: Services push with manifest
- **WHEN** the user runs `localbox services push --manifest assembles/v1.json`
- **THEN** the CLI SHALL push all service images to the registry using coordinates from the manifest

#### Scenario: Services list renders tree
- **WHEN** the user runs `localbox services list`
- **THEN** the CLI SHALL render a rich tree of all services grouped by their `group` attribute
