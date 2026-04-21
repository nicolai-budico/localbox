## Context

`GradleBuilder` and `GradleWrapperBuilder` (in `src/localbox/models/builder.py`) configure their default build command in `__post_init__`:

```python
self.build_command_list = [
    "gradle", "build", "-x", "test", "--no-daemon",
    "-Dmaven.repo.local=/var/maven/.m2/repository",
]
```

Two important details ride on those defaults:
1. `-x test` — skips tests during cross-project builds
2. `-Dmaven.repo.local=/var/maven/.m2/repository` — points Gradle at the shared `.build/maven/.m2` cache that Maven builders also mount, so artifacts published from Gradle (e.g. via `publishToMavenLocal`) are visible to downstream Maven projects in the same solution

Today, a user who wants to add `publishToMavenLocal` must replace the entire list and remember to re-include both flags. Forgetting `-Dmaven.repo.local` silently breaks cache sharing — the Gradle build "succeeds" but downstream Maven projects can't find the artifacts.

## Goals / Non-Goals

**Goals:**
- Make appending one or more Gradle tasks to the default build command a one-liner
- Preserve all existing default flags automatically
- Apply uniformly to both `GradleBuilder` (preinstalled Gradle image) and `GradleWrapperBuilder` (`./gradlew`)
- Fail loudly if the user mixes `tasks` with a custom command — silent merge would be confusing
- Keep the default behavior (no `tasks` set) byte-for-byte identical to today

**Non-Goals:**
- Adding a Maven `goals` equivalent (deferred — propose separately if needed)
- Multi-target/named build phases on a project (the option-C idea from exploration; deferred)
- Changing how the `.build/maven` cache volume is wired
- Touching `MavenBuilder`, `MavenWrapperBuilder`, `node()`, or `Builder` base

## Decisions

### Decision 1: Field name `tasks` (not `extra_tasks`, `goals`, or `extras`)

`tasks` is Gradle's own term for the unit of work. It reads naturally on a `GradleBuilder` / `GradleWrapperBuilder`. `goals` is Maven's term and would be a poor fit here. `extra_tasks` is more explicit but verbose; `extras` is generic and loses the Gradle-specific signal.

**Alternatives considered:**
- `extra_tasks`: clearer that it's additive but extra noise on every call site
- `extras`: too generic; obscures that items become CLI args to `gradle`
- Adding a generic `extra_args` to the base `Builder`: tempting but premature — only Gradle has a clear "tasks are first-class" model right now

### Decision 2: `tasks` items are passed verbatim as argv

Items in the `tasks` list are appended to the default `build_command_list` unchanged. This means flags like `-PreleaseVersion=1.2.3` or `-i` (info logging) also work — the field is "extra args" in practice, named after its primary use.

**Alternatives considered:**
- Restrict to bare task names (regex `[a-zA-Z][a-zA-Z0-9:._-]*`): rejected — Gradle DSL legitimately mixes tasks and `-P`/`-D` flags on one line; users will want this
- Separate `tasks` and `extra_args` fields: extra surface area for marginal value

### Decision 3: `tasks` is mutually exclusive with custom `build_command*`

If `tasks` is set AND any of `build_command`, `build_command_list`, `build_script` are set, raise `ValueError` in `__post_init__`. Sugar-on-default vs. fully-custom should not silently combine.

The check runs *before* the deprecated-alias migration in the parent `Builder.__post_init__` (i.e., we check the post-migration state) so passing `command=[…]` (legacy) plus `tasks=[…]` is also rejected.

**Alternatives considered:**
- Silently append to the custom command: violates least surprise; user clearly meant their custom command to be authoritative
- Silently ignore `tasks` when custom command is present: hides a likely bug
- Warn instead of raise: easy to miss in CI; raise is unambiguous

### Decision 4: Position — appended at the end

The `tasks` items are appended after the existing default args:

```
gradle build -x test --no-daemon -Dmaven.repo.local=… <tasks…>
```

Gradle resolves the task DAG regardless of CLI order, so position doesn't affect execution. End-position is the simplest implementation and matches how a human would type it.

### Decision 5: Factory parameter passthrough

`gradle(version: str = "8.14", *, tasks: list[str] | None = None)` and `gradlew(*, tasks: list[str] | None = None)` accept the field as a keyword-only parameter for ergonomic call sites:

```python
builder=gradle(tasks=["publishToMavenLocal"])
builder=gradlew(tasks=["publishToMavenLocal", "-PreleaseTag=ci"])
```

Keyword-only avoids any future positional-arg ambiguity if the factory grows more parameters.

### Decision 6: Type — `list[str] | None`, default `None`

`None` (not `[]`) is the "unset" sentinel. An empty list means "the user explicitly cleared tasks" — same outcome as `None` here, but distinguishing keeps intent clear if we ever attach behavior to "explicitly empty."

## Risks / Trade-offs

- **Risk**: User sets `tasks=["test"]` expecting tests to run, but `-x test` still wins because it appears earlier on the line. → **Mitigation**: docstring note explicitly. Users wanting tests can use a custom `build_command_list` (which already disables the `tasks` field via the mutual-exclusion check).

- **Risk**: Same field name on `GradleBuilder` and `GradleWrapperBuilder` invites copy-paste drift between them. → **Mitigation**: define `tasks` once on `JavaBuilder` (the shared base). Subclasses inherit it; only `GradleBuilder.__post_init__` and `GradleWrapperBuilder.__post_init__` consume it. Maven subclasses ignore it (with a `ValueError` if set there, to prevent silent confusion when a Maven user copies a Gradle snippet).

- **Risk**: Items containing shell metacharacters (`&&`, `|`, `>`) won't behave as expected because we use `build_command_list` (no shell). → **Acceptable**: this is consistent with how `build_command_list` already works elsewhere; documented as "argv-style, no shell."

- **Trade-off**: This is Gradle-specific and may foreshadow a Maven `goals` field. Accepting some near-term asymmetry to ship the actual user need now, rather than designing a unified abstraction speculatively.

## Migration Plan

No migration required. The change is backward compatible:
- Existing `gradle()` / `gradlew()` calls without `tasks=` produce the exact same command
- Existing custom-command users are unaffected
- No spec/CLI/cache-layout changes

Roll-forward only; no rollback steps needed beyond reverting the commit.

## Open Questions

None blocking. Two to revisit later:
1. Should a Maven `goals` equivalent land next? Wait for a concrete user request.
2. If `Builder.command` (the deprecated alias) plus `tasks` is set, the mutual-exclusion error fires after migration. Should the error message hint at the deprecated alias to ease migration? Minor UX nicety; deferred.
