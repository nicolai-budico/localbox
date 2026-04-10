"""Golden-file tests for docker-compose.yml generation.

A golden-file test generates output from known input and compares it
to a checked-in reference file. Any unintentional change to the YAML
output (new keys, reordered sections, formatting changes) will fail the
test, forcing the developer to explicitly review and accept the diff.

To update the reference file after an intentional change:
    UPDATE_GOLDEN=1 pytest tests/test_compose_golden.py
"""

import os
from pathlib import Path

import pytest

from localbox.builders.compose import generate_compose_file
from localbox.config import DirectoriesConfig, DockerSettings, Solution
from localbox.models.builder import named_volume
from localbox.models.docker_image import DockerImage
from localbox.models.healthcheck import HttpCheck, PgCheck, SpringBootCheck
from localbox.models.service import ComposeConfig, Service
from localbox.models.solution_config import SolutionConfig

UPDATE_GOLDEN = os.getenv("UPDATE_GOLDEN") == "1"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_solution(tmp_path: Path, services: list[Service]) -> Solution:
    build = tmp_path / ".build"
    config = SolutionConfig(name="test", compose_project="test", network="test-net")
    return Solution(
        root=tmp_path,
        name="test",
        directories=DirectoriesConfig(
            build=build,
            projects=build / "projects",
            compose=build / "compose",
        ),
        docker=DockerSettings(compose_project="test", network="test-net"),
        config=config,
        services={s.name: s for s in services},
    )


@pytest.fixture()
def golden_services():
    """Three services covering the main cases: grouped, ungrouped, deps, healthchecks."""
    db = Service(
        name="db:primary",
        image=DockerImage(image="postgres:16"),
        compose=ComposeConfig(
            order=1,
            volumes=named_volume("db_data", "/var/lib/postgresql/data"),
            healthcheck=PgCheck(),
        ),
    )
    db._finalize_image_name()

    api = Service(
        name="be:api",
        compose=ComposeConfig(
            order=10,
            ports=["8080:8080"],
            depends_on=[db],
            healthcheck=HttpCheck(url="http://localhost:8080/actuator/health"),
        ),
    )
    api._finalize_image_name()

    proxy = Service(
        name="proxy",
        image=DockerImage(image="nginx:alpine"),
        compose=ComposeConfig(ports=["80:80"]),
    )
    proxy._finalize_image_name()

    return [db, api, proxy]


def test_compose_golden(tmp_path, golden_services):
    """Generated docker-compose.yml must match the checked-in golden file."""
    sol = _make_solution(tmp_path, golden_services)
    generate_compose_file(sol)
    result = (tmp_path / "docker-compose.yml").read_text()

    golden_path = FIXTURES_DIR / "docker-compose.golden.yml"

    if UPDATE_GOLDEN:
        FIXTURES_DIR.mkdir(exist_ok=True)
        golden_path.write_text(result)
        return  # Always passes on update

    assert golden_path.exists(), (
        "Golden file missing. Generate it with:\n"
        "  UPDATE_GOLDEN=1 pytest tests/test_compose_golden.py"
    )
    expected = golden_path.read_text()
    assert result == expected, (
        "docker-compose.yml output has changed from the golden file.\n"
        "Review the diff. If the change is intentional, update with:\n"
        "  UPDATE_GOLDEN=1 pytest tests/test_compose_golden.py"
    )


class TestRegistryImageTag:
    """Compose image tag includes registry prefix when registry is configured."""

    def test_no_registry_uses_local_tag(self, tmp_path):
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="db:primary",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert defn["image"] == "test/service/db/primary:latest"

    def test_registry_prefixes_image_tag(self, tmp_path):
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="db:primary",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])
        sol.registry = "registry.io/myteam"

        defn = generate_service_definition(sol, service)
        assert defn["image"] == "registry.io/myteam/test/service/db/primary:latest"


