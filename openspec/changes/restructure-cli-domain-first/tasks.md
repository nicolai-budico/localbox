## 1. Resolver contract change

- [x] 1.1 Rewrite `resolve_targets` in `src/localbox/utils/resolver.py` to accept bare short-form tokens: drop the `parts[0] != target_type` checks, reinterpret 1-part as group-or-name, 2-part as `group:name`, and reject 3+-part tokens with `TargetError`.
- [x] 1.2 Make `resolve_targets` treat an empty `targets` tuple as "all items of target_type" (replaces ad-hoc `("projects",)` / `("services",)` fallbacks currently used by a few commands in `cli.py`).
- [x] 1.3 Update `parse_target` in the same file to match the new short-form grammar, or delete it if no caller remains after the CLI rewrite.
- [x] 1.4 Rewrite `tests/test_resolver.py` to exercise the new short-form contract: 1-part as group, 1-part as ungrouped name, `group:name`, empty tuple, unknown group, unknown name, malformed 3+-part token.

## 2. CLI: top-level groups

- [x] 2.1 In `src/localbox/cli.py`, add `@cli.group()` declarations for `projects`, `services`, `compose` (already present — keep), `override`, and `solution`.
- [x] 2.2 Delete the top-level `@cli.command("list")` (`list_cmd`) once its sub-verbs are wired under the domain groups (see tasks 3.7 and 4.2).
- [x] 2.3 Delete the top-level `@cli.command()` decorators for `init`, `init-override`, `clone`, `fetch`, `switch`, `build`, `status` once their replacements are in place (see tasks 3 and 4 and 5).

## 3. CLI: `projects` domain

- [x] 3.1 Move `clone` body under `@projects.command("clone")`, keep `--verbose` behavior, call `resolve_targets(solution, targets, "projects")`.
- [x] 3.2 Move `fetch` body under `@projects.command("fetch")`, same pattern as 3.1.
- [x] 3.3 Move `switch` body under `@projects.command("switch")`, keep the `--branch/-b` flag.
- [x] 3.4 Move the projects half of `build` under `@projects.command("build")`; delete the `targets[0].startswith(...)` branch — this command SHALL call only `resolve_targets(solution, targets, "projects")` and `build_projects`. Keep `--no-cache` and `--keep-going/-k` flags.
- [x] 3.5 Move `status` body under `@projects.command("status")`, same pattern as 3.1.
- [x] 3.6 Move the existing `clean projects` sub-command from the `clean` group to `@projects.command("clean")`; delete the `clean` group declaration since `projects clean` is now the only clean verb.
- [x] 3.7 Add `@projects.command("list")` that calls `list_projects(solution)` (existing helper).

## 4. CLI: `services` domain

- [x] 4.1 Move the services half of `build` under `@services.command("build")`; this command SHALL call only `resolve_targets(solution, targets, "services")` and `build_images`. Keep `--no-cache` flag.
- [x] 4.2 Add `@services.command("list")` that calls `list_services(solution)` (existing helper).

## 5. CLI: `override` and `solution` domains

- [x] 5.1 Move the body of `init_override` under `@override.command("init")`; keep `--force/-f` and the merge-and-backup behavior. Delete the top-level `init-override` command.
- [x] 5.2 Move the body of the top-level `init` under `@solution.command("init")`; keep `--force/-f`. Delete the top-level `init` command.

## 6. CLI: verify unchanged top-level commands

- [x] 6.1 Verify `doctor`, `config`, `completion`, `purge`, and the `prune` group (with `caches`, `builders`, `images`, `all`) remain at the top level and unchanged in shape.

## 7. Shell completion

