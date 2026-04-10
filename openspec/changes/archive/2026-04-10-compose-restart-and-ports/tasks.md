## 1. Compose generator: remove restart default

- [x] 1.1 In `src/localbox/builders/compose.py`, delete the two lines at the end of `generate_service_definition` that set `service_def["restart"] = "unless-stopped"` (the comment `# Restart policy` and the assignment itself).
- [x] 1.2 Verify by inspection that `service.compose.extra` is still merged into `service_def` at the top of the function, so `ComposeConfig(extra={"restart": "always"})` still produces `"restart": "always"` in the output dict.

## 2. Compose generator: quote port strings

- [x] 2.1 In `src/localbox/builders/compose.py`, change the `ports` assignment in `generate_service_definition` from `service_def["ports"] = service.compose.ports` to `service_def["ports"] = [_QuotedStr(p) for p in service.compose.ports]` so PyYAML emits each entry as a double-quoted scalar.
- [x] 2.2 Confirm that `_QuotedStr` is already in scope in `compose.py` (it is defined at module top). No import change needed.

## 3. Tests

- [x] 3.1 In `tests/test_compose_golden.py`, rename `TestComposeExtra::test_named_field_overrides_extra` to `test_extra_restart_passes_through` and change its assertion from `assert defn["restart"] == "unless-stopped"` to `assert defn["restart"] == "always"`. Update the docstring to say that `extra` values pass through when no typed field shadows them.
- [x] 3.2 In `tests/test_compose_golden.py::test_extra_empty_by_default`, remove `"restart"` from the `known_keys` set so it reads `known_keys = {"networks", "image"}`.
- [x] 3.3 Regenerate `tests/fixtures/docker-compose.golden.yml`:
  - [x] 3.3.1 Delete the three `restart: unless-stopped` lines (one per service).
  - [x] 3.3.2 Double-quote each entry under every `ports:` list, e.g. `- "8080:8080"` and `- "80:80"`.
- [x] 3.4 Add a dedicated unit test `TestComposeGeneration::test_ports_are_quoted` in `tests/test_compose_golden.py` that builds a service with `ComposeConfig(ports=["0.0.0.0:80:80"])`, runs the compose generator end-to-end, reads the generated `docker-compose.yml`, and asserts the file contains `- "0.0.0.0:80:80"` verbatim (i.e. the port line is double-quoted).
- [x] 3.5 Add a dedicated unit test `TestComposeGeneration::test_no_default_restart_policy` that builds a service with `ComposeConfig()` (no `extra`), runs `generate_service_definition`, and asserts `"restart" not in defn`.

## 4. Quality gates

- [x] 4.1 Run `ruff format src/ tests/` — 36 files left unchanged.
- [x] 4.2 Run `ruff check src/ tests/` — all checks passed.
- [x] 4.3 Run `mypy src/localbox/` — no issues found in 29 source files.
- [x] 4.4 Run `pytest tests/ -q` — 226 passed, 3 skipped.
- [ ] 4.5 End-to-end sanity: from `solutions/myapp`, run `localbox compose generate` and confirm the produced `docker-compose.yml` has no `restart:` keys and that every `ports:` entry is double-quoted. (Skipped — requires a live solution with real projects; the new golden test and `test_ports_are_quoted` cover the generator output.)

## 5. Changelog (if one exists for this repo)

- [x] 5.1 Added `[Unreleased]` entries to `CHANGELOG.md` noting the removed `restart: unless-stopped` default and the quoted port strings.
