## ADDED Requirements

### Requirement: `compose generate` accepts manifest and explicit tag/registry flags

`localbox compose generate` SHALL accept three new optional flags:
- `--manifest=<path>` — reads `tag` and `registry` from the manifest file at `<path>`.
- `--tag=<tag>` — explicit image tag; must be used together with `--registry`.
- `--registry=<registry>` — explicit registry prefix; optional when `--tag` is used because
  `solution.config.registry` is used as a fallback.

`--manifest` and `--tag`/`--registry` SHALL be mutually exclusive: providing both SHALL be
a hard `UsageError`. When neither is provided the existing local-tag behavior is preserved
unchanged.

When `tag` and `registry` are both resolved (from either source), the generator SHALL write
`{registry}/{solution}/service/{service.image.name}:{tag}` as the `image:` value for each
service in the generated `docker-compose.yml`, instead of the default local tag.

#### Scenario: compose generate --manifest writes registry-qualified image refs
- **GIVEN** a manifest with `registry="reg.example.com"` and `tag="v1"` and solution name `"mysol"`
- **AND** services `api` and `db`
- **WHEN** the user runs `localbox compose generate --manifest assembles/v1.json`
- **THEN** the generated `docker-compose.yml` SHALL contain `image: reg.example.com/mysol/service/api:v1` and `image: reg.example.com/mysol/service/db:v1`

#### Scenario: compose generate with explicit --tag and --registry writes registry-qualified image refs
- **WHEN** the user runs `localbox compose generate --tag v1 --registry reg.example.com`
- **THEN** the generated `docker-compose.yml` SHALL contain registry-qualified image refs identical to those produced by `--manifest` with the same values

#### Scenario: compose generate --tag falls back to solution.config.registry when --registry omitted
- **GIVEN** `solution.config.registry` is set to `"reg.example.com"` and solution name `"mysol"`
- **WHEN** the user runs `localbox compose generate --tag v1` (no `--registry`)
- **THEN** the generated `docker-compose.yml` SHALL contain `image: reg.example.com/mysol/service/<service>:v1` for each service

#### Scenario: compose generate --manifest and --tag together is a hard error
- **WHEN** the user runs `localbox compose generate --manifest assembles/v1.json --tag v1`
- **THEN** the CLI SHALL exit non-zero with a UsageError indicating that `--manifest` and `--tag`/`--registry` are mutually exclusive

#### Scenario: compose generate --tag without registry and without solution.config.registry is an error
- **GIVEN** `solution.config.registry` is not set
- **WHEN** the user runs `localbox compose generate --tag v1` (no `--registry`)
- **THEN** the CLI SHALL exit non-zero with an error indicating that a registry must be provided

#### Scenario: compose generate without flags preserves local tag behavior
- **WHEN** the user runs `localbox compose generate` with no manifest or tag flags
- **THEN** the generated `docker-compose.yml` SHALL use the default local image tag for each service
