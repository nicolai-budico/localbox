# Cookbook: Debugging Builds

When a build fails, Localbox gives you several tools to find out what went wrong — from reading log files to running the build container interactively.

---

## What this covers

- Reading build logs
- Verbose mode (see the full Docker command)
- Forcing a clean build with `--no-cache`
- Running the build container manually for interactive debugging
- Common errors and their causes

---

## Step 1 — Read the build log

Every project build writes its output to a log file:

```
.build/logs/<project-name>.log
```

For a project named `backend:api`, the log is at `.build/logs/api.log`.

```bash
cat .build/logs/api.log
```

The log contains the full build output — Maven resolver output, compiler errors, test failures, etc. This is usually enough to identify the problem.

---

## Step 2 — Run in verbose mode

Add `-v` before the subcommand to see the exact Docker command that Localbox constructs:

```bash
localbox -v build projects:backend:api
```

Verbose output shows:
- The Docker `run` command with all flags expanded
- Every volume mount
- The image tag being used
- The exact build command

Example verbose output:

```
Building backend:api...
  $ docker run --rm --name localbox-build-a1b2c3d4 \
    --user 1000:1000 \
    -v /home/user/myapp/.build/projects/api:/var/src \
    -w /var/src \
    -v /home/user/myapp/.build/maven:/var/maven/.m2 \
    -e MAVEN_REPO=/var/maven/.m2 \
    myapp/builder/api:latest \
    mvn -Duser.home=/var/maven install -Dmaven.test.skip=true
```

You can copy this command and run it yourself to get interactive output.

---

## Step 3 — Force a clean build

Docker caches layers. If you suspect a stale builder image or cached dependency:

```bash
# Rebuild without Docker layer cache
localbox build projects:backend:api --no-cache

# Also works for service images
localbox build services:be:api --no-cache
```

`--no-cache` passes `--no-cache` to `docker build` and rebuilds all layers from scratch.

---

## Step 4 — Check project status

```bash
localbox status projects
```

This shows which projects are cloned, which branch they're on, and when they were last built. If a project shows "not cloned", the source directory is missing — run `localbox clone projects` first.

---

## Step 5 — Run the build container interactively

Get a shell inside the exact build environment to debug manually:

1. Find the builder image name from verbose output (e.g. `myapp/builder/api:latest`)
2. Find the source directory: `.build/projects/api/`

```bash
docker run --rm -it \
  --user "$(id -u):$(id -g)" \
  -v "$(pwd)/.build/projects/api:/var/src" \
  -v "$(pwd)/.build/maven:/var/maven/.m2" \
  -w /var/src \
  myapp/builder/api:latest \
  bash
```

Once inside:
```bash
# Try the build command manually
mvn -Duser.home=/var/maven install -Dmaven.test.skip=true

# Inspect the directory
ls -la /var/src

# Check Maven cache
ls /var/maven/.m2/repository
```

This is the fastest way to reproduce and fix environment issues interactively.

---

## Step 6 — Inspect service image builds

Service images are built with `docker buildx build`. To debug a failing service build:

```bash
localbox -v build services:be:api
```

This prints the full `docker buildx build` command, including all `--build-context` arguments. If a `COPY --from=api` fails, check that:

1. `localbox build projects:backend:api` completed successfully
2. The artifact path in the Dockerfile matches what was actually produced

---

## Common errors

### "No builder configured for project"

The `Project` (not `JavaProject`) base class has no default builder. You must set one explicitly:

```python
# Wrong — Project has no builder
api = Project("api", repo="...")

# Correct — use JavaProject with explicit builder
from localbox.models import JavaProject, maven
api = JavaProject("api", repo="...", jdk=17, builder=maven())
```

### "Source directory not found" / "not cloned"

The project hasn't been cloned yet:

```bash
localbox clone projects:backend:api
```

Or if you see output like `Skip api (not cloned)`, the clone failed or was never run.

### Maven: "Could not resolve artifact"

The Maven dependency can't be found. Possible causes:

1. **Missing dependency in cache** — A library that `api` depends on via `deps=` wasn't built first. Build in the correct order:
   ```bash
   localbox build projects:libs    # build libraries first
   localbox build projects:backend # then applications
   ```

2. **Private registry not configured** — Add a `settings.xml` with your Nexus/Artifactory URL. See [private-registry.md](private-registry.md).

3. **No network access** — The build container can't reach Maven Central. Check Docker network settings.

### Maven: "Build timed out after N minutes"

The `timeout` on the builder was exceeded. Increase it:

```python
builder = maven("3.9")
builder.timeout = 60    # 60 minutes
```

Or `None` for no timeout.

### Gradle: "Could not resolve ... -plain.jar"

Localbox filters out `-plain.jar` and `-sources.jar` artifacts automatically for Gradle. If the service Dockerfile refers to the wrong artifact, check:

```bash
ls .build/projects/api/build/libs/
```

And update the `COPY` line in your Dockerfile to match the actual filename.

### "Dockerfile not found"

```
FileNotFoundError: Dockerfile not found: /path/to/solution/assets/Dockerfile
```

The path in `DockerImage(dockerfile="...")` is resolved relative to the solution root. Check that the file exists:

```bash
ls assets/dockerfiles/
```

### Service starts but fails healthcheck

The container started but the healthcheck command is failing. Inspect container logs:

```bash
docker compose logs api
```

Or exec into the container:

```bash
docker compose exec api sh
curl http://localhost:8080/actuator/health
```

---

## Checking what Localbox sees

```bash
# List all detected projects and services
localbox list projects
localbox list services

# Show full status (cloned, branch, last build)
localbox status projects
```

If a project or service isn't listed, it wasn't detected. Common reasons:

- The `solution.py` module wasn't loaded (syntax error in one of the Python files)
- The object wasn't assigned to a module-level variable (it was defined inside a function)
- The file isn't in a recognized location (`projects/*.py`, `services/*.py`, etc.)

Run `python solution.py` from the solution root to check for syntax errors:

```bash
cd my-solution
python solution.py    # should produce no output if all imports are correct
```

---

## Log file locations

| File | Contents |
|------|----------|
| `.build/logs/<project>.log` | Full output of the last project build |
| `.build/logs/` | All build logs (one file per project) |
| `docker compose logs <service>` | Runtime logs of a running service |

Logs are overwritten on each build, so if you need to preserve them, copy them before re-running.
