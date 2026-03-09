# Localbox - AI Assistant Instructions

## Project Overview

Localbox is a Python CLI tool for development environment orchestration. It manages external Git repositories, builds them in Docker containers, and orchestrates Docker Compose services.

**Architecture:**
- **Tool** (`src/localbox/`) - Python CLI installed via pip
- **Solutions** (`solutions/`) - Independent solution directories with Python configs
- **Models as library** - Project/Builder/Service models work for both Python CDK-style definition and programmatic use

## Directory Structure

```
localbox/
├── src/localbox/                # Python CLI tool
│   ├── cli.py                   # Click CLI entry point
│   ├── config.py                # Solution detection & Python module loading
│   ├── models/
│   │   ├── __init__.py          # Public API exports
│   │   ├── docker_image.py      # DockerImage (universal for builders and services)
│   │   ├── builder.py           # Builder, VolumeMount, maven(), gradle(), node()
│   │   ├── project.py           # Project, JavaProject, NodeProject, GitConfig
│   │   ├── service.py           # Service, ComposeConfig
│   │   └── solution_config.py   # SolutionConfig
│   ├── commands/
│   │   ├── project.py           # clone, fetch, switch, build
│   │   └── service.py           # start, stop, logs, build-image
│   ├── builders/
│   │   ├── build.py             # Unified run_builder() for all project types
│   │   ├── docker.py            # Service image building (build or pull)
│   │   └── compose.py           # Docker Compose generation
│   ├── utils/
│   │   └── resolver.py          # Target resolution (colon-separated paths)
├── solutions/                   # Solution directories
│   └── viveka/                  # Viveka solution
│       ├── solution.py          # Solution config + all projects/services
│       └── assets/              # Build scripts, patches, configs
├── tests/                       # Pytest tests (60 tests)
├── pyproject.toml               # Python project config
└── localdev/                    # Development notes
    ├── python-localbox.md       # Implementation plan
    └── tasks.md                 # Task tracking
```

## Key Models

### SolutionConfig (`models/solution_config.py`)
Solution-level settings:
- `SolutionConfig` - default_branch, build_dir, compose_project, network

### DockerImage (`models/docker_image.py`)
Universal Docker image config for both builders and services:
- `DockerImage` - image, dockerfile (no context field; context derived from dockerfile's parent dir)

### Builder (`models/builder.py`)
Defines how to build a project in Docker:
- `Builder` - docker_image (DockerImage), command, volumes, environment
- `maven(version)` - pre-configured Maven builder (JDK-agnostic; JDK comes from JavaProject)
- `gradle(version)` - pre-configured Gradle builder (JDK-agnostic)
- `node(version)` - pre-configured Node.js builder

### Project (`models/project.py`)
- `Project` - base with ergonomic `InitVar` params: `repo`, `branch`, `patches`, `deps`
- `JavaProject` - no default builder; must always pass `builder=` explicitly
- `NodeProject` - defaults to `node()` builder, has `output_dir`
- Dependencies: pass Project objects to `deps=` (auto-resolves names)
- Auto-derives `group`/`local_name` from name containing `:` (e.g. `"libs:utils"`)

### Service (`models/service.py`)
- `Service` - DockerImage, ComposeConfig, optional shell command
- `ComposeConfig` - order, ports, depends_on, links, environment, volumes, healthcheck
- Auto-derives `group`/`local_name` from name containing `:`

## Solution Structure

```
my-solution/
├── solution.py          # Required — marks solution root
├── projects.py          # Optional — additional project definitions
├── services.py          # Optional — additional service definitions
├── projects/            # Optional — one .py per project or group
│   └── backend.py
├── services/            # Optional — one .py per service or group
│   └── databases.py
└── assets/              # Build scripts, patches (unchanged)
```

Config loading: `solution.py` imports Python modules, scans for `Project`, `Service`, and `SolutionConfig` instances.

## CLI Usage

```bash
source .venv/bin/activate
cd solutions/viveka

# Target syntax: type:group:name
localbox list projects                    # List all projects
localbox clone projects:libs:utils        # Clone single project
localbox build projects                   # Build all projects
localbox status projects                  # Show status

localbox list services                    # List all services

localbox compose generate                 # Generate docker-compose.yml
docker compose up -d                      # Start all services (manage via docker directly)
```

## Key Conventions

### Solution Root
- `solution.py` marks solution root (like `.git` for git repos)
- All configuration is Python — no YAML config files
- Load order: `solution.py` → `projects.py` → `services.py` → `projects/*.py` → `services/*.py`

### Target Syntax
```
projects                    # All projects
projects:processor          # Single project (root level)
projects:libs               # All in libs group
projects:libs:utils         # Single grouped project

services:db                 # All db services
services:db:main            # Single service
```

### Build System
- All builds run inside Docker containers via the `Builder` model
- `run_builder()` in `builders/build.py` is the unified build entry point
- Pre-configured builders: `maven()`, `gradle()`, `node()` factory functions
- Project sources mounted at `/var/src` in the container
- Cache volumes for Maven (`.build/maven`), Gradle (`.build/gradle`), npm (`.build/node`)
- Custom Dockerfile builders: `dockerfile` path resolves relative to solution root; context is always the Dockerfile's parent directory

## Working on This Project

### Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests
```bash
pytest tests/ -v
```

### Committing
Only commit when the **current prompt** explicitly asks for it. Permission given in a previous prompt does not carry over.

Do not include `Co-Authored-By` trailers in commit messages.

### Before Committing or Releasing
Run all checks in this order:
```bash
ruff format src/ tests/       # auto-format (must run before check)
ruff check src/ tests/        # lint
mypy src/localbox/            # type-check
pytest tests/ -q              # tests (166 items, 3 skipped)
```
All four must pass cleanly. CI will fail the release if any do not.

### Key Files
- `src/localbox/cli.py` - CLI commands (Click)
- `src/localbox/config.py` - Solution loading, Python module import
- `src/localbox/models/docker_image.py` - DockerImage dataclass (universal)
- `src/localbox/models/solution_config.py` - SolutionConfig dataclass
- `src/localbox/models/builder.py` - Builder model and factory functions
- `src/localbox/models/project.py` - Project models with ergonomic constructors
- `src/localbox/builders/build.py` - Unified Docker build runner
- `src/localbox/utils/resolver.py` - Target resolution
- `solutions/viveka/` - Test solution
- `solutions/viveka/solution.py` - Viveka project/service definitions
