## Why

CI/CD pipelines that build and test from source need a way to record exactly which commit
of each configured project was used and which Docker image coordinates were produced. Today
localbox has no such concept: there is no way to reproduce a prior build, no way to hand
off a set of image coordinates to a downstream job, and no way to restore all repos to the
exact state at which a set of images was built.

A **manifest** — a small JSON file recording repository SHAs and image coordinates — closes
all three gaps. Once generated it can be checked into an `assembles/` directory, consumed
by later pipeline steps, and used by developers to re-run a test suite against a known set
of images.

Five commands are added or extended. Together they form a complete pipeline loop:
generate manifest → switch repos to recorded SHAs → build images (record image digests back
into manifest) → push images to registry → generate compose file pointing at registry images.

## What Changes

### New: `manifest` command group + `manifest generate`

A new top-level Click group `manifest` with one initial subcommand:

```
localbox manifest generate --manifest=<path> --tag=<tag> [--registry=<registry>] [--extra key=value …]
```

Reads all configured projects, captures HEAD SHA and `origin` remote URL for each, and
writes the manifest JSON. Only solution projects are recorded — the localbox solution repo
itself is not included. A missing source directory for any configured project is a hard
error (exit non-zero) — the manifest must represent a complete, known state.

`--registry` is optional: if omitted, `solution.config.registry` is used. If neither
is set the command exits with an error.

`--extra key=value` allows callers to embed arbitrary metadata in the manifest (e.g.
`triggered_by`, `pr_number`, `run_id`). Nothing is pulled from environment variables
automatically; callers who want CI context pass it explicitly via `--extra`. Extra pairs
are stored under a top-level `"extra"` key in the manifest JSON.

### Extend: `projects switch --manifest`

```
localbox projects switch [targets] [-b branch]    # existing
localbox projects switch --manifest=<path>         # new mode
```

`--manifest` is mutually exclusive with `[targets]` and `-b`. Reads `repositories` from
the manifest, runs `git fetch --all` + `git checkout <commit>` in each matched project's
source directory.

If a repository name in the manifest does not match any configured project, the command
prints an error for each unmatched name and exits non-zero. Silent skips are not
acceptable — an unmatched name almost always means a stale manifest or a mis-named
project.

### Extend: `services build --manifest`

```
localbox services build [targets] [--no-cache] [--manifest=<path>]
```

When `--manifest` is present, two things happen after each service image is built:

1. An extra `docker tag` applies the remote tag `{registry}/{service.image.name}:{tag}`.
2. The image digest (from `docker inspect --format '{{.Id}}'`) is written back into the
   manifest under `images.<service-name>.digest`. This records the exact image SHA
   alongside the repository SHAs, making the manifest a full snapshot of the build state.

The manifest file is updated in place after each service build. The remote-tag pattern is
identical to the one `services push` pushes, ensuring round-trip consistency.

### New: `services push --manifest`

```
localbox services push --manifest=<path>
```

New subcommand under the existing `services` group. Reads `tag` and `registry`
from the manifest and runs `docker push` for `{registry}/{service.image.name}:{tag}`
for every service. Assumes `docker login` was already performed by the caller. No target
filtering — always pushes all services.

### Extend: `compose generate --manifest` / `--tag` + `--registry`

```
localbox compose generate [--manifest=<path>]
localbox compose generate [--tag=<tag> --registry=<registry>]
```

When image coordinates are known, writes ECR-qualified image refs into the generated
`docker-compose.yml`. Two equivalent input paths:

1. `--manifest` — reads `tag` and `registry` from the manifest.
2. `--tag` + `--registry` — explicit flags.

**These two paths are mutually exclusive.** Mixing them (e.g. `--manifest` + `--tag`)
is a hard error. Making one silently override the other would be non-obvious and error-prone.

`--registry` falls back to `solution.config.registry` when omitted from explicit flags.
`--tag` has no fallback and remains required when using the explicit-flags path.

If neither path is active, the existing local-tag behavior is preserved unchanged.

## Capabilities

### New Capabilities
- `manifest-flow`: Defines the manifest JSON format, the `manifest generate` command,
  and the `--manifest` extensions to `projects switch`, `services build`, `services push`,
  and `compose generate`.

### Modified Capabilities
- `cli-structure`: add `manifest` group to the list of top-level domain groups; add
  `services push` to the `services` subcommand list; note the new flags on `projects switch`,
  `services build`, and `compose generate`.
- `compose-generation`: add requirements for `--manifest`, `--tag`, `--registry`
  flags and the mutual-exclusion rule.

## Decisions on Open Questions

1. **Manifest format — top-level repo entry**: Only solution projects are included in
   `"repositories"`. The localbox solution repo is not recorded — it is infrastructure,
   not a solution dependency.

2. **`services push` targets**: All services only. Partial pushes can be added later
   without breaking changes.

3. **`manifest generate` and services**: Image digests are captured by `services build
   --manifest` and written back into the manifest under `"images"`. Not captured at
   generate time (no images exist yet then).

4. **`--extra` value types**: All string. Callers cast as needed.

## Impact

- **Code**:
  - `src/localbox/cli.py`: register `manifest` group; add flags to `compose generate`.
  - `src/localbox/commands/manifest.py`: new file implementing `manifest generate`.
  - `src/localbox/commands/project.py`: extend `projects switch` with `--manifest`.
  - `src/localbox/commands/service.py`: extend `services build` with `--manifest`; add `services push`.
  - `src/localbox/builders/compose.py`: extend `generate_compose_file` to accept
    `tag` and `registry` parameters.
- **Models**: no changes to `Project`, `Service`, `SolutionConfig`, or `DockerImage`.
- **Tests**: new unit/integration tests for each command. Golden-file update for
  `compose generate` if the new flags are covered by the golden fixture.
- **Docs**: `CLAUDE.md` CLI usage section; `README.md` if it lists commands.
- **Dependencies**: none — `json`, `subprocess`, `datetime`, `os`, `pathlib` are all
  already used in the codebase.
