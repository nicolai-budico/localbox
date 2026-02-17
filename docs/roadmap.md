# Localbox — Product Roadmap

**Current version:** 0.1.0 (Alpha)
**Goal:** A reliable, discoverable open-source tool that a developer can find, install, and use productively within an hour.

---

## v0.3 — Distributable

### GitHub-Based Installation

```bash
pip install "git+https://github.com/localbox/localbox.git"
```

- Tag releases (`v0.3.0`, `v0.3.1`, etc.) on GitHub
- Users install pinned versions: `pip install "git+https://github.com/localbox/localbox.git@v0.3.0"`
- Bump `Development Status` classifier to `4 - Beta`
- Add status badges to README (CI passing, version, Python versions)

### GitHub Actions CI

```yaml
# .github/workflows/ci.yml
jobs:
  test:
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps: [checkout, install dev deps, pytest, ruff, mypy]
```

### README Improvements

- **Document `SpringBootService`** — add a library section alongside `TomcatService`. Currently users
  write Dockerfiles by hand not knowing auto-generation exists.
- **Add `CHANGELOG.md`** with a v0.1.0 entry (Keep a Changelog format).

---

## v0.6 — Documentation

All documentation lives in `./docs/` in the repository.

### Structure

```
docs/
├── roadmap.md           # This file
├── TRD.md               # Technical requirements
├── getting-started.md   # Walkthrough of the example/ solution
├── concepts.md          # Solution, Project, Builder, Service explained
├── api-reference.md     # All models, fields, and factory functions
└── cookbook/
    ├── spring-boot.md           # Spring Boot + PostgreSQL
    ├── node-frontend.md         # Node.js build + nginx service
    ├── multi-module-maven.md    # Projects with deps (libs → app)
    ├── custom-build-env.md      # Dockerfile-based builder
    ├── private-registry.md      # Private Docker registry + Maven settings
    └── debugging-builds.md      # How to debug a failing build
```

### Priority pages

1. **`getting-started.md`** — mirrors `example/README.md` but explains every command and why
2. **`concepts.md`** — diagram showing Solution → Projects → Builders → Services
3. **`api-reference.md`** — every field of every model, with types and defaults
4. **Troubleshooting section in README** — common failures: Docker not running, env not set, clone fails
5. **`CONTRIBUTING.md`** — how to run tests, add a feature, submit a PR

---

## Backlog (Future Improvements)

### Bug Fixes

**`compose.py` — links normalization**

The condition `":" in link.split(":")[0]` is always `False` — the first element after `split(":")` never contains a colon. Service names with `:` in the links key are not normalized to `-`. Latent bug; affects solutions using `ComposeConfig(links=...)`.

**`cli.py` — `build` command with mixed-type targets**

Passing targets that span both types (`localbox build services:db projects:api`) processes only the first prefix. The second type reaches the wrong resolver and raises `TargetError`. Should either support mixed targets or emit a clear, actionable error message.

**`builders/docker.py` — `_build_dockerfile_service` no output streaming**

Uses `subprocess.check_call` without streaming. Docker build output from library services (`TomcatService`, `SpringBootService`) is invisible until the process exits; failures surface as `CalledProcessError` with no user-readable context. Should mirror the streaming approach used in `builders/build.py`.

**`resolver.py` — `parse_target()` is dead code**

`parse_target()` is implemented but never called anywhere in the codebase. Remove or wire it up.

### DX Improvements

**`localbox validate`**

Validate solution configuration without side effects (no cloning, no building). Currently misconfigurations only surface during `build` or `compose generate`. Useful for CI sanity checks and onboarding.

**`localbox info <target>`**

Show detailed information about a single project or service:

```bash
localbox info projects:be:api   # repo URL, branch, JDK, builder, artifact pattern
localbox info services:db:main  # image, ports, volumes, depends_on, healthcheck
```

**Improved `localbox status`**

Currently shows raw `git status`. Add: current branch name, commits ahead/behind the remote, and whether a built artifact exists in `.build/projects/<name>/`.

**Compose Profiles — resolve the TODO**

Profiles are implemented but disabled with `# TODO: profiles temporarily disabled` in `compose.py`; three tests are marked `@pytest.mark.skip`. Either enable the feature with proper test coverage, or remove the dead code and delete the skipped tests.

### Test Coverage

**`commands/` module tests**

`clone_projects`, `build_projects`, `fetch_projects`, `switch_projects`, and `build_images` have no test coverage. Use `unittest.mock.patch("subprocess.run", ...)` to test the logic without real git or Docker calls.

---

## Will Not Implement

### `localbox status services` / `localbox start` / `localbox stop` / `localbox logs`

Localbox will not wrap `docker compose` commands. Docker Compose already has an excellent CLI:

```bash
docker compose ps          # service status
docker compose up -d       # start
docker compose down        # stop
docker compose logs -f api # follow logs for a service
```

Adding thin wrappers brings no value — they would immediately lag behind `docker compose`
features and options, and create an endless maintenance surface.
**Localbox's boundary is code → image. Service lifecycle is Docker Compose's domain.**

### Parallel Project Builds

`ThreadPoolExecutor` over topological waves would give a 10× speedup for large solutions,
but introduces non-trivial complexity: interleaved log output, partial failure semantics,
and interaction with the log-per-project file. Deferred until there is a concrete report
of build time being a blocker.

### PyPI Publication

Publishing to PyPI requires a stable public API, a versioning policy, and a commitment
to not break existing solution configs. Premature at alpha stage.
GitHub-based pip install (`pip install git+https://...`) is sufficient for now.

### Homebrew Tap

No macOS-specific need; pip covers all platforms. Low value for the effort of maintaining
a Homebrew tap and its release automation.
