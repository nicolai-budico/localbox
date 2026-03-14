"""JavaService — base class for Java-based services."""

from __future__ import annotations

from dataclasses import dataclass

from localbox.models.service import Service


@dataclass
class JavaService(Service):
    """Base class for services that run Java applications.

    Adds JVM configuration shared by all Java service types
    (TomcatService, SpringBootService, etc.).

    Fields:
        jvm_opts: JVM flags passed at startup, e.g. ``"-Xmx512m -Xms256m"``.
                  Applied via JAVA_OPTS environment variable (Tomcat)
                  or as arguments in the ENTRYPOINT array (Spring Boot).
    """

    jvm_opts: str | None = None
