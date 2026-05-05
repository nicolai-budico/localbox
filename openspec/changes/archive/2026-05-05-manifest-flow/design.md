## Context

`localbox` currently has no concept of a recorded build state. Builds are ephemeral:
project checkouts drift, image tags are local-only, and there is no way to reconstruct
the exact combination of source commits and images that a prior pipeline run produced.

The manifest introduces that concept. It is a JSON file written by `manifest generate`,
enriched in place by `services build --manifest` (image digests), and consumed by
`projects switch`, `services push`, and `compose generate`. The file lives in the
solution directory (e.g. `assembles/<tag>.json`) and can be committed alongside
solution code.

Relevant existing code:
- `src/localbox/commands/service.py` — `build_images()` iterates services, calls
  `do_build()` per service, then prints summary.
- `src/localbox/commands/project.py` — `switch_project()` runs `git checkout` on a
  single project's source directory.
- `src/localbox/builders/compose.py` — `generate_compose_file(solution)` builds the
  compose dict; image field set via `solution.service_image_tag(name)` at lines 347/354.
- `src/localbox/config.py` — `Solution.service_image_tag(name)` returns the local image
  tag, prefixed with `solution.registry` when set. `Solution.registry` mirrors
  `SolutionConfig.registry`.
- `src/localbox/models/project.py` — `Project.path_name` is the filesystem key used to
  match a project to its source directory.

Stakeholders: CI/CD pipeline jobs (generate, build, push, deploy steps) and developers
who want to reproduce a prior test run locally.

## Goals / Non-Goals

**Goals:**

- Define a stable manifest JSON format that carries repository SHAs and image digests.
- Implement `manifest generate` as the entry point that creates a manifest from current
  checkout state.
- Extend `services build` to write image digests back into the manifest and apply remote
  tags.
- Implement `services push` to push all service images using manifest coordinates.
- Extend `projects switch` with a `--manifest` mode that checks out recorded SHAs.
- Extend `compose generate` to emit registry-qualified image refs from manifest or
  explicit flags.
- Keep the manifest file as the single source of truth; never require callers to repeat
  coordinates across pipeline steps.

**Non-Goals:**

- No changes to `Project`, `Service`, `SolutionConfig`, or `DockerImage` models.
- No partial push targets for `services push` (always all services).
- No automatic reading of environment variables into the manifest.
- No manifest validation command (can be added later).
- No migration or backwards-compat for callers of the current `compose generate`
  signature — that function is internal.

## Decisions

### Decision 1: Manifest format

```json
{
  "tag":      "<tag>",
  "registry": "<registry>",
  "repositories": {
    "<project-path-name>": {
      "commit": "<SHA>",
      "remote": "<git-remote-url>"
    }
  },
  "extra": {
    "<key>": "<value>"
  }
}
```

Remote image ref pattern: `{registry}/{solution}/service/{service.image.name}:{tag}`

Keys:
- `tag` — the assemble tag, used as the Docker image tag.
- `registry` — registry prefix, combined with solution name and service name to form remote image refs.
- `repositories` — keyed by `project.path_name`; written by `manifest generate`.
- `extra` — arbitrary string key-value pairs from `--extra`; may be absent.

**Why this shape:** `path_name` is already the canonical filesystem identifier for a
project in localbox and is what `resolve_source_dir` uses. Using it as the manifest key
means matching a manifest entry to a project requires no extra lookup table. `image.name`
is the analogous canonical key for services.

**Alternatives considered:**
- *Use `project.name` (full colon-qualified name) as key.* Rejected: `path_name` is
  always a clean filesystem-safe string; full names like `be:api` contain colons that
  would need escaping in some contexts.
- *Merge `repositories` and `images` into one flat map.* Rejected: they are populated at
  different pipeline stages and have different shapes; keeping them separate avoids
  partial-read ambiguity.

### Decision 2: `manifest generate` — missing source directory is a hard error

If a configured project has no cloned source directory, `manifest generate` exits
non-zero after printing all missing projects.

**Why:** A manifest must be a complete snapshot. A partial manifest would silently allow
`projects switch --manifest` to leave some repos at the wrong commit, which defeats the
purpose. Fail fast and let the caller fix the environment (run `localbox projects clone`
first).

