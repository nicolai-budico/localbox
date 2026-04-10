## ADDED Requirements

### Requirement: Instance access on BaseEnv returns a compose-style reference

Instance-level access to a field on a `BaseEnv` subclass instance SHALL return
an `EnvRef` object — a `str` subclass whose string value is `${<field_name>}`.
This applies to every declared field, whether or not the user supplied a value
at construction time, so that `solution.py` can build `ComposeConfig` values
that reference fields which will only be set later (for example in
`solution-override.py`). Raw values SHALL be retrievable through
`env.raw_value(<field_name>)` and through `EnvRef.raw`; both SHALL surface only
values that were actually set. Class-level access (`Env.<field>`) SHALL
continue to return the `EnvField` sentinel for declaration and introspection
purposes.

#### Scenario: f-string interpolation produces a variable reference
- **WHEN** a solution declares `MAIN_DB_LOIP: str = env_field()` on a
  `BaseEnv` subclass and instantiates `Env(MAIN_DB_LOIP="127.0.0.21")`
- **AND** user code evaluates `f"{config.env.MAIN_DB_LOIP}:5432"`
- **THEN** the resulting string SHALL equal `"${MAIN_DB_LOIP}:5432"`
- **AND** `config.env.raw_value("MAIN_DB_LOIP")` SHALL equal `"127.0.0.21"`

#### Scenario: bare instance access is a string reference
- **WHEN** user code evaluates `config.env.MAIN_DB_LOIP` directly
- **THEN** the value SHALL be a `str` equal to `"${MAIN_DB_LOIP}"`
- **AND** `isinstance(config.env.MAIN_DB_LOIP, str)` SHALL be `True`

#### Scenario: unset required field is still referenceable at import time
- **WHEN** a `BaseEnv` subclass field is never assigned a real value
- **AND** the solution is instantiated without supplying that field
- **THEN** instance access SHALL still return an `EnvRef` whose string form
  is `${<field_name>}` so that `solution.py` can reference it in
  `ComposeConfig` values at import time
- **AND** `env.raw_value(<field_name>)` SHALL raise `KeyError`
- **AND** the compose generator SHALL raise `ValueError` if the field is
  still unset when a service actually references it at generate time
  (covered by the unset-required-field requirement below)

#### Scenario: late override through instance assignment
- **WHEN** a `solution-override.py` file executes
  `solution.config.env.db_pass = "s3cr3t"` after `solution.py` has imported
- **THEN** subsequent instance access (`config.env.db_pass`) SHALL return
  an `EnvRef` whose string form is `"${db_pass}"` and whose `raw` attribute
  is `"s3cr3t"`
- **AND** `env.raw_value("db_pass")` SHALL return `"s3cr3t"`
- **AND** `env.raw_values()` SHALL contain `"db_pass": "s3cr3t"`

### Requirement: Compose generator writes variable references, not raw values

The compose generator SHALL walk every string emitted into `docker-compose.yml`
(ports, environment values, volumes, extras, healthcheck, links, hostname, and
any other string-valued field) and SHALL leave `${NAME}` references intact in
the output. Raw values SHALL NOT appear in `docker-compose.yml` for any field
that was produced by instance access on a `BaseEnv` subclass.

#### Scenario: port reference passes through to compose
- **WHEN** a service sets `ports=[f"{config.env.MAIN_DB_LOIP}:5432"]` on its
  `ComposeConfig`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain the port entry
  `"${MAIN_DB_LOIP}:5432"` verbatim

#### Scenario: environment value reference passes through to compose
- **WHEN** a service sets
  `environment={"POSTGRES_DB": config.env.db_name}`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain
  `POSTGRES_DB: "${db_name}"`

#### Scenario: reference embedded in extra passthrough field
- **WHEN** a service sets `extra={"command": ["--host", config.env.db_host]}`
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain
  `--host` followed by `"${db_host}"` in the command list

#### Scenario: plain string values are emitted unchanged
- **WHEN** a service sets `environment={"REDIS_MAXMEMORY": "256mb"}` without
  any `BaseEnv` reference
