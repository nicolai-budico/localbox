# manifest-flow Specification

## Purpose

Defines the manifest JSON format and the CLI commands that produce and consume manifests: `manifest generate`, `projects switch --manifest`, `services build --manifest`, and `services push --manifest`. Manifests are assemble snapshots used to reproduce a specific build: they record the exact git SHAs of all solution repositories plus the registry coordinates for published Docker images.

## Requirements

### Requirement: Manifest JSON format

A manifest is a JSON file with the following top-level fields:

- `tag` (string, required) — the assemble tag; used as the Docker image tag in remote refs.
- `registry` (string, required) — Docker registry prefix; combined with solution name, service name, and tag to form remote image refs as `{registry}/{solution}/service/{service.image.name}:{tag}`.
- `repositories` (object, required) — keyed by `project.path_name`; each value is an object with `commit` (git SHA string) and `remote` (git remote URL string). Written by `manifest generate`.
- `extra` (object, optional) — arbitrary string key-value pairs; may be absent.

#### Scenario: Manifest contains required top-level fields
- **WHEN** `manifest generate` runs successfully
- **THEN** the output JSON SHALL contain `tag`, `registry`, and `repositories` as top-level keys

#### Scenario: Extra section is absent when no --extra flags given
- **WHEN** `manifest generate` runs without any `--extra` flags
- **THEN** the manifest file SHALL NOT contain an `extra` key

### Requirement: `manifest` command group exists

A `manifest` Click group SHALL be registered at the top level in `cli.py`. It SHALL
expose the subcommand `generate`. The group SHALL be structured as a Click group so
future subcommands can be added without reshaping the CLI.

#### Scenario: manifest group help lists generate
- **WHEN** the user runs `localbox manifest --help`
- **THEN** the CLI SHALL print a help block listing `generate` as a subcommand and exit 0

### Requirement: `manifest generate` writes a manifest from current checkout state

`localbox manifest generate --manifest=<path> --tag=<tag> [--registry=<registry>] [--extra <key>=<value> ...]`
SHALL iterate all projects configured in the solution, read each project's source
directory to obtain the HEAD commit SHA (`git rev-parse HEAD`) and `origin` remote URL
(`git remote get-url origin`), and write the manifest JSON at `<path>`. The parent
directory of `<path>` SHALL be created if it does not exist.

`--tag` is required. `--registry` is optional; when omitted, `solution.config.registry`
is used. If neither `--registry` nor `solution.config.registry` is set, the command SHALL
exit non-zero with an error message.

`--extra` may be supplied multiple times as `key=value` pairs. All values are stored as
strings. Extra pairs are written under the top-level `"extra"` key.

Only solution projects are recorded in `"repositories"`. The localbox solution repo
itself is not included.

#### Scenario: manifest generate writes all configured projects
- **GIVEN** a solution with projects `api` and `worker`, both cloned to their source directories
- **WHEN** the user runs `localbox manifest generate --manifest out.json --tag v1 --registry reg.example.com`
- **THEN** `out.json` SHALL exist and SHALL contain `"tag": "v1"`, `"registry": "reg.example.com"`, and a `"repositories"` object with keys `api` and `worker`, each having non-empty `"commit"` and `"remote"` strings

#### Scenario: manifest generate uses solution.config.registry when --registry omitted
- **GIVEN** `solution.config.registry` is set to `"reg.example.com"`
- **WHEN** the user runs `localbox manifest generate --manifest out.json --tag v1` (no `--registry`)
- **THEN** `out.json` SHALL contain `"registry": "reg.example.com"`

#### Scenario: manifest generate fails when no registry available
- **GIVEN** `solution.config.registry` is not set
- **WHEN** the user runs `localbox manifest generate --manifest out.json --tag v1` (no `--registry`)
- **THEN** the CLI SHALL exit non-zero and print an error indicating that registry must be provided

#### Scenario: manifest generate creates parent directories
- **GIVEN** the directory `assembles/` does not exist
- **WHEN** the user runs `localbox manifest generate --manifest assembles/v1.json --tag v1 --registry reg.example.com`
- **THEN** `assembles/` SHALL be created and `assembles/v1.json` SHALL be written without error

#### Scenario: manifest generate stores extra key-value pairs
- **WHEN** the user runs `localbox manifest generate --manifest out.json --tag v1 --registry reg.example.com --extra pr_number=42 --extra run_id=abc`
- **THEN** `out.json` SHALL contain `"extra": {"pr_number": "42", "run_id": "abc"}`

#### Scenario: manifest generate fails hard when any project source directory is missing
- **GIVEN** a solution with projects `api` and `worker`, where `worker` has not been cloned
- **WHEN** the user runs `localbox manifest generate`
- **THEN** the CLI SHALL exit non-zero and print an error listing `worker` as missing
- **AND** SHALL NOT write the manifest file

