## Context

Localbox lets users declare typed environment values via a dataclass that
subclasses `BaseEnv`:

```python
@dataclasses.dataclass
class Env(BaseEnv):
    MAIN_DB_LOIP: str = env_field()

config = SolutionConfig[Env](env=Env(MAIN_DB_LOIP="127.0.0.21"))
```

The intent is for that typed object to be the single source of truth that
drives `.env` generation, and for `docker-compose.yml` to use `${NAME}` Docker
Compose variable references. Today that only works for the `environment:`
dict of a service, and only when users pass the class-level sentinel
(`Env.MAIN_DB_LOIP`), not the instance attribute:

```python
# Works: sentinel round-trip through generate_service_definition
environment = {"POSTGRES_DB": Env.db_name}

# Broken: literal value is baked into docker-compose.yml,
# and .env is never consulted for these fields
ports = [f"{config.env.MAIN_DB_LOIP}:5432"]
```

`src/localbox/builders/compose.py` owns the generator; `_collect_all_solution_env_vars`
writes all env fields to `.env`, but those values are disconnected from
anything outside `environment:`. `src/localbox/models/base_env.py` currently
stores plain values on the dataclass instance with no indirection.

Stakeholders: anyone writing `solution.py`, and anyone who wants to check in a
shared compose file and override values per-machine via `.env`.

## Goals / Non-Goals

**Goals:**

- Make instance access (`config.env.FIELD`) produce compose-style variable
  references (`${FIELD}`) in any string context, not raw values.
- Surface those references in every compose field (ports, volumes, environment
  values, extras, healthcheck, links, ...) so they appear as `${FIELD}` in
  `docker-compose.yml`.
- Keep `.env` as the single place where raw values live.
- Unify the two existing styles (class-level `Env.FIELD` sentinel vs. instance
  access) into one idiomatic pattern: instance access.
- Fail loudly when a user references a required `BaseEnv` field that was not
  set, with a message that points at the specific field.

**Non-Goals:**

- No change to how `.env` is parsed or how `SolutionConfig.env` is passed to
  `SolutionConfig` — the declaration surface stays the same.
- No change to `is_secret`, logging, or secret masking behavior.
- No support for computed/derived values that depend on other env fields (the
  user can still compose via f-strings; each referenced name stays a `${NAME}`
  reference).
- No support for `${NAME}` references inside `Dockerfile`/build inputs — this
  change is scoped to `docker-compose.yml` + `.env`.
- No deprecation shim for the class-level `Env.FIELD` sentinel path — it is
  removed outright because the project has no external users to preserve.

## Decisions

### Decision 1: `EnvRef` is a `str` subclass whose value is `${NAME}`

**Choice:** Introduce `EnvRef(str)` in `models/base_env.py`. An instance is
constructed as `EnvRef(name, raw_value)` and its string value is `${NAME}`.
The raw value is attached as `EnvRef.raw` for code that needs it.

**Why:** F-strings call `__str__`/`__format__`, which for a `str` subclass just
returns the string content. If `EnvRef` *is* the string `${NAME}`, then
`f"{config.env.MAIN_DB_LOIP}:5432"` naturally produces `"${MAIN_DB_LOIP}:5432"`
with zero extra machinery in user code. Attribute access, `yaml.dump`, dict
iteration, and `==` comparisons all still see a normal string.

**Alternatives considered:**
- *Plain sentinel object (not a string)*: breaks f-strings (would render as
  `<EnvRef ...>`), forcing users to call `.ref()` or similar. Rejected.
- *Property returning a plain string*: works for the happy path, but then the
  `.raw` value has nowhere to live without an extra lookup table. `EnvRef`
  carries both for free.
- *Jinja-style lazy template*: overkill for a value that only ever resolves to
  `${NAME}`.

### Decision 2: `BaseEnv.__post_init__` rewrites instance attrs and stashes raw values

**Choice:** In `BaseEnv.__post_init__`, walk `dataclasses.fields(self)`. For
each field that holds a real value, store the raw value in a private
`_raw_values: dict[str, str]` and overwrite the instance attribute with
`EnvRef(field.name, raw)`. Fields still holding the `EnvField` sentinel (i.e.
not set by the user) are left alone, which preserves the current
"required-but-missing" detection.

Expose raw values via two accessors:
- `BaseEnv.raw_value(name) -> str` — single lookup, raises `KeyError` if the
  field was never set.
- `BaseEnv.raw_values() -> dict[str, str]` — mapping of every set field, used
  by `_collect_all_solution_env_vars`.

**Why:** Users keep writing `Env(MAIN_DB_LOIP="127.0.0.21")` the same way they
always have. The rewrite happens once at construction time, so per-access cost
is zero. Storing raw values on a private mapping (rather than a parallel
object) keeps the public surface a single `BaseEnv` instance.

**Alternatives considered:**
- *Descriptor per field*: would require per-class metaclass work and would fight
  with `@dataclass`. `__post_init__` is simpler and runs in the right place.
- *Override `__getattribute__`*: runs on every access and makes `dataclasses.fields`
  introspection trickier. Rejected.
- *Store raw values on a sibling object (`env.raw.MAIN_DB_LOIP`)*: fine, but
  duplicates the schema. A private dict is enough; `raw_value()` hides it.

### Decision 3: The compose generator scans generated strings for `${NAME}` references

