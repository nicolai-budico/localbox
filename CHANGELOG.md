# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-02-28

### Added

- `SolutionConfig` — typed, generic solution configuration with `BaseEnv` for secret management
- `Project`, `JavaProject`, `NodeProject` — Git repository models with builder configuration
- `Builder` — Docker-based build runner with `maven()`, `gradle()`, `node()` factory functions
- `Service`, `ComposeConfig` — Docker Compose service model with dependency ordering
- `DockerImage` — universal image model for both builders and services
- Volume types: `BindVolume`, `CacheVolume`, `NamedVolume` with factory helpers
- JDK providers: `corretto()`, `temurin()`, `graalvm()` with version resolution
- Health checks: `HealthCheck`, `HttpCheck`, `PgCheck`, `SpringBootCheck`
- Library services: `SpringBootService`, `TomcatService` — auto-generate Dockerfiles
- CLI commands: `init`, `init-override`, `doctor`, `clone`, `fetch`, `switch`, `build`, `status`, `list`, `compose generate`, `clean`, `completion`
- Colon-separated target syntax: `projects:group:name`, `services:group:name`
- Auto-patching: applies `*.patch` files from `patches/<project>/` after clone
- Shared build cache volumes for Maven, Gradle, and npm
- `solution-override.py` — gitignored per-developer secrets and local overrides
- Spring PetClinic REST example at `example/`
