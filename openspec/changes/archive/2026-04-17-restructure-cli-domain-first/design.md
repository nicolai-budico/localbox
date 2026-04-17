## Context

The CLI in `src/localbox/cli.py` has grown by accretion. It exposes three different shapes at once:

1. Verb-first with a domain-prefixed target: `localbox build projects:api`, `localbox clone projects:api`, `localbox fetch projects`, `localbox status projects`, `localbox switch projects:api`, `localbox list projects`.
2. Verb-first with an embedded domain-switch inside the handler: the `build` command peeks at the first token (`targets[0].startswith("projects")` vs `startswith("services")`) and dispatches to completely different code paths inside one Click command (see `cli.py:887–935`).
3. Domain-first group with sub-verbs, already the right shape: `localbox compose generate`, `localbox prune caches|builders|images|all`, `localbox clean projects`.

On top of that, two "init" commands use hyphenated names: `init` (scaffold a new solution) and `init-override` (create/regenerate the per-developer override file). They are orphans in grammar — there is no place to add a sibling verb like `override show` without either inventing another hyphenated command or finally introducing a group.

Target resolution in `src/localbox/utils/resolver.py` is written against the current shape: `resolve_targets(solution, ("projects:api",), "projects")` requires the token's first segment to equal the `target_type` argument (`resolver.py:48-49, 55-56, 70-71`). When the user is already inside a domain group, that prefix is redundant noise.

The shell completion script (`src/localbox/completions/localbox.bash`) and the `complete_targets` callback (`cli.py:62-86`) emit fully-qualified tokens (`projects:libs:utils`, `services:db:primary`) that match the current grammar.

Test coverage of the CLI uses `click.testing.CliRunner` with argument lists that match the current grammar (e.g., `runner.invoke(cli, ["init-override", "--force"])` in `tests/test_cli.py`). The tests will need to migrate alongside the CLI.

This change is being made before any 1.0 release and there are no known third-party consumers of the legacy shape beyond the project's own scripts and docs, so a clean break is acceptable.

## Goals / Non-Goals

**Goals:**
- Single consistent CLI grammar: `localbox <domain> <command> [args…]`.
- Every domain is a real Click `@cli.group()` — there is one obvious place to add sub-verbs later (especially for `override`).
- `build` no longer sniffs the first token to decide which domain it's operating on. Two separate commands (`projects build`, `services build`) each call only their own resolver.
- Targets under a domain group are short-form (`<group>[:<name>]`), and multiple targets are accepted — so `localbox projects build be:api fe:api workers` works as specified.
- Completion and docs reflect the new grammar everywhere.

**Non-Goals:**
- Implementing `override show`, `override set`, `override clear`. The `override` group exists so these can be added without further restructuring, but this change ships only `override init`.
- Implementing new `compose` sub-verbs beyond `generate`.
- Deprecation shims or aliases for the old grammar. This is a clean break.
- Relocating `doctor`, `config`, `completion`, `purge`, `prune` under domain groups. They either have no natural domain (`doctor`, `config`, `completion`) or are already internally consistent with the new grammar (`prune caches`, `prune builders`, `prune all`).
- Changing `src/localbox/commands/project.py`, `src/localbox/commands/service.py`, or `src/localbox/builders/*.py`. Only the Click wrapping in `cli.py` and one call-site pattern (how `resolve_targets` is invoked) change.
- Changing how plugins attach. Plugins registered through the `localbox.commands` entry point continue to attach at the top level via `_load_plugins()`.

## Decisions

### 1. Domains implemented as Click groups, not as a custom dispatcher

Use `@cli.group()` for each of `projects`, `services`, `compose`, `override`, `solution`. Move the existing command functions under those groups (`@projects.command("build")` instead of `@cli.command("build")`, etc.).

**Why**: Click handles help generation, sub-command dispatch, and completion for groups natively. Writing a custom dispatcher would duplicate machinery Click already provides well.

**Alternative considered**: A single top-level `localbox` command that manually splits `sys.argv[1]` into a domain and re-dispatches. Rejected — it would break `--help` at every level and require re-implementing completion.

### 2. `projects build` and `services build` are separate Click commands

