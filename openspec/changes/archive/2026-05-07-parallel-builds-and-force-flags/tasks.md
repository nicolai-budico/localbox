## 1. Force Fetch (`projects fetch --force`)

- [x] 1.1 Add `--force` flag to `projects fetch` CLI in `cli.py`
- [x] 1.2 Implement force path in `fetch_project()` in `commands/project.py`: `git fetch --all`, `git reset --hard origin/<branch>`, `git clean -fd`
- [x] 1.3 Resolve `<branch>` from `project.git.branch or solution.default_branch`
- [x] 1.4 Add tests for force fetch: dirty tree, detached HEAD, untracked artifacts

## 2. Force Switch (`projects switch --force`)

- [x] 2.1 Add `--force` flag to `projects switch` CLI in `cli.py`
- [x] 2.2 Implement `_clean_working_tree(path)` helper in `commands/project.py`: `git reset --hard HEAD`, `git clean -fd`
- [x] 2.3 Call `_clean_working_tree` before checkout in branch-switch mode when `--force` is set
- [x] 2.4 Call `_clean_working_tree` before each SHA checkout in `--manifest` mode when `--force` is set
- [x] 2.5 Add tests for force switch: branch mode dirty tree, manifest mode dirty tree, untracked files

## 3. Parallel Projects Build (`projects build -j`)

- [x] 3.1 Add `-j / --jobs` option to `projects build` CLI in `cli.py`; accept integer or string `"auto"`/`"0"` → `os.cpu_count()`
- [x] 3.2 Update `build_projects()` in `builders/build.py` to accept `jobs` param
- [x] 3.3 Within each dependency tier, use `ThreadPoolExecutor` when `jobs > 1`; submit all tier projects, collect with `as_completed`
- [x] 3.4 Prefix each output line with `[<project-name>]` when running in parallel
- [x] 3.5 Propagate `--keep-going` across parallel tier failures (collect failures, abort next tier unless keep-going)
- [x] 3.6 Add tests for parallel projects build: tier ordering preserved, failure propagation, j=1 sequential

## 4. Parallel Services Build (`services build -j`)

- [x] 4.1 Add `-j / --jobs` option to `services build` CLI in `cli.py`
- [x] 4.2 Update service build dispatch in `commands/service.py` or `builders/docker.py` to accept `jobs` param
- [x] 4.3 When `jobs > 1`, submit all services to `ThreadPoolExecutor` at once; collect with `as_completed`
- [x] 4.4 Prefix each output line with `[<service-name>]` when running in parallel
- [x] 4.5 Ensure `--manifest` extra-tag logic applies correctly per service when parallel
- [x] 4.6 Add tests for parallel services build: concurrent execution, manifest tag applied to all

## 5. QA

- [x] 5.1 `ruff format src/ tests/` — auto-format
- [x] 5.2 `ruff check src/ tests/` — lint clean
- [x] 5.3 `mypy src/localbox/` — type-check clean
- [x] 5.4 `pytest tests/ -q` — all tests pass
