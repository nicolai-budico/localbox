## 1. Model changes

- [x] 1.1 Add `tasks: list[str] | None = None` field to `JavaBuilder` in `src/localbox/models/builder.py` (declared once on the shared base; see Decision 6 in design.md)
- [x] 1.2 In `MavenBuilder.__post_init__` and `MavenWrapperBuilder.__post_init__`, raise `ValueError` if `self.tasks is not None` (with message: "tasks is Gradle-only; use build_command_list on Maven builders")
- [x] 1.3 In `GradleBuilder.__post_init__`, after the existing default-command setup but before `super().__post_init__()`, append `self.tasks` to `self.build_command_list` only when `tasks` is set AND no custom `build_command` / `build_command_list` / `build_script` was supplied; otherwise raise `ValueError` naming both conflicting fields
- [x] 1.4 Apply the same logic in `GradleWrapperBuilder.__post_init__`
- [x] 1.5 Ensure the mutual-exclusion check considers the deprecated aliases (`command`, `command_list`, `script`) by running it AFTER the parent `Builder.__post_init__` migration (i.e., place the append/raise logic in a small helper called at the end of each Gradle subclass `__post_init__`)
- [x] 1.6 Update `gradle()` factory signature to `gradle(version: str = "8.14", *, tasks: list[str] | None = None) -> GradleBuilder` and pass `tasks` through
- [x] 1.7 Update `gradlew()` factory signature to `gradlew(*, tasks: list[str] | None = None) -> GradleWrapperBuilder` and pass `tasks` through
- [x] 1.8 Update class docstrings on `GradleBuilder`, `GradleWrapperBuilder`, `gradle()`, and `gradlew()` to document `tasks`, including the note that items are passed verbatim (so flags like `-PreleaseVersion=…` work) and that `-x test` still wins if `tasks=["test"]` is passed

## 2. Tests (`tests/test_models.py`)

- [x] 2.1 Test: `GradleBuilder()` (no `tasks`) produces the documented default `build_command_list`
- [x] 2.2 Test: `GradleWrapperBuilder()` (no `tasks`) produces the documented default `build_command_list`
- [x] 2.3 Test: `GradleBuilder(tasks=["publishToMavenLocal"])` ends with `["publishToMavenLocal"]` and retains all default flags before it
- [x] 2.4 Test: `GradleWrapperBuilder(tasks=["publishToMavenLocal", ":app:assemble"])` appends both items in order
- [x] 2.5 Test: flag-shaped item (`-PreleaseVersion=1.2.3`) appears verbatim in the resulting command list
- [x] 2.6 Test: `gradle(tasks=["publishToMavenLocal"])` factory passes through correctly
- [x] 2.7 Test: `gradlew(tasks=["publishToMavenLocal"])` factory passes through correctly
- [x] 2.8 Test: `GradleBuilder(tasks=["x"], build_command_list=["gradle", "y"])` raises `ValueError` mentioning both `tasks` and `build_command_list`
- [x] 2.9 Test: `GradleBuilder(tasks=["x"], build_command="gradle y")` raises `ValueError`
- [x] 2.10 Test: `GradleBuilder(tasks=["x"], build_script="b.sh")` raises `ValueError`
- [x] 2.11 Test: `GradleBuilder(tasks=["x"], command_list=["gradle", "y"])` (deprecated alias) raises `ValueError` after migration runs
- [x] 2.12 Test: `MavenBuilder(tasks=["site"])` raises `ValueError` mentioning Gradle-only
- [x] 2.13 Test: `MavenWrapperBuilder(tasks=["site"])` raises `ValueError`

## 3. Verification

- [x] 3.1 Run `ruff format src/ tests/`
- [x] 3.2 Run `ruff check src/ tests/` — must pass clean
- [x] 3.3 Run `mypy src/localbox/` — must pass clean
- [x] 3.4 Run `pytest tests/ -q` — all tests pass (existing 236 + new ones)
- [x] 3.5 Manually check: open `example/solution.py` mentally and confirm the existing `maven("3.9")` builder still constructs without warnings or errors (no behavior change for users not adopting `tasks`)
- [x] 3.6 Run `openspec verify add-gradle-tasks-field` (or the equivalent `/opsx:verify`) before archiving (used `openspec validate`; `verify` is not a command — `validate` reports the change as valid)
