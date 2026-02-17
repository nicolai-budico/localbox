"""Docker image configuration - universal for both builders and services."""

from dataclasses import dataclass


@dataclass
class DockerImage:
    """Docker image configuration.

    Used by both Builder (build environment image) and Service (service image).

    Attributes:
        dockerfile: Path to Dockerfile relative to solution root.
        image: Name of the Docker image (e.g. 'postgres:14').
        name: Logical name for tagging (e.g. 'maven-builder', 'postgres').
    """

    name: str = ""
    dockerfile: str | None = None
    image: str | None = None
