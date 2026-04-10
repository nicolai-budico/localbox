## ADDED Requirements

### Requirement: User-provided group takes precedence over module-derived group

When a `Project` or `Service` has an explicit `group` value set by the user, `_collect_objects` SHALL preserve that value regardless of which module the object is defined in. The module-derived group SHALL only be used as a fallback when no user-provided group exists.

#### Scenario: Service with explicit group in root module
- **WHEN** a Service is defined as `Service(name="primary", group="db")` in `solution.py`
- **THEN** the service SHALL have `group="db"`, `local_name="primary"`, and `name="db:primary"`

#### Scenario: Service with explicit group in sub-package
- **WHEN** a Service is defined as `Service(name="primary", group="db")` in `services/infra.py`
- **THEN** the service SHALL have `group="db"`, `local_name="primary"`, and `name="db:primary"` (user group wins over module-derived "infra")

#### Scenario: Service without group in sub-package (fallback)
- **WHEN** a Service is defined as `Service(name="primary")` in `services/infra.py`
- **THEN** the service SHALL have `group="infra"`, `local_name="primary"`, and `name="infra:primary"` (module-derived group used as fallback)

#### Scenario: Project with explicit group in root module
- **WHEN** a Project is defined as `Project(name="utils", group="libs")` in `solution.py`
- **THEN** the project SHALL have `group="libs"`, `local_name="utils"`, and `name="libs:utils"`
