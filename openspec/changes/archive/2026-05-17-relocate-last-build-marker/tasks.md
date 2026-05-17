## 1. Relocate marker storage

- [ ] 1.1 Add helper `_last_build_path(build_dir: Path, project_name: str) -> Path` that returns `build_dir / "last-build" / project_name`
- [ ] 1.2 Update `_write_last_build` to accept `build_dir` and `project_name` and write to the new path; create the `last-build/` directory if needed
- [ ] 1.3 In `_write_last_build`, delete `<source_dir>/.last-build` if it exists (legacy cleanup)
- [ ] 1.4 Update `_read_last_build` to read from the new path
- [ ] 1.5 Update call sites in `build_project` to pass `solution.directories.build` and `project.name`
- [ ] 1.6 Update call site in `show_project_status` to read from the new path

## 2. Tests

- [x] 2.1 Update existing last-build tests (if any) to reflect new path
- [x] 2.2 Add test: successful build writes marker to `.build/last-build/<project-name>`, not inside source dir
- [x] 2.3 Add test: `projects status` reads last-build from the new location
- [x] 2.4 Add test: legacy `.last-build` file inside source dir is deleted on next successful build

## 3. Quality

- [x] 3.1 Run `ruff format src/ tests/`, `ruff check src/ tests/`, `mypy src/localbox/`, `pytest tests/ -q` — all must pass
