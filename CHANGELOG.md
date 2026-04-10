# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **BREAKING** — Instance access on a `BaseEnv` subclass (e.g.
  `config.env.db_host`) now returns an `EnvRef` — a `str` subclass whose
  string form is `"${db_host}"`. F-strings and concatenation therefore
  produce Docker Compose variable references, not the raw values. The
  generated `docker-compose.yml` contains `${field_name}` references for
  every compose field (ports, environment, volumes, extras, healthchecks,
  ...) and the real values are written once to `.env` alongside it.
- **BREAKING** — Class-level `Env.<field>` sentinel references inside
  `ComposeConfig.environment` are now rejected. Use instance access on
  `config.env.<field>` instead.
- `Builder.environment` values that are `EnvRef` instances are automatically
  resolved to their raw value before being passed to `docker run -e`, since
  `docker run` does not perform `${NAME}` substitution.
- New `BaseEnv.raw_value(name)` and `BaseEnv.raw_values()` accessors return
  the literal values, for the rare code paths (e.g. build-time scripts) that
  need them. `EnvRef.raw` exposes the same value on a single reference.
- `EnvRef` is exported from `localbox.models`.

### Migration

- Replace every `Env.<field>` in `ComposeConfig.environment` or `extra` with
  `config.env.<field>` (instance access through your solution's
  `SolutionConfig`).
- If any `solution.py` relied on `config.env.<field>` returning the literal
  value (e.g. passing it to a custom script or using it in a comparison),
  switch to `config.env.raw_value("<field>")`.
- `solution-override.py` files that do
  `solution.config.env.db_pass = "value"` continue to work unchanged — the
  assignment updates both the `EnvRef` attribute and the underlying
  raw-value map.

## [0.1.0] - 2026-02-28

Initial release.

### Features

- **Solution model** — `SolutionConfig` with generic `BaseEnv` for typed, secret-aware environment configuration; `solution-override.py` for gitignored per-developer overrides
- **Project model** — `Project`, `JavaProject`, `NodeProject` with Git configuration, builder assignment, and colon-grouped names (`libs:utils`)
- **Builder model** — Docker-based build runner; `maven()`, `gradle()`, `node()` factory functions; shared cache volumes for Maven, Gradle, and npm; script and timeout support
- **Service model** — `Service` and `ComposeConfig` with dependency ordering, health checks, and volume mounts
- **Docker image model** — `DockerImage` used uniformly for both builders and services
- **JDK providers** — `corretto()`, `temurin()`, `graalvm()` with runtime image resolution
- **Health checks** — `HttpCheck`, `PgCheck`, `SpringBootCheck`
- **Library services** — `SpringBootService` and `TomcatService` auto-generate Dockerfiles from project artifacts
- **CLI** — `init`, `init-override`, `doctor`, `clone`, `fetch`, `switch`, `build`, `status`, `list`, `compose generate`, `clean`, `completion`
- **Target syntax** — colon-separated `projects:group:name` and `services:group:name`
- **Auto-patching** — applies `*.patch` files from `patches/<project>/` on clone
- **Example** — Spring PetClinic REST at `example/`
