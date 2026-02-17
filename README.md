# Localbox

Development environment orchestrator for Git repositories, Docker builds, and service management.

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
localbox clone projects   # git clone all repos
localbox build projects   # build inside Docker (no local JDK needed)
localbox compose generate # write docker-compose.yml
docker compose up -d      # start everything
```

**Boundary:** Localbox handles _code → image_. Service lifecycle (start, stop, logs) is Docker Compose's domain — use `docker compose` directly.

---

## Installation

```bash
pip install "git+https://github.com/localbox/localbox.git"
```

Or install a pinned version:

```bash
pip install "git+https://github.com/localbox/localbox.git@v0.3.0"
```

**Requirements:** Python 3.10+, Docker Engine 20.10+, Docker Compose V2, Git 2.0+

Run `localbox doctor` to verify all requirements after installation.

---

## Quick Start

The fastest way to see Localbox in action is the included example — Spring PetClinic REST backed by PostgreSQL:

```bash
cd example
cp solution-override.py.example solution-override.py
# Edit solution-override.py and set db_pass to any value
localbox clone projects
localbox build projects
localbox build services
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
localbox init                  # creates solution.py, assets/, patches/
# edit solution.py
localbox clone projects
localbox build projects
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
    name="db:main",
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

### Target Syntax

```bash
projects                    # All projects
projects:processor          # Single project (root level)
projects:libs               # All projects in the "libs" group
projects:libs:utils         # Single grouped project

services                    # All services
services:db                 # All services in the "db" group
services:db:main            # Single service
```

### Commands

```bash
# Initialization
localbox init                           # Create solution.py, assets/, patches/
localbox init-override                  # Create solution-override.py template
localbox doctor                         # Verify system requirements

# Project management
localbox clone projects                 # Clone all repos
localbox clone projects:processor       # Clone single project
localbox fetch projects                 # git pull (all)
localbox fetch projects:processor       # git pull (one)
localbox switch projects -b feature     # Switch branch
localbox build projects                 # Build all (in dependency order)
localbox build projects:libs            # Build group
localbox status projects                # Git status of all repos

# Service image building
localbox build services                 # Build all service images
localbox build services:be              # Build a group

# Docker Compose
localbox compose generate               # Generate docker-compose.yml
docker compose up -d                    # Start services (Docker manages lifecycle)
docker compose down                     # Stop services

# Info
localbox config                         # Show solution config
localbox list projects                  # List projects (tree view)
localbox list services                  # List services (tree view)
localbox clean --build                  # Remove .build/ entirely
localbox clean --compose                # Remove docker-compose.yml
localbox clean projects:api             # Remove one cloned project

# Shell completion
localbox completion bash > ~/.local/share/bash-completion/completions/localbox
```

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

Generate a template: `localbox init-override`

### Referencing env values in services

```python
from localbox.models import Service, DockerImage, ComposeConfig

db = Service(
    name="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        environment={
            "POSTGRES_PASSWORD": Env.db_pass,  # resolved at compose generate time
        }
    ),
)
```

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

be_processor = TomcatService(
    name="be:processor",
    webapps={"processor": processor.artifact()},
    tomcat_version="9-jdk8",
    compose=ComposeConfig(order=10, ports=["8080:8080"], depends_on=[db]),
)

# Multiple webapps
be_multi = TomcatService(
    name="be:multi",
    webapps={
        "authserver": auth.artifact("auth-server/target/oauth2-auth-server.war"),
        "processor":  processor.artifact(),
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
| `node(20)` | `node:20` | `npm ci && npm run build` |
| `node(22)` | `node:22` | `npm ci && npm run build` |

`{jdk}` is resolved from `JavaProject.jdk` at build time.

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
    command="make build",
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
Create `solution-override.py` and set the required value: `solution.config.env.db_pass = "mypassword"`. Run `localbox init-override` to generate a template.

**BuildKit not available**
Enable BuildKit: `export DOCKER_BUILDKIT=1`, or update Docker to 20.10+ where it is enabled by default.

**`localbox build projects` fails with a non-zero exit code**
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
