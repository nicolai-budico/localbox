"""Health check configuration for Docker Compose services."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HealthCheck:
    """Docker Compose healthcheck configuration.

    For common cases use the typed subclasses instead of constructing manually:

        h = HttpCheck(url="http://localhost:8080/actuator/health")
        h = PgCheck()
        h = PgCheck(user="myuser", retries=10)

    For anything else, pass the raw ``test`` list directly:

        h = HealthCheck(test=["CMD", "redis-cli", "ping"])
    """

    test: list[str] = field(default_factory=list)
    interval: str = "30s"
    timeout: str = "10s"
    retries: int = 3
    start_period: str = "10s"

    def to_compose_dict(self) -> dict:
        """Serialize to a Docker Compose healthcheck mapping."""
        return {
            "test": self.test,
            "interval": self.interval,
            "timeout": self.timeout,
            "retries": self.retries,
            "start_period": self.start_period,
        }


@dataclass
class HttpCheck(HealthCheck):
    """HTTP endpoint health check using ``curl -f``.

    A non-2xx response or connection failure counts as unhealthy.

    Usage::

        HttpCheck(url="http://localhost:8080/actuator/health")
        HttpCheck(url="http://localhost:9090/health", start_period="30s")
    """

    url: str = ""
    # HTTP apps (Spring Boot, Node.js) typically need more time to start
    # than a DB, so the default start_period is longer than HealthCheck's.
    start_period: str = "20s"

    def __post_init__(self) -> None:
        self.test = ["CMD", "curl", "-f", self.url]


@dataclass
class PgCheck(HealthCheck):
    """PostgreSQL health check using ``pg_isready``.

    ``pg_isready`` is bundled with every official ``postgres`` Docker image,
    so no extra tooling is needed.

    Usage::

        PgCheck()                  # user=postgres (default)
        PgCheck(user="mydb_user")
    """

    user: str = "postgres"
    # Check more frequently and with shorter timeout than HTTP —
    # dependent services will not start until the DB is healthy.
    interval: str = "10s"
    timeout: str = "5s"
    retries: int = 5

    def __post_init__(self) -> None:
        self.test = ["CMD-SHELL", f"pg_isready -U {self.user}"]


@dataclass
class SpringBootCheck(HttpCheck):
    """Health check for Spring Boot applications via Spring Actuator.

    Hits ``/actuator/health`` — the standard endpoint exposed by
    ``spring-boot-starter-actuator``.  Returns HTTP 200 with
    ``{"status":"UP"}`` when healthy, HTTP 503 when not.

    ``SpringBootService`` uses this automatically unless you supply a
    different healthcheck (or disable it with ``healthcheck=None`` via
    a custom ``ComposeConfig``).

    Usage::

        SpringBootCheck()           # port 8080 (default)
        SpringBootCheck(port=9090)  # non-standard port
    """

    port: int = 8080

    def __post_init__(self) -> None:
        self.url = f"http://localhost:{self.port}/actuator/health"
        super().__post_init__()  # sets self.test from self.url
