## Context

`generate_service_definition` in `src/localbox/builders/compose.py` is the
single place that translates a `Service`/`ComposeConfig` object into a
dictionary that `yaml.dump` serializes into `docker-compose.yml`. It handles
networks, image, ports, environment, volumes, depends_on, links, healthcheck,
restart, and the generic `extra` passthrough.

Two behaviors in that function are wrong:

1. **Hardcoded restart policy.** Near the end of the function:
   ```python
   # Restart policy
   service_def["restart"] = "unless-stopped"
   ```
   This assignment runs *after* `service_def.update(service.compose.extra)`
   at the top of the function, so if a user sets
   `ComposeConfig(extra={"restart": "always"})`, the final dict still has
   `"unless-stopped"`. `test_named_field_overrides_extra` enshrines this.
   There is no field on `ComposeConfig` for a restart policy, no docs for
   this default, and no way to opt out short of deleting the key in
   post-processing. The right behavior is "leave `restart` alone unless the
   user asks for one via `extra`".

2. **Unquoted port strings.** Ports are user-supplied strings (e.g.
   `"8080:8080"`, `"0.0.0.0:80:80"`). They go straight into the service dict:
   ```python
   if service.compose.ports:
       service_def["ports"] = service.compose.ports
   ```
   PyYAML emits each element as a bare scalar, so a list like
   `["0.0.0.0:80:80", "0.0.0.0:9001:9001"]` serializes as:
   ```yaml
   ports:
     - 0.0.0.0:80:80
     - 0.0.0.0:9001:9001
   ```
   Docker Compose v2 logs a warning on load:
   `WARN[0000] unquoted port mapping: "0.0.0.0:80:80"`. The reason is
   historical: YAML 1.1 parses colon-separated integers as base-60, so
   `80:80` could in principle round-trip to a different value. Compose wants
   the strings double-quoted so the YAML parser cannot second-guess them.

The module already has a `_QuotedStr` subclass for exactly this purpose, and
a representer registered with `_NoAliasDumper` that forces double-quoting:
```python
_NoAliasDumper.add_representer(
    _QuotedStr,
    lambda dumper, data: dumper.represent_scalar("tag:yaml.org,2002:str", data, style='"'),
)
```
It is currently used for environment values only. Reusing it for ports is a
one-line change.

Stakeholders: anyone running `localbox compose generate` and feeding the
output to `docker compose up`. The golden-file snapshot test also pins the
current (wrong) output and has to move with the fix.

## Goals / Non-Goals

**Goals:**

- Remove the default `restart: unless-stopped` so that an empty
  `ComposeConfig()` produces no `restart:` key at all in the generated YAML.
- Let `ComposeConfig(extra={"restart": "always"})` flow through unchanged,
  because the `extra` passthrough already merges into `service_def` first.
- Emit every entry in `ports:` as a double-quoted YAML string, eliminating
  the `unquoted port mapping` warning from Docker Compose.
- Update the golden fixture and the two affected unit tests in a single
  change so CI stays green.

**Non-Goals:**

- No first-class `restart` field on `ComposeConfig`. Adding a typed field
  would invite API churn for a feature that `extra` already supports.
- No blanket "quote every string field" pass. Only `ports` triggers the
  Compose warning today; applying `_QuotedStr` universally would force
  large, meaningless diffs across every service in the golden fixture and
  obscure future real changes.
- No changes to `compose-env-resolution` semantics. Port strings that
  contain `${NAME}` references (e.g. `f"{config.env.MAIN_DB_LOIP}:5432"`)
  must keep working; `_QuotedStr` is a plain `str` subclass, so `EnvRef`
  contents survive wrapping unchanged and the walker still sees the
  references as strings.
- No migration shim for users relying on the implicit `restart: unless-stopped`.
  The feature was undocumented and has no external-consumer story; a
  CHANGELOG note at most.

## Decisions

### Decision 1: Delete the hardcoded restart assignment rather than adding a typed field

**Choice:** Remove these two lines from `generate_service_definition`:
```python
# Restart policy
service_def["restart"] = "unless-stopped"
```
Do not add a `restart` attribute to `ComposeConfig`. Users who want a restart
policy pass it through `extra={"restart": "..."}`, which is already supported
and already flows into `service_def` via `service_def.update(service.compose.extra)`.

**Why:** The `extra` passthrough exists precisely to avoid proliferating
typed fields for every compose key. A `restart` field would duplicate a
mechanism we already have, force a second code path to test, and add a
second "does the named field override extra?" edge case. Deleting the
hardcoded line is the smallest possible fix.

