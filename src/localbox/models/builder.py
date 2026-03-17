"""Builder model - defines how to build a project in Docker."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from localbox.models.docker_image import DockerImage
from localbox.models.jdk import JDK

if TYPE_CHECKING:
    pass


class Packaging(Enum):
    """Java artifact packaging type."""

    JAR = "jar"
    WAR = "war"


@dataclass
class Volume:
    """Base class for Docker volume mounts."""

    container: str
    readonly: bool = False


@dataclass
class BindVolume(Volume):
    """Bind mount from host filesystem, resolved relative to solution root."""

    host: str = ""  # Path relative to solution root (or absolute)


@dataclass
class CacheVolume(Volume):
    """Cache directory under .build/<name>/."""

    name: str = ""  # Folder name inside .build/


@dataclass
class NamedVolume(Volume):
    """Docker named volume."""

    name: str = ""  # Docker volume name, e.g. "postgresql_data"


@dataclass
class Builder:
    """Defines how to build a project in Docker.

    A Builder encapsulates the Docker image (or Dockerfile), build command,
    volume mounts, and environment variables needed to build a project.

    Sources are mounted at `workdir` (/var/src by default).

    Usage:
        # Pre-configured builders
        b = maven("3.9")
        b = gradle("8.14")
        b = node(20)

        # Custom builder with image
        b = Builder(
            docker_image=DockerImage(name="custom", image="myimage:latest"),
            command="make build"
        )

        # Custom builder with Dockerfile
        b = Builder(docker_image=DockerImage(name="custom", dockerfile="./Dockerfile"))
    """

    # Image source
    docker_image: DockerImage | None = None

    # Build command (one of these)
    command: str | None = None  # Shell command string
    command_list: list[str] | None = None  # Explicit command list
    script: str | None = None  # Script file to mount and run

    # Container config
    volumes: list[Volume] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    entrypoint: str | None = None  # Override entrypoint
    workdir: str = "/var/src"

    # Build timeout in minutes. None = no timeout.
    # For large Maven/Gradle projects, set to 30–60. Default is no timeout.
    timeout: int | None = None

    # Clean command (one of these — used by `localbox clean projects`)
    clean_command: str | None = None  # Shell command string
    clean_command_list: list[str] | None = None  # Explicit command list
    clean_script: str | None = None  # Script file to mount and run

    def __post_init__(self) -> None:
        if isinstance(self.volumes, Volume):  # type: ignore[arg-type]
            self.volumes = [self.volumes]  # type: ignore[assignment]

    @property
    def uses_dockerfile(self) -> bool:
        return self.docker_image is not None and self.docker_image.dockerfile is not None

    def resolve_image_tag(self, jdk: JDK | None = None) -> str:
        """Get the Docker image name. Raises if using dockerfile instead."""
        if self.docker_image and self.docker_image.image:
            return self.docker_image.image
        raise ValueError("Builder uses a Dockerfile, not a pre-built image")


@dataclass
class JavaBuilder(Builder):
    """Base class for Java build tools (Maven, Gradle).

    Provides artifact detection and JDK-aware image resolution.
    JDK is specified on the JavaProject, not the builder.
    """

    version: str = ""  # Build tool version

    def resolve_image_tag(self, jdk: JDK | None = None) -> str:
        """Resolve Docker image tag using provided JDK."""
        raise NotImplementedError("Subclasses must implement resolve_image_tag")

    def get_artifact_pattern(self, packaging: Packaging) -> str:
        """Returns glob pattern for finding artifacts."""
        raise NotImplementedError("Subclasses must implement get_artifact_pattern")

    def detect_packaging(self, project_dir: Path) -> Packaging:
        """Auto-detect packaging type from build files."""
        raise NotImplementedError("Subclasses must implement detect_packaging")

    def find_artifact(self, project_dir: Path, packaging: Packaging) -> Path | None:
        """Find the artifact file in the project directory."""
        pattern = self.get_artifact_pattern(packaging)
        candidates = list(project_dir.glob(pattern))
        return candidates[0] if candidates else None


@dataclass
class MavenBuilder(JavaBuilder):
    """Maven builder with auto-configuration.

    Resolves Docker image based on project's JDK.
    Auto-detects packaging from pom.xml.

    Usage:
        builder = maven()  # Default version 3.9
        builder = maven("4.0")  # Custom version
    """

    version: str = "3.9"

    def __post_init__(self) -> None:
        # Set up volumes and command if not already set
        if not self.volumes:
            self.volumes = [
                CacheVolume(name="maven", container="/var/maven/.m2"),
            ]
        if not self.command_list and not self.command:
            self.entrypoint = ""
            self.command_list = [
                "mvn",
                "-Duser.home=/var/maven",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
                "install",
                "-Dmaven.test.skip=true",
            ]
        if not self.clean_command_list and not self.clean_command:
            self.clean_command_list = [
                "mvn",
                "-Duser.home=/var/maven",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
                "clean",
            ]
        super().__post_init__()

    def resolve_image_tag(self, jdk: JDK | None = None) -> str:
        """Resolve Maven Docker image tag using JDK."""
        if jdk is None:
            jdk = JDK(8)  # Default
        return f"maven:{self.version}-{jdk.maven_image_suffix()}"

    def get_artifact_pattern(self, packaging: Packaging) -> str:
        """Maven artifacts are in target/."""
        return f"target/*.{packaging.value}"

    def detect_packaging(self, project_dir: Path) -> Packaging:
        """Parse <packaging> from pom.xml. Defaults to JAR."""
        pom_path = project_dir / "pom.xml"
        if not pom_path.exists():
            return Packaging.JAR

        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()

            # Handle namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            packaging_elem = root.find(f"{ns}packaging")
            if packaging_elem is not None and packaging_elem.text:
                pkg = packaging_elem.text.lower()
                if pkg == "war":
                    return Packaging.WAR
        except ET.ParseError:
            pass

        return Packaging.JAR


@dataclass
class GradleBuilder(JavaBuilder):
    """Gradle builder with auto-configuration.

    Resolves Docker image based on project's JDK.
    Auto-detects packaging and filters out non-runnable JARs.

    Usage:
        builder = gradle()  # Default version 8.14
        builder = gradle("9.0")  # Custom version
    """

    version: str = "8.14"

    def __post_init__(self) -> None:
        # Set up volumes and command if not already set
        if not self.volumes:
            self.volumes = [
                CacheVolume(name="gradle", container="/var/gradle"),
                CacheVolume(name="maven", container="/var/maven/.m2"),
            ]
        if not self.command_list and not self.command:
            self.command_list = [
                "gradle",
                "build",
                "-x",
                "test",
                "--no-daemon",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
            ]
            self.environment = {
                "GRADLE_USER_HOME": "/var/gradle",
                "MAVEN_LOCAL_REPO": "/var/maven/.m2/repository",
            }
        if not self.clean_command_list and not self.clean_command:
            self.clean_command_list = [
                "gradle",
                "clean",
                "--no-daemon",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
            ]
        super().__post_init__()

    def resolve_image_tag(self, jdk: JDK | None = None) -> str:
        """Resolve Gradle Docker image tag using JDK."""
        if jdk is None:
            jdk = JDK(21)  # Default
        return f"gradle:{self.version}-{jdk.gradle_image_suffix()}"

    def get_artifact_pattern(self, packaging: Packaging) -> str:
        """Gradle artifacts are in build/libs/."""
        return f"build/libs/*.{packaging.value}"

    def detect_packaging(self, project_dir: Path) -> Packaging:
        """Check for 'war' plugin in build.gradle."""
        for build_file in ["build.gradle", "build.gradle.kts"]:
            build_path = project_dir / build_file
            if build_path.exists():
                content = build_path.read_text()
                # Check for war plugin
                if "plugin: 'war'" in content or "id 'war'" in content or 'id("war")' in content:
                    return Packaging.WAR
        return Packaging.JAR

    def find_artifact(self, project_dir: Path, packaging: Packaging) -> Path | None:
        """Find artifact, filtering out -plain, -sources, etc."""
        pattern = self.get_artifact_pattern(packaging)
        candidates = list(project_dir.glob(pattern))

        # Filter out non-runnable artifacts
        excluded_suffixes = ("-plain.", "-sources.", "-javadoc.")
        excluded_prefixes = ("original-",)

        filtered = [
            p
            for p in candidates
            if not any(suf in p.name for suf in excluded_suffixes)
            and not any(p.name.startswith(pre) for pre in excluded_prefixes)
        ]

        return filtered[0] if filtered else None


@dataclass
class MavenWrapperBuilder(JavaBuilder):
    """Maven Wrapper builder — runs ./mvnw on a plain JDK image.

    JDK image is determined from the project's JDK; Maven version comes from the wrapper.

    Usage:
        builder = mavenw()
    """

    def __post_init__(self) -> None:
        if not self.volumes:
            self.volumes = [CacheVolume(name="maven", container="/var/maven/.m2")]
        if not self.command_list and not self.command:
            self.entrypoint = ""
            self.command_list = [
                "./mvnw",
                "-Duser.home=/var/maven",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
                "install",
                "-Dmaven.test.skip=true",
            ]
        if not self.clean_command_list and not self.clean_command:
            self.clean_command_list = [
                "./mvnw",
                "-Duser.home=/var/maven",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
                "clean",
            ]
        super().__post_init__()

    def resolve_image_tag(self, jdk: JDK | None = None) -> str:
        if jdk is None:
            jdk = JDK(8)
        return jdk.jdk_image()

    def get_artifact_pattern(self, packaging: Packaging) -> str:
        return f"target/*.{packaging.value}"

    def detect_packaging(self, project_dir: Path) -> Packaging:
        pom_path = project_dir / "pom.xml"
        if not pom_path.exists():
            return Packaging.JAR
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"
            packaging_elem = root.find(f"{ns}packaging")
            if packaging_elem is not None and packaging_elem.text:
                if packaging_elem.text.lower() == "war":
                    return Packaging.WAR
        except ET.ParseError:
            pass
        return Packaging.JAR


@dataclass
class GradleWrapperBuilder(JavaBuilder):
    """Gradle Wrapper builder — runs ./gradlew on a plain JDK image.

    JDK image is determined from the project's JDK; Gradle version comes from the wrapper.

    Usage:
        builder = gradlew()
    """

    def __post_init__(self) -> None:
        if not self.volumes:
            self.volumes = [
                CacheVolume(name="gradle", container="/var/gradle"),
                CacheVolume(name="maven", container="/var/maven/.m2"),
            ]
        if not self.command_list and not self.command:
            self.command_list = [
                "./gradlew",
                "build",
                "-x",
                "test",
                "--no-daemon",
                "-Dmaven.repo.local=/var/maven/.m2/repository",
            ]
            self.environment = {
                "GRADLE_USER_HOME": "/var/gradle",
                "MAVEN_LOCAL_REPO": "/var/maven/.m2/repository",
            }
        if not self.clean_command_list and not self.clean_command:
            self.clean_command_list = ["./gradlew", "clean", "--no-daemon"]
        super().__post_init__()

    def resolve_image_tag(self, jdk: JDK | None = None) -> str:
        if jdk is None:
            jdk = JDK(21)
        return jdk.jdk_image()

    def get_artifact_pattern(self, packaging: Packaging) -> str:
        return f"build/libs/*.{packaging.value}"

    def detect_packaging(self, project_dir: Path) -> Packaging:
        for build_file in ["build.gradle", "build.gradle.kts"]:
            build_path = project_dir / build_file
            if build_path.exists():
                content = build_path.read_text()
                if "plugin: 'war'" in content or "id 'war'" in content or 'id("war")' in content:
                    return Packaging.WAR
        return Packaging.JAR

    def find_artifact(self, project_dir: Path, packaging: Packaging) -> Path | None:
        pattern = self.get_artifact_pattern(packaging)
        candidates = list(project_dir.glob(pattern))
        excluded_suffixes = ("-plain.", "-sources.", "-javadoc.")
        excluded_prefixes = ("original-",)
        filtered = [
            p
            for p in candidates
            if not any(suf in p.name for suf in excluded_suffixes)
            and not any(p.name.startswith(pre) for pre in excluded_prefixes)
        ]
        return filtered[0] if filtered else None


# Factory functions for convenience


def named_volume(name: str, container: str, readonly: bool = False) -> NamedVolume:
    """Create a Docker named volume mount."""
    return NamedVolume(name=name, container=container, readonly=readonly)


def cache_volume(name: str, container: str, readonly: bool = False) -> CacheVolume:
    """Create a cache volume mount under .build/<name>/."""
    return CacheVolume(name=name, container=container, readonly=readonly)


def bind_volume(host: str, container: str, readonly: bool = False) -> BindVolume:
    """Create a bind mount from a path relative to solution root."""
    return BindVolume(host=host, container=container, readonly=readonly)


def maven(version: str = "3.9") -> MavenBuilder:
    """Create a Maven builder.

    Args:
        version: Maven version (e.g. "3.9", "4.0")

    JDK is specified on the JavaProject, not the builder.
    """
    return MavenBuilder(version=version)


def gradle(version: str = "8.14") -> GradleBuilder:
    """Create a Gradle builder.

    Args:
        version: Gradle version (e.g. "8.5", "8.14", "9.0")

    JDK is specified on the JavaProject, not the builder.
    """
    return GradleBuilder(version=version)


def mavenw() -> MavenWrapperBuilder:
    """Create a Maven Wrapper builder (runs ./mvnw on a plain JDK image)."""
    return MavenWrapperBuilder()


def gradlew() -> GradleWrapperBuilder:
    """Create a Gradle Wrapper builder (runs ./gradlew on a plain JDK image)."""
    return GradleWrapperBuilder()


def node(version: int = 20) -> Builder:
    """Create a Node.js builder.

    Args:
        version: Node.js major version (e.g. 18, 20, 22)
    """
    return Builder(
        docker_image=DockerImage(name=f"node-{version}", image=f"node:{version}"),
        command="npm ci && npm run build",
        clean_command="rm -rf node_modules",
        volumes=[
            CacheVolume(name="node", container="/home/node/.npm"),
        ],
        environment={"npm_config_cache": "/home/node/.npm"},
    )
