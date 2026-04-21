# API Reference

All public symbols are importable from `localbox.models`:

```python
from localbox.models import (
    SolutionConfig, BaseEnv, env_field,
    Project, JavaProject, NodeProject, GitConfig, JavaArtifact,
    Builder, MavenBuilder, GradleBuilder, JavaBuilder, Packaging,
    DockerImage,
    Volume, BindVolume, CacheVolume, NamedVolume,
    bind_volume, cache_volume, named_volume,
    maven, gradle, mavenw, gradlew, node,
    MavenWrapperBuilder, GradleWrapperBuilder,
    JDK, JDKProvider, corretto, temurin, graalvm,
    Service, ComposeConfig,
    HealthCheck, HttpCheck, PgCheck, SpringBootCheck,
)
```

Library services (higher-level abstractions) are importable from `localbox.library`:

```python
from localbox.library import JavaService, TomcatService, SpringBootService
```

---

## SolutionConfig

```python
from localbox.models import SolutionConfig
```

Global settings for the solution. Instantiate once in `solution.py`.

```python
@dataclass
class SolutionConfig(Generic[EnvT]):
    name: str | None = None
    default_branch: str = "dev"
    build_dir: str = ".build"
    compose_project: str | None = None
    network: str | None = None
    project_dir: str | None = None
    registry: str | None = None
    env: EnvT = {}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str \| None` | `None` | Solution name. Used as Docker Compose project name and image namespace prefix if `compose_project`/`network` not set. Defaults to the directory name. |
| `default_branch` | `str` | `"dev"` | Default git branch for all projects. Per-project `branch=` overrides this. |
| `build_dir` | `str` | `".build"` | Directory for all generated artifacts (clones, caches, logs). Relative to solution root. |
| `compose_project` | `str \| None` | `None` | Docker Compose project name. Defaults to `name`. |
| `network` | `str \| None` | `None` | Docker network name. Defaults to `name`. |
| `project_dir` | `str \| None` | `None` | Overrides the default projects directory; defaults to `{build_dir}/projects`. |
| `registry` | `str \| None` | `None` | Docker registry prefix for push/pull, e.g. `registry.io/myteam`. |
| `env` | `EnvT` | `{}` | Environment definition. Use a `BaseEnv` subclass for typed access, or a plain dict. |

**Generic typing:** `SolutionConfig[Env]` gives type-aware access to `config.env` fields in IDE and type checkers.

**Example:**
```python
import dataclasses
from localbox.models import SolutionConfig, BaseEnv, env_field

@dataclasses.dataclass
class Env(BaseEnv):
    db_pass: str = env_field(is_secret=True)
    db_name: str = env_field()

config = SolutionConfig[Env](
    name="myapp",
    default_branch="main",
    env=Env(db_name="myapp"),
)
```

---

## BaseEnv / env_field / EnvRef

```python
from localbox.models import BaseEnv, EnvRef, env_field
```

Typed environment variable base class.

**Rules:**
- Subclass must be decorated with `@dataclasses.dataclass`
- Every annotated field must use `env_field()` as its default — plain string defaults are rejected at class definition time
- Fields with no value assigned in the `SolutionConfig` constructor are _required_ — `compose generate` raises `ValueError` if the field is referenced by any service
- Set required values in `solution-override.py`: `solution.config.env.db_pass = "value"`

```python
def env_field(is_secret: bool = False) -> EnvField
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `is_secret` | `bool` | `False` | If `True`, the value is masked (`***`) in log output and CLI display. |

**Example:**
```python
import dataclasses
from localbox.models import BaseEnv, env_field

@dataclasses.dataclass
class Env(BaseEnv):
    db_host: str = env_field()                  # required, visible
    db_pass: str = env_field(is_secret=True)    # required, masked
    log_level: str = env_field()                # required
```

**Referencing values in services (instance access):**

Every attribute on a `BaseEnv` instance is an `EnvRef` — a `str` subclass whose
string form is `${<field>}`. Any f-string, concatenation, or direct use in a
`ComposeConfig` field produces a Docker Compose variable reference. The raw
value lands in the generated `.env` file and is looked up at `docker compose up`
time.

```python
ComposeConfig(
    ports=[f"{config.env.db_host}:5432"],           # → "${db_host}:5432"
    environment={
        "POSTGRES_HOST":     config.env.db_host,    # → "${db_host}"
        "POSTGRES_PASSWORD": config.env.db_pass,    # → "${db_pass}"
    },
)
```

```yaml
# Generated docker-compose.yml
services:
  db:
    ports:
      - ${db_host}:5432
    environment:
      POSTGRES_HOST:     "${db_host}"
      POSTGRES_PASSWORD: "${db_pass}"
