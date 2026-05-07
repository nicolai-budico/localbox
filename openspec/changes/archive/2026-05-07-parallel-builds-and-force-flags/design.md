## Context

On persistent hosts, repos accumulate dirty state between runs: modified tracked files, untracked build artifacts, detached HEADs left by `switch --manifest`. This causes `git pull --rebase` and `git checkout` to fail. Sequential builds underutilize available CPU cores despite a warm Maven/Gradle/npm cache.

Current state:
- `projects fetch` always uses `git pull --rebase` — fails on dirty trees
- `projects switch` runs `git checkout` without pre-cleaning — fails if artifacts would be overwritten
- `projects build` and `services build` run sequentially — N builds × single-core time
- `toposort` (non-flattened) already yields `list[set[str]]` — tier structure is available

## Goals / Non-Goals

**Goals:**
- `--force` on fetch/switch: hard-reset repos to a clean state, tolerating any working tree condition
- `-j <jobs>` on projects/services build: parallel execution within each independent tier; default `1` (sequential)
- Preserve all existing default behaviour (no flags = unchanged)

**Non-Goals:**
- Cross-tier parallelism for `projects build` (dependency order must be respected)
- Streaming per-line subprocess output during parallel builds (prefixed summary lines are sufficient)
- New progress UI / TUI

## Decisions

### D1: `--force` uses `reset --hard` + `clean -fd`, not `stash`

`stash` preserves changes, which is irrelevant on a CI machine and complicates state. Hard reset + clean is atomic, predictable, and matches the intent: "throw it all away".

Alternatives considered:
- `git stash` before pull/checkout — preserves state unnecessarily, stash can accumulate
- `git checkout --force` alone — doesn't remove untracked files

### D2: Parallel builds use `ThreadPoolExecutor`, not `multiprocessing`

Builds invoke `subprocess` calls that are I/O-bound (waiting on Docker/Maven). The GIL is irrelevant. `ThreadPoolExecutor` is simpler, shares the Rich console safely, and avoids pickle issues with complex objects.

Alternatives considered:
- `multiprocessing.Pool` — process-level isolation, but pickle complexity and no shared console
- `asyncio` — requires all build code to be async; too invasive

### D3: `-j 0` / `-j auto` maps to `os.cpu_count()`

Matches GNU make and Maven `-T 1C` convention. Intuitive for CI engineers familiar with those tools.

### D4: Output prefixed per-project name, not interleaved raw subprocess stdout

Raw subprocess stdout from parallel processes produces unreadable interleaved output. Capturing per-build and prefixing with `[service-name]` keeps output scannable. Rich console is thread-safe for individual `print` calls.

### D5: Force flags are independent for fetch vs. switch

`fetch --force` resets to `origin/<configured-branch>`; `switch --force` resets to `HEAD` before checkout. These are different semantics: fetch restores the tracked branch, switch just cleans before moving. Separate flags, separate logic.

## Risks / Trade-offs

- **Irreversible data loss with `--force`**: Hard reset + clean discards all local changes permanently. → Mitigation: Flag is opt-in; caller must pass it explicitly.
- **Parallel build failures surface later**: A failing tier-N build isn't visible until all tier-N futures complete. → Mitigation: `as_completed` collects failures eagerly; `--keep-going` semantics preserved.
- **Thread safety of build helpers**: `build_project` and `build_service_image` call subprocess and Rich console. Both are thread-safe for the patterns used. → Mitigation: No shared mutable state between build calls.
