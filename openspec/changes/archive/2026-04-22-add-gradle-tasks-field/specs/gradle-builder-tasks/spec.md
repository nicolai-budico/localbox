## ADDED Requirements

### Requirement: Append extra tasks to default Gradle command via `tasks` field

`GradleBuilder` and `GradleWrapperBuilder` SHALL accept an optional `tasks: list[str] | None` field. When set, items in the list MUST be appended verbatim to the default Gradle build command, after the existing default arguments. The `tasks` field MUST also be exposed as a keyword-only parameter on the `gradle()` and `gradlew()` factory functions.

#### Scenario: tasks unset preserves default command
- **WHEN** a `GradleBuilder` is constructed without `tasks` (or with `tasks=None`)
- **THEN** its `build_command_list` MUST equal `["gradle", "build", "-x", "test", "--no-daemon", "-Dmaven.repo.local=/var/maven/.m2/repository"]`

#### Scenario: tasks unset preserves wrapper default command
- **WHEN** a `GradleWrapperBuilder` is constructed without `tasks`
- **THEN** its `build_command_list` MUST equal `["./gradlew", "build", "-x", "test", "--no-daemon", "-Dmaven.repo.local=/var/maven/.m2/repository"]`

#### Scenario: tasks appended to default Gradle command
- **WHEN** a `GradleBuilder` is constructed with `tasks=["publishToMavenLocal"]`
- **THEN** its `build_command_list` MUST end with `["publishToMavenLocal"]`
- **AND** all of `gradle`, `build`, `-x`, `test`, `--no-daemon`, and `-Dmaven.repo.local=/var/maven/.m2/repository` MUST still be present, preceding the appended task

#### Scenario: multiple tasks appended in order
- **WHEN** a `GradleWrapperBuilder` is constructed with `tasks=["publishToMavenLocal", ":app-server:assemble"]`
- **THEN** its `build_command_list` MUST end with `["publishToMavenLocal", ":app-server:assemble"]` in that exact order

#### Scenario: tasks accepts flag-shaped items verbatim
- **WHEN** a `GradleBuilder` is constructed with `tasks=["publishToMavenLocal", "-PreleaseVersion=1.2.3"]`
- **THEN** its `build_command_list` MUST contain `"-PreleaseVersion=1.2.3"` as an unmodified element after `"publishToMavenLocal"`

#### Scenario: factory function passes tasks through
- **WHEN** `gradle(tasks=["publishToMavenLocal"])` or `gradlew(tasks=["publishToMavenLocal"])` is called
- **THEN** the returned builder's `build_command_list` MUST end with `["publishToMavenLocal"]`

### Requirement: `tasks` is mutually exclusive with custom build command

If `tasks` is set together with any of `build_command`, `build_command_list`, `build_script` (or their deprecated aliases `command`, `command_list`, `script`), construction MUST raise `ValueError` with a message identifying both fields.

#### Scenario: tasks plus build_command_list raises
- **WHEN** a `GradleBuilder` is constructed with both `tasks=["publishToMavenLocal"]` and `build_command_list=["gradle", "myTask"]`
- **THEN** `ValueError` MUST be raised
- **AND** the error message MUST mention both `tasks` and `build_command_list`

#### Scenario: tasks plus build_command raises
- **WHEN** a `GradleWrapperBuilder` is constructed with both `tasks=["publishToMavenLocal"]` and `build_command="./gradlew myTask"`
- **THEN** `ValueError` MUST be raised

#### Scenario: tasks plus build_script raises
- **WHEN** a `GradleBuilder` is constructed with both `tasks=["publishToMavenLocal"]` and `build_script="build.sh"`
- **THEN** `ValueError` MUST be raised

#### Scenario: tasks plus deprecated command alias raises
- **WHEN** a `GradleBuilder` is constructed with `tasks=["publishToMavenLocal"]` and the deprecated `command_list=["gradle", "myTask"]`
- **THEN** `ValueError` MUST be raised after the deprecated alias is migrated to `build_command_list`

### Requirement: `tasks` on Maven builders raises

`MavenBuilder` and `MavenWrapperBuilder` SHALL reject the `tasks` field. If a user passes `tasks` to a Maven builder (directly or via a future Maven factory parameter), construction MUST raise `ValueError` indicating that `tasks` is Gradle-only.

#### Scenario: tasks on MavenBuilder raises
- **WHEN** a `MavenBuilder` is constructed with `tasks=["site"]`
- **THEN** `ValueError` MUST be raised
- **AND** the error message MUST indicate that `tasks` applies only to Gradle builders
