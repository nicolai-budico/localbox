## 1. Core quiet-mode output in build runner

- [x] 1.1 Add `quiet: bool = True` parameter to `_run_docker_with_cleanup` — when True, suppress per-line `sys.stdout.write`; still write to `log_file`
- [x] 1.2 Auto-generate log path in `run_builder` when `quiet=True` and no `log_path` provided: `.build/logs/<project-path-name>.log`; create parent dir
- [x] 1.3 Print `[<name>] Building...` before `_run_docker_with_cleanup` when quiet
- [x] 1.4 Print `[<name>] OK  (<N>s)` or `[<name>] FAILED (<N>s) — log: <path>` after the call when quiet; use elapsed time
- [x] 1.5 Pass `quiet=not verbose` through `run_builder` → `_run_docker_with_cleanup`

## 2. --verbose flag on CLI commands

- [x] 2.1 Add `--verbose` option to `localbox projects build` (Click flag, default False); thread through to `run_builder`
- [x] 2.2 Add `--verbose` option to `localbox services build`; thread through to service image builder
- [x] 2.3 Verify `--verbose -j N` combo works: verbose mode + parallel still prefixes output with `[name]` as specified

## 3. Parallel builds quiet-mode status lines

- [x] 3.1 Confirm parallel worker path in `commands/project.py` passes `verbose` flag to `run_builder` per-worker
- [x] 3.2 Confirm quiet status lines from parallel workers don't interleave mid-line (each `print` call is atomic; verify with a manual test or note in code)

## 4. Tests

- [x] 4.1 Unit test: `_run_docker_with_cleanup` with `quiet=True` does not write to stdout but writes to log file
- [x] 4.2 Unit test: `_run_docker_with_cleanup` with `quiet=False` writes to stdout
- [x] 4.3 Integration test (or existing test update): `run_builder` in quiet mode prints status lines and creates log file
- [x] 4.4 CLI test: `localbox projects build --verbose` passes `verbose=True` to builder

## 5. Documentation

- [x] 5.1 Update `CLAUDE.md` CLI Usage section: add `--verbose` to `localbox projects build` and `localbox services build` examples; add note about quiet-by-default and log file location
- [x] 5.2 Update `--help` text (Click docstrings/`help=` params) for `projects build` and `services build` to describe quiet default, log path, and `--verbose` flag

## 6. Checks

- [x] 6.1 `ruff format src/ tests/` passes
- [x] 6.2 `ruff check src/ tests/` passes
- [x] 6.3 `mypy src/localbox/` passes
- [x] 6.4 `pytest tests/ -q` passes (all existing + new tests)
