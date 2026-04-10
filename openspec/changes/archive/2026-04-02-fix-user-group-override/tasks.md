## 1. Fix group precedence in _collect_objects

- [x] 1.1 In `src/localbox/config.py` `_collect_objects`, update the Project else branch (~line 295-301): compute `effective_group = obj.group or group`, use it for name construction and `obj.group` assignment
- [x] 1.2 Apply the identical fix to the Service else branch (~line 325-329)

## 2. Tests

- [x] 2.1 Add test: Service with explicit `group` in root module preserves group and builds qualified name
- [x] 2.2 Add test: Project with explicit `group` in root module preserves group and builds qualified name
- [x] 2.3 Add test: Service without explicit group in sub-package still gets module-derived group (regression guard)