#### Scenario: --tag is required
- **WHEN** the user runs `localbox manifest generate --manifest out.json --registry reg.example.com` (no `--tag`)
- **THEN** the CLI SHALL exit non-zero and print a Click "Missing option '--tag'" error

### Requirement: `projects switch --manifest` checks out recorded SHAs

`localbox projects switch --manifest=<path>` SHALL read `repositories` from the manifest,
and for each entry run `git fetch --all` followed by `git checkout <commit>` in the
matching project's source directory. The match is by `project.path_name` equal to the
repository key. `--manifest` SHALL be mutually exclusive with positional `[targets]` and
`-b`/`--branch`; combining them SHALL be a hard `UsageError`.

If any repository key in the manifest does not match any configured project, the command
SHALL print an error for each unmatched key and exit non-zero without modifying any
repository.

#### Scenario: switch --manifest checks out all recorded commits
- **GIVEN** a manifest with `repositories: {"api": {"commit": "abc123", ...}, "worker": {"commit": "def456", ...}}`
- **AND** both projects are cloned
- **WHEN** the user runs `localbox projects switch --manifest out.json`
- **THEN** the `api` source directory SHALL be at commit `abc123`
- **AND** the `worker` source directory SHALL be at commit `def456`

#### Scenario: switch --manifest fails when any repo key is unmatched
- **GIVEN** a manifest containing key `unknown-service` which is not a configured project
- **WHEN** the user runs `localbox projects switch --manifest out.json`
- **THEN** the CLI SHALL exit non-zero and print an error naming `unknown-service` as unmatched
- **AND** SHALL NOT modify any repository

#### Scenario: switch --manifest is mutually exclusive with targets
- **WHEN** the user runs `localbox projects switch api --manifest out.json`
- **THEN** the CLI SHALL exit non-zero with a UsageError indicating `--manifest` cannot be combined with targets or `-b`

#### Scenario: switch --manifest is mutually exclusive with -b
- **WHEN** the user runs `localbox projects switch --manifest out.json -b main`
- **THEN** the CLI SHALL exit non-zero with a UsageError indicating `--manifest` cannot be combined with targets or `-b`

### Requirement: `services build --manifest` tags images with manifest coordinates

`localbox services build [targets] [--no-cache] [--manifest=<path>]` SHALL, when
`--manifest` is provided, build each service image directly with the manifest registry tag
(`{registry}/{solution}/service/{service.image.name}:latest`) as the local tag, then apply
an additional versioned remote tag (`{registry}/{solution}/service/{service.image.name}:{tag}`)
via `docker tag`. Both `registry` and `tag` are read from the manifest. The remote tag
pattern SHALL be identical to the tag pushed by `services push --manifest`.

#### Scenario: services build --manifest applies manifest registry tags
- **GIVEN** a manifest with `registry="reg.example.com"` and `tag="v1"` and solution name `"mysol"`
- **AND** a service with `image.name="api"`
- **WHEN** the user runs `localbox services build --manifest out.json`
- **THEN** the image SHALL be built as `reg.example.com/mysol/service/api:latest`
- **AND** additionally tagged as `reg.example.com/mysol/service/api:v1`
- **AND** the solution-level registry (from `solution.config.registry`) SHALL be ignored

#### Scenario: services build without --manifest applies only local tag
- **WHEN** the user runs `localbox services build` with no `--manifest`
- **THEN** only the local image tag SHALL be applied; no remote tag or manifest update SHALL occur

### Requirement: `services push --manifest` pushes all service images to registry

`localbox services push --manifest=<path>` SHALL read `registry` and `tag` from the
manifest and run `docker push {registry}/{solution}/service/{service.image.name}:{tag}` for
every service in the solution. The command SHALL push all services; target filtering is not
supported. The caller is responsible for running `docker login` before invoking this
command. The remote tag pattern SHALL be identical to the one applied by
`services build --manifest`.

#### Scenario: services push pushes all services using manifest coordinates
- **GIVEN** a manifest with `registry="reg.example.com"` and `tag="v1"` and solution name `"mysol"`
- **AND** services `api` and `worker`
- **WHEN** the user runs `localbox services push --manifest out.json`
- **THEN** the CLI SHALL invoke `docker push reg.example.com/mysol/service/api:v1` and `docker push reg.example.com/mysol/service/worker:v1`

#### Scenario: services push --manifest is required
- **WHEN** the user runs `localbox services push` without `--manifest`
- **THEN** the CLI SHALL exit non-zero and print a Click "Missing option '--manifest'" error

#### Scenario: services push tag pattern matches services build tag pattern
- **GIVEN** the same manifest used for both `services build` and `services push`
- **THEN** the remote tag applied by `build` (`{registry}/{service.image.name}:{tag}`) SHALL equal the tag pushed by `push`
