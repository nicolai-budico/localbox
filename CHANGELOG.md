# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- **`tasks=` field on Gradle builders** — `GradleBuilder`, `GradleWrapperBuilder`, `gradle()`, and `gradlew()` now accept an optional `tasks: list[str] | None` keyword that appends extra Gradle tasks/args to the default build command. Designed for the common case of running `publishToMavenLocal` so a Gradle module's libraries land in the shared `.build/maven/.m2` cache for downstream Maven projects to consume. Items are passed verbatim, so flags like `-PreleaseVersion=1.2.3` also work. Mutually exclusive with custom `build_command*`; rejected on Maven builders. See `docs/cookbook/multi-module-maven.md` for the Gradle-libs → Maven-apps recipe.

## [0.2.0] - 2026-04-17

### BREAKING: CLI restructured to `localbox <domain> <command>`

The CLI is now **domain-first**. The legacy verb-first shape (`localbox <verb> <domain>[:path]`) is removed — there are no deprecation aliases.

#### Translation table

| Old | New |
|---|---|
| `localbox init` | `localbox solution init` |
| `localbox init-override` | `localbox override init` |
| `localbox list projects` | `localbox projects list` |
| `localbox list services` | `localbox services list` |
| `localbox clone projects` | `localbox projects clone` |
| `localbox clone projects:api` | `localbox projects clone api` |
| `localbox fetch projects` | `localbox projects fetch` |
| `localbox fetch projects:libs` | `localbox projects fetch libs` |
| `localbox switch projects -b feat` | `localbox projects switch -b feat` |
| `localbox switch projects:api -b main` | `localbox projects switch api -b main` |
| `localbox build projects` | `localbox projects build` |
| `localbox build projects:libs:utils` | `localbox projects build libs:utils` |
| `localbox build services` | `localbox services build` |
| `localbox build services:be` | `localbox services build be` |
| `localbox status projects` | `localbox projects status` |
| `localbox clean projects` | `localbox projects clean` |
| `localbox compose generate` | unchanged |
| `localbox doctor` / `config` / `completion` / `prune …` / `purge` | unchanged (top-level utilities) |

#### New capabilities

- **Multiple short-form targets per command**: `localbox projects build be:api fe:api workers` resolves and unions all three tokens in a single call.
- **Targets are scoped to the current domain** and written short-form — no redundant `projects:` / `services:` prefix.
- **Empty target list means "all items in this domain"**, replacing the legacy `localbox build projects` fallback.
- **`projects build` and `services build` are now two independent commands** — no more target sniffing to decide which builder to run.
- New reserved subcommand space under `localbox override …` for the planned `show` / `set` / `clear` verbs.

#### Why

The legacy grammar mixed verb and domain (`localbox <verb> <domain>[:path]`), which made the target-argument rules ambiguous (is `projects:libs` a group or a project?) and forced `build` to sniff its targets to decide whether to run project or service builders. Domain-first shape closes all three problems and gives each domain a natural home for future subcommands.

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
