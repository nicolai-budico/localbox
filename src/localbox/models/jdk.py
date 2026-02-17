"""JDK configuration for Java projects."""

from dataclasses import dataclass
from enum import Enum


class JDKProvider(Enum):
    """JDK distribution providers."""

    CORRETTO = "corretto"
    TEMURIN = "temurin"
    GRAALVM = "graalvm"


@dataclass
class JDK:
    """JDK configuration with version and provider.

    Used by JavaProject to specify required JDK, which is then
    resolved to appropriate Docker images by MavenBuilder/GradleBuilder.

    Usage:
        jdk = JDK(17)  # Defaults to Corretto
        jdk = JDK(21, JDKProvider.TEMURIN)
        jdk = temurin(17)  # Factory function
    """

    version: int
    provider: JDKProvider = JDKProvider.CORRETTO

    def maven_image_suffix(self) -> str:
        """Returns suffix for Maven Docker image tag.

        Example: maven:3.9-{suffix}
        """
        match self.provider:
            case JDKProvider.CORRETTO:
                return f"amazoncorretto-{self.version}"
            case JDKProvider.TEMURIN:
                return f"eclipse-temurin-{self.version}"
            case JDKProvider.GRAALVM:
                return f"graalvm-{self.version}"

    def gradle_image_suffix(self) -> str:
        """Returns suffix for Gradle Docker image tag.

        Example: gradle:8.14-{suffix}
        """
        match self.provider:
            case JDKProvider.GRAALVM:
                return f"jdk{self.version}-graal"
            case _:
                return f"jdk{self.version}"

    def runtime_image(self) -> str:
        """Returns Docker image for runtime (JRE).

        Used by SpringBootService and similar.
        """
        match self.provider:
            case JDKProvider.CORRETTO:
                return f"amazoncorretto:{self.version}"
            case JDKProvider.TEMURIN:
                return f"eclipse-temurin:{self.version}-jre"
            case JDKProvider.GRAALVM:
                return f"ghcr.io/graalvm/jdk:{self.version}"


# Factory functions for convenience
def corretto(version: int) -> JDK:
    """Create JDK with Amazon Corretto provider."""
    return JDK(version, JDKProvider.CORRETTO)


def temurin(version: int) -> JDK:
    """Create JDK with Eclipse Temurin provider."""
    return JDK(version, JDKProvider.TEMURIN)


def graalvm(version: int) -> JDK:
    """Create JDK with GraalVM provider."""
    return JDK(version, JDKProvider.GRAALVM)