Replace the one `build` handler that peeks at `targets[0]` with two independent commands. Each calls `resolve_targets(solution, targets, "projects")` or `resolve_targets(solution, targets, "services")` respectively, then calls its own build entry point (`commands.project.build_projects` vs `commands.service.build_images`).

**Why**: The current `build` handler has a runtime branch that decides the command's entire behavior from string-prefix sniffing. Under the new grammar the user has already picked the domain with the group — the code can just trust it. This removes a whole class of "Target must start with 'projects' or 'services'" error paths and makes each command simpler to read and test.

**Alternative considered**: Keep a single top-level `build` command. Rejected — it reintroduces the sniffing that the reorganization is meant to eliminate.

### 3. Target short-form: extend `resolve_targets` rather than wrap it

Modify `resolve_targets` to accept bare `<group>[:<name>]` tokens (and the empty case — no targets → all items of the target_type), not just `<target_type>[:…]` tokens. The `target_type` argument already tells the resolver which domain to work in; requiring it to also appear as the first segment of every token is redundant.

Concretely: drop the `parts[0] != target_type` checks in `resolver.py:48-49, 55-56, 70-71`. Reinterpret a 1-part token as "this is a group name or an ungrouped item name"; a 2-part token as "group:name". The resolver's own helpers (`is_group`, `get_single`, `get_group`) already key off the `target_type` argument, so the semantic change is small.

Also: commands SHALL call `resolve_targets(solution, targets, <type>)` with `targets` possibly being an empty tuple; the resolver treats an empty tuple as "all items of target_type" (equivalent to the current default `("projects",)` / `("services",)` fallback used by a few commands today).

**Why**: Keeping one resolver (with an expanded contract) is simpler than introducing a second "domain-scoped" resolver. Every call site is inside a domain group in the new world, and every call site already passes the right `target_type`.

**Alternative considered**: Add a new `resolve_targets_scoped(solution, targets, domain)` and leave `resolve_targets` alone. Rejected — there are no remaining callers of the old shape after the reorg, so maintaining both is dead weight.

**Alternative considered**: Accept both short-form and `<type>:…` long-form in the resolver for compatibility. Rejected — the proposal calls for a clean break and explicitly rejects the legacy prefix under a domain group (spec requirement "Domain-prefixed target is rejected under a domain group").

### 4. Rename `init` → `solution init` and `init-override` → `override init`, no aliases

Delete the top-level `init` and `init-override` commands. Add `solution init` and `override init` under their respective groups, each keeping the same `--force/-f` flag and internal behavior.

**Why**: Aliases delay the actual migration and double the surface that needs to be documented, tested, and eventually removed. A clean break in one release is easier to communicate in release notes than a two-phase deprecation.

**Alternative considered**: Keep the top-level aliases for one release with a deprecation warning. Rejected per non-goals — there are no known external consumers yet, and adding a warning requires shipping two forms that both need tests.

### 5. `list projects` / `list services` become `projects list` / `services list`

Add a `list` sub-command to each domain group. The existing `list_cmd` body in `cli.py:719-728` splits into two small wrappers that call `list_projects(solution)` and `list_services(solution)` directly.

**Why**: Consistent with the rest of the reorganization. There is no longer a reason to have a single `list` command that takes a Click `Choice` between "projects" and "services".

### 6. `compose` stays a group even though it has one verb today

`compose generate` is already the new shape. Keep `compose` as a `@cli.group()` rather than collapsing to `@cli.command()`, so that additions like `compose up`, `compose down`, or `compose lint` do not require another restructuring.

**Why**: The cost of keeping it a group is zero (the current code already does); the cost of collapsing it and re-inflating it later is a second breaking change.

### 7. Completion rewritten to match the new grammar

Update both `src/localbox/completions/localbox.bash` and the `complete_targets` callback:

- At the top level, suggest the domain groups plus `doctor`, `config`, `completion`, `purge`, `prune`.
- Under each domain, suggest its sub-verbs.
- For commands that take targets under a domain group, the completion callback should be parameterized by the domain (`"projects"` or `"services"`) and emit short-form tokens only: `<group>`, `<name>`, `<group>:<name>`. Implement this as two small callbacks: `complete_project_targets` and `complete_service_targets`, replacing the single domain-prefixed `complete_targets`.

