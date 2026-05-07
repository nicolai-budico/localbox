## Why

On persistent hosts (long-lived developer machines, dedicated build nodes), project repos accumulate state between runs: dirty working trees, detached HEADs, and lingering build artifacts cause `git pull` and `git checkout` failures. Sequential builds also underutilize available CPU cores on machines with a warm dependency cache, increasing total build time.

## What Changes

- `localbox projects build` gains `-j <jobs>` for intra-tier parallel builds
- `localbox services build` gains `-j <jobs>` for parallel Docker image builds
- `localbox projects fetch` gains `--force` to hard-reset repos to remote HEAD
- `localbox projects switch` gains `--force` to clean working tree before checkout

## Capabilities

### New Capabilities

- `parallel-builds`: Parallel execution for `projects build` and `services build` via `-j <jobs>` flag; uses `ThreadPoolExecutor` within dependency tiers
- `force-fetch`: Hard-reset variant of `projects fetch` that tolerates dirty working trees and detached HEADs
- `force-switch`: Pre-checkout clean for `projects switch` that discards modified/untracked files before branch or SHA checkout

### Modified Capabilities

## Impact

- `src/localbox/commands/project.py` — fetch and switch commands extended
- `src/localbox/commands/service.py` — services build extended
- `src/localbox/builders/build.py` — parallel project build logic
- `src/localbox/builders/docker.py` — parallel image build logic
- `src/localbox/cli.py` — new CLI flags wired up
