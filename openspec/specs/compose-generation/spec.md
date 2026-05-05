### Requirement: Generated services have no default restart policy

The compose generator SHALL NOT emit a `restart` key in a generated service
definition unless the user explicitly supplied one via the
`ComposeConfig.extra` passthrough. Leaving `restart` unset matches Docker
Compose's own default (no automatic restart) and lets the user opt in
per-service when they want one.

#### Scenario: default ComposeConfig omits restart
- **WHEN** a service is declared as `Service(name="api", compose=ComposeConfig())`
- **AND** the compose generator runs
- **THEN** the generated service definition SHALL NOT contain a `restart` key
- **AND** the generated `docker-compose.yml` SHALL NOT contain a `restart:`
  line for that service

#### Scenario: extra restart passes through to compose
- **WHEN** a service is declared as
  `Service(name="api", compose=ComposeConfig(extra={"restart": "always"}))`
- **AND** the compose generator runs
- **THEN** the generated service definition SHALL contain
  `"restart": "always"`
- **AND** the generated `docker-compose.yml` SHALL contain `restart: always`
  for that service

#### Scenario: extra restart unless-stopped still supported via opt-in
- **WHEN** a service is declared as
  `Service(name="api", compose=ComposeConfig(extra={"restart": "unless-stopped"}))`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain
  `restart: unless-stopped` for that service

### Requirement: Generated port strings are double-quoted in compose output

The compose generator SHALL emit every entry in a service's `ports:` list as
a double-quoted YAML scalar in the generated `docker-compose.yml`. This
silences Docker Compose's `unquoted port mapping` warning, which fires
whenever a colon-containing port string (e.g. `host_ip:host:container`) is
serialized as a bare YAML scalar.

This requirement applies to every form of port string a user may pass:
`"8080"`, `"8080:8080"`, `"0.0.0.0:8080:8080"`, and strings containing
`${NAME}` variable references produced by `compose-env-resolution`.

#### Scenario: simple host:container port is quoted
- **WHEN** a service sets `ports=["8080:8080"]` on its `ComposeConfig`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain the line
  `- "8080:8080"` under that service's `ports:` key

#### Scenario: host_ip:host:container triplet is quoted
- **WHEN** a service sets `ports=["0.0.0.0:80:80", "0.0.0.0:9001:9001"]`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain
  `- "0.0.0.0:80:80"` and `- "0.0.0.0:9001:9001"` under that service's
  `ports:` key
- **AND** Docker Compose SHALL NOT log an `unquoted port mapping` warning
  when loading the generated file

#### Scenario: port with BaseEnv reference is quoted and resolves
- **WHEN** a service sets `ports=[f"{config.env.MAIN_DB_LOIP}:5432"]`
- **AND** `config.env = Env(MAIN_DB_LOIP="127.0.0.21")`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain
  `- "${MAIN_DB_LOIP}:5432"` under that service's `ports:` key
- **AND** the generated `.env` file SHALL contain `MAIN_DB_LOIP="127.0.0.21"`

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