**Alternatives considered:**
- *Add `ComposeConfig.restart: str | None = None` and let that override
  `extra`.* Rejected: adds API surface for zero benefit. `extra` already works.
- *Keep `unless-stopped` but only set it when neither `extra` nor any typed
  field provides one.* Rejected: the whole point is that we should not
  assume a restart policy — localbox is a local-dev tool, not a production
  orchestrator. Leaving `restart` unset matches the Compose default.

### Decision 2: Wrap port strings in `_QuotedStr` at assignment time

**Choice:** Change
```python
if service.compose.ports:
    service_def["ports"] = service.compose.ports
```
to
```python
if service.compose.ports:
    service_def["ports"] = [_QuotedStr(p) for p in service.compose.ports]
```

**Why:** `_QuotedStr` is a `str` subclass whose registered representer
forces double-quoting. Wrapping at assignment time is the single point where
the list is built, so the fix is localized. `yaml.dump` handles the rest.
Because `_QuotedStr(EnvRef(...))` produces a `_QuotedStr` whose content is
the `"${NAME}:..."` string, the env-reference walker in `_walk_env_refs`
still sees a plain `str` and its regex still matches — env resolution
continues to work for ports.

**Alternatives considered:**
- *Post-process the YAML text with a regex to quote port lines.* Rejected:
  fragile, and we already have the right mechanism via `_QuotedStr`.
- *Wrap inside `_walk_env_refs` or after the walker runs.* Rejected: the
  walker's job is env resolution, not formatting. Mixing the two would make
  both harder to reason about.
- *Use a custom port representer (register a representer for a `PortStr`
  type).* Rejected: `_QuotedStr` is the established pattern in this file;
  introducing a sibling class for one use site is unnecessary.

### Decision 3: Regenerate the golden fixture in the same change

**Choice:** `tests/fixtures/docker-compose.golden.yml` is updated by hand in
this change to (a) remove the three `restart: unless-stopped` lines and (b)
double-quote the `ports:` entries. The golden-file test rereads the file on
each run, so no code change there is needed.

**Why:** The fixture is a snapshot of expected generator output. The whole
point of this change is to change that output. Regenerating in the same
commit keeps the snapshot, the code, and the unit tests aligned, which is
what makes the golden test useful as a regression guard.

**Alternatives considered:**
- *Split into "fix code" + "update fixture" commits.* Rejected: the "fix
  code" commit would leave the golden test failing, breaking `git bisect`.

## Risks / Trade-offs

- **Risk:** Users who implicitly relied on `restart: unless-stopped` will see
  containers no longer restart after a reboot or crash. **Mitigation:** call
  this out in `CHANGELOG.md`; the fix is a one-liner in each affected
  `solution.py` (`compose=ComposeConfig(extra={"restart": "unless-stopped"})`).
  This is a local-dev tool so the blast radius is contained.

- **Risk:** Wrapping ports in `_QuotedStr` could interact badly with the env
  reference walker, which recurses into lists and matches strings with a
  regex. **Mitigation:** `_QuotedStr` is a `str` subclass; `isinstance(p, str)`
  in `_walk_env_refs` stays `True` and the regex still applies. A test that
  exercises a port f-string already exists (`test_port_reference_via_fstring`)
  and will cover this.

- **Trade-off:** The golden fixture churn touches six lines in the same file
  and has to be reviewed by hand. This is a one-time cost and worth paying
  to keep the snapshot authoritative.

## Migration Plan

Internal-only — no external consumers.

1. Delete the two `restart` lines in `generate_service_definition`.
2. Wrap `service.compose.ports` entries in `_QuotedStr` at the one assignment
   site.
3. Update `tests/test_compose_golden.py`:
   - Rename `test_named_field_overrides_extra` →
     `test_extra_restart_passes_through`, assert `defn["restart"] == "always"`.
   - Drop `"restart"` from `known_keys` in `test_extra_empty_by_default`.
4. Regenerate `tests/fixtures/docker-compose.golden.yml` by hand (delete the
   three `restart:` lines; double-quote the `ports:` entries).
5. Run the four quality gates (`ruff format`, `ruff check`, `mypy`, `pytest`).

Rollback is a single-commit revert: the change is purely additive/deletive
in one file plus test fixtures, no data or on-disk format migrations.

## Open Questions

- Should `ComposeConfig.ports` be promoted to `list[str]` explicitly typed
  (it already is) and get docstring guidance about `host:container` vs
  `host_ip:host:container` form? Out of scope for this change — a docs-only
  follow-up if anyone asks.
- Should we add a lint that rejects port strings containing colons outside
  of the expected positions? Also out of scope; Docker Compose already
  validates port strings at load time.
