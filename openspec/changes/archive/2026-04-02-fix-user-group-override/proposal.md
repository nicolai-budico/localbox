## Why

When a user explicitly sets `group` on a `Service` or `Project` defined in the root module (`solution.py`), the config loader overwrites it with the module-derived group (which is `None` for root modules). This silently discards user intent, causing services to lose their group assignment and breaking target resolution (e.g., `services:db` won't find the service).

## What Changes

- Fix `_collect_objects` in `config.py` to respect user-provided `group` values on both `Project` and `Service` objects.
- In the "partial name" else branch, use `obj.group or group` instead of unconditionally assigning `obj.group = group`. This ensures user-provided group wins, with module-derived group as fallback.
- When the user provided a group, reconstruct the qualified name as `{group}:{local_name}`.

## Capabilities

### New Capabilities

_None — this is a bug fix._

### Modified Capabilities

_None — no spec-level behavior changes, just correcting the implementation to match existing intent._

## Impact

- `src/localbox/config.py`: `_collect_objects` function, both the Project branch (~line 295) and Service branch (~line 325).
- Solutions that define grouped services/projects in root `solution.py` will now work correctly.
- No breaking changes — this restores expected behavior.