```

```env
# Generated .env (gitignored)
db_host="localhost"
db_pass="s3cr3t"
```

**Raw-value accessors** (for code paths that need the literal, e.g. a
`Builder.environment` value passed to `docker run -e`):

```python
env.raw_value("db_host")   # → "localhost"    (KeyError if unset/unknown)
env.raw_values()           # → {"db_host": "localhost", "db_pass": "s3cr3t"}
```

Direct instance assignment (`solution.config.env.db_pass = "x"`) from
`solution-override.py` is supported and updates both the `EnvRef` attribute
and the underlying raw-value map.

**EnvRef** exposes `.name` (the field name) and `.raw` (the raw value):

```python
ref = config.env.db_host                  # EnvRef
str(ref)     # "${db_host}"
ref.name     # "db_host"
ref.raw      # "localhost"
```

---

## DockerImage

```python
from localbox.models import DockerImage
```

Universal image configuration for both builders and services.

```python
@dataclass
class DockerImage:
    name: str = ""
    dockerfile: str | None = None
    image: str | None = None
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | `""` | Logical name used for tagging. For services, auto-set from `service.name` if empty. |
| `dockerfile` | `str \| None` | `None` | Path to Dockerfile, relative to solution root. When set, the image is built with `docker buildx`. The build context defaults to the Dockerfile's parent directory. |
| `image` | `str \| None` | `None` | Docker image name (e.g., `postgres:16`, `nginx:alpine`). When set without `dockerfile`, the image is pulled and tagged. |

**Service image tagging rule:** `{solution.name}/service/{service.name.replace(":", "/")}:latest`
- `"proxy"` → `myapp/service/proxy:latest`
- `"db:primary"` → `myapp/service/db/primary:latest`
- `"be:payments:api"` → `myapp/service/be/payments/api:latest`

---

## Project

```python
from localbox.models import Project
```

Base project class for any Git repository.

```python
@dataclass
class Project:
    name: str | None = None
    git: GitConfig | None = None
    builder: Builder | None = None
    depends_on: list[Project] = []

    # Convenience init params (not stored as-is)
    repo: InitVar[str | None] = None
    branch: InitVar[str | None] = None
    deps: InitVar[list[Project] | None] = None

    # Per-developer override (set in solution-override.py)
    path: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str \| None` | Unique identifier. May contain `:` for grouping: `"libs:utils"`. Set to `None` to auto-generate from module variable name and repo URL during loading. |
| `git` | `GitConfig \| None` | Full git configuration. Use `repo=` and `branch=` convenience params instead. |
| `builder` | `Builder \| None` | How to build this project. May be `None` for projects that are cloned but not built. |
| `depends_on` | `list[Project]` | Other projects this one depends on. Localbox builds dependencies first. Use `deps=` convenience param. |
| `path` | `str \| None` | Per-developer source path override. Absolute or relative to solution root. Set in `solution-override.py` when the project is already cloned elsewhere. |

**Convenience params** (accepted in constructor, not stored directly):

| Param | Equivalent to |
|-------|--------------|
| `repo="git@..."` | `git=GitConfig(url="git@...")` |
| `branch="main"` | `git=GitConfig(url=..., branch="main")` |
| `deps=[a, b]` | `depends_on=[a, b]` |

**Auto-derived fields** (read-only, set during loading):

| Field | Description |
|-------|-------------|
| `group` | Left part of name before `:` — `"libs"` for `"libs:utils"` |
| `local_name` | Right part — `"utils"` for `"libs:utils"`, equals `name` for ungrouped |

---

## GitConfig

```python
from localbox.models import GitConfig
```

```python
@dataclass
class GitConfig:
    url: str
    branch: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | Git URL. SSH (`git@github.com:org/repo.git`) or HTTPS (`https://github.com/org/repo.git`). |
| `branch` | `str \| None` | Branch to clone. Falls back to `SolutionConfig.default_branch` if `None`. |

---

## JavaProject

```python
from localbox.models import JavaProject
```

Extends `Project` with a JDK requirement. The JDK determines which Docker build image is used.