class TestHealthCheckSerialisation:
    """Unit tests for HealthCheck → compose dict, independent of golden file."""

    def test_pg_check_defaults(self):
        hc = PgCheck()
        d = hc.to_compose_dict()
        assert d["test"] == ["CMD-SHELL", "pg_isready -U postgres"]
        assert d["interval"] == "10s"
        assert d["timeout"] == "5s"
        assert d["retries"] == 5
        assert d["start_period"] == "10s"

    def test_pg_check_custom_user(self):
        hc = PgCheck(user="mydb")
        assert hc.to_compose_dict()["test"] == ["CMD-SHELL", "pg_isready -U mydb"]

    def test_http_check(self):
        hc = HttpCheck(url="http://localhost:8080/actuator/health")
        d = hc.to_compose_dict()
        assert d["test"] == ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
        assert d["interval"] == "30s"
        assert d["start_period"] == "20s"

    def test_http_check_custom_params(self):
        hc = HttpCheck(url="http://localhost:9090/health", retries=5, start_period="30s")
        d = hc.to_compose_dict()
        assert d["retries"] == 5
        assert d["start_period"] == "30s"

    def test_base_healthcheck(self):
        hc = PgCheck()
        assert isinstance(hc.to_compose_dict(), dict)
        assert "test" in hc.to_compose_dict()

    def test_healthcheck_in_service_definition(self, tmp_path):
        """HealthCheck is serialised correctly inside generate_service_definition."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="db:primary",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(healthcheck=PgCheck()),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert "healthcheck" in defn
        hc = defn["healthcheck"]
        assert hc["test"] == ["CMD-SHELL", "pg_isready -U postgres"]
        assert hc["retries"] == 5

    def test_no_healthcheck(self, tmp_path):
        """Service without healthcheck must not have the healthcheck key."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="proxy",
            image=DockerImage(image="nginx:alpine"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert "healthcheck" not in defn

    # --- SpringBootCheck ---

    def test_spring_boot_check_default_port(self):
        hc = SpringBootCheck()
        d = hc.to_compose_dict()
        assert d["test"] == ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
        assert d["interval"] == "30s"
        assert d["start_period"] == "20s"

    def test_spring_boot_check_custom_port(self):
        hc = SpringBootCheck(port=9090)
        d = hc.to_compose_dict()
        assert d["test"] == ["CMD", "curl", "-f", "http://localhost:9090/actuator/health"]

    def test_spring_boot_check_is_http_check(self):
        """SpringBootCheck must be an HttpCheck so it inherits all HTTP defaults."""
        from localbox.models.healthcheck import HttpCheck

        assert isinstance(SpringBootCheck(), HttpCheck)


class TestComposeConfigExtra:
    """Tests for ComposeConfig.extra passthrough field."""

    def test_extra_fields_appear_in_output(self, tmp_path):
        """extra dict keys are included in the service definition."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="be:api",
            compose=ComposeConfig(
                extra={"logging": {"driver": "json-file", "options": {"max-size": "10m"}}}
            ),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert defn["logging"] == {"driver": "json-file", "options": {"max-size": "10m"}}

    def test_extra_restart_passes_through(self, tmp_path):
        """extra values pass through when no typed field shadows them."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="be:api",
            compose=ComposeConfig(extra={"restart": "always"}),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert defn["restart"] == "always"

    def test_extra_empty_by_default(self, tmp_path):
        """A bare ComposeConfig() produces no unexpected extra keys."""
        from localbox.builders.compose import generate_service_definition

        service = Service(name="be:api", compose=ComposeConfig())
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        known_keys = {"networks", "image"}
        assert defn.keys() == known_keys

    def test_extra_multiple_keys(self, tmp_path):
        """Multiple keys in extra all appear in the service definition."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="be:api",
            compose=ComposeConfig(
                extra={
                    "logging": {"driver": "json-file"},
                    "cap_add": ["NET_ADMIN"],
                    "ulimits": {"nofile": {"soft": 65536, "hard": 65536}},
                }
            ),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert defn["logging"] == {"driver": "json-file"}
        assert defn["cap_add"] == ["NET_ADMIN"]
        assert defn["ulimits"] == {"nofile": {"soft": 65536, "hard": 65536}}


class TestComposeGeneration:
    """Generator-level rules: no default restart, quoted port strings."""

    def test_no_default_restart_policy(self, tmp_path):
        """A bare ComposeConfig() does not produce a `restart` key."""
        from localbox.builders.compose import generate_service_definition

        service = Service(name="be:api", compose=ComposeConfig())
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        defn = generate_service_definition(sol, service)
        assert "restart" not in defn

    def test_ports_are_quoted(self, tmp_path):
        """Generated compose file double-quotes every ports: entry."""
        service = Service(
            name="proxy",
            image=DockerImage(image="nginx:alpine"),
            compose=ComposeConfig(ports=["0.0.0.0:80:80", "0.0.0.0:9001:9001"]),
        )
        service._finalize_image_name()
        sol = _make_solution(tmp_path, [service])

        generate_compose_file(sol)
        result = (tmp_path / "docker-compose.yml").read_text()

        assert '- "0.0.0.0:80:80"' in result
        assert '- "0.0.0.0:9001:9001"' in result


class TestSpringBootServiceHealthcheck:
    """Integration tests for SpringBootService auto-generated healthcheck."""

    def _make_project(self):
        from localbox.models.project import JavaProject

        return JavaProject("api", repo="git@example.com/api.git")

    def test_auto_healthcheck_default_port(self):
        """SpringBootService generates SpringBootCheck on port 8080 by default."""
        from localbox.library.spring_boot_service import SpringBootService

        project = self._make_project()
        svc = SpringBootService(name="be:api", project=project)
        assert isinstance(svc.compose.healthcheck, SpringBootCheck)
        assert svc.compose.healthcheck.port == 8080

    def test_auto_healthcheck_custom_port(self):
        """SpringBootService uses server_port for the generated check URL."""
        from localbox.library.spring_boot_service import SpringBootService

        project = self._make_project()
        svc = SpringBootService(name="be:api", project=project, server_port=9090)
        assert isinstance(svc.compose.healthcheck, SpringBootCheck)
        assert svc.compose.healthcheck.port == 9090

    def test_opt_out_disables_healthcheck(self):
        """healthcheck=None must leave compose.healthcheck as None."""
        from localbox.library.spring_boot_service import SpringBootService

        project = self._make_project()
        svc = SpringBootService(name="be:api", project=project, healthcheck=None)
        assert svc.compose.healthcheck is None

    def test_custom_healthcheck_override(self):
        """A caller-supplied HealthCheck is used as-is, not replaced."""
        from localbox.library.spring_boot_service import SpringBootService

        project = self._make_project()
        custom = HttpCheck(url="http://localhost:8080/health")
        svc = SpringBootService(name="be:api", project=project, healthcheck=custom)
        assert svc.compose.healthcheck is custom

    def test_auto_overrides_compose_config_healthcheck(self):
        """_AUTO always generates SpringBootCheck, overriding compose.healthcheck.

        To keep a custom compose-level healthcheck, pass it via the service's
        ``healthcheck=`` parameter instead of inside ComposeConfig.
        """
        from localbox.library.spring_boot_service import SpringBootService

        project = self._make_project()
        svc = SpringBootService(
            name="be:api",
            project=project,
            compose=ComposeConfig(healthcheck=PgCheck()),  # will be overwritten
        )
        assert isinstance(svc.compose.healthcheck, SpringBootCheck)
