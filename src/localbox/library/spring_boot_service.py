"""SpringBootService — runs a Spring Boot JAR in a JRE container."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from localbox.library.java_service import JavaService
from localbox.models.healthcheck import HealthCheck, SpringBootCheck
from localbox.models.project import JavaArtifact, JavaProject

if TYPE_CHECKING:
    from localbox.config import Solution

# Sentinel: "auto-generate a SpringBootCheck" (the default behaviour).
# Using object() means the sentinel survives identity checks across modules.
_AUTO = object()


@dataclass
class SpringBootService(JavaService):
    """Service that runs a Spring Boot JAR.

    Auto-generates a Dockerfile using the project's JDK to select the right
    runtime image. No Dockerfile authorship needed for standard Spring Boot apps.

    A ``SpringBootCheck`` healthcheck targeting ``/actuator/health`` is added
    automatically.  Pass ``healthcheck=None`` to disable it, or pass any
    ``HealthCheck`` instance to override it.

    Usage::

        api = SpringBootService(
            name="be:api",
            artifact=api_project.artifact(),
            compose=ComposeConfig(ports=["8080:8080"], depends_on=[db]),
        )

        # With JVM tuning, Spring profiles, and explicit artifact path
        api = SpringBootService(
            name="be:api",
            artifact=api_project.artifact("target/myapp-exec.jar"),
            jvm_opts="-Xmx512m -Xms256m",
            spring_profiles="local,postgres",
            compose=ComposeConfig(ports=["8080:8080"], depends_on=[db]),
        )

        # Opt out of the auto-generated healthcheck
        api = SpringBootService(name="be:api", artifact=..., healthcheck=None)
    """

    artifact: JavaArtifact | None = None
    spring_profiles: str | None = None
    server_port: int = 8080
    # _AUTO  → generate SpringBootCheck(port=server_port) automatically
    # None   → no healthcheck
    # <check> → use the provided HealthCheck instance
    healthcheck: HealthCheck | None | object = field(default=_AUTO, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()

        # Derive project from artifact
        if self.artifact is not None:
            self.project = self.artifact.project

        if not isinstance(self.project, JavaProject):
            raise TypeError(
                f"SpringBootService '{self.name}' requires a JavaProject. "
                f"Pass artifact=<java_project>.artifact() or project=<JavaProject>."
            )

        # Resolve healthcheck sentinel → apply to compose config
        if self.healthcheck is _AUTO:
            self.compose.healthcheck = SpringBootCheck(port=self.server_port)
        elif self.healthcheck is not None:
            self.compose.healthcheck = self.healthcheck  # type: ignore[assignment]
        # else: healthcheck=None → leave compose.healthcheck untouched (no check)

    def build_contexts(self, solution: Solution) -> list[tuple[str, Path]]:
        """Return the single ``(name, path)`` build context for the JAR project."""
        project = self.project
        if not isinstance(project, JavaProject):
            return []
        project_local = project.local_name or project.name
        src_dir = solution.directories.projects / project_local
        return [(project_local, src_dir)]

    def generate_dockerfile(self, solution: Solution) -> str:
        """Generate Dockerfile content for a Spring Boot JAR deployment.

        Args:
            solution: The loaded Solution (provides directories.projects)

        Returns:
            Dockerfile content as string
        """
        from localbox.models.builder import JavaBuilder, Packaging

        projects_dir = solution.directories.projects

        project = self.project
        assert isinstance(project, JavaProject)

        project_local = project.local_name or project.name
        project_dir = projects_dir / project_local
        runtime_image = project.jdk.runtime_image()

        # Resolve artifact path: explicit > auto-detect > glob fallback
        explicit_path = self.artifact.path if self.artifact else None
        if explicit_path:
            jar_path = explicit_path
        elif isinstance(project.builder, JavaBuilder):
            artifact = project.builder.find_artifact(project_dir, Packaging.JAR)
            if artifact:
                jar_path = str(artifact.relative_to(project_dir))
            else:
                # Fallback to glob pattern — will fail at build time if not found
                jar_path = project.builder.get_artifact_pattern(Packaging.JAR)
        else:
            raise ValueError(
                f"SpringBootService '{self.name}': project has no JavaBuilder. "
                f"Use maven()/gradle() builder or pass an explicit artifact path."
            )

        lines = [
            f"FROM {runtime_image}",
            "",
            f"COPY --from={project_local} {jar_path} /app.jar",
            "",
        ]

        if self.spring_profiles:
            lines.append(f'ENV SPRING_PROFILES_ACTIVE="{self.spring_profiles}"')
            lines.append("")

        lines.append(f"EXPOSE {self.server_port}")
        lines.append("")

        java_cmd = ["java"]
        if self.jvm_opts:
            java_cmd.extend(self.jvm_opts.split())
        java_cmd.extend(["-jar", "/app.jar"])
        entrypoint = "[" + ", ".join(f'"{a}"' for a in java_cmd) + "]"
        lines.append(f"ENTRYPOINT {entrypoint}")

        return "\n".join(lines)