**Why**: A single domain-agnostic callback cannot know which tokens are valid without inspecting the Click context, and the current callback hard-codes the legacy prefix. Two small callbacks are simpler than making one callback conditional on the parent group.

### 8. `prune` and `purge` stay top-level

`prune` already follows the domain-first sub-verb shape internally (`prune caches`, `prune builders`, `prune images`, `prune all`). `purge` is a single verb with no domain. Neither gains anything from being moved under a group.

**Why**: The reorg's goal is consistency, not depth. Moving `prune` to e.g. `projects prune builders` and `services prune images` would double the commands the user has to remember and split `prune all` across two places. Leaving these top-level keeps the utility surface flat.

## Risks / Trade-offs

- **Risk**: Every existing documentation snippet, script, CI pipeline, and shell history becomes wrong in one commit. → **Mitigation**: Update `README.md`, `CLAUDE.md`, and any solution-level `README` in the same change. Call out the break prominently in release notes and the changelog. Bump the minor version.
- **Risk**: Users with muscle memory for `localbox build projects:api` will hit a cryptic Click "no such command" error. → **Mitigation**: Consider adding a short `localbox --help` tip mentioning the domain-first grammar, and make the release-note example-rich so the translation table is obvious. No in-CLI shim, per Decision 4.
- **Risk**: Third-party plugins (registered via the `localbox.commands` entry point) currently attach at the top level; they will still do so, which means a plugin's command will appear alongside `projects`/`services`/etc. That is not a regression, but it is a visible inconsistency. → **Mitigation**: Document in the plugin-author section of the README that first-party convention is to register under a domain group (e.g., by exposing a group and adding sub-commands under it) while leaving the loading mechanism untouched. No code change in this release.
- **Risk**: `resolve_targets` contract widens (accepts bare `<group>[:<name>]` tokens), which could mask bugs where a caller forgets to pass the right `target_type`. → **Mitigation**: Every call site is updated in this change, and tests in `tests/test_resolver.py` are rewritten against the new contract. The resolver still raises `TargetError` for unknown groups or names.
- **Trade-off**: No deprecation shim means users who upgrade without reading notes get a failing command rather than a warning. Acceptable pre-1.0.
- **Trade-off**: `prune` and `purge` remaining top-level introduces a small exception to "everything is under a domain". The exception is well-defined (domain-less utilities stay top-level) and is worth the cost of not double-nesting `prune`.

## Migration Plan

1. Land the `cli.py` rewrite, the resolver change, the completion update, the test rewrite, and the doc update in one commit (or one PR with small per-concern commits). Because the CLI shape changes atomically, a split that leaves the tree in a half-migrated state is worse than one larger change.
2. Release as a minor version bump (e.g., `0.X.0` → `0.(X+1).0`). Tag release notes as BREAKING and include a translation table:
   - `localbox init` → `localbox solution init`
   - `localbox init-override` → `localbox override init`
   - `localbox list projects` → `localbox projects list`
   - `localbox list services` → `localbox services list`
   - `localbox clone projects:api` → `localbox projects clone api`
   - `localbox fetch projects` → `localbox projects fetch`
   - `localbox switch projects:api -b main` → `localbox projects switch api -b main`
   - `localbox build projects:api` → `localbox projects build api`
   - `localbox build services:db:primary` → `localbox services build db:primary`
   - `localbox status projects:api` → `localbox projects status api`
   - `localbox clean projects` → `localbox projects clean`
   - `localbox compose generate` → unchanged
   - `localbox prune …` → unchanged
   - `localbox purge` → unchanged
   - `localbox doctor`, `localbox config`, `localbox completion <shell>` → unchanged
3. Rollback strategy: revert the release commit. There is no state on disk that needs migration — the change is purely grammar.

## Open Questions

- Should `projects list` and `services list` accept an optional target filter (e.g., `localbox projects list be`) to list only one group? The current `list projects` has no such filter. Out of scope for this change; flag it for a follow-up if users ask.
- Should `completion` move under `solution` (e.g., `solution completion bash`)? Today it generates a shell script for the whole CLI, which is not solution-scoped, so leaving it top-level is the right call. Noted here only so the question does not re-surface in review.
