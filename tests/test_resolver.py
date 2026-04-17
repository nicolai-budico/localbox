"""Tests for target resolution."""

import shutil
import tempfile
from pathlib import Path

import pytest

from localbox.config import CONFIG_FILE, load_solution
from localbox.utils.resolver import TargetError, resolve_targets


@pytest.fixture
def solution_with_groups():
    """Create a solution with grouped projects and services."""
    temp_dir = Path(tempfile.mkdtemp())

    (temp_dir / CONFIG_FILE).write_text("""\
from localbox.models import (
    Project, JavaProject, maven, node,
    Service, DockerImage, ComposeConfig,
)

# Root-level project (Java with JDK 8)
api = JavaProject(
    "api",
    repo="git@example.com/api.git",
    jdk=8,
    builder=maven("3.9"),
)

# Grouped projects (Java)
utils = JavaProject(
    "libs:utils",
    repo="git@example.com/utils.git",
    jdk=8,
    builder=maven("3.9"),
)

parser = JavaProject(
    "libs:parser",
    repo="git@example.com/parser.git",
    jdk=8,
    builder=maven("3.9"),
    deps=[utils],
)

# Non-Java project (Node)
ui = Project(
    "frontend:ui",
    repo="git@example.com/ui.git",
    builder=node(20),
)

# Services
db_primary = Service(
    name="db:primary",
    image=DockerImage(image="postgres:14"),
    compose=ComposeConfig(order=1, ports=["5432:5432"]),
)

db_secondary = Service(
    name="db:secondary",
    image=DockerImage(image="postgres:14"),
    compose=ComposeConfig(order=2, ports=["5433:5433"]),
)

be_api = Service(
    name="be:api",
    project=api,
    image=DockerImage(dockerfile="assets/Dockerfile.api"),
    compose=ComposeConfig(order=10, ports=["8080:8080"]),
)
""")

    solution = load_solution(temp_dir)

    yield solution

    shutil.rmtree(temp_dir)


class TestResolveProjects:
    """Tests for resolving project targets under the 'projects' domain."""

    def test_empty_tuple_resolves_all(self, solution_with_groups):
        """An empty target tuple resolves to all projects."""
        result = resolve_targets(solution_with_groups, (), "projects")

        assert len(result) == 4
        names = {p.name for p in result}
        assert names == {"api", "libs:utils", "libs:parser", "frontend:ui"}

    def test_resolve_ungrouped_name(self, solution_with_groups):
        """A bare name resolves to an ungrouped project."""
        result = resolve_targets(solution_with_groups, ("api",), "projects")

        assert len(result) == 1
        assert result[0].name == "api"

    def test_resolve_group_name(self, solution_with_groups):
        """A bare name matching a group resolves to all projects in that group."""
        result = resolve_targets(solution_with_groups, ("libs",), "projects")

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"libs:utils", "libs:parser"}

    def test_resolve_qualified_name(self, solution_with_groups):
        """'group:name' resolves to a single grouped project."""
        result = resolve_targets(solution_with_groups, ("libs:utils",), "projects")

        assert len(result) == 1
        assert result[0].name == "libs:utils"
        assert result[0].group == "libs"
        assert result[0].local_name == "utils"

    def test_resolve_multiple_targets(self, solution_with_groups):
        """Multiple short-form tokens resolve independently and union."""
        result = resolve_targets(
            solution_with_groups,
            ("api", "libs:utils"),
            "projects",
        )

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"api", "libs:utils"}

    def test_resolve_groups_and_qualified_mixed(self, solution_with_groups):
        """'libs frontend:ui' resolves the libs group plus one qualified name."""
        result = resolve_targets(
            solution_with_groups,
            ("libs", "frontend:ui"),
            "projects",
        )

        assert len(result) == 3
        names = {p.name for p in result}
        assert names == {"libs:utils", "libs:parser", "frontend:ui"}

    def test_deduplicates_overlapping_targets(self, solution_with_groups):
        """An item matched by both a group and a qualified token appears once."""
        result = resolve_targets(
            solution_with_groups,
            ("libs", "libs:utils"),
            "projects",
        )

        names = [p.name for p in result]
        assert names.count("libs:utils") == 1

    def test_error_on_unknown_name(self, solution_with_groups):
        """A bare name that is neither a group nor a project raises TargetError."""
        with pytest.raises(TargetError) as exc_info:
            resolve_targets(solution_with_groups, ("unknown",), "projects")
        assert "unknown" in str(exc_info.value).lower()

    def test_error_on_unknown_qualified_name(self, solution_with_groups):
        """An unknown group:name raises TargetError."""
        with pytest.raises(TargetError):
            resolve_targets(solution_with_groups, ("libs:missing",), "projects")

    def test_error_on_legacy_domain_prefix(self, solution_with_groups):
        """Legacy 'projects:...' tokens are rejected under the 'projects' domain."""
        with pytest.raises(TargetError) as exc_info:
            resolve_targets(solution_with_groups, ("projects:api",), "projects")
        assert "domain-prefixed" in str(exc_info.value).lower() or "projects" in str(exc_info.value)

    def test_error_on_bare_domain_token(self, solution_with_groups):
        """A bare 'projects' token is rejected under the 'projects' domain."""
        with pytest.raises(TargetError):
            resolve_targets(solution_with_groups, ("projects",), "projects")

    def test_error_on_too_many_colons(self, solution_with_groups):
        """Targets with more than one colon are rejected."""
        with pytest.raises(TargetError) as exc_info:
            resolve_targets(
                solution_with_groups,
                ("libs:utils:extra",),
                "projects",
            )
        assert "max 1 level" in str(exc_info.value)


class TestResolveServices:
    """Tests for resolving service targets under the 'services' domain."""

    def test_empty_tuple_resolves_all(self, solution_with_groups):
        """An empty target tuple resolves to all services."""
        result = resolve_targets(solution_with_groups, (), "services")

        assert len(result) == 3
        names = {s.name for s in result}
        assert names == {"db:primary", "db:secondary", "be:api"}

    def test_resolve_service_group(self, solution_with_groups):
        """A bare group name resolves to all services in that group."""
        result = resolve_targets(solution_with_groups, ("db",), "services")

        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"db:primary", "db:secondary"}

    def test_resolve_qualified_service(self, solution_with_groups):
        """'group:name' resolves to a single service."""
        result = resolve_targets(solution_with_groups, ("db:primary",), "services")

        assert len(result) == 1
        assert result[0].name == "db:primary"
        assert result[0].group == "db"
        assert result[0].local_name == "primary"

    def test_error_on_legacy_domain_prefix(self, solution_with_groups):
        """Legacy 'services:...' tokens are rejected under the 'services' domain."""
        with pytest.raises(TargetError):
            resolve_targets(solution_with_groups, ("services:db",), "services")

    def test_error_on_cross_domain_token(self, solution_with_groups):
        """A token from the other domain is rejected (e.g. 'projects:api' under services)."""
        with pytest.raises(TargetError):
            resolve_targets(solution_with_groups, ("projects:api",), "services")