**Alternatives considered:**
- *Skip and warn.* Rejected per explicit design decision: silent partial manifests are
  worse than a clear error.

### Decision 3: `services build --manifest` does not record image digests

`services build --manifest` builds and tags images but does not write any digest data
back into the manifest. The manifest `images` key is absent.

**Why:** Image digest recording was removed as unnecessary. The manifest carries `tag` and
`registry` which are sufficient to reference images in `services push` and
`compose generate`. Adding digests would require a `docker inspect` round-trip per service
with no consumed value in the current pipeline.

### Decision 4: `projects switch --manifest` — unmatched repo names are a hard error

Every key in `manifest.repositories` must match exactly one configured project (by
`path_name`). If any key is unmatched, the command prints all unmatched names and exits
non-zero without modifying any repo.

**Why:** An unmatched name almost always indicates a stale manifest or a mis-named
project. Silently skipping conceals the mismatch and may leave repos at wrong commits.
Fail before touching anything — partial checkout state is dangerous.

**Alternatives considered:**
- *Warn and skip unknown keys.* Rejected per explicit design decision.
- *Fail after checking out the matched repos.* Rejected: failing before any checkout
  is the safest rollback strategy — no partial state to reason about.

### Decision 5: `compose generate` — `--manifest` and explicit flags are mutually exclusive

Mixing `--manifest` with `--tag` or `--registry` is a hard `UsageError`. The two
paths cannot be merged silently.

**Why:** Silent precedence rules are non-obvious and hard to debug in CI scripts. A caller
who passes both has likely made a mistake. Forcing an error surfaces the issue immediately.

**Alternatives considered:**
- *`--manifest` overrides explicit flags.* Rejected: non-obvious behavior that masks
  caller mistakes.
- *Explicit flags override manifest.* Same problem.

### Decision 6: `--registry` falls back to `solution.config.registry`

For both `manifest generate` and `compose generate --tag`, `--registry` is optional.
When absent, `solution.config.registry` is used. If that is also unset, the command exits
with an error.

**Why:** `SolutionConfig.registry` already exists for this purpose (`service_image_tag`
uses it). Re-requiring it on the CLI for every pipeline invocation is redundant and
error-prone.

### Decision 7: `generate_compose_file` signature extension

`generate_compose_file(solution)` becomes
`generate_compose_file(solution, *, image_tag=None, registry=None)`.
When both are set, the image field for each service is `f"{registry}/{service.image.name}:{image_tag}"`.
When neither is set, existing `solution.service_image_tag(name)` is used unchanged.

The CLI layer is responsible for resolving the two input paths (manifest vs. explicit
flags) into `(image_tag, registry)` before calling `generate_compose_file`. The function
itself stays unaware of manifests.

**Why:** Keeps `builders/compose.py` decoupled from manifest I/O. The CLI command handles
flag resolution; the builder handles generation.

## Risks / Trade-offs

- **Manifest grows stale if repos are modified after generate.** → Document that
  `manifest generate` must be called after all repos are at the intended state. The
  hard-error on missing directories partially enforces this.

- **`switch --manifest` does `git fetch --all` before checkout.** On large repos or slow
  CI networks this adds latency. → Fetch is necessary because the recorded commit may not
  be in the local clone's object store. It cannot be skipped safely.

## Migration Plan

No existing behavior changes for callers who do not use the new flags.

1. Add `src/localbox/commands/manifest.py` with the `manifest` Click group and
   `generate` subcommand.
2. Register the `manifest` group in `src/localbox/cli.py`.
3. Extend `src/localbox/commands/project.py`: add `--manifest` to `projects switch`;
   add `switch_projects_from_manifest()` helper.
4. Extend `src/localbox/commands/service.py`: add `--manifest` to `services build`;
   add `services push` subcommand.
5. Extend `src/localbox/builders/compose.py`: add `image_tag` / `registry` keyword
   args to `generate_compose_file`.
6. Extend the `compose generate` Click command in `cli.py` with `--manifest`,
   `--tag`, `--registry` flags and mutual-exclusion validation.
7. Add tests for each new command path.
8. Update `CLAUDE.md` CLI usage section.

Rollback: revert the five touched files. No on-disk format migrations — manifests are
written fresh each pipeline run and are not schema-versioned in v1.
