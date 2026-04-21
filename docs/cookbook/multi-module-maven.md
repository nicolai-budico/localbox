# Cookbook: Multi-Module Maven (Libraries → Applications)

A recipe for solutions where shared libraries must be built before the applications that depend on them.

---

## What this covers

- Build-time dependencies between `JavaProject` objects via `deps=`
- Topological build ordering (localbox handles it automatically)
- Shared library JARs installed into the Maven cache
- Pattern for a typical `libs → core → app` dependency chain

---

## The dependency chain

```
libs:commons  (shared utilities, no deps)
     │
     └──► libs:security  (depends on commons)
               │
               └──► backend:api  (depends on security + commons)
               └──► backend:worker  (depends on security)
```

Localbox computes the topological order and runs builds sequentially:
`commons → security → api, worker`

---

## projects/libs.py

```python
from localbox.models import JavaProject, maven

mvn = maven("3.9")

commons = JavaProject(
    "libs:commons",
    repo="git@github.com:org/commons.git",
    jdk=8,
    builder=mvn,
)

security = JavaProject(
    "libs:security",
    repo="git@github.com:org/security.git",
    jdk=8,
    builder=mvn,
    deps=[commons],           # built after commons
)
```

## projects/backend.py

```python
from localbox.models import JavaProject, maven
import projects.libs as libs

mvn = maven("3.9")

api = JavaProject(
    "backend:api",
    repo="git@github.com:org/api.git",
    jdk=17,
    builder=mvn,
    deps=[libs.commons, libs.security],  # built after both libs
)

worker = JavaProject(
    "backend:worker",
    repo="git@github.com:org/worker.git",
    jdk=17,
    builder=mvn,
    deps=[libs.security],
)
```

## solution.py

```python
from localbox.models import SolutionConfig

config = SolutionConfig(name="myapp", default_branch="main")

# Auto-imported from projects/ and services/ (if __init__.py exists)
# Import them explicitly to make the graph visible:
import projects.libs      # noqa: F401  (ensures objects are collected)
import projects.backend   # noqa: F401
```

> **Note:** If `projects/` has `__init__.py`, these modules are auto-imported and you don't need explicit imports in `solution.py`.

---

## How shared libraries work

Maven uses a local repository cache (`.build/maven/`). When `libs:commons` is built, its JAR is installed into the Maven cache via `mvn install`. When `backend:api` is built, Maven resolves `commons` from that same cache — no additional setup required.

```
.build/maven/repository/
└── com/
    └── org/
        ├── commons-1.0.0.jar      ← installed by libs:commons build
        └── security-1.0.0.jar     ← installed by libs:security build
```

This works because all Maven builds share the same `.build/maven/` cache volume.

---

## Building

```bash
# Build everything in the correct order
localbox projects build

# Build only the libs group
localbox projects build libs

# Build only a specific project (its deps are NOT auto-built)
localbox projects build libs:commons
```

> **Warning:** If you build a specific project without its dependencies, Maven will fail if the dependency JARs aren't already in the cache.

---

## Variations

### Gradle multi-project build (single repo)

If your entire dependency graph lives in one Gradle multi-project repository, you only need one `JavaProject`:

```python
monorepo = JavaProject(
    "backend",
    repo="git@github.com:org/backend-monorepo.git",
    jdk=21,
    builder=gradle("8.14"),
    # All subprojects are built by `gradle build`
)
```

### Mixed Maven + Gradle

The `.build/maven/.m2` cache volume is shared by every Java builder in the solution (`maven()`, `gradle()`, `mavenw()`, `gradlew()`). Both `maven()` and `gradle()` are configured with `-Dmaven.repo.local=/var/maven/.m2/repository`, so artifacts written by one tool are visible to the other on the next build.

#### Maven libs → Gradle app

Maven's default `mvn install` writes to the local repo. No extra configuration needed — the Gradle app picks up the JARs via Maven Local resolution.

```python
lib = JavaProject(
    "libs:commons",
    repo="git@github.com:org/commons.git",
    jdk=8,
    builder=maven(),       # publishes to .build/maven/.m2/repository
)

app = JavaProject(
    "backend:app",
    repo="git@github.com:org/app.git",
    jdk=17,
    builder=gradle(),      # reads from the same .m2/repository
    deps=[lib],
)
```

#### Gradle libs → Maven apps

Gradle's default `gradle build` does **not** publish to Maven Local — it writes JARs to `build/libs/` only. To make a Gradle module's libraries available to downstream Maven projects, use the `tasks=` field on the Gradle builder to append `publishToMavenLocal` (the Gradle module must apply the `maven-publish` plugin):

```python
sdk = JavaProject(
    "backend:sdk",
    repo="git@github.com:org/sdk.git",     # Gradle multi-project
    jdk=21,
    builder=gradle(tasks=["publishToMavenLocal"]),
    # → gradle build -x test --no-daemon -Dmaven.repo.local=… publishToMavenLocal
)

api = JavaProject(
    "backend:api",
    repo="git@github.com:org/api.git",     # Maven app that consumes sdk
    jdk=21,
    builder=maven(),
    deps=[sdk],                            # built after sdk publishes
)
```

This pattern works equally well for `gradlew()`. The same shared `.build/maven/.m2` cache means no copy-step is needed between builds.

### SNAPSHOT versions

If your libraries use SNAPSHOT versions, make sure `mvn install` is the build command (default). Snapshots are installed locally and resolved in dependent builds.

### Different JDK versions across the chain

Each project picks its own JDK:

```python
lib_8  = JavaProject("libs:legacy", repo="...", jdk=8,  builder=maven())
lib_17 = JavaProject("libs:modern", repo="...", jdk=17, builder=maven())
app    = JavaProject("backend:app", repo="...", jdk=17, builder=maven(), deps=[lib_8, lib_17])
```

Localbox uses the appropriate Maven Docker image per project. All artifacts land in the shared `.build/maven/` cache regardless of JDK version.

---

## Listing the resolved build order

After defining projects, you can inspect what `localbox projects build` would do:

```bash
localbox projects list
```

Projects are displayed in group/tree form. The actual build order is computed from the dependency graph at build time and printed as builds proceed.
