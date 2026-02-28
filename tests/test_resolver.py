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
processor = JavaProject(
    "processor",
    repo="git@example.com/processor.git",
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
db_main = Service(
    name="db:main",
    image=DockerImage(image="postgres:14"),
    compose=ComposeConfig(order=1, ports=["5432:5432"]),
)

db_shared = Service(
    name="db:shared",
    image=DockerImage(image="postgres:14"),
    compose=ComposeConfig(order=2, ports=["5433:5433"]),
)

be_processor = Service(
    name="be:processor",
    project=processor,
    image=DockerImage(dockerfile="assets/Dockerfile.processor"),
    compose=ComposeConfig(order=10, ports=["8080:8080"]),
)
""")

    solution = load_solution(temp_dir)

    yield solution

    shutil.rmtree(temp_dir)


class TestResolveProjects:
    """Tests for resolving project targets."""

    def test_resolve_all_projects(self, solution_with_groups):
        """Should resolve 'projects' to all projects."""
        result = resolve_targets(solution_with_groups, ("projects",), "projects")

        assert len(result) == 4
        names = {p.name for p in result}
        assert names == {"processor", "libs:utils", "libs:parser", "frontend:ui"}

    def test_resolve_single_project(self, solution_with_groups):
        """Should resolve 'projects:processor' to single project."""
        result = resolve_targets(solution_with_groups, ("projects:processor",), "projects")

        assert len(result) == 1
        assert result[0].name == "processor"

    def test_resolve_grouped_project(self, solution_with_groups):
        """Should resolve 'projects:libs:utils' to grouped project."""
        result = resolve_targets(solution_with_groups, ("projects:libs:utils",), "projects")

        assert len(result) == 1
        assert result[0].name == "libs:utils"
        assert result[0].group == "libs"
        assert result[0].local_name == "utils"

    def test_resolve_group(self, solution_with_groups):
        """Should resolve 'projects:libs' to all projects in group."""
        result = resolve_targets(solution_with_groups, ("projects:libs",), "projects")

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"libs:utils", "libs:parser"}

    def test_resolve_multiple_targets(self, solution_with_groups):
        """Should resolve multiple targets."""
        result = resolve_targets(
            solution_with_groups,
            ("projects:processor", "projects:libs:utils"),
            "projects",
        )

        assert len(result) == 2
        names = {p.name for p in result}
        assert names == {"processor", "libs:utils"}

    def test_deduplicates_results(self, solution_with_groups):
        """Should deduplicate when same project matched multiple times."""
        result = resolve_targets(
            solution_with_groups,
            ("projects:libs", "projects:libs:utils"),
            "projects",
        )

        # libs:utils should appear only once
        names = [p.name for p in result]
        assert names.count("libs:utils") == 1

    def test_error_on_unknown_project(self, solution_with_groups):
        """Should raise error for unknown project."""
        with pytest.raises(TargetError):
            resolve_targets(solution_with_groups, ("projects:unknown",), "projects")

    def test_error_on_wrong_prefix(self, solution_with_groups):
        """Should raise error when prefix doesn't match target type."""
        with pytest.raises(TargetError):
            resolve_targets(solution_with_groups, ("services:db",), "projects")


class TestResolveServices:
    """Tests for resolving service targets."""

    def test_resolve_all_services(self, solution_with_groups):
        """Should resolve 'services' to all services."""
        result = resolve_targets(solution_with_groups, ("services",), "services")

        assert len(result) == 3
        names = {s.name for s in result}
        assert names == {"db:main", "db:shared", "be:processor"}

    def test_resolve_service_group(self, solution_with_groups):
        """Should resolve 'services:db' to all db services."""
        result = resolve_targets(solution_with_groups, ("services:db",), "services")

        assert len(result) == 2
        names = {s.name for s in result}
        assert names == {"db:main", "db:shared"}

    def test_resolve_single_service(self, solution_with_groups):
        """Should resolve 'services:db:main' to single service."""
        result = resolve_targets(solution_with_groups, ("services:db:main",), "services")

        assert len(result) == 1
        assert result[0].name == "db:main"
        assert result[0].group == "db"
        assert result[0].local_name == "main"


class TestTargetValidation:
    """Tests for target validation."""

    def test_error_on_too_many_colons(self, solution_with_groups):
        """Should raise error when target has too many colons."""
        with pytest.raises(TargetError) as exc_info:
            resolve_targets(
                solution_with_groups,
                ("projects:libs:utils:extra",),
                "projects",
            )

        assert "max 1 level" in str(exc_info.value)
