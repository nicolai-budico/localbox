"""Service data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from localbox.models.builder import Volume
from localbox.models.docker_image import DockerImage
from localbox.models.healthcheck import HealthCheck
from localbox.models.project import Project


@dataclass
class ComposeConfig:
    """Docker Compose configuration for a service."""

    order: int = 20
    hostname: str | None = None
    # Override compose service name (default: derived from Service.name)
    service_name: str | None = None
    ports: list[str] = field(default_factory=list)
    depends_on: list[Service] = field(default_factory=list)
    links: list[str] = field(default_factory=list)  # "service:alias" format
    environment: dict[str, str] = field(default_factory=dict)
    volumes: list[Volume] = field(default_factory=list)
    healthcheck: HealthCheck | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.volumes, Volume):  # type: ignore[arg-type]
            self.volumes = [self.volumes]  # type: ignore[assignment]

    def get_depends_on_names(self) -> list[str]:
        """Resolve depends_on Service objects to names."""
        result = []
        for dep in self.depends_on:
            if dep.name is None:
                raise ValueError("Service dependency has no name (not yet loaded?)")
            result.append(dep.name)
        return result


@dataclass
class Service:
    """Service definition."""

    name: str | None = None  # Qualified name: "db:primary" or "be:api" (auto-generated if None)
    image: DockerImage = field(default_factory=DockerImage)
    compose: ComposeConfig = field(default_factory=ComposeConfig)
    project: Project | None = None  # Primary project
    projects: list[Project] = field(default_factory=list)  # Additional source projects

    # Internal: set during loading
    config_path: Path | None = None  # Path to config.yaml or name.yaml
    base_dir: Path | None = None  # Directory containing config (for folder-based)
    group: str | None = None  # "db", "be", "fe" (required for services)
    local_name: str | None = None  # "primary", "api" (without group prefix)

    @property
    def all_projects(self) -> list[Project]:
        """Return combined list of project and projects."""
        result = []
        if self.project:
            result.append(self.project)
        result.extend(self.projects)
        return result

    def __post_init__(self) -> None:
        # Auto-derive group/local_name from name (if name is set)
        if self.name:
            if self.group is None and ":" in self.name:
                self.group, self.local_name = self.name.split(":", 1)
            elif self.local_name is None:
                self.local_name = self.name

    @property
    def path_name(self) -> str:
        """Short filesystem-safe name: local_name if grouped, else name.

        Raises ValueError if both are None (the service was never loaded/named).
        """
        name = self.local_name or self.name
        if name is None:
            raise ValueError("Service has no name — this is a config loading bug")
        return name

    @property
    def compose_name(self) -> str:
        """Compose service name used in docker-compose.yml and docker compose commands."""
        return self.compose.service_name or (self.name or "").replace(":", "-")

    def _finalize_image_name(self) -> None:
        """Set default image name after name is finalized.

        Colons in the service name map to path separators in the image tag:
            proxy              → proxy
            db:primary         → db/primary
            be:payments:api    → be/payments/api
        """
        if not self.image.name and self.name:
            self.image.name = self.name.replace(":", "/")

    def get_dockerfile_path(self, solution_root: Path) -> Path | None:
        """Return Dockerfile: service-local first, then solution root."""
        if self.image.dockerfile:
            if self.base_dir:
                local = self.base_dir / self.image.dockerfile
                if local.exists():
                    return local
            # Check if it's an absolute or relative path
            dockerfile_path = Path(self.image.dockerfile)
            if dockerfile_path.is_absolute():
                return dockerfile_path if dockerfile_path.exists() else None
            # Relative to solution root
            return solution_root / self.image.dockerfile
        return None

    def container_name(self, compose_project: str) -> str:
        """Get the Docker container name for this service."""
        return f"{compose_project}-{self.compose_name}"
