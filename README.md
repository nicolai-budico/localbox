# Localbox

Development environment orchestrator for Git repositories, Docker builds, and service management.

[![CI](https://github.com/nicolai-budico/localbox/actions/workflows/ci.yml/badge.svg)](https://github.com/nicolai-budico/localbox/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## What is Localbox?

Localbox lets you describe your entire local development environment in Python — which repositories to clone, how to build them, and what Docker services to run — and then execute that description with a few commands.

```python
# solution.py
from localbox.models import JavaProject, Service, ComposeConfig, DockerImage, maven

api = JavaProject("api", repo="git@github.com:org/api.git", jdk=17, builder=maven())

db = Service(
    name="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(ports=["5432:5432"]),
)
```

```bash
localbox projects clone   # git clone all repos
localbox projects build   # build inside Docker (no local JDK needed)
localbox compose generate # write docker-compose.yml + .env
docker compose up -d      # start everything
```

**Boundary:** Localbox handles _code → image_. Service lifecycle (start, stop, logs) is Docker Compose's domain — use `docker compose` directly.

---

## Installation

Install the latest `v0.2` release (floating tag — always the newest patch on the v0.2 line):

```bash
pip install "git+https://github.com/nicolai-budico/localbox.git@v0.2"
```

Or pin to a specific release:

```bash
pip install "git+https://github.com/nicolai-budico/localbox.git@v0.2.0"
```

**Requirements:** Python 3.10+, Docker Engine 20.10+, Docker Compose V2, Git 2.0+

Run `localbox doctor` to verify all requirements after installation.

### Updating

```bash
pip install --upgrade "git+https://github.com/nicolai-budico/localbox.git@v0.2"
```

Each patch release bumps the version number, so `--upgrade` is sufficient.

---

## Quick Start

The fastest way to see Localbox in action is the included example — Spring PetClinic REST backed by PostgreSQL:

```bash
cd example
cp solution-override.py.example solution-override.py
# Edit solution-override.py and set db_pass to any value
localbox projects clone
localbox projects build
localbox services build
localbox compose generate
docker compose up -d
# API: http://localhost:9966/petclinic/api/vets
# Swagger: http://localhost:9966/petclinic/swagger-ui/index.html
```

See [example/README.md](example/README.md) for a step-by-step walkthrough.

---

## Starting a New Solution

```bash
mkdir my-project && cd my-project
localbox solution init         # creates solution.py, assets/, patches/
# edit solution.py
localbox projects clone
localbox projects build
localbox compose generate
docker compose up -d
```

---

## Concepts

### Solution

A **solution** is a directory marked by `solution.py`. The `localbox` command discovers it by walking up the directory tree — the same way `git` finds `.git`. All paths in the solution are relative to this root.

### Projects

**Projects** are external Git repositories. Localbox clones them into `.build/projects/` and builds them inside Docker containers. No local JDK, Maven, Gradle, or Node.js required.

```python
from localbox.models import JavaProject, NodeProject, maven, gradle, node

# Java with Maven
api = JavaProject("api", repo="git@github.com:org/api.git", jdk=17, builder=maven())

# Java with Gradle
engine = JavaProject("engine", repo="git@github.com:org/engine.git", jdk=21, builder=gradle())

# Node.js
ui = NodeProject("frontend:ui", repo="git@github.com:org/ui.git")
```

### Builders

A **builder** defines the Docker image and command used to compile a project. Pre-configured builders are available for Maven, Gradle, and Node.js. The JDK version is a property of the _project_, not the builder — so one `maven()` instance works with any JDK version.

```python
from localbox.models import maven, gradle, node, corretto, temurin, graalvm

mvn = maven("3.9")    # any JDK version
grd = gradle("8.14")  # any JDK version
nd  = node(20)        # Node.js 20

JavaProject("api", repo="...", jdk=temurin(17), builder=mvn)  # → maven:3.9-eclipse-temurin-17
JavaProject("api", repo="...", jdk=21,          builder=grd)  # → gradle:8.14-jdk21
```

### Services

**Services** are Docker containers managed via Compose. Each service has an image and a Compose configuration:

```python
from localbox.models import Service, DockerImage, ComposeConfig, named_volume

db = Service(
    name="db:primary",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        order=1,
        ports=["5432:5432"],
        environment={"POSTGRES_DB": "myapp"},
        volumes=named_volume("db_data", "/var/lib/postgresql/data"),
        healthcheck=PgCheck(),
    ),
)
```

---

## Solution Structure

```
my-solution/
├── solution.py          # Required — marks solution root
├── solution-override.py # Gitignored — per-developer secrets and overrides
├── docker-compose.yml   # Gitignored — generated by localbox compose generate
├── .env                 # Gitignored — generated alongside docker-compose.yml
├── projects.py          # Optional — additional project definitions
├── services.py          # Optional — additional service definitions
├── projects/            # Optional — one .py per group
│   └── backend.py
├── services/            # Optional — one .py per group
│   └── databases.py
├── patches/             # Patch files auto-applied after clone
│   └── <project-name>/ # *.patch files applied in sort order
└── assets/              # Dockerfiles, scripts, configs
```

Load order: `solution.py` → `projects.py` → `services.py` → `projects/*.py` → `services/*.py`.

---

## CLI Reference

The CLI is **domain-first**: `localbox <domain> <command> [targets…]`. Domains are `projects`, `services`, `compose`, `override`, and `solution`. Top-level utilities (`doctor`, `config`, `completion`, `prune`, `purge`) have no domain.

### Target Syntax

Targets are **short-form tokens**, scoped to the current domain. No `projects:` or `services:` prefix:

```bash
# Under `localbox projects <command> …`
(no target)                 # All projects
api                         # Single ungrouped project
libs                        # All projects in the "libs" group
libs:utils                  # Single grouped project
be:api fe:api workers       # Multiple targets (union, deduplicated)

# Under `localbox services <command> …`
(no target)                 # All services
db                          # All services in the "db" group
db:primary                  # Single service
```

### Commands

```bash
# Solution & override scaffolding
localbox solution init                  # Create solution.py, assets/, patches/
localbox override init                  # Create solution-override.py template

# Projects
localbox projects list                  # List projects (tree view)
localbox projects clone                 # Clone all repos
localbox projects clone api             # Clone a single project
localbox projects fetch                 # git pull (all)
localbox projects fetch libs            # git pull for every project in the libs group
localbox projects switch -b feature     # Switch branch (all projects)
localbox projects build                 # Build all (in dependency order)
localbox projects build be:api workers  # Build multiple targets
localbox projects status                # Git status of all repos
localbox projects clean                 # Run builder clean (mvn clean, gradle clean, …)

# Services
localbox services list                  # List services (tree view)
localbox services build                 # Build all service images
localbox services build be              # Build one group

# Docker Compose
localbox compose generate               # Generate docker-compose.yml and .env
docker compose up -d                    # Start services (Docker manages lifecycle)
docker compose down                     # Stop services

# Utilities (top-level — no domain)
localbox doctor                         # Verify system requirements
localbox config                         # Show solution config
localbox prune caches                   # Remove .build/maven, .build/gradle, .build/node
localbox prune builders                 # Remove builder Docker images
localbox prune images                   # Remove service Docker images
localbox prune all                      # Remove all caches + images
localbox purge                          # Remove entire .build/ directory

# Shell completion
localbox completion bash > ~/.local/share/bash-completion/completions/localbox
```

### Migrating from the legacy grammar

| Old | New |
|---|---|
| `localbox init` | `localbox solution init` |
| `localbox init-override` | `localbox override init` |
| `localbox clone projects` | `localbox projects clone` |
| `localbox clone projects:api` | `localbox projects clone api` |
| `localbox fetch projects:libs` | `localbox projects fetch libs` |
| `localbox switch projects -b feat` | `localbox projects switch -b feat` |
| `localbox build projects` | `localbox projects build` |
| `localbox build projects:libs:utils` | `localbox projects build libs:utils` |
| `localbox build services:be` | `localbox services build be` |
| `localbox status projects` | `localbox projects status` |
| `localbox list projects` | `localbox projects list` |
| `localbox list services` | `localbox services list` |
| `localbox clean projects` | `localbox projects clean` |
| `localbox compose generate` | `localbox compose generate` (unchanged) |
| `localbox doctor` / `config` / `prune …` / `purge` | unchanged (top-level utilities) |

Legacy forms are removed — there are no deprecation aliases.

---

## Configuration

### solution.py — basic

```python
from localbox.models import SolutionConfig

config = SolutionConfig(
    name="myproject",
    default_branch="main",    # Default git branch for all projects
    compose_project="myapp",  # Docker Compose project name
    network="myapp-net",      # Docker network name
)
```

All fields are optional and have sensible defaults.

### solution.py — with typed environment

```python
import dataclasses
from localbox.models import BaseEnv, SolutionConfig, env_field

@dataclasses.dataclass
class Env(BaseEnv):
    db_host: str = env_field()
    db_pass: str = env_field(is_secret=True)  # masked in output

config = SolutionConfig[Env](
    name="myproject",
    env=Env(db_host="localhost"),
)
```

### solution-override.py — per-developer secrets

```python
# solution-override.py — DO NOT COMMIT
import solution

solution.config.env.db_pass = "my-local-password"
```

Generate a template: `localbox override init`

### Referencing env values in services

Reference env values through **instance access** on `config.env`. Every attribute
is an `EnvRef` — a `str` subclass whose string form is `${<field>}` — so any
f-string, concatenation, or direct dict value produces a Docker Compose
variable reference. The raw value is written once to `.env`.

```python
from localbox.models import Service, DockerImage, ComposeConfig

db = Service(
    name="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        ports=[f"{config.env.db_host}:5432"],       # → "${db_host}:5432"
        environment={
            "POSTGRES_PASSWORD": config.env.db_pass,  # → "${db_pass}"
            "POSTGRES_DB":       "myapp",             # plain literal
        },
    ),
)
```

`localbox compose generate` writes two files:

- **`docker-compose.yml`** — every field reference appears as `${field_name}`; plain string values are written as literals.
- **`.env`** — one `field_name="value"` line per field on the `BaseEnv` instance, plus any other references the walker finds. Docker Compose reads this file automatically when starting services.

One `SolutionConfig.env` field can be mapped to multiple compose environment keys — only one `.env` entry is written per field. Both files are automatically added to `.gitignore` and regenerated on every run.

---

## Library Services

For common Java deployment patterns, use the pre-built library services instead of writing Dockerfiles manually.

### SpringBootService

Runs a Spring Boot JAR in a JRE container. Dockerfile is generated automatically. Adds a `/actuator/health` healthcheck by default.

```python
from localbox.library import SpringBootService
from localbox.models import ComposeConfig

api = SpringBootService(
    name="be:api",
    artifact=api_project.artifact(),      # auto-detect JAR
    compose=ComposeConfig(
        order=10,
        ports=["8080:8080"],
        depends_on=[db],
    ),
)

# With JVM tuning
api = SpringBootService(
    name="be:api",
    artifact=api_project.artifact("target/myapp-exec.jar"),
    jvm_opts="-Xmx512m -Xms256m",
    spring_profiles="local,postgres",
    server_port=8080,
    compose=ComposeConfig(ports=["8080:8080"], depends_on=[db]),
)

# Disable auto-healthcheck
api = SpringBootService(name="be:api", artifact=..., healthcheck=None)
```

### TomcatService

Deploys WAR artifacts to Tomcat. Dockerfile is generated automatically.

```python
from localbox.library import TomcatService

be_api = TomcatService(
    name="be:api",
    webapps={"api": api.artifact()},
    tomcat_version="9-jdk8",
    compose=ComposeConfig(order=10, ports=["8080:8080"], depends_on=[db]),
)

# Multiple webapps
be_multi = TomcatService(
    name="be:multi",
    webapps={
        "auth": auth.artifact("auth-server/target/auth.war"),
        "api":  api.artifact(),
    },
    tomcat_version="9-jdk17",
)
```

---

## Builder Reference

| Factory | Docker Image | Default Command |
|---------|-------------|-----------------|
| `maven()` | `maven:3.9-amazoncorretto-{jdk}` | `mvn install -Dmaven.test.skip=true` |
| `maven("4.0")` | `maven:4.0-amazoncorretto-{jdk}` | `mvn install -Dmaven.test.skip=true` |
| `gradle()` | `gradle:8.14-jdk{jdk}` | `gradle build -x test --no-daemon` |
| `gradle(tasks=[…])` | `gradle:8.14-jdk{jdk}` | `gradle build -x test --no-daemon …extra tasks` |
| `node(20)` | `node:20` | `npm ci && npm run build` |
| `node(22)` | `node:22` | `npm ci && npm run build` |

`{jdk}` is resolved from `JavaProject.jdk` at build time. The `tasks=` keyword is also supported on `gradlew()`; use it to append tasks like `publishToMavenLocal` so Gradle modules feed the shared `.build/maven/.m2` cache for downstream Maven projects (see `docs/cookbook/multi-module-maven.md`).

### JDK Providers

```python
from localbox.models import corretto, temurin, graalvm

JavaProject("api", repo="...", jdk=corretto(17), builder=maven())  # → maven:3.9-amazoncorretto-17
JavaProject("api", repo="...", jdk=temurin(17),  builder=maven())  # → maven:3.9-eclipse-temurin-17
JavaProject("api", repo="...", jdk=graalvm(21),  builder=gradle()) # → gradle:8.14-jdk21-graal
```

Default is Amazon Corretto. `jdk=17` is shorthand for `jdk=corretto(17)`.

### Custom Builder

```python
from localbox.models import Builder, DockerImage, bind_volume

custom = Builder(
    docker_image=DockerImage(image="my-registry/my-builder:latest"),
    build_command="make build",
    environment={"MAKE_OPTS": "-j4"},
    volumes=[bind_volume("./config", "/etc/build-config", readonly=True)],
    timeout=60,  # minutes
)
```

### Dockerfile Builder

```python
builder = Builder(
    docker_image=DockerImage(dockerfile="assets/dockerfiles/special/Dockerfile"),
    command="make build",
)
```

Path resolves relative to the solution root. The build context defaults to the Dockerfile's parent directory.

---

## Health Checks

```python
from localbox.models import HealthCheck, HttpCheck, PgCheck, SpringBootCheck

# Raw command
HealthCheck(test=["CMD", "redis-cli", "ping"])

# HTTP endpoint
HttpCheck(url="http://localhost:8080/health")

# PostgreSQL
PgCheck()              # user=postgres
PgCheck(user="mydb")

# Spring Boot Actuator
SpringBootCheck()              # port 8080
SpringBootCheck(port=9090)
```

---

## Troubleshooting

**`localbox: command not found`**
Run `localbox doctor` after install. Ensure your virtualenv or pip bin directory is in `PATH`.

**`docker: command not found` or Docker daemon not running**
Start Docker Desktop or the Docker Engine service. Run `localbox doctor` to verify.

**`Permission denied (publickey)`** during `localbox clone`
Your SSH key is not registered with the Git host. Check `ssh -T git@github.com`. For HTTPS repos, no SSH key is needed.

**`env.db_pass is required but not set`**
Create `solution-override.py` and set the required value: `solution.config.env.db_pass = "mypassword"`. Run `localbox override init` to generate a template.

**BuildKit not available**
Enable BuildKit: `export DOCKER_BUILDKIT=1`, or update Docker to 20.10+ where it is enabled by default.

**`localbox projects build` fails with a non-zero exit code**
Check `.build/logs/<project-name>.log` for the full build output. Pass `--verbose` to see output in the terminal.

---

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest tests/ -v     # run tests + ruff lint
mypy src/localbox    # type check
```

---

## Documentation

- [docs/concepts.md](docs/concepts.md) — core model diagram and concepts explained
- [docs/getting-started.md](docs/getting-started.md) — step-by-step walkthrough
- [docs/api-reference.md](docs/api-reference.md) — every field, type, and default
- [docs/cookbook/](docs/cookbook/) — recipes for common scenarios

---

## License

MIT
