# Developer Guide

This guide covers setting up a development environment, running checks, and releasing new versions of Localbox.

---

## Setup

```bash
git clone git@github.com:nicolai-budico/localbox.git
cd localbox
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

This installs Localbox in editable mode with all development dependencies (pytest, ruff, mypy).

---

## Running Checks

All four checks must pass before committing or opening a PR. CI enforces the same set.

```bash
ruff format src/ tests/       # 1. Auto-format
ruff check src/ tests/        # 2. Lint
mypy src/localbox/            # 3. Type-check
pytest tests/ -q              # 4. Tests
```

Run them in this order — formatting first, so the linter sees clean code.

### Tests

```bash
pytest tests/ -v              # verbose output
pytest tests/test_models.py   # single file
pytest tests/ -k "test_name"  # single test by name
```

Tests are pure unit tests — no Docker or network access required.

### Linting and Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) for both linting and formatting. Configuration is in `pyproject.toml`:

- Target: Python 3.10
- Line length: 100
- Lint rules: `E`, `F`, `I`, `N`, `W`, `UP`

### Type Checking

[mypy](https://mypy-lang.org/) runs in strict mode (`disallow_untyped_defs = true`). All public functions must have type annotations.

---

## Project Layout

```
src/localbox/
├── cli.py                   # Click CLI entry point
├── config.py                # Solution detection & Python module loading
├── models/                  # Core data models (Project, Builder, Service, etc.)
├── commands/                # CLI command implementations
├── builders/                # Docker build runner, Compose generation
├── library/                 # Pre-built service types (SpringBootService, etc.)
├── completions/             # Shell completion scripts
└── utils/                   # Target resolver, helpers
```

Tests live in `tests/` and mirror the source structure.

---

## Branch Model

```
main          ──A──B──C──D──────────────────────── (version = "0.0.0-dev")
                            \
release-0.2.X               ──[merge + resolve + bump]──┐
                                                         ↓
v0.2          ──[prev]───────────────────────────[merge PR]  ← tag v0.2.X
```

- **`main`** — development branch. Feature branches are rebased and merged here with `--no-ff`. Carries a `0.0.0-dev` sentinel in `pyproject.toml`; the release script resolves the resulting conflict deterministically.
- **`v0.2`** — active stable release branch. Only advances via release PRs. This is what users install from.
- **`release-X.Y.Z`** — short-lived branch created during the release process.
- **`v0.1`** — archived. Not wired into CI, no longer receives patches. Existing `@v0.1` install URLs still resolve.
- **`RELEASE_BRANCH`** — env var (default: `v0.2`) that the release scripts consult, so a future `v0.3` line is a one-env-var override.

---

## CI

CI runs on every push to `main` and on PRs targeting `main`. It has three jobs:

| Job | What it does |
|-----|--------------|
| **Lint** | `ruff check` + `ruff format --check` |
| **Type check** | `mypy src/localbox` |
| **Test** | `pytest tests/` on Python 3.10, 3.11, 3.12 |

All three must pass for a PR to be mergeable.

---

## Making Changes

1. Create a feature branch from `main`:
   ```bash
   git checkout main && git pull
   git checkout -b my-feature
   ```

2. Make changes, run checks locally (see [Running Checks](#running-checks)).

3. Push and open a PR targeting `main`:
   ```bash
   git push -u origin my-feature
   gh pr create --base main
   ```

4. After review and CI pass, merge the PR (no squash — use merge commit).

---

## Release Process

### Step 1 — Prepare the release

Run from anywhere inside the repo:

```bash
./scripts/create-release-pr.sh
```

The script will:
1. Fetch origin, read the current version from `v0.2` (or `$RELEASE_BRANCH`), compute the next patch version
2. Create a `release-<next>` branch from `v0.2`
3. Merge `main` into the release branch (no-commit), resolve the expected `pyproject.toml` conflict by taking `main`'s side, bump version, commit
4. Push the branch and open a PR: `release-<next>` → `v0.2`
5. Wait for CI to pass

Alternatively, trigger the **Release Prepare** workflow from the GitHub Actions UI — it does the same thing.

### Step 2 — Merge the PR

Review the PR, then merge. **Do not squash or rebase** — use the default merge strategy so the commit is signed by GitHub.

```bash
gh pr merge --merge
```

### Step 3 — Automatic tagging and release

When the PR merges into `v0.2`, the **Release Create** workflow fires automatically:
- Reads the version from `pyproject.toml`
- Creates an annotated tag (`v0.2.X`) on the merge commit
- Publishes a GitHub Release with auto-generated notes

Monitor the workflow:

```bash
gh run list --workflow=release-create.yml --limit=1
gh run watch
```

### Verifying a release

```bash
# Check the tag exists
git fetch --tags && git tag -l "v0.2.*" | tail -5

# Check GitHub release
gh release list --limit=5

# Test installation
pip install --upgrade "git+https://github.com/nicolai-budico/localbox.git@v0.2"
localbox --version
```
