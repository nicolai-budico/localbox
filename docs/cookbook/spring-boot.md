# Cookbook: Spring Boot + PostgreSQL

A complete recipe for a Spring Boot REST API backed by a PostgreSQL database.

---

## What this covers

- `JavaProject` with Maven builder
- `BaseEnv` for typed secrets
- PostgreSQL service with `PgCheck` healthcheck
- `SpringBootService` for zero-Dockerfile deployment
- `depends_on` wiring

---

## solution.py

```python
import dataclasses
from localbox.models import (
    BaseEnv, SolutionConfig, env_field,
    JavaProject, maven,
    Service, DockerImage, ComposeConfig,
    named_volume, PgCheck,
)
from localbox.library import SpringBootService

# ── Environment ────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Env(BaseEnv):
    db_name: str = env_field()
    db_user: str = env_field()
    db_pass: str = env_field(is_secret=True)

config = SolutionConfig[Env](
    name="myapp",
    env=Env(
        db_name="myapp",
        db_user="myapp",
        # db_pass intentionally left unset — must be set in solution-override.py
    ),
)

# ── Projects ───────────────────────────────────────────────────────────────────

api_project = JavaProject(
    "api",
    repo="git@github.com:org/api.git",
    jdk=17,
    builder=maven("3.9"),
)

# ── Services ───────────────────────────────────────────────────────────────────

db = Service(
    name="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        order=1,
        ports=["5432:5432"],
        environment={
            "POSTGRES_DB":       config.env.db_name,
            "POSTGRES_USER":     config.env.db_user,
            "POSTGRES_PASSWORD": config.env.db_pass,
        },
        volumes=named_volume("db_data", "/var/lib/postgresql/data"),
        healthcheck=PgCheck(),
    ),
)

api = SpringBootService(
    name="api",
    artifact=api_project.artifact(),   # auto-detect JAR in target/
    spring_profiles="postgres",
    compose=ComposeConfig(
        order=10,
        ports=["8080:8080"],
        depends_on=[db],
        environment={
            "SPRING_DATASOURCE_URL":      f"jdbc:postgresql://db:5432/{config.env.db_name}",
            "SPRING_DATASOURCE_USERNAME": config.env.db_user,
            "SPRING_DATASOURCE_PASSWORD": config.env.db_pass,
        },
    ),
)
```

---

## solution-override.py

```python
# solution-override.py — DO NOT COMMIT
import solution

solution.config.env.db_pass = "my-local-password"
```

---

## Commands

```bash
localbox projects clone
localbox projects build
localbox services build
localbox compose generate
docker compose up -d
```

---

## What SpringBootService generates

No Dockerfile to maintain. `SpringBootService` automatically generates:

```dockerfile
FROM amazoncorretto:17

COPY --from=api target/api-*.jar /app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app.jar"]
```

And adds to `docker-compose.yml`:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 20s
```

---

## Variations

### With JVM tuning

```python
api = SpringBootService(
    name="api",
    artifact=api_project.artifact(),
    jvm_opts="-Xmx512m -Xms256m -XX:+UseG1GC",
    server_port=8080,
    compose=ComposeConfig(ports=["8080:8080"], depends_on=[db]),
)
```

### With explicit artifact path

When a project produces multiple JARs, specify the exact one:

```python
api = SpringBootService(
    name="api",
    artifact=api_project.artifact("api-module/target/api-exec.jar"),
    ...
)
```

### Disable the auto-healthcheck

```python
api = SpringBootService(
    name="api",
    artifact=api_project.artifact(),
    healthcheck=None,      # no healthcheck in docker-compose.yml
    ...
)
```

### With Gradle instead of Maven

```python
from localbox.models import gradle, graalvm

api_project = JavaProject(
    "api",
    repo="git@github.com:org/api.git",
    jdk=graalvm(21),
    builder=gradle("8.14"),
)
# SpringBootService usage is identical — it detects the artifact automatically
```

### PostgreSQL with custom user

```python
db = Service(
    name="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        order=1,
        environment={
            "POSTGRES_DB":       config.env.db_name,
            "POSTGRES_USER":     config.env.db_user,
            "POSTGRES_PASSWORD": config.env.db_pass,
        },
        volumes=named_volume("db_data", "/var/lib/postgresql/data"),
        healthcheck=PgCheck(user=config.env.db_user),  # match the DB user
    ),
)
```

---

## Multi-database setup

```python
db_primary = Service(
    name="db:primary",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        order=1,
        ports=["5432:5432"],
        environment={"POSTGRES_DB": "primary", "POSTGRES_PASSWORD": config.env.db_pass},
        volumes=named_volume("db_primary_data", "/var/lib/postgresql/data"),
        healthcheck=PgCheck(),
    ),
)

db_reporting = Service(
    name="db:reporting",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(
        order=2,
        ports=["5433:5432"],
        environment={"POSTGRES_DB": "reporting", "POSTGRES_PASSWORD": config.env.db_pass},
        volumes=named_volume("db_reporting_data", "/var/lib/postgresql/data"),
        healthcheck=PgCheck(),
    ),
)

api = SpringBootService(
    name="api",
    artifact=api_project.artifact(),
    compose=ComposeConfig(
        order=10,
        ports=["8080:8080"],
        depends_on=[db_primary, db_reporting],
    ),
)
```
