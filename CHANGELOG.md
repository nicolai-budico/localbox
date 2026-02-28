# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
