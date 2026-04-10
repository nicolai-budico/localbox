## Why

Today, reading `config.env.MAIN_DB_LOIP` inside `solution.py` returns the raw
value (e.g. `"127.0.0.21"`), so any f-string using it bakes that literal into
`docker-compose.yml`. The `.env` file is meant to be the single source of truth
for values, but it is currently bypassed everywhere except the `environment:`
dict of a service. This defeats the purpose of having a typed `BaseEnv`:
rebinding a value in `.env` does not re-wire ports, volumes, URLs, or any other
compose field. Users cannot share a checked-in compose file and override values
per-machine through `.env`, which is Docker Compose's standard flow.

## What Changes

- **BREAKING**: Instance-level access to a `BaseEnv` field (e.g.
  `config.env.MAIN_DB_LOIP`) returns an `EnvRef` — a `str` subclass whose string
  form is `${MAIN_DB_LOIP}`. F-strings and concatenation therefore produce
  compose-style variable references, not resolved values.
- `BaseEnv` stores raw values in a private `_raw_values` mapping on the
  instance. A helper (`env.raw_value(name)` / `env.raw_values()`) exposes them
  for the compose generator and for any code that genuinely needs the literal.
- The compose generator scans every string emitted into `docker-compose.yml`
  (ports, environment values, volumes, extras, healthcheck args, etc.) for
  `${NAME}` references whose `NAME` matches a `BaseEnv` field, and collects the
  corresponding raw values into the `.env` file that is written next to
  `docker-compose.yml`.
- The existing `Env.FIELD` (class-level sentinel) code path in
  `generate_service_definition` is removed; users migrate to instance access
  (`config.env.FIELD`). This unifies the two styles and shrinks the generator.
- `example/solution.py` is updated to the new instance-access style so the
  shipped example demonstrates the intended pattern.
- Docs (`docs/concepts.md`, `docs/getting-started.md`, cookbook entries,
  `README.md`) are updated to teach the new pattern and to note the breaking
  change for users upgrading.

## Capabilities

### New Capabilities
- `compose-env-resolution`: How `BaseEnv` field references flow from
  `solution.py` to `docker-compose.yml` and `.env`. Covers instance-access
  semantics, reference detection in arbitrary compose fields, `.env` writeback,
  and error behavior for unset/required fields.

### Modified Capabilities
<!-- None — `config-loading` is unaffected; env resolution is not currently
     spec'd, so we introduce a fresh capability instead of deltaing one. -->

## Impact

- Code:
  - `src/localbox/models/base_env.py` — add `EnvRef`, `__post_init__` that
    rewrites instance attrs and stores raw values, public accessors.
  - `src/localbox/builders/compose.py` — add a walker that finds `${NAME}`
    references across the generated service dict, populate the `.env`
    collector from the env instance's `_raw_values`, drop the `Env.FIELD`
    class-level sentinel branch in `generate_service_definition`, update
    `_collect_all_solution_env_vars` to read raw values.
  - `example/solution.py` — switch to instance-access style.
- Tests:
  - `tests/test_base_env.py` — several tests assert
    `env_inst.db_name == "mydb"`; these change to assert the `EnvRef` shape
    (`str(ref) == "${db_name}"`, `ref.raw == "mydb"`). Add coverage for port
    references, volume references, and references embedded in `extra`.
- Docs: `docs/concepts.md`, `docs/getting-started.md`,
  `docs/cookbook/spring-boot.md`, `docs/cookbook/private-registry.md`,
  `docs/api-reference.md`, `README.md`, `CHANGELOG.md`.
- APIs / dependencies: no new third-party deps. Public Python API of
  `BaseEnv` subclasses changes at the instance-access level — this is the
  breaking surface users will notice.
