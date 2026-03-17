"""Data models for localbox."""

from localbox.models.base_env import BaseEnv, env_field
from localbox.models.builder import (
    BindVolume,
    Builder,
    CacheVolume,
    GradleBuilder,
    GradleWrapperBuilder,
    JavaBuilder,
    MavenBuilder,
    MavenWrapperBuilder,
    NamedVolume,
    Packaging,
    Volume,
    bind_volume,
    cache_volume,
    gradle,
    gradlew,
    maven,
    mavenw,
    named_volume,
    node,
)
from localbox.models.docker_image import DockerImage
from localbox.models.healthcheck import HealthCheck, HttpCheck, PgCheck, SpringBootCheck
from localbox.models.jdk import (
    JDK,
    JDKProvider,
    corretto,
    graalvm,
    temurin,
)
from localbox.models.project import (
    GitConfig,
    JavaArtifact,
    JavaProject,
    NodeProject,
    Project,
)
from localbox.models.service import (
    ComposeConfig,
    Service,
)
from localbox.models.solution_config import SolutionConfig

__all__ = [
    # JDK models
    "JDK",
    "JDKProvider",
    "corretto",
    "temurin",
    "graalvm",
    # Builder models
    "Builder",
    "JavaBuilder",
    "MavenBuilder",
    "GradleBuilder",
    "Packaging",
    "Volume",
    "BindVolume",
    "CacheVolume",
    "NamedVolume",
    "bind_volume",
    "cache_volume",
    "named_volume",
    "MavenWrapperBuilder",
    "GradleWrapperBuilder",
    "maven",
    "gradle",
    "mavenw",
    "gradlew",
    "node",
    # Docker image
    "DockerImage",
    # Project models
    "Project",
    "JavaProject",
    "NodeProject",
    "JavaArtifact",
    "GitConfig",
    # Health checks
    "HealthCheck",
    "HttpCheck",
    "PgCheck",
    "SpringBootCheck",
    # Service models
    "Service",
    "ComposeConfig",
    # Solution config
    "SolutionConfig",
    # Base env
    "BaseEnv",
    "env_field",
]
