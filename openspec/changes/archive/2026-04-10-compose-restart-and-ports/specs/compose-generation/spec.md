## ADDED Requirements

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
