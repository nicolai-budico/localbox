# Cookbook: Private Docker Registry & Private Maven Repository

A recipe for environments where images are pulled from a private Docker registry and Maven artifacts come from a private artifact repository (Nexus, Artifactory, etc.).

---

## What this covers

- Using private Docker registry images for services
- Authenticating with a private Docker registry
- Mounting a custom Maven `settings.xml` to reach a private Nexus/Artifactory
- Private npm registry configuration
- Keeping credentials out of version control

---

## Private Docker registry for services

To use an image from a private registry, just set the full image reference:

```python
from localbox.models import Service, DockerImage, ComposeConfig

db = Service(
    name="db",
    image=DockerImage(image="registry.company.com/infra/postgres:16-hardened"),
    compose=ComposeConfig(
        order=1,
        ports=["5432:5432"],
    ),
)
```

Docker pulls from `registry.company.com` using your local Docker credentials (`docker login registry.company.com`).

Localbox does not manage Docker credentials — use `docker login` or a credential helper configured in `~/.docker/config.json`.

---

## Private registry for builders

The same applies to builder images:

```python
from localbox.models import Builder, DockerImage, cache_volume

internal_builder = Builder(
    docker_image=DockerImage(
        name="internal-maven",
        image="registry.company.com/tools/maven:3.9-jdk17",
    ),
    build_command="mvn install -Dmaven.test.skip=true",
    volumes=[cache_volume("maven", "/var/maven/.m2")],
)
```

---

## Private Maven repository (Nexus / Artifactory)

The standard approach is to mount a `settings.xml` into the Maven cache directory. This keeps credentials out of the repository.

### assets/maven/settings.xml

Create this file at `assets/maven/settings.xml` (and add to `.gitignore`):

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.0.0">
  <mirrors>
    <mirror>
      <id>nexus</id>
      <mirrorOf>*</mirrorOf>
      <url>https://nexus.company.com/repository/maven-public/</url>
    </mirror>
  </mirrors>

  <servers>
    <server>
      <id>nexus</id>
      <username>${env.NEXUS_USER}</username>
      <password>${env.NEXUS_PASS}</password>
    </server>
  </servers>
</settings>
```

Using `${env.NEXUS_USER}` means Maven reads credentials from environment variables at build time — the file itself can be committed without secrets.

### solution.py

```python
import dataclasses
from localbox.models import (
    SolutionConfig, BaseEnv, env_field,
    JavaProject, maven,
    bind_volume,
)

@dataclasses.dataclass
class Env(BaseEnv):
    nexus_user: str = env_field()
    nexus_pass: str = env_field(is_secret=True)

config = SolutionConfig[Env](
    name="myapp",
    env=Env(nexus_user="ci-reader"),  # nexus_pass must be set in solution-override.py
)

mvn = maven("3.9")
mvn.volumes.append(
    bind_volume(
        "assets/maven/settings.xml",
        "/var/maven/.m2/settings.xml",
        readonly=True,
    )
)
# Pass credentials from env into the build container.
# Instance access returns an EnvRef (a str whose value is "${nexus_user}"),
# but the build runner unwraps EnvRef values back to their raw strings before
# passing them to `docker run -e`, because Docker does not perform ${...}
# substitution on `-e KEY=VALUE` arguments the way docker-compose does.
mvn.environment["NEXUS_USER"] = config.env.nexus_user
mvn.environment["NEXUS_PASS"] = config.env.nexus_pass   # resolved at runtime

api = JavaProject(
    "api",
    repo="git@github.com:org/api.git",
    jdk=17,
    builder=mvn,
)
```

### solution-override.py

```python
# DO NOT COMMIT
import solution
solution.config.env.nexus_pass = "my-secret-password"
```

---

## Alternative: settings.xml from ~/.m2

If every developer already has a configured `~/.m2/settings.xml` on their machine, mount it directly:

```python
from pathlib import Path
from localbox.models import BindVolume

home = str(Path.home() / ".m2" / "settings.xml")

mvn = maven("3.9")
mvn.volumes.append(BindVolume(host=home, container="/var/maven/.m2/settings.xml", readonly=True))
```

`BindVolume` with an absolute path mounts it as-is. With a relative path it resolves from the solution root.

---

## Private npm registry

### Option A — environment variable (.npmrc style)

```python
from localbox.models import Builder, DockerImage, cache_volume

ui_builder = Builder(
    docker_image=DockerImage(name="node-20", image="node:20"),
    build_command="npm ci && npm run build",
    volumes=[cache_volume("node", "/home/node/.npm")],
    environment={
        "npm_config_cache": "/home/node/.npm",
        "npm_config_registry": "https://nexus.company.com/repository/npm-public/",
        "npm_config__auth": "base64encodeduser:pass",  # from override
    },
)
```

### Option B — mount .npmrc file

```
assets/npm/.npmrc:
  registry=https://nexus.company.com/repository/npm-public/
  //nexus.company.com/repository/npm-public/:_authToken=${NPM_TOKEN}
```

```python
from localbox.models import Builder, DockerImage, cache_volume, bind_volume

ui_builder = Builder(
    docker_image=DockerImage(name="node-20", image="node:20"),
    build_command="npm ci && npm run build",
    volumes=[
        cache_volume("node", "/home/node/.npm"),
        bind_volume("assets/npm/.npmrc", "/home/node/.npmrc", readonly=True),
    ],
    environment={
        "npm_config_cache": "/home/node/.npm",
        "NPM_TOKEN": "my-token",   # set via solution-override.py or env
    },
)
```

---

## Private Gradle repository

Mount a `gradle.properties` or `init.gradle` for Gradle:

```
assets/gradle/init.gradle:
  allprojects {
      repositories {
          maven {
              url "https://nexus.company.com/repository/maven-public/"
              credentials {
                  username = System.getenv("NEXUS_USER") ?: ""
                  password = System.getenv("NEXUS_PASS") ?: ""
              }
          }
      }
  }
```

```python
from localbox.models import GradleBuilder, cache_volume, bind_volume

gr = GradleBuilder()
gr.volumes.append(
    bind_volume("assets/gradle/init.gradle", "/var/gradle/init.d/init.gradle", readonly=True)
)
gr.environment["NEXUS_USER"] = "ci-reader"
gr.environment["NEXUS_PASS"] = "..."    # from override

project = JavaProject("api", repo="...", jdk=17, builder=gr)
```

Gradle reads `init.d/init.gradle` from `GRADLE_USER_HOME` automatically.

---

## .gitignore recommendations

```gitignore
# Local override (secrets)
solution-override.py

# Maven settings with embedded credentials
assets/maven/settings-local.xml

# npm token files
assets/npm/.npmrc
```

Keep parameterized settings files (with `${env.VAR}` / `${ENV_VAR}`) in version control; keep files with literal credentials out.