```python
@dataclass
class JavaProject(Project):
    jdk: JDK | int = 8
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `jdk` | `JDK \| int` | `8` | JDK version or full `JDK` object. An integer is automatically converted to `JDK(version)` with the default Corretto provider. |

**Note:** `JavaProject` has no default builder. You must always pass `builder=maven()`, `builder=gradle()`, or a custom `Builder`. Omitting it means the project will be cloned but not built.

**`.artifact()` method:**

```python
project.artifact() -> JavaArtifact
project.artifact("target/myapp-exec.jar") -> JavaArtifact
```

Returns a `JavaArtifact` reference for use in `TomcatService.webapps` or `SpringBootService.artifact`. With no argument, the builder auto-detects the artifact at build time. Pass an explicit relative path to override.

**Examples:**
```python
# Corretto (default)
JavaProject("api", repo="...", jdk=17, builder=maven())          # JDK 17 Corretto

# Temurin
JavaProject("api", repo="...", jdk=temurin(17), builder=maven()) # JDK 17 Temurin

# GraalVM with Gradle
JavaProject("api", repo="...", jdk=graalvm(21), builder=gradle())

# With dependencies
utils = JavaProject("libs:utils", repo="...", jdk=8, builder=maven())
app   = JavaProject("backend:app", repo="...", jdk=8, builder=maven(), deps=[utils])
```

---

## NodeProject

```python
from localbox.models import NodeProject
```

Extends `Project` for Node.js projects. Defaults to `node(20)` builder.

```python
@dataclass
class NodeProject(Project):
    output_dir: str = "dist"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | `str` | `"dist"` | Directory where the build outputs files (e.g. `"dist"`, `"build"`). Used by service Dockerfiles to `COPY --from`. |

The default builder is `node(20)`. Override with `builder=node(22)` or a custom `Builder`.

**Example:**
```python
ui = NodeProject("frontend:ui", repo="git@github.com:org/ui.git")
app = NodeProject("frontend:app", repo="git@github.com:org/app.git", output_dir="build", builder=node(22))
```

---

## JavaArtifact

```python
from localbox.models import JavaArtifact
```

Reference to a built artifact from a `JavaProject`. Created via `project.artifact()`.

```python
@dataclass
class JavaArtifact:
    project: JavaProject
    path: str | None = None
```

| Field | Type | Description |
|-------|------|-------------|
| `project` | `JavaProject` | The project that produces the artifact. |
| `path` | `str \| None` | Explicit path relative to the project root. `None` = auto-detect using the builder at build time. |

---

## Builder

```python
from localbox.models import Builder
```

Defines how to build a project inside Docker.

```python
@dataclass
class Builder:
    docker_image: DockerImage | None = None
    build_command: str | None = None
    build_command_list: list[str] | None = None
    build_script: str | None = None
    clean_command: str | None = None
    clean_command_list: list[str] | None = None
    clean_script: str | None = None
    volumes: Volume | list[Volume] = []
    environment: dict[str, str] = {}
    entrypoint: str | None = None
    workdir: str = "/var/src"
    timeout: int | None = None
```

> **Deprecated aliases:** `command`, `command_list`, and `script` are accepted but deprecated — use `build_command`, `build_command_list`, and `build_script` instead.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `docker_image` | `DockerImage \| None` | `None` | The Docker image to run, or a Dockerfile to build the image from. |
| `build_command` | `str \| None` | `None` | Shell command string for the build step: run as `sh -c "<command>"`. |
| `build_command_list` | `list[str] \| None` | `None` | Explicit argv for the build step, passed directly to Docker without a shell wrapper. |
| `build_script` | `str \| None` | `None` | Path to a build script (relative to solution root). Mounted into the container and executed. |
| `clean_command` | `str \| None` | `None` | Shell command string for the clean step (used by `localbox projects clean`). |
| `clean_command_list` | `list[str] \| None` | `None` | Explicit argv for the clean step. |
| `clean_script` | `str \| None` | `None` | Path to a clean script (relative to solution root). |
| `volumes` | `Volume \| list[Volume]` | `[]` | Volume mounts. A single `Volume` is normalized to a list. |
| `environment` | `dict[str, str]` | `{}` | Environment variables injected into the build container. |
| `entrypoint` | `str \| None` | `None` | Override the container entrypoint. Set `""` to clear the image's default entrypoint. |
| `workdir` | `str` | `"/var/src"` | Working directory inside the container. Project sources are mounted here. |
| `timeout` | `int \| None` | `None` | Build timeout in minutes. `None` = no timeout. |

