## Context

`_collect_objects` in `config.py` assigns `group`, `local_name`, and qualified `name` to Project/Service objects during config loading. It has three branches for name handling:

1. **`obj.name is None`** — auto-generate from variable name + module group
2. **`":" in obj.name`** — qualified name provided, derive group from it
3. **else** — partial name, prefix with module group

Branch 3 unconditionally sets `obj.group = group` (the module-derived group), overwriting any user-provided value. For root modules (`solution.py`), the module-derived group is `None`.

## Goals / Non-Goals

**Goals:**
- Preserve user-provided `group` when the loader assigns names
- Reconstruct qualified name from user-provided group + partial name

**Non-Goals:**
- Changing group precedence for qualified names (colon branch) — already correct
- Adding parent-group semantics for sub-packages
- Changing how `_derive_group_from_module` works

## Decisions

**User-provided group takes precedence over module-derived group.**

In the else branch, replace:
```python
obj.group = group
```
with:
```python
effective_group = obj.group or group
```

Then use `effective_group` for both the qualified name construction and `obj.group` assignment. This applies identically to both the Project block and the Service block.

**Rationale**: The user explicitly set `group=` — that's a stronger signal than file location. Module-derived group serves as a sensible default when the user didn't specify one.

## Risks / Trade-offs

- **Risk**: Someone relies on module group overriding user group → extremely unlikely since the current behavior silently drops the group, which is clearly a bug.
- **Risk**: Divergence between Project and Service branches if fixed inconsistently → mitigated by applying the identical change to both branches.
