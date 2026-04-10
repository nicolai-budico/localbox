## 1. BaseEnv: EnvRef and raw-value storage

- [x] 1.1 Add `EnvRef(str)` class in `src/localbox/models/base_env.py`: `__new__(cls, name, raw)` builds `str` value `"${<name>}"`, attaches `name` and `raw` attributes.
- [x] 1.2 Add `BaseEnv.__post_init__` that walks `dataclasses.fields(self)`, stashes real values into a private `_raw_values: dict[str, str]`, and replaces each instance attribute with an `EnvRef` (leaves unset fields holding the `EnvField` sentinel untouched).
- [x] 1.3 Add `BaseEnv.raw_value(name) -> str` and `BaseEnv.raw_values() -> dict[str, str]` public methods, both backed by `_raw_values`; `raw_value` raises `KeyError` for unset or unknown names.
- [x] 1.4 Export `EnvRef` from `src/localbox/models/__init__.py` so solution authors can type-check / introspect if desired.
- [x] 1.5 Verify `@dataclasses.dataclass` decoration on user subclasses still works: `dataclasses.fields(Env)` must return real fields after `__post_init__` rewires instance attributes.

## 2. Compose generator: reference walker

- [x] 2.1 In `src/localbox/builders/compose.py`, add `_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")`.
- [x] 2.2 Add `_walk_env_refs(value, env_instance, collector)` that recursively visits `dict`, `list`, `tuple`, and `str` values; for each `str`, finds every regex match and, if the captured name is a field of `env_instance`, adds `{name: env_instance.raw_value(name)}` to `collector`.
- [x] 2.3 Handle the "required-but-unset" case in `_walk_env_refs`: if the referenced name is a declared field but `raw_value` raises `KeyError` because the field still holds `EnvField`, raise `ValueError(f"Env.{name} is required but not set. Set it in solution.py or solution-override.py.")`.
- [x] 2.4 Call `_walk_env_refs(service_def, env_instance, env_collector)` at the end of `generate_service_definition`, after all fields are populated (including `extra` passthrough).
- [x] 2.5 Remove the `EnvField`-sentinel branch from `generate_service_definition`'s `service.compose.environment` handling; environment values now flow through the generic walker like every other string field. Raise a clear `TypeError`/`ValueError` if an `EnvField` class-level sentinel appears in `service_def` (defensive, because the walker doesn't understand it).
- [x] 2.6 Update `_collect_all_solution_env_vars` to consume `env_instance.raw_values()` instead of per-field `getattr`, so it sees raw values and not `EnvRef` strings. Keep the plain-`dict` branch unchanged.
- [x] 2.7 Ensure YAML serialization emits `"${NAME}:5432"` style strings verbatim (no unwanted escaping of `$` or `{`). Verify with an integration test that round-trips through `yaml.dump`.

## 3. Example and user-facing surfaces

- [x] 3.1 Update `example/solution.py` to use `config.env.db_name` / `config.env.db_user` / `config.env.db_pass` in both the `db` service `environment` dict and the `api` service's `POSTGRES_URL` f-string. (Already on instance-access style — no content change needed under new semantics.) Class-level `Env.db_name` style never appeared in the example.
- [x] 3.2 Verified end-to-end: running `generate_compose_file(load_solution("example/"))` with `db_pass` overridden produces `POSTGRES_DB/USER/PASSWORD: "${db_name/user/pass}"`, `POSTGRES_URL: "jdbc:postgresql://db:5432/${db_name}"`, and a `.env` file containing `db_name`, `db_user`, `db_pass` with their raw values.

## 4. Tests

- [x] 4.1 Replaced `TestBaseEnv::test_instance_has_correct_values` with `test_instance_access_returns_envref` + `test_fstring_produces_reference` + `test_raw_value_missing_key_raises` + `test_dataclasses_fields_still_work`.
- [x] 4.2 Rewrote `TestComposeEnvResolution::test_envfield_reference_resolved` → `test_envref_reference_resolved` using instance access.
- [x] 4.3 Rewrote `TestComposeEnvResolution::test_unset_required_field_raises` to exercise an unset field referenced via an explicit `${db_pass}` compose value.
- [x] 4.4 Removed `test_non_baseenv_with_envfield_raises` and replaced with `test_unknown_reference_in_dict_env_passthrough`.
- [x] 4.5 Added `TestComposeEnvResolution::test_port_reference_via_fstring`.
- [x] 4.6 Added `TestComposeEnvResolution::test_extra_reference_walked`.
- [x] 4.7 Added `TestComposeEnvResolution::test_unknown_ref_passthrough`.
- [x] 4.8 Added `TestComposeEnvResolution::test_class_level_sentinel_in_environment_rejected`.

## 5. Docs and changelog

- [x] 5.1 Update `docs/concepts.md` to describe instance access, `EnvRef`, and the `.env` writeback model.
- [x] 5.2 Update `docs/getting-started.md` to show the f-string pattern in at least one service example (ports or URL).
- [x] 5.3 Update `docs/cookbook/spring-boot.md` (switched `Env.FIELD` → `config.env.FIELD`); `docs/cookbook/private-registry.md` already used instance access.
- [x] 5.4 Update `docs/api-reference.md` entries for `BaseEnv`, `env_field`, and (new) `EnvRef`, including `raw_value` / `raw_values`.
- [x] 5.5 Update `README.md` quickstart to reflect the new pattern.
- [x] 5.6 Add an `[Unreleased]` BREAKING entry to `CHANGELOG.md` explaining the instance-access semantics change and migration steps.

## 6. Quality gates

- [x] 6.1 `ruff format src/ tests/` — 36 files unchanged.
- [x] 6.2 `ruff check src/ tests/` — all checks passed.
- [x] 6.3 `mypy src/localbox/` — no issues found in 29 source files.
- [x] 6.4 `pytest tests/ -q` — 223 passed, 3 skipped.
- [x] 6.5 End-to-end compose generate against `example/` produces the expected `${name}` references and a `.env` file with raw values (see 3.2).
