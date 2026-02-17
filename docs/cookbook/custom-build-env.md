# Cookbook: Custom Build Environment

For cases where the standard Maven, Gradle, or Node builders aren't enough — custom toolchains, special OS requirements, or build scripts that need extra setup.

---

## What this covers

- Dockerfile-based builders for complete control over the build environment
- Mounting configuration files into the build container (`bind_volume`)
- Multi-step build scripts (`script` field)
- Build timeouts for large projects
- Composing a custom builder with a `BindVolume` for secrets

---

## When to use a custom builder

Use a Dockerfile-based builder when:

- Your build tool isn't Maven, Gradle, or Node (e.g. Ant, sbt, custom scripts)
- You need OS-level packages (e.g. `libssl-dev`, `gcc`)
- You need to inject configuration files (Maven `settings.xml`, `.npmrc`, `.netrc`)
- You need a specific runtime that doesn't have a public Docker Hub image
- You need a multi-step build that can't be expressed as a single command string

---

## Pattern 1 — Dockerfile-based builder

### solution.py

```python
from localbox.models import (
    SolutionConfig,
    JavaProject,
    Builder, DockerImage,
    bind_volume, cache_volume,
)

config = SolutionConfig(name="myapp")

api = JavaProject(
    "api",
    repo="git@github.com:org/api.git",
    jdk=17,
    builder=Builder(
        docker_image=DockerImage(
            name="custom-maven",
            dockerfile="assets/dockerfiles/builder/Dockerfile",
        ),
        command="mvn -Duser.home=/var/maven install -Dmaven.test.skip=true",
        volumes=[
            cache_volume("maven", "/var/maven/.m2"),
        ],
    ),
)
```

### assets/dockerfiles/builder/Dockerfile

```dockerfile
FROM maven:3.9-amazoncorretto-17

# Install extra OS packages needed for native compilation
RUN yum install -y libssl-dev curl

# Copy custom Maven wrapper or config
COPY settings.xml /var/maven/.m2/settings.xml

# Default entrypoint is the same (sh -c "...")
```

When `dockerfile` is set, Localbox runs `docker buildx build` to create the builder image before running it.

---

## Pattern 2 — Mount a Maven settings.xml

If you don't want to embed secrets in a Dockerfile (good practice), mount a `settings.xml` that lives outside version control:

```python
from localbox.models import (
    JavaProject, maven,
    BindVolume,
)

api = JavaProject(
    "api",
    repo="git@github.com:org/api.git",
    jdk=17,
    builder=maven("3.9"),
)

# Extend the default maven builder
api.builder.volumes.append(
    BindVolume(
        host="~/.m2/settings.xml",    # from user's home (absolute path OK)
        container="/var/maven/.m2/settings.xml",
        readonly=True,
    )
)
```

Or build the builder inline:

```python
from localbox.models import Builder, DockerImage, bind_volume, cache_volume, maven

mvn = maven("3.9")
mvn.volumes = [
    cache_volume("maven", "/var/maven/.m2"),
    bind_volume("assets/maven/settings.xml", "/var/maven/.m2/settings.xml", readonly=True),
]
```

`bind_volume(host, container)` resolves `host` relative to the solution root if it is not an absolute path.

---

## Pattern 3 — Build script

For complex multi-step builds, put the logic in a shell script and reference it with `script=`:

```python
from localbox.models import Builder, DockerImage, cache_volume

builder = Builder(
    docker_image=DockerImage(name="jdk17", image="amazoncorretto:17"),
    script="assets/scripts/build-api.sh",     # relative to solution root
    volumes=[
        cache_volume("maven", "/root/.m2"),
    ],
)
```

Localbox mounts the script at `/build.sh` inside the container and runs it with `sh /build.sh`.

### assets/scripts/build-api.sh

```bash
#!/bin/sh
set -e

# Install build tool if needed
curl -s https://downloads.apache.org/maven/maven-3/3.9.9/binaries/apache-maven-3.9.9-bin.tar.gz \
  | tar xz -C /opt/
export PATH=/opt/apache-maven-3.9.9/bin:$PATH

# Generate code from protobuf first
/usr/local/bin/protoc --java_out=src/main/java/ proto/*.proto

# Then build
mvn install -Dmaven.test.skip=true
```

---

## Pattern 4 — Custom Node.js environment

For Node.js builds that need a custom registry, environment-specific config, or yarn:

```python
from localbox.models import NodeProject, Builder, DockerImage, cache_volume

ui = NodeProject(
    "frontend:ui",
    repo="git@github.com:org/ui.git",
    builder=Builder(
        docker_image=DockerImage(name="node-20", image="node:20"),
        command="npm ci && npm run build",
        volumes=[
            cache_volume("node", "/home/node/.npm"),
        ],
        environment={
            "npm_config_cache": "/home/node/.npm",
            "NPM_TOKEN": "read-from-env-or-override",
        },
    ),
)
```

Or with yarn:

```python
builder=Builder(
    docker_image=DockerImage(name="node-20", image="node:20"),
    command="yarn install --frozen-lockfile && yarn build",
    volumes=[
        cache_volume("yarn", "/home/node/.yarn"),
    ],
    environment={"YARN_CACHE_FOLDER": "/home/node/.yarn"},
)
```

---

## Pattern 5 — Timeout for large builds

For projects that sometimes get stuck (infinite loop, hung network call):

```python
from localbox.models import Builder, DockerImage, cache_volume

builder = Builder(
    docker_image=DockerImage(name="maven39-jdk17", image="maven:3.9-amazoncorretto-17"),
    command="mvn install -Dmaven.test.skip=true",
    volumes=[cache_volume("maven", "/var/maven/.m2")],
    timeout=45,    # kill after 45 minutes; exit code 124
)
```

If the build exceeds `timeout` minutes, Localbox kills the container and reports an error.

---

## Pattern 6 — Fully custom builder image with entrypoint

Some images use a non-standard entrypoint. Override it to run a shell command:

```python
builder = Builder(
    docker_image=DockerImage(name="sbt", image="sbtscala/scala-sbt:eclipse-temurin-17.0.5_8_1.8.2_2.13.10"),
    command="sbt clean assembly",
    entrypoint="",    # override the image's entrypoint so "sh -c <command>" works
    volumes=[
        cache_volume("ivy2", "/root/.ivy2"),
        cache_volume("sbt",  "/root/.sbt"),
    ],
)
```

Setting `entrypoint=""` clears the image's default ENTRYPOINT, letting Localbox run the command via `sh -c`.

---

## Builder field reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `docker_image` | `DockerImage` | `None` | Image or Dockerfile to use |
| `command` | `str` | `None` | Shell command (passed to `sh -c`) |
| `command_list` | `list[str]` | `None` | Explicit argv (bypasses shell) |
| `script` | `str` | `None` | Path to script (relative to solution root) |
| `volumes` | `list[Volume]` | `[]` | Volume mounts |
| `environment` | `dict[str, str]` | `{}` | Environment variables |
| `entrypoint` | `str` | `None` | Override container entrypoint (`""` to clear) |
| `workdir` | `str` | `/var/src` | Container working directory (source root) |
| `timeout` | `int` | `None` | Kill container after N minutes |

Only one of `command`, `command_list`, or `script` is used — checked in that order.
