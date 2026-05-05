## 1. Manifest command group

- [x] 1.1 Create `src/localbox/commands/manifest.py` with `manifest` Click group
- [x] 1.2 Implement `manifest generate`: iterate projects, read HEAD SHA + origin remote, write JSON
- [x] 1.3 Add `--tag` (required), `--registry` (optional, fallback to `solution.config.registry`), `--extra` (multiple, key=value) options
- [x] 1.4 Hard-error when any project source directory is missing (collect all missing, exit non-zero)
- [x] 1.5 Hard-error when no registry available (neither `--registry` nor `solution.config.registry`)
- [x] 1.6 Create parent directories of manifest path if absent
- [x] 1.7 Register `manifest` group in `src/localbox/cli.py`

## 2. `projects switch --manifest`

- [x] 2.1 Add `--manifest` option (`click.Path(exists=True)`) to `projects switch` in `cli.py`
- [x] 2.2 Add mutual-exclusion guard: `--manifest` + targets or `-b` → `UsageError`
- [x] 2.3 Implement `switch_projects_from_manifest()` in `src/localbox/commands/project.py`: match manifest repo keys to `project.path_name`, collect all unmatched keys, exit non-zero before touching any repo if any are unmatched
- [x] 2.4 For each matched project: run `git fetch --all` then `git checkout <commit>`

## 3. `services build --manifest`

- [x] 3.1 Add `--manifest` option (`click.Path(exists=True)`) to `services build` in `cli.py`
- [x] 3.2 After each successful build: apply remote tag `{registry}/{service.image.name}:{tag}` via `docker tag`
- [ ] 3.3 After tagging: read digest via `docker inspect --format '{{.Id}}'` on the local tag — **not implemented** (digest recording removed by design decision)
- [ ] 3.4 Write digest into manifest `images` map in place after each service (`{service.image.name}: <digest>`) — **not implemented** (digest recording removed by design decision)

## 4. `services push --manifest`

- [x] 4.1 Add `push` subcommand to `services` group in `cli.py`
- [x] 4.2 Implement `push` in `src/localbox/commands/service.py`: read `registry` and `tag` from manifest, run `docker push {registry}/{service.image.name}:{tag}` for every service
- [x] 4.3 Make `--manifest` required; no target filtering

## 5. `compose generate --manifest` / `--tag` / `--registry`

- [x] 5.1 Add `--manifest`, `--tag`, `--registry` options to `compose generate` command in `cli.py`
- [x] 5.2 Add mutual-exclusion guard: `--manifest` + `--tag`/`--registry` together → `UsageError`
- [x] 5.3 Resolve `(tag, registry)` in CLI layer: from manifest, or from explicit flags (with `solution.config.registry` fallback for `--registry`); error if tag set but no registry available
- [x] 5.4 Extend `generate_compose_file(solution, *, image_tag=None, registry=None)` in `src/localbox/builders/compose.py`: when both set, emit `{registry}/{service.image.name}:{image_tag}` as `image:` value

## 6. Tests

- [x] 6.1 Unit tests for `manifest generate`: happy path, missing project dir, missing registry, extra pairs, parent dir creation
- [x] 6.2 Unit tests for `projects switch --manifest`: happy path, unmatched key hard error, mutual exclusion
- [x] 6.3 Unit tests for `services build --manifest`: extra tag applied, digest written per-service, partial failure tolerance
- [x] 6.4 Unit tests for `services push --manifest`: all services pushed, missing `--manifest` error
- [x] 6.5 Unit tests for `compose generate` new flags: manifest path, explicit flags, mutual exclusion, registry fallback, no-flag local-tag behavior
- [x] 6.6 Update compose golden fixture if `compose generate` golden test covers image fields

## 7. Quality gates and docs

- [x] 7.1 Run `ruff format src/ tests/` → `ruff check src/ tests/` → `mypy src/localbox/` → `pytest tests/ -q`, all pass clean
- [x] 7.2 Update `CLAUDE.md` CLI usage section with new commands and flags
