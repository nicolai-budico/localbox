# Localbox Example: Spring PetClinic REST

This example demonstrates how to use **Localbox** to orchestrate a local development environment for a Java application backed by a PostgreSQL database.

It uses the canonical [Spring PetClinic REST](https://github.com/spring-petclinic/spring-petclinic-rest) project.

**What this demonstrates:**
- Cloning a public GitHub repository
- Building a Maven project inside Docker (no local JDK or Maven required)
- Packaging the built JAR into a runtime Docker image via Dockerfile
- Generating a `docker-compose.yml` from Python service definitions
- Managing per-developer secrets with `solution-override.py`

## Prerequisites

- Python 3.10+
- Docker Engine with BuildKit (Docker Desktop or Engine 20.10+)
- Docker Compose V2 plugin (`docker compose`, not `docker-compose`)
- Git

## Quick Start

### 1. Install Localbox

If you haven't installed `localbox` yet, install it from the root of the repository:

```bash
# From the root of the localbox repo
pip install -e .
```

### 2. Prepare the Solution

Navigate to the `example` directory:

```bash
cd example
```

Create your local overrides file. This file is used to set secrets (like database passwords) that should not be committed to Git:

```bash
cp solution-override.py.example solution-override.py
```

Edit `solution-override.py` and set a password for the database:

```python
import solution
solution.config.env.db_pass = "your-password-here"
```

The `db_pass` field has no default value — localbox will raise an error if it is not set before generating the Compose file.

### 3. Clone & Build Projects

Localbox clones the external Git repository and builds it inside a Docker container using Maven — no local JDK or Maven installation required:

```bash
localbox projects clone
localbox projects build
```

**First run downloads ~200 MB of Maven dependencies — this takes a few minutes. Subsequent builds are fast** because the dependency cache is stored in `.build/maven/` and reused.

### 4. Build Service Images

Once the JAR is built, create the runtime Docker image for the API service:

```bash
localbox services build
```

### 5. Generate & Run

Generate the `docker-compose.yml` and start the environment:

```bash
localbox compose generate
docker compose up -d
```

The `api` service takes ~15 seconds to start as Spring Boot initializes. Check that both containers are running:

```bash
docker compose ps
```

### 6. Access the Application

- **Swagger UI:** http://localhost:9966/petclinic/swagger-ui/index.html
- **API Endpoint:** http://localhost:9966/petclinic/api/vets

## What just happened?

1. **`solution.py`** defined the environment: 1 Java project, 1 database service, 1 API service.
2. **`localbox projects clone`** fetched the source code for `spring-petclinic-rest` into `.build/projects/pet_clinic/`.
3. **`localbox projects build`** spun up a Maven container, mounted the source code, compiled it, and cached the `.m2` repository in `.build/maven/` for speed.
4. **`localbox services build`** built a runtime image for the API service using `assets/Dockerfile`, which copied the compiled JAR from the build step.
5. **`localbox compose generate`** created a `docker-compose.yml` that wires up the database and API service with the correct environment variables and networking.

## Stopping

```bash
docker compose down       # Stop containers, keep database volume
docker compose down -v    # Stop containers and delete database volume
```

## What to look at next

| File | What it shows |
|------|---------------|
| `solution.py` | Project + Service definitions, `BaseEnv` for typed config |
| `assets/Dockerfile` | Runtime image built from the Maven artifact |
| `solution-override.py.example` | Per-developer secret pattern |
