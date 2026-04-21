## Why

Gradle projects with multiple modules often need to invoke extra tasks alongside the default `build` — most commonly `publishToMavenLocal` so library modules become available in the shared `.m2` cache that Maven projects later consume. Today this requires overriding the entire `build_command_list`, which forces the user to re-include `--no-daemon`, `-Dmaven.repo.local=...`, and `-x test`; forgetting any of these silently breaks cache sharing or test-skipping. A small ergonomic field would make the easy thing easy and remove a real footgun.

## What Changes

- Add a `tasks: list[str] | None = None` field to `GradleBuilder` and `GradleWrapperBuilder`
- When `tasks` is set and no custom `build_command_list` / `build_command` / `build_script` was supplied, append the items to the default Gradle command (after the existing default args)
- Expose `tasks` as a parameter on the `gradle()` and `gradlew()` factory functions
- If a user sets `tasks` *and* a custom build command, raise a `ValueError` at construction time — the two are mutually exclusive
- Document in builder docstrings that list items are passed verbatim, so flags like `-PreleaseVersion=1.2.3` are also accepted

No changes to `MavenBuilder`, `MavenWrapperBuilder`, or non-Java builders in this change. A future change can introduce a Maven `goals` equivalent if needed.

## Capabilities

### New Capabilities
- `gradle-builder-tasks`: declarative way to append extra Gradle tasks/args to the default build command without overriding it wholesale

### Modified Capabilities
<!-- none -->

## Impact

- `src/localbox/models/builder.py` — adds `tasks` field to `GradleBuilder` and `GradleWrapperBuilder`; updates `gradle()` and `gradlew()` factories
- `tests/test_models.py` — new tests covering: default behavior unchanged, tasks appended when set, error when combined with custom command, factory parameter passthrough
- No CLI grammar changes
- No changes to `.build/` cache layout or container conventions
- Backward compatible: omitting `tasks` produces the exact same command as today
