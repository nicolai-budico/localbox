## Why

The current CLI grammar `localbox <command> <domain>[:path]` makes commands inconsistent and hard to extend. Some verbs dispatch on the domain prefix in the target string (e.g., `build projects:api` vs `build services:db` is resolved by sniffing the first argument); others are verb-only (`clone`, `fetch`, `switch`, `status`); a few already use a domain-first group (`compose generate`, `prune caches`, `clean projects`). The result is a mix of shapes, ad-hoc argument sniffing inside `build`, and awkward names like `init-override` that cannot grow a sub-verb family. Reorganizing to `localbox <domain> <command> [targets…]` makes the grammar uniform, removes the domain-sniffing branch in `build`, and leaves clean room to add `override show/set/clear` and to extend `compose` without re-litigating the shape of the CLI every time.

## What Changes

- **BREAKING**: Restructure top-level CLI from `localbox <command> <domain>[:path]` to `localbox <domain> <command> [targets…]`. All existing command invocations that mix verbs and domains change shape.
- Introduce domain groups: `projects`, `services`, `compose`, `override`, `solution`.
- Move project verbs under `projects`: `projects clone`, `projects fetch`, `projects switch`, `projects build`, `projects status`, `projects clean`, `projects list`.
- Move service verbs under `services`: `services build`, `services list`.
- `projects build` and `services build` accept multiple targets with short-form paths (no `projects:` / `services:` domain prefix): `localbox projects build be:api fe:api workers`. Targets are resolved within the command's own domain.
- Rename `init` → `solution init` (domain: `solution`).
- Rename `init-override` → `override init` (domain: `override`). Reserve the `override` group for future `show`, `set`, `clear` sub-verbs (not implemented in this change, but the group exists so the shape is set).
- Keep `compose generate` as-is in shape; it already matches the new grammar.
- Keep top-level utility commands that are not domain-specific: `doctor`, `config`, `completion`, `purge`, `prune` (the latter two already use domain-first sub-verbs and stay top-level to avoid a redundant nesting).
- Update shell completion script (`localbox.bash`) and `complete_targets` to reflect the new grammar (targets no longer carry a domain prefix when used under a domain group).
- Update user-facing docs (`README.md`, `docs/usage.md` if present, `CLAUDE.md`) to show the new invocations.

No deprecated-alias shim: this is a breaking rename. The previous CLI shape is removed in the same release.

## Capabilities

### New Capabilities
- `cli-structure`: Defines the top-level CLI grammar, the set of domain groups (`projects`, `services`, `compose`, `override`, `solution`), the sub-verbs under each, how targets are parsed within a domain (short-form `group[:name]`, multiple targets allowed), and which utility commands stay top-level.

### Modified Capabilities
<!-- None — `config-loading` is the only existing spec and it is not affected by this change. -->

## Impact

- **Code**: `src/localbox/cli.py` is rewritten to use Click groups for each domain. Command bodies (the functions in `src/localbox/commands/project.py`, `src/localbox/commands/service.py`, `src/localbox/builders/compose.py`) are unchanged — only the Click decorators and dispatching wrappers move.
- **Target resolution**: `src/localbox/utils/resolver.py` is called from inside each domain group, so it receives bare `group[:name]` tokens rather than `projects:group:name`. `resolve_targets` already takes a `default_type` parameter, so the change is at the call site, not inside the resolver — but tests that pass domain-prefixed targets will need to be updated or a thin wrapper kept.
- **Shell completion**: `src/localbox/completions/localbox.bash` and the `complete_targets` callback need to emit bare `group[:name]` suggestions when completing under a domain group, and emit the domain groups themselves at the top level.
- **Docs**: `README.md`, `CLAUDE.md`, and any usage examples under `docs/` or solution READMEs.
- **Tests**: All CLI integration tests under `tests/` that invoke `localbox <verb> <domain>:...` need rewriting. Unit tests of `resolve_targets`, command bodies, and model loading are unaffected.
- **Plugins**: Plugins register commands via the `localbox.commands` entry-point group and today attach at the top level (see `_load_plugins` in `cli.py`). This stays the same — plugins remain top-level commands unless they explicitly choose a domain — but the convention for new first-party plugins will be to register under a domain group. No breaking change for existing plugins.
- **User habit**: Every user-facing invocation changes. Release notes must call this out prominently; the version bump is a minor breaking release.
