# Spec: force-switch

## Purpose

Defines the behaviour of the `--force` flag on `localbox projects switch`. When provided, the command cleans the working tree before performing the checkout, allowing it to succeed even when there are local modifications or untracked files.

## Requirements

### Requirement: projects switch accepts force flag
`localbox projects switch` SHALL accept a `--force` flag compatible with both operating modes (branch switch and `--manifest` mode). When provided, each repo SHALL be cleaned via `git reset --hard HEAD` and `git clean -fd` before the checkout step. When omitted, existing checkout behaviour is unchanged.

#### Scenario: Force switch on branch mode with dirty tree
- **WHEN** `localbox projects switch be:api -b origin/feature/my-fix --force` is run with modified tracked files
- **THEN** working tree is cleaned before checkout and checkout succeeds

#### Scenario: Force switch on manifest mode with dirty tree
- **WHEN** `localbox projects switch --manifest assembles/v1.json --force` is run with modified tracked files
- **THEN** working tree is cleaned for each repo before the SHA checkout and checkout succeeds

#### Scenario: Force switch removes untracked files
- **WHEN** `localbox projects switch --force` is run with untracked build artifacts present
- **THEN** untracked files are deleted before checkout proceeds

#### Scenario: No-force switch is unchanged
- **WHEN** `localbox projects switch` is run without `--force`
- **THEN** behaviour is identical to before this change