Command priority: `build_script` > `build_command` > `build_command_list`. Only one should be set.

A single `Volume` passed to `volumes=` is automatically wrapped in a list.

---

## MavenBuilder / GradleBuilder

Pre-configured Java builders. Extend `JavaBuilder` and provide JDK-aware image resolution.

### MavenBuilder

```python
@dataclass
class MavenBuilder(JavaBuilder):
    version: str = "3.9"
```

Auto-configured defaults when using `maven()`:
- **Image:** resolved at build time as `maven:{version}-{jdk.maven_image_suffix()}`
- **Command:** `mvn -Duser.home=/var/maven -Dmaven.repo.local=/var/maven/.m2/repository install -Dmaven.test.skip=true`
- **Volumes:** `CacheVolume(name="maven", container="/var/maven/.m2")`
- **Entrypoint:** `""` (clears Maven image's default entrypoint)

Artifacts found in `target/*.jar` or `target/*.war`.

### GradleBuilder

```python
@dataclass
class GradleBuilder(JavaBuilder):
    version: str = "8.14"
```

Auto-configured defaults when using `gradle()`:
- **Image:** resolved as `gradle:{version}-{jdk.gradle_image_suffix()}`
- **Command:** `gradle build -x test --no-daemon -Dmaven.repo.local=/var/maven/.m2/repository`
- **Volumes:** `CacheVolume("gradle", "/var/gradle")` + `CacheVolume("maven", "/var/maven/.m2")`
- **Environment:** `GRADLE_USER_HOME=/var/gradle`, `MAVEN_LOCAL_REPO=/var/maven/.m2/repository`

Artifacts found in `build/libs/*.jar` (excluding `-plain`, `-sources`, `-javadoc`, `original-` variants).

### Appending extra Gradle tasks (`tasks=`)

`GradleBuilder` and `GradleWrapperBuilder` accept an optional `tasks: list[str] | None` field that appends extra tasks/args to the default Gradle command — useful when a Gradle module needs to publish libraries into the shared `.build/maven/.m2` cache so downstream Maven projects can consume them.

```python
# gradle build -x test --no-daemon -Dmaven.repo.local=… publishToMavenLocal
sdk = JavaProject(
    "backend:sdk",
    repo="git@github.com:org/sdk.git",
    jdk=21,
    builder=gradle(tasks=["publishToMavenLocal"]),
)
```

- Items are appended to the default command verbatim — flag-shaped items like `-PreleaseVersion=1.2.3` work too.
- `tasks` is mutually exclusive with `build_command` / `build_command_list` / `build_script` (and their deprecated aliases). Passing both raises `ValueError`.
- Maven builders (`maven()`, `mavenw()`) reject `tasks` with `ValueError` — the field is Gradle-only.
- Caveat: the default command's `-x test` still wins, so `tasks=["test"]` will not actually run tests. Use a custom `build_command_list` for that.

---

## MavenWrapperBuilder / GradleWrapperBuilder

Wrapper builders run `./mvnw` / `./gradlew` on a plain JDK image (no Maven or Gradle installed separately). The JDK image is determined from the project's JDK; the tool version comes from the wrapper scripts committed to the repository.

```python
def mavenw() -> MavenWrapperBuilder
def gradlew(*, tasks: list[str] | None = None) -> GradleWrapperBuilder
```

Use when the project ships its own wrapper scripts (`mvnw` / `gradlew` in the repository root). `gradlew()` accepts the same `tasks=` field as `gradle()` — see above.

---

## Volume types

```python
from localbox.models import BindVolume, CacheVolume, NamedVolume
from localbox.models import bind_volume, cache_volume, named_volume
```

### BindVolume

Bind mount from the host filesystem.

```python
@dataclass
class BindVolume(Volume):
    host: str = ""      # path relative to solution root, or absolute
    container: str = ""
    readonly: bool = False
```

```python
bind_volume(host: str, container: str, readonly: bool = False) -> BindVolume
```

### CacheVolume

Mounts a subdirectory of `.build/` as a volume. Used for build tool caches.

```python
@dataclass
class CacheVolume(Volume):
    name: str = ""      # folder under .build/
    container: str = ""
    readonly: bool = False
```

```python
cache_volume(name: str, container: str, readonly: bool = False) -> CacheVolume
```

### NamedVolume

Docker named volume. Declared at the top level in the generated Compose file.

```python
@dataclass
class NamedVolume(Volume):
    name: str = ""      # Docker volume name
    container: str = ""
    readonly: bool = False
```

```python
named_volume(name: str, container: str, readonly: bool = False) -> NamedVolume
```

---

## Factory functions

### maven

```python
def maven(version: str = "3.9") -> MavenBuilder
```

Creates a Maven builder. JDK is specified on the `JavaProject`, not here.

### gradle

```python
def gradle(version: str = "8.14", *, tasks: list[str] | None = None) -> GradleBuilder
```

Creates a Gradle builder. JDK is specified on the `JavaProject`, not here. The optional `tasks` keyword appends extra Gradle tasks/args to the default build command (see [GradleBuilder defaults](#gradlebuilder)).

### mavenw

```python
def mavenw() -> MavenWrapperBuilder
```

Creates a Maven wrapper builder. Runs `./mvnw` on a plain JDK image. JDK is specified on the `JavaProject`.

### gradlew

```python
def gradlew(*, tasks: list[str] | None = None) -> GradleWrapperBuilder
```

Creates a Gradle wrapper builder. Runs `./gradlew` on a plain JDK image. JDK is specified on the `JavaProject`. Accepts the same `tasks=` keyword as `gradle()`.

### node

```python
def node(version: int = 20) -> Builder
```

Creates a Node.js builder. Uses the full Debian `node:{version}` image (not Alpine) to ensure `bash` is available for build scripts.

---

## JDK

```python
from localbox.models import JDK, JDKProvider, corretto, temurin, graalvm
```

```python
@dataclass
class JDK:
    version: int
    provider: JDKProvider = JDKProvider.CORRETTO
```

| Provider | `JDKProvider` value | Maven image suffix | Gradle image suffix |
|----------|--------------------|--------------------|---------------------|
| Amazon Corretto (default) | `CORRETTO` | `amazoncorretto-{v}` | `jdk{v}` |
| Eclipse Temurin | `TEMURIN` | `eclipse-temurin-{v}` | `jdk{v}` |
| GraalVM | `GRAALVM` | `graalvm-{v}` | `jdk{v}-graal` |

**Factory functions:**

```python
corretto(version: int) -> JDK   # Amazon Corretto (same as JDK(version))
temurin(version: int) -> JDK    # Eclipse Temurin
graalvm(version: int) -> JDK    # GraalVM
```

**Runtime images** (used by `SpringBootService`):

| Provider | `jdk.runtime_image()` |
|----------|----------------------|
| Corretto | `amazoncorretto:{v}` |
| Temurin | `eclipse-temurin:{v}-jre` |
| GraalVM | `ghcr.io/graalvm/jdk:{v}` |

---

## Service

```python
from localbox.models import Service
```

```python
@dataclass
class Service:
    name: str | None = None
    image: DockerImage = DockerImage()
    compose: ComposeConfig = ComposeConfig()
    project: Project | None = None
    projects: list[Project] = []
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str \| None` | `None` | Service identifier. May contain `:` for grouping. Auto-generated from module variable name if `None`. |
| `image` | `DockerImage` | `DockerImage()` | Image configuration. |
| `compose` | `ComposeConfig` | `ComposeConfig()` | Compose-level settings. |
| `project` | `Project \| None` | `None` | Primary source project. Its build output is a Docker build context. |
| `projects` | `list[Project]` | `[]` | Additional source projects. Combined with `project` for `--build-context` entries. |

**Auto-derived:**

| Property | Description |
|----------|-------------|
| `group` | Left of `:` in name. `None` for ungrouped services. |
| `local_name` | Right of `:` in name, or full name if ungrouped. |
| `compose_name` | Name as it appears in `docker-compose.yml` — colons replaced with dashes: `"db:primary"` → `"db-primary"`. Override with `compose.service_name`. |
| `all_projects` | `[project] + projects` (excluding `None`). |

---

## ComposeConfig

```python
from localbox.models import ComposeConfig
```

```python
@dataclass
class ComposeConfig:
    order: int = 20
    hostname: str | None = None
    service_name: str | None = None
    ports: list[str] = []
    depends_on: list[Service] = []
    links: list[str] = []
    environment: dict[str, str] = {}
    volumes: Volume | list[Volume] = []
    healthcheck: HealthCheck | None = None
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `order` | `int` | `20` | Sort order within `docker-compose.yml`. Lower numbers appear first (start earlier). |
| `hostname` | `str \| None` | `None` | Docker container hostname override. Other services can reach it at this name within the network. |
| `service_name` | `str \| None` | `None` | Override the Compose service key. Defaults to `service.name.replace(":", "-")`. |
| `ports` | `list[str]` | `[]` | Port mappings in Docker format: `"8080:8080"`, `"127.0.0.1:5432:5432"`. |
| `depends_on` | `list[Service]` | `[]` | Services that must start before this one. Pass `Service` objects — names are resolved automatically. |
| `links` | `list[str]` | `[]` | Docker links in `"service:alias"` format (legacy; prefer `depends_on` + hostname). |
| `environment` | `dict[str, str]` | `{}` | Environment variables. Values may be plain strings or `config.env.<field>` (instance access on a `BaseEnv` subclass). The latter becomes `${<field>}` in the generated compose file and lands in `.env`. Class-level `Env.<field>` sentinels are rejected — use instance access. |
| `volumes` | `Volume \| list[Volume]` | `[]` | Volume mounts. A single `Volume` is normalized to a list. |
| `healthcheck` | `HealthCheck \| None` | `None` | Docker healthcheck. Use typed subclasses (`PgCheck()`, `SpringBootCheck()`). |

---

## HealthCheck

```python
from localbox.models import HealthCheck, HttpCheck, PgCheck, SpringBootCheck
```

### HealthCheck (base)

```python
@dataclass
class HealthCheck:
    test: list[str] = []
    interval: str = "30s"
    timeout: str = "10s"
    retries: int = 3
    start_period: str = "10s"
```

Use for custom checks:
```python
HealthCheck(test=["CMD", "redis-cli", "ping"])
HealthCheck(test=["CMD-SHELL", "mysqladmin ping -h localhost"], interval="15s")
```

### HttpCheck

HTTP endpoint check using `curl -f`. Non-2xx response or connection failure → unhealthy.

```python
@dataclass
class HttpCheck(HealthCheck):
    url: str = ""
    start_period: str = "20s"  # longer default than base (apps take time to start)
```

```python
HttpCheck(url="http://localhost:8080/health")
HttpCheck(url="http://localhost:9090/ready", timeout="5s", retries=5)
```

Generated test: `["CMD", "curl", "-f", url]`

### PgCheck

PostgreSQL readiness check using `pg_isready` (bundled in all official `postgres` images).

```python
@dataclass
class PgCheck(HealthCheck):
    user: str = "postgres"
    interval: str = "10s"   # more frequent than base
    timeout: str = "5s"
    retries: int = 5
```

```python
PgCheck()               # user=postgres
PgCheck(user="myapp")
```

Generated test: `["CMD-SHELL", "pg_isready -U {user}"]`

### SpringBootCheck

Spring Boot Actuator health check. Hits `/actuator/health`.

```python
@dataclass
class SpringBootCheck(HttpCheck):
    port: int = 8080
    # url auto-set to http://localhost:{port}/actuator/health
    # start_period inherited from HttpCheck: 20s
```

```python
SpringBootCheck()            # port 8080
SpringBootCheck(port=9090)
```

Added automatically by `SpringBootService`. Requires `spring-boot-starter-actuator` dependency.

---

## Library — TomcatService

```python
from localbox.library import TomcatService
```

Extends `JavaService` (which extends `Service`) for WAR deployments to Tomcat. Generates a Dockerfile automatically.

```python
@dataclass
class TomcatService(JavaService):
    webapps: dict[str, JavaArtifact] = {}
    tomcat_version: str = "9-jdk8"
    jvm_opts: str | None = None  # inherited from JavaService
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str \| None` | `None` | Service name (inherited from `Service`). |
| `compose` | `ComposeConfig` | `ComposeConfig()` | Compose config (inherited). |
| `webapps` | `dict[str, JavaArtifact]` | `{}` | Map of webapp context path → artifact. Key becomes the path in Tomcat webapps/. |
| `tomcat_version` | `str` | `"9-jdk8"` | Tomcat Docker image tag (e.g., `"9-jdk8"`, `"10-jdk17"`, `"9-jdk17"`). |
| `jvm_opts` | `str \| None` | `None` | JVM flags injected as `JAVA_OPTS` env var in the container. |

The generated Dockerfile:
1. `FROM tomcat:{tomcat_version}`
2. Removes the default Tomcat webapps (`rm -rf /usr/local/tomcat/webapps/*`)
3. `COPY --from={project}` for each webapp artifact
4. `ENV JAVA_OPTS` if `jvm_opts` is set

**Example:**
```python
be = TomcatService(
    name="be:api",
    webapps={"api": api.artifact()},
    tomcat_version="9-jdk8",
    jvm_opts="-Xmx512m",
    compose=ComposeConfig(order=10, ports=["8080:8080"], depends_on=[db]),
)
```

---

## Library — SpringBootService

```python
from localbox.library import SpringBootService
```

Extends `JavaService` for Spring Boot JAR deployments. Generates a Dockerfile automatically and adds a Spring Actuator healthcheck by default.

```python
@dataclass
class SpringBootService(JavaService):
    artifact: JavaArtifact | None = None
    spring_profiles: str | None = None
    server_port: int = 8080
    healthcheck: HealthCheck | None | _AUTO = _AUTO  # see below
    jvm_opts: str | None = None  # inherited
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str \| None` | `None` | Service name (inherited). |
| `compose` | `ComposeConfig` | `ComposeConfig()` | Compose config (inherited). |
| `artifact` | `JavaArtifact \| None` | `None` | The JAR to deploy. Create via `project.artifact()`. |
| `project` | `JavaProject \| None` | _(from artifact)_ | Inferred from `artifact.project` automatically. |
| `spring_profiles` | `str \| None` | `None` | Comma-separated Spring profiles injected as `SPRING_PROFILES_ACTIVE`. |
| `server_port` | `int` | `8080` | Port the app listens on. Used in the generated `EXPOSE` and `SpringBootCheck`. |
| `jvm_opts` | `str \| None` | `None` | JVM flags added to the `ENTRYPOINT` array (e.g., `"-Xmx512m -Xms256m"`). |
| `healthcheck` | `HealthCheck \| None \| sentinel` | `_AUTO` | `_AUTO` (default) → add `SpringBootCheck(port=server_port)`. `None` → no healthcheck. `HealthCheck` instance → use it. |

**Healthcheck control:**

```python
# Default: auto-adds SpringBootCheck(port=8080)
SpringBootService(name="be:api", artifact=proj.artifact(), ...)

# Custom port
SpringBootService(..., server_port=9090)  # → SpringBootCheck(port=9090)

# Disable
SpringBootService(..., healthcheck=None)

# Custom check
SpringBootService(..., healthcheck=HttpCheck(url="http://localhost:8080/my-health"))
```

The generated Dockerfile:
1. `FROM {jdk.runtime_image()}` (e.g., `eclipse-temurin:17-jre`)
2. `COPY --from={project} {artifact_path} /app.jar`
3. `ENV SPRING_PROFILES_ACTIVE` if `spring_profiles` is set
4. `EXPOSE {server_port}`
5. `ENTRYPOINT ["java", {jvm_opts...}, "-jar", "/app.jar"]`

---

## Library — JavaService

```python
from localbox.library import JavaService
```

Base class for Java runtime services. Adds JVM configuration.

```python
@dataclass
class JavaService(Service):
    jvm_opts: str | None = None
```

| Field | Description |
|-------|-------------|
| `jvm_opts` | JVM flags. Applied differently by subclasses: as `JAVA_OPTS` env var in Tomcat, as ENTRYPOINT args in SpringBoot. |

---

## Target syntax reference

The CLI is domain-first: `localbox <domain> <command> [targets…]`. Targets are short-form tokens **scoped to the current domain** — no `projects:` or `services:` prefix:

```
[<group>:]<name>   or   <group>
```

| Target under `localbox projects …` | Meaning |
|------------------------------------|---------|
| *(none)* | All projects |
| `api` | Ungrouped project `"api"` (or whole group `"api"` if no exact match) |
| `libs` | All projects in the `"libs"` group |
| `libs:utils` | Project `"libs:utils"` |

| Target under `localbox services …` | Meaning |
|------------------------------------|---------|
| *(none)* | All services |
| `db` | All services in the `"db"` group |
| `db:primary` | Service `"db:primary"` |

Multiple targets are accepted by most commands (union, deduplicated):
```bash
localbox projects clone libs backend
localbox projects build libs:utils backend:app
```
