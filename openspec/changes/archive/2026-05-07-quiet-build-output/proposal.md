## Why

Build output from Docker containers is verbose and noisy, making it hard to track overall progress. Users need a quiet mode (like Gentoo's `--quiet-build`) that shows one summary line per job while still capturing full output to log files for debugging.

## What Changes

- Default build output switches to quiet mode: one status line per build job (project name, status, duration)
- Full container output is redirected to per-job log files
- New `--verbose` flag restores current behavior (full output to stdout)
- Log file path printed on build failure so users can inspect it

## Capabilities

### New Capabilities
- `quiet-build`: Suppress verbose Docker build output by default; show compact per-job status lines; stream full output to log files; print log path on failure

### Modified Capabilities
- `parallel-builds`: Quiet mode interacts with parallel execution — each job line must update in-place or append cleanly without interleaving

## Impact

- `src/localbox/builders/build.py` — main change site; output capture logic
- `src/localbox/commands/project.py` — pass `--verbose` flag through to builder
- `src/localbox/commands/service.py` — same for service builds
- CLI help strings updated
- Tests for build output behavior
