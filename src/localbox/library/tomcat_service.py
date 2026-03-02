"""TomcatService — deploys Java WAR artifacts to Tomcat."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from localbox.library.java_service import JavaService
from localbox.models.project import JavaArtifact

if TYPE_CHECKING:
    from localbox.config import Solution


@dataclass
class TomcatService(JavaService):
    """Service that deploys Java WAR artifacts to Tomcat.

    Auto-generates Dockerfile that copies WAR files to Tomcat webapps.
    Uses JavaArtifact to specify which artifact to deploy.

    Usage:
        be_processor = TomcatService(
            name="be:processor",
            webapps={"processor": processor.artifact()},
            tomcat_version="9-jdk8",
        )

        # Multiple webapps with explicit artifact path
        be_multi = TomcatService(
            name="be:multi",
            webapps={
                "authserver": auth_server.artifact("auth-server/target/oauth2-auth-server.war"),
                "processor": processor.artifact(),  # auto-detect
            },
            tomcat_version="9-jdk17",
        )
    """

    webapps: dict[str, JavaArtifact] = field(default_factory=dict)
    tomcat_version: str = "9-jdk8"

    def __post_init__(self) -> None:
        super().__post_init__()

        # Set image to tomcat base
        if not self.image.image:
            self.image.image = f"tomcat:{self.tomcat_version}"

        # Collect all projects from webapps artifacts
        if self.webapps:
            self.projects = [artifact.project for artifact in self.webapps.values()]

    def build_contexts(self, solution: Solution) -> list[tuple[str, Path]]:
        """Return ``(name, path)`` pairs for every ``--build-context`` entry.

        An empty list means there are no webapps configured; the caller should
        fall back to a standard image pull instead of a Dockerfile build.
        """
        contexts = []
        for artifact in self.webapps.values():
            project = artifact.project
            project_local = project.path_name
            src_dir = project.resolve_source_dir(solution.directories.projects)
            contexts.append((project_local, src_dir))
        return contexts

    def generate_dockerfile(self, solution: Solution) -> str:
        """Generate Dockerfile content for Tomcat with WAR deployments.

        Args:
            solution: The loaded Solution (provides directories.projects)

        Returns:
            Dockerfile content as string
        """
        from localbox.models.builder import JavaBuilder, Packaging

        projects_dir = solution.directories.projects

        lines = [
            f"FROM tomcat:{self.tomcat_version}",
            "",
            "# Remove default webapps",
            "RUN rm -rf /usr/local/tomcat/webapps/*",
            "",
            "# Deploy WAR files",
        ]

        for webapp_name, java_artifact in self.webapps.items():
            project = java_artifact.project
            if not isinstance(project.builder, JavaBuilder):
                continue

            # Get project directory
            project_local = project.path_name
            project_dir = project.resolve_source_dir(projects_dir)

            if java_artifact.path:
                # Explicit artifact path provided
                rel_path = java_artifact.path
                # Determine extension from path
                ext = Path(rel_path).suffix.lstrip(".")
                lines.append(
                    f"COPY --from={project_local} {rel_path} "
                    f"/usr/local/tomcat/webapps/{webapp_name}.{ext}"
                )
            else:
                # Auto-detect artifact
                packaging = project.builder.detect_packaging(project_dir)
                artifacts = list(project_dir.glob(project.builder.get_artifact_pattern(packaging)))

                # Filter artifacts for Gradle (exclude -plain, -sources, etc.)
                if hasattr(project.builder, "find_artifact"):
                    artifact = project.builder.find_artifact(project_dir, packaging)
                    artifacts = [artifact] if artifact else []

                if len(artifacts) > 1:
                    raise ValueError(
                        f"Multiple artifacts found for {project.name} in {project_dir}. "
                        f"Use .artifact('path/to/file.war') to specify which one."
                    )

                if artifacts:
                    rel_path = str(artifacts[0].relative_to(project_dir))
                    lines.append(
                        f"COPY --from={project_local} {rel_path} "
                        f"/usr/local/tomcat/webapps/{webapp_name}.{packaging.value}"
                    )
                else:
                    # Fallback to pattern (will fail at build time if not found)
                    pattern = project.builder.get_artifact_pattern(Packaging.WAR)
                    lines.append(
                        f"COPY --from={project_local} {pattern} "
                        f"/usr/local/tomcat/webapps/{webapp_name}.war"
                    )

        if self.jvm_opts:
            lines.extend(
                [
                    "",
                    f'ENV JAVA_OPTS="{self.jvm_opts}"',
                ]
            )

        lines.extend(
            [
                "",
                "EXPOSE 8080",
                'CMD ["catalina.sh", "run"]',
            ]
        )

        return "\n".join(lines)
