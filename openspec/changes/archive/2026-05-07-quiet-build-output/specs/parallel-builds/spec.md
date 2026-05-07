## MODIFIED Requirements

### Requirement: projects build accepts parallel jobs flag
`localbox projects build` SHALL accept a `-j <jobs>` / `--jobs <jobs>` option with a default of `1`. When `jobs > 1`, projects within the same dependency tier SHALL be built concurrently up to `<jobs>` workers. Projects in different tiers SHALL still execute sequentially (tier N completes before tier N+1 starts). When omitted (default `1`), behaviour is fully sequential and unchanged.

#### Scenario: Parallel build within a tier
- **WHEN** `localbox projects build -j 4` is run with multiple projects in the same dependency tier
- **THEN** up to 4 projects in that tier are built concurrently
- **THEN** the next tier starts only after all builds in the current tier complete

#### Scenario: j=1 is identical to no flag
- **WHEN** `localbox projects build -j 1` is run
- **THEN** builds execute sequentially, identical to running without `-j`

#### Scenario: j=auto uses cpu count
- **WHEN** `localbox projects build -j auto` (or `-j 0`) is run
- **THEN** worker count equals `os.cpu_count()`

#### Scenario: Quiet parallel output shows one status line per job
- **WHEN** parallel builds are running in default (quiet) mode
- **THEN** each job prints its own `[<project-name>] Building...` / `OK` / `FAILED` status lines
- **THEN** no raw Docker container output appears on stdout

#### Scenario: Verbose parallel output is raw Docker output
- **WHEN** `localbox projects build -j 4 --verbose` is run
- **THEN** all Docker container output is streamed to stdout without line prefixing
- **THEN** output from concurrent jobs may interleave; the `[<project-name>]` prefix is NOT added in verbose mode

### Requirement: services build accepts parallel jobs flag
`localbox services build` SHALL accept a `-j <jobs>` / `--jobs <jobs>` option with a default of `1`. All service images are independent; when `jobs > 1`, all services SHALL be submitted to a thread pool up to `<jobs>` workers simultaneously. When omitted (default `1`), behaviour is fully sequential and unchanged.

#### Scenario: Parallel service image builds
- **WHEN** `localbox services build -j 4` is run with multiple services
- **THEN** up to 4 service images are built concurrently

#### Scenario: Manifest flag compatible with parallel flag
- **WHEN** `localbox services build -j 2 --manifest assembles/v1.json` is run
- **THEN** images are built in parallel and each is additionally tagged with the manifest registry coordinates

#### Scenario: Quiet parallel service output shows one status line per job
- **WHEN** parallel service builds are running in default (quiet) mode
- **THEN** each service prints its own `[<service-name>] Building...` / `OK` / `FAILED` status lines

#### Scenario: Verbose parallel service output is raw Docker output
- **WHEN** `localbox services build -j 4 --verbose` is run
- **THEN** all Docker output is streamed to stdout without line prefixing; interleaving is expected in parallel mode