**Choice:** After `generate_service_definition` builds the service dict, walk
the dict recursively (strings, lists, tuples, nested dicts). For every `str`
value, regex-match `\$\{([A-Za-z_][A-Za-z0-9_]*)\}`. If the captured name is a
field of the solution's `BaseEnv` instance, look up its raw value and add it to
the env collector. Leave the original string untouched.

The same walker runs over `service.compose.extra` (already merged into the
service dict) and over any other string-valued compose field.

**Why:** Once `EnvRef` is a `str` with value `${NAME}`, every f-string using it
collapses to a plain `str`. Type-based detection (`isinstance(value, EnvRef)`)
would miss everything except bare references. A regex over generated strings
is the only reliable way to find references that survived through
concatenation and formatting, and it has the happy side effect of also
picking up `"${NAME}"` string literals that a user might write by hand.

**Alternatives considered:**
- *`EnvRef` detection only (no regex)*: fails for f-strings, which is the whole
  point of this change.
- *Lazy `EnvRef` that survives formatting via `__format__`*: Python's string
  machinery forces f-strings to return `str`, not the subclass. Not viable.
- *Template strings + two-pass generation*: would require users to learn a
  second DSL. Rejected in favor of "just use f-strings".

### Decision 4: `.env` contents are the union of raw values from `BaseEnv` + referenced names

**Choice:** `.env` is written from `env.raw_values()` (every field set on the
`BaseEnv` instance) *plus* any referenced name discovered by the walker that
was not already in that mapping. For `SolutionConfig.env` given as a plain
`dict`, we fall back to the current behavior: every non-`None` value is
written.

**Why:** Keeping the current "write every declared field" rule means users get
a complete `.env` from day one, even for fields they have not yet wired up.
The walker strictly adds to this set, so nothing is lost.

### Decision 5: Remove the class-level `Env.FIELD` sentinel branch from the compose generator

**Choice:** `generate_service_definition`'s special handling of `EnvField` in
`service.compose.environment` is deleted. Users migrate to
`environment={"POSTGRES_DB": config.env.db_name}`.

**Why:** With `EnvRef` in place, the class-level path is redundant and its
existence would force the spec + tests to cover two styles forever. The
project has no external consumers to preserve, so we remove it now.

## Risks / Trade-offs

- **Risk:** Existing tests assert `env_inst.db_name == "mydb"`. Under the new
  design that comparison is `"${db_name}" == "mydb"` → `False`. **Mitigation:**
  update `tests/test_base_env.py` to assert `env_inst.db_name == "${db_name}"`
  and `env_inst.raw_value("db_name") == "mydb"`. Add dedicated coverage for
  port / volume / extra references.

- **Risk:** The regex walker will match any `${...}` string the user writes,
  even ones that are *not* meant to be resolved from `BaseEnv` (e.g. a literal
  `"${PATH}"` they want Docker Compose itself to expand). **Mitigation:** scope
  the walker to names that exist on the solution's `BaseEnv` instance. Anything
  else is left untouched and flows to Docker Compose as-is, matching today's
  behavior.

- **Risk:** A user references `config.env.FIELD` without ever setting it.
  Today they would get an `EnvField` sentinel in the f-string
  (`"<EnvField ...>:5432"`) — surprising but visible. **Mitigation:**
  `__post_init__` replaces every declared field — set or unset — with an
  `EnvRef`, so instance access always produces `"${FIELD}"` and f-strings
  stay well-formed at import time (important for `solution-override.py`
  flows where values arrive after `solution.py` has already built its
  `ComposeConfig`s). Unset fields are recorded by their *absence* from the
  private `_raw_values` mapping. The compose walker then raises
  `ValueError` with the field name whenever it sees a `${FIELD}` reference
  whose raw value is missing, matching current behavior for `environment:`
  references.

- **Trade-off:** Because `EnvRef` is a `str`, `env_inst.FIELD` no longer
  equals the raw value in user code. Any existing `solution.py` that compared
  or used `config.env.FIELD` as a literal needs to switch to
  `config.env.raw_value("FIELD")`. This is the intentional breaking change.

- **Trade-off:** The walker adds an O(n) pass over each service dict. This is
  negligible next to disk I/O and YAML serialization for any realistic service
  count.

## Migration Plan

This project does not currently publish or support external consumers of the
`BaseEnv` Python API, so the migration is internal:

1. Implement `EnvRef` + `__post_init__` rewiring in `models/base_env.py`.
2. Implement the reference walker in `builders/compose.py`; delete the
   `EnvField` branch in `generate_service_definition`.
3. Update `example/solution.py` to use `config.env.FIELD` instead of
   `Env.FIELD`.
4. Update `tests/test_base_env.py` (see Risks above) and add walker coverage.
5. Update docs and `CHANGELOG.md` with a **BREAKING** entry describing the
   new instance-access semantics and how to migrate any ad-hoc user solutions.

Rollback is a single revert commit: there is no on-disk or on-wire format
change, only in-memory semantics.

## Open Questions

- Do we want to expose `EnvRef.raw` publicly, or force all raw lookups through
  `env.raw_value(name)`? Leaning public (`EnvRef.raw`) for ergonomics in tests
  and advanced code paths, but the spec can pick either.
- Should the walker also rewrite bare literal strings that happen to equal a
  known field name (e.g. a user writing `ports=["MAIN_DB_LOIP:5432"]` without
  the `${...}`)? Current plan: no — only recognise the explicit `${NAME}`
  form, because that is what Docker Compose itself understands.
