## Context

`_run_docker_with_cleanup` in `builders/build.py` currently streams all Docker container output directly to `sys.stdout`. The `run_builder` signature already accepts `verbose: bool` and `log_path: Path | None`, but `verbose` is unused for output filtering — it only gates the `docker run` command echo.

The parallel-builds spec already requires per-job output prefixing (`[<project-name>]`) during concurrent runs. Quiet mode generalises this: even in serial runs, users want a single status line per job.

## Goals / Non-Goals

**Goals:**
- Default (quiet) mode: print one status line per build job — `[project-name] Building...` → `[project-name] OK (12s)` / `[project-name] FAILED (12s) → <log-path>`
- Full Docker output goes to a log file (existing `log_path` mechanism, but now always populated unless `--verbose`)
- `--verbose` flag: restore current behavior — stream all Docker output to stdout, no log file required
- Flag propagated through `localbox projects build` and `localbox services build`

**Non-Goals:**
- Real-time progress bars or spinner animations (keep it simple; a static status line is enough)
- Changing how `run_builder_clean` works (clean commands are fast; keep them verbose)
- Per-line log tailing in quiet mode

## Decisions

### Decision 1: quiet is default, verbose is opt-in
Mirrors Gentoo `--quiet-build`: noisy output is the exception, not the rule. Users debugging a build failure use `--verbose` or read the log.

**Alternative**: quiet as opt-in (`--quiet`). Rejected — the whole motivation is to reduce noise by default.

### Decision 2: always write a log file in quiet mode; auto-generate path if caller provides none
`run_builder` already accepts `log_path`. In quiet mode, if no path is provided, generate one under the solution's `.build/logs/` directory (e.g., `.build/logs/<project-name>.log`). This avoids requiring callers to manage log paths.

**Alternative**: require callers to pass a path. Rejected — too much boilerplate; log path management should be internal.

### Decision 3: `--verbose` propagated as a flag on build commands, stored in context, passed to `run_builder`
The CLI commands already thread `verbose` through to `run_builder`. Extend the existing `verbose` parameter rather than adding a new one.

### Decision 4: quiet mode output format
```
[project-name] Building...
[project-name] OK  (12s)
```
or on failure:
```
[project-name] FAILED (12s) — log: .build/logs/project-name.log
```
Single fixed-width status word (`OK` / `FAILED`) makes it easy to grep.

### Decision 5: `_run_docker_with_cleanup` gains a `quiet` parameter
When `quiet=True`:
- stdout is suppressed (not written to `sys.stdout`)
- output still written to `log_file`

When `quiet=False` (current behavior, triggered by `--verbose`):
- output streamed to stdout as today
- log file written only if `log_path` provided

## Risks / Trade-offs

- **Log disk usage**: Always writing log files means disk fills if many builds run. Mitigation: log per job (overwritten on retry); users can `rm -rf .build/logs/`.
- **Parallel builds**: status lines from concurrent jobs will interleave. Each line is atomic (single `print`), so interleaving is cosmetic, not confusing. The `[name]` prefix already disambiguates.
- **Timeout message**: the timeout `console.print` in `_run_docker_with_cleanup` currently always goes to stdout. In quiet mode, it should still print (it's a status event, not build chatter).
