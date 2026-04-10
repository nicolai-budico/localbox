# Getting Started

This guide walks you through setting up a real local development environment from scratch using the included `example/` — a Spring Boot REST API backed by PostgreSQL.

By the end you will have:
- Cloned an external GitHub repository
- Built a Java project inside Docker (no local JDK needed)
- Generated a `docker-compose.yml`
- A running API at `http://localhost:9966/petclinic/api/vets`

---

## Prerequisites

Run `localbox doctor` to check all requirements:

```bash
localbox doctor
```

Requirements:
- Python 3.10+
- Docker Engine 20.10+ with BuildKit enabled
- Docker Compose V2 (`docker compose`, not `docker-compose`)
- Git 2.0+

---

## Step 1 — Install Localbox

Install the latest `v0.1` release (floating tag — always the newest patch on the v0.1 line):

```bash
pip install "git+https://github.com/nicolai-budico/localbox.git@v0.1"
```

Verify:
```bash
localbox --version
```

To update to the latest patch:

```bash
pip install --upgrade "git+https://github.com/nicolai-budico/localbox.git@v0.1"
```

### Shell completion (optional)

Localbox supports tab-completion for commands and colon-separated targets like `projects:libs:utils`.

**Bash:**
```bash
localbox completion bash > ~/.local/share/bash-completion/completions/localbox
source ~/.local/share/bash-completion/completions/localbox
```

**Zsh:**
```bash
localbox completion zsh > ~/.zfunc/_localbox
# Add to ~/.zshrc if not already there:
#   fpath=(~/.zfunc $fpath)
#   autoload -Uz compinit && compinit
```

**Fish:**
```bash
localbox completion fish > ~/.config/fish/completions/localbox.fish
```

---

## Step 2 — Navigate to the example solution

```bash
cd example
```

This directory contains `solution.py`, which marks it as a Localbox solution root. Open it and you'll see the entire environment defined in ~40 lines of Python:

```python
# solution.py (simplified)
from localbox.models import JavaProject, Service, DockerImage, ComposeConfig, maven

pet_clinic = JavaProject(
    "pet_clinic",
    repo="https://github.com/spring-petclinic/spring-petclinic-rest.git",
    jdk=17,
    builder=maven("3.9"),
)

db = Service(name="db", image=DockerImage(image="postgres:16"), ...)
api = Service(name="api", project=pet_clinic, image=DockerImage(dockerfile="assets/Dockerfile"), ...)
```

---

## Step 3 — Set up secrets

The database password is a required secret. Create your local overrides file from the template:

```bash
cp solution-override.py.example solution-override.py
```

Edit `solution-override.py` and set a password:

```python
import solution

solution.config.env.db_pass = "my-local-password"
```

This file is gitignored — it stays on your machine only. The assignment
updates the typed env so that the generated `.env` file (also gitignored)
picks up the new value, while `docker-compose.yml` keeps referencing it as
`${db_pass}`.

> **Why is this a required field?**
> `db_pass` is declared as `env_field(is_secret=True)` with no default value. Localbox enforces that required fields are set before generating the Compose file. This prevents accidentally running with empty credentials.

> **How env values flow into compose**
> Instance access on `config.env.<field>` returns a reference whose string
> form is `${<field>}`. Writing
> `ports=[f"{config.env.db_host}:5432"]` in `solution.py` therefore produces
> `${db_host}:5432` in the generated `docker-compose.yml`, and the raw value
> lands once in `.env` as `db_host="localhost"`.

---

## Step 4 — Clone the project

```bash
localbox clone projects
```

Localbox clones `spring-petclinic-rest` from GitHub into `.build/projects/pet_clinic/`.

If the solution had multiple projects, they would all be cloned here. Use `localbox status projects` to check the state of all repos at any time.

---

## Step 5 — Build the project

```bash
localbox build projects
```

What happens:
1. Localbox spins up a `maven:3.9-amazoncorretto-17` container
2. Mounts `.build/projects/pet_clinic/` at `/var/src` inside the container
3. Mounts `.build/maven/` as a Maven cache at `/var/maven/.m2`
4. Runs `mvn install -Dmaven.test.skip=true`
5. The compiled JAR lands in `.build/projects/pet_clinic/target/`

**First run** downloads ~200 MB of Maven dependencies — this takes a few minutes. Subsequent builds are fast because the cache in `.build/maven/` is reused.

Check progress in `.build/logs/pet_clinic.log` or add `--verbose` to see output in the terminal.

---

## Step 6 — Build the service image

```bash
localbox build services
```

The `api` service uses a custom `assets/Dockerfile` that packages the compiled JAR into a runtime image. Localbox runs `docker buildx build` with the project directory as a named build context.

```dockerfile
# assets/Dockerfile
FROM eclipse-temurin:17-jre
COPY --from=pet_clinic target/spring-petclinic-rest-*.jar /app.jar
ENTRYPOINT ["java", "-jar", "/app.jar"]
```

After this step `docker images | grep pet_clinic` should show `pet_clinic/service/api:latest`.

---

## Step 7 — Generate docker-compose.yml

```bash
localbox compose generate
```

Localbox reads all service definitions and writes `docker-compose.yml` to the solution root. Open it to see the full configuration — ports, environment variables, volumes, and the Docker network are all set up automatically.

---

## Step 8 — Start the environment

```bash
docker compose up -d
```

Check that both services started:

```bash
docker compose ps
```

The API service takes ~15 seconds to start as Spring Boot initializes.

---

## Step 9 — Access the application

- **API endpoint:** http://localhost:9966/petclinic/api/vets
- **Swagger UI:** http://localhost:9966/petclinic/swagger-ui/index.html

---

## Stop the environment

```bash
docker compose down        # stop containers, keep database volume
docker compose down -v     # stop containers and delete database volume
```

---

## What you just did — explained

| Command | What happened |
|---------|--------------|
| `localbox clone projects` | Cloned the Git repo into `.build/projects/pet_clinic/` |
| `localbox build projects` | Ran Maven inside Docker; JAR is in `.build/projects/pet_clinic/target/` |
| `localbox build services` | Built the runtime Docker image from `assets/Dockerfile` |
| `localbox compose generate` | Wrote `docker-compose.yml` with all env vars, ports, volumes wired together |
| `docker compose up -d` | Started `db` (Postgres) and `api` (Spring Boot) containers |

---

## Starting your own solution

Now that you've seen the pattern, create a new solution:

```bash
mkdir my-project && cd my-project
localbox init
```

Edit the generated `solution.py` to define your projects and services.
See [concepts.md](concepts.md) for the mental model and [api-reference.md](api-reference.md) for all available fields.

The cookbook has ready-to-use recipes:
- [Spring Boot + PostgreSQL](cookbook/spring-boot.md)
- [Node.js + nginx](cookbook/node-frontend.md)
- [Multi-module Maven (libs → app)](cookbook/multi-module-maven.md)