- **AND** the compose generator runs
- **THEN** the generated `docker-compose.yml` SHALL contain
  `REDIS_MAXMEMORY: "256mb"` verbatim

### Requirement: Referenced env fields are written to the env file with raw values

The compose generator SHALL write the `.env` file next to `docker-compose.yml`
and SHALL include an entry for every field set on the solution's `BaseEnv`
instance, plus an entry for every Docker Compose variable reference detected
in any generated compose string whose name matches a `BaseEnv` field. Each
entry SHALL use the field name as the key and the raw value as the value, and
values SHALL be quoted using the existing `_quote_env_value` escaping.

#### Scenario: referenced port field appears in .env
- **WHEN** a service uses `ports=[f"{config.env.MAIN_DB_LOIP}:5432"]`
- **AND** `config.env = Env(MAIN_DB_LOIP="127.0.0.21")`
- **AND** the compose generator writes `.env`
- **THEN** the `.env` file SHALL contain the line `MAIN_DB_LOIP="127.0.0.21"`

#### Scenario: unreferenced BaseEnv fields still appear in .env
- **WHEN** `config.env = Env(db_name="mydb", db_pass="secret")` and no
  service references either field
- **AND** the compose generator writes `.env`
- **THEN** the `.env` file SHALL contain `db_name="mydb"`
- **AND** the `.env` file SHALL contain `db_pass="secret"`

#### Scenario: values with shell metacharacters are escaped
- **WHEN** a raw value contains `$`, `` ` ``, `\`, or `"`
- **AND** the compose generator writes `.env`
- **THEN** the value SHALL be double-quoted with each metacharacter
  backslash-escaped

### Requirement: Unknown variable references pass through untouched

The compose generator SHALL leave Docker Compose variable references verbatim
in the generated compose output when the referenced name does not correspond
to any field on the solution's `BaseEnv` instance, and SHALL NOT add any entry
for such references to the env file. This preserves Docker Compose's own
variable expansion for names the user manages outside of `BaseEnv`.

#### Scenario: Compose-native variable is not captured
- **WHEN** a service uses `volumes=["${HOME}/data:/var/data"]`
- **AND** `HOME` is not a field on the solution's `BaseEnv`
- **THEN** the generated `docker-compose.yml` SHALL contain
  `${HOME}/data:/var/data` verbatim
- **AND** the `.env` file SHALL NOT contain any `HOME=` entry

### Requirement: Referencing an unset required field fails with a clear error

The compose generator SHALL raise `ValueError` whenever it encounters a
Docker Compose variable reference whose name matches a declared field on the
solution's `BaseEnv` subclass but that field is still holding the `EnvField`
sentinel because the user never supplied a value. The raised exception SHALL
name the offending field and SHALL point the user at `solution.py` or
`solution-override.py` as the place to set it.

#### Scenario: required field referenced by a service but never set
- **WHEN** a service uses `ports=[f"{config.env.MAIN_DB_LOIP}:5432"]`
- **AND** `config.env = Env(MAIN_DB_LOIP=Env.MAIN_DB_LOIP)` (sentinel, unset)
- **AND** the compose generator runs
- **THEN** it SHALL raise `ValueError`
- **AND** the exception message SHALL contain `"MAIN_DB_LOIP"`
- **AND** the exception message SHALL mention that the field is required and
  not set

### Requirement: Legacy class-level sentinel path is removed

The compose generator SHALL NOT accept class-level `EnvField` sentinels as
values inside `service.compose.environment` or anywhere else in a service
definition. Users SHALL reference env fields exclusively through instance
access on the `BaseEnv` instance owned by `SolutionConfig`.

#### Scenario: class-level sentinel used as environment value is rejected
- **WHEN** a service sets `environment={"POSTGRES_DB": Env.db_name}`
  (class-level `EnvField` sentinel)
- **AND** the compose generator runs
- **THEN** it SHALL raise an error indicating that `EnvField` sentinels are
  not valid compose values and that instance access should be used instead