- [x] 7.1 Replace `complete_targets` in `src/localbox/cli.py` with two callbacks: `complete_project_targets` and `complete_service_targets`. Each emits bare `<group>`, `<name>`, `<group>:<name>` tokens scoped to its domain — no `projects:` / `services:` prefix.
- [x] 7.2 Wire `complete_project_targets` as `shell_complete=` on every `projects` sub-command that takes targets; wire `complete_service_targets` on every `services` sub-command that takes targets.
- [x] 7.3 Rewrite `src/localbox/completions/localbox.bash` to suggest the domain groups (`projects`, `services`, `compose`, `override`, `solution`) and the utility commands (`doctor`, `config`, `completion`, `purge`, `prune`) at the top level, and to suggest the correct sub-verbs under each domain. — The bash script delegates to Click's runtime `_LOCALBOX_COMPLETE=bash_complete` mechanism, which reads the current decorator tree; only a header comment update was required.
- [x] 7.4 Regenerate `localbox completion zsh` and `localbox completion fish` output and verify they reflect the new grammar (Click generates these from the decorators, so this is a smoke test, not a hand-edit). — Smoke-tested: `COMP_WORDS="localbox " _LOCALBOX_COMPLETE=bash_complete localbox` returns the new domain groups and utility commands; `COMP_WORDS="localbox projects " …` returns the correct sub-verbs.

## 8. Tests

- [x] 8.1 Rewrite every `runner.invoke(cli, ["init", …])` in `tests/test_cli.py` to `["solution", "init", …]`.
- [x] 8.2 Rewrite every `runner.invoke(cli, ["init-override", …])` in `tests/test_cli.py` to `["override", "init", …]`.
- [x] 8.3 Rewrite every `runner.invoke(cli, [<verb>, "projects…", …])` to `["projects", <verb>, <short-form targets>…]` and similarly for services.
- [x] 8.4 Add a CLI test that `localbox projects build` (no targets) builds all projects, asserting against the project.build call count.
- [x] 8.5 Add a CLI test that `localbox projects build be:api fe:api workers` resolves all three tokens within the projects domain.
- [x] 8.6 Add a CLI test that `localbox projects build projects:api` fails with a `TargetError`-style error message (domain-prefixed tokens rejected under a domain group).
- [x] 8.7 Add a CLI test that `localbox clone projects:api` (legacy shape) fails with Click's "No such command" error.
- [x] 8.8 Add CLI tests for the top-level utility commands (`doctor`, `config`, `completion bash`, `prune caches`, `purge`) to lock their top-level location in place.
- [x] 8.9 Update `tests/test_compose_golden.py` if it invokes `compose generate` via `CliRunner` — the invocation shape is unchanged, but verify the import of the group/command still works after the rewrite. — `test_compose_golden.py` calls `generate_compose_file` directly, not via CliRunner; no changes needed.
- [x] 8.10 Update `tests/test_models.py` if it references any target string in the legacy prefix form. — Grep confirmed the one `projects:` match is inside a `DockerImage` image string, not a target; no changes needed.

## 9. Documentation

- [x] 9.1 Update the "CLI Usage" section of `CLAUDE.md` to show the new domain-first grammar, including the `projects build be:api fe:api workers` example.
- [x] 9.2 Update `README.md` with the new grammar and a translation table from old to new (mirrors the Migration Plan in `design.md`).
- [x] 9.3 Update any solution-level READMEs under `solutions/` that show CLI invocations. — No `solutions/` tree exists; the live example lives at `example/README.md` and was updated in 9.2.
- [x] 9.4 Grep the repo for `localbox ` (with a trailing space) to find every command example in `.md`, `.sh`, and comments; update each to the new grammar.

## 10. Release prep

- [x] 10.1 Bump the version in `pyproject.toml` to the next minor version; this is a breaking release. — 0.1.16 → 0.2.0.
- [x] 10.2 Add a CHANGELOG or release-notes entry (whichever this project uses — see `localdev/release.md`) headed "BREAKING: CLI restructured to `localbox <domain> <command>`" with the full translation table. — Added to `CHANGELOG.md`.
- [x] 10.3 Run the release gate locally in order: `ruff format src/ tests/`, `ruff check src/ tests/`, `mypy src/localbox/`, `pytest tests/ -q`. All four MUST pass. — All four pass cleanly: format clean, check passes, mypy no issues across 29 files, pytest 233 passed + 3 skipped.
