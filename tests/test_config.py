"""Tests for configuration loading."""

import shutil
import tempfile
from pathlib import Path

import pytest

from localbox.config import (
    CONFIG_FILE,
    SolutionNotFoundError,
    create_default_solution,
    find_solution_root,
    load_solution,
)


@pytest.fixture
def temp_solution():
    """Create a temporary solution directory with a minimal solution.py."""
    temp_dir = Path(tempfile.mkdtemp())

    (temp_dir / CONFIG_FILE).write_text(
        "from localbox.models import SolutionConfig\nconfig = SolutionConfig()\n"
    )

    yield temp_dir

    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_solution_with_projects(temp_solution):
    """Create a solution with sample projects and services defined in Python."""
    (temp_solution / CONFIG_FILE).write_text("""\
from localbox.models import (
    SolutionConfig, Project, JavaProject, maven, gradle, node,
    Service, DockerImage, ComposeConfig,
)

config = SolutionConfig()

utils = JavaProject(
    "utils",
    repo="git@github.com:example/utils.git",
    jdk=8,
    builder=maven("3.9"),
)

parser = JavaProject(
    "libs:parser",
    repo="git@github.com:example/parser.git",
    jdk=17,
    builder=gradle("8.14"),
    deps=[utils],
)

ui = Project(
    "frontend:ui",
    repo="git@github.com:example/ui.git",
    builder=node(20),
)

db_main = Service(
    name="db:primary",
    image=DockerImage(image="postgres:14"),
    compose=ComposeConfig(
        order=1,
        ports=["5432:5432"],
        environment={"POSTGRES_USER": "postgres"},
    ),
)
""")

    return temp_solution


class TestFindSolutionRoot:
    """Tests for find_solution_root function."""

    def test_finds_root_in_current_dir(self, temp_solution):
        """Should find solution root when solution.py is in current directory."""
        root = find_solution_root(temp_solution)
        assert root == temp_solution

    def test_finds_root_in_parent_dir(self, temp_solution):
        """Should find solution root when starting from subdirectory."""
        subdir = temp_solution / "subdir"
        subdir.mkdir()
        root = find_solution_root(subdir)
        assert root == temp_solution

    def test_finds_root_in_deep_subdir(self, temp_solution):
        """Should find solution root from deeply nested directory."""
        deep_dir = temp_solution / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)
        root = find_solution_root(deep_dir)
        assert root == temp_solution

    def test_raises_when_not_found(self, tmp_path):
        """Should raise SolutionNotFoundError when no solution.py exists."""
        with pytest.raises(SolutionNotFoundError):
            find_solution_root(tmp_path)


class TestLoadSolution:
    """Tests for load_solution function."""

    def test_loads_basic_solution(self, temp_solution):
        """Should load a basic solution with default config."""
        solution = load_solution(temp_solution)

        assert solution.root == temp_solution
        assert solution.name == Path(temp_solution).name
        assert solution.default_branch == "dev"
        # compose_project defaults to solution name
        assert solution.docker.compose_project == solution.name

    def test_loads_projects(self, temp_solution_with_projects):
        """Should discover and load all projects."""
        solution = load_solution(temp_solution_with_projects)

        assert len(solution.projects) == 3
        assert "utils" in solution.projects
        assert "libs:parser" in solution.projects
        assert "frontend:ui" in solution.projects

    def test_loads_services(self, temp_solution_with_projects):
        """Should discover and load all services."""
        solution = load_solution(temp_solution_with_projects)

        assert len(solution.services) == 1
        assert "db:primary" in solution.services

    def test_project_properties(self, temp_solution_with_projects):
        """Should correctly parse project properties."""
        from localbox.models.builder import MavenBuilder
        from localbox.models.project import JavaProject

        solution = load_solution(temp_solution_with_projects)

        utils = solution.projects["utils"]
        assert utils.git.url == "git@github.com:example/utils.git"
        assert utils.builder is not None
        assert isinstance(utils.builder, MavenBuilder)
        assert utils.builder.version == "3.9"
        # For JavaProject, image is resolved dynamically using project's JDK
        assert isinstance(utils, JavaProject)
        assert utils.jdk.version == 8
        assert utils.builder.resolve_image_tag(utils.jdk) == "maven:3.9-amazoncorretto-8"

    def test_grouped_project_properties(self, temp_solution_with_projects):
        """Should correctly handle grouped projects."""
        solution = load_solution(temp_solution_with_projects)

        parser = solution.projects["libs:parser"]
        assert parser.group == "libs"
        assert parser.local_name == "parser"
        # depends_on contains Project objects now
        assert len(parser.depends_on) == 1
        assert parser.depends_on[0].name == "utils"

    def test_service_properties(self, temp_solution_with_projects):
        """Should correctly parse service properties."""
        solution = load_solution(temp_solution_with_projects)

        db = solution.services["db:primary"]
        assert db.image.image == "postgres:14"
        assert db.compose.ports == ["5432:5432"]
        assert db.compose.order == 1

    def test_service_explicit_group_in_root_module(self, tmp_path):
        """User-provided group on Service should not be overridden by loader."""
        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig, Service, DockerImage, ComposeConfig

config = SolutionConfig()

primary = Service(
    name="primary",
    group="db",
    image=DockerImage(image="postgres:16"),
    compose=ComposeConfig(ports=["5432:5432"]),
)
""")
        solution = load_solution(tmp_path)

        assert "db:primary" in solution.services
        svc = solution.services["db:primary"]
        assert svc.group == "db"
        assert svc.local_name == "primary"

    def test_project_explicit_group_in_root_module(self, tmp_path):
        """User-provided group on Project should not be overridden by loader."""
        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig, Project

config = SolutionConfig()

utils = Project(
    "utils",
    group="libs",
    repo="git@github.com:example/utils.git",
)
""")
        solution = load_solution(tmp_path)

        assert "libs:utils" in solution.projects
        proj = solution.projects["libs:utils"]
        assert proj.group == "libs"
        assert proj.local_name == "utils"

    def test_service_no_group_in_subpackage_uses_module_group(self, tmp_path):
        """Service without explicit group in sub-package gets module-derived group."""
        import sys

        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig
import services.infra

config = SolutionConfig()
""")
        pkg_dir = tmp_path / "services" / "infra"
        pkg_dir.mkdir(parents=True)
        (tmp_path / "services" / "__init__.py").write_text("")
        (pkg_dir / "__init__.py").write_text("""\
from localbox.models import Service, DockerImage, ComposeConfig

redis = Service(
    name="redis",
    image=DockerImage(image="redis:7"),
    compose=ComposeConfig(ports=["6379:6379"]),
)
""")
        try:
            solution = load_solution(tmp_path)

            assert "infra:redis" in solution.services
            svc = solution.services["infra:redis"]
            assert svc.group == "infra"
            assert svc.local_name == "redis"
        finally:
            # Clean up sub-package modules to avoid leaking into other tests
            for key in list(sys.modules):
                if key.startswith(("services.", "services")):
                    del sys.modules[key]

    def test_custom_config(self, tmp_path):
        """Should apply custom SolutionConfig values."""
        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig
config = SolutionConfig(
    name="mycoolproject",
    default_branch="main",
    compose_project="myproject",
    network="mynet",
)
""")
        solution = load_solution(tmp_path)

        assert solution.name == "mycoolproject"
        assert solution.default_branch == "main"
        assert solution.docker.compose_project == "myproject"
        assert solution.docker.network == "mynet"


class TestDirectories:
    """Tests for directory configuration."""

    def test_default_directories(self, temp_solution):
        """Should set default directory paths."""
        solution = load_solution(temp_solution)

        assert solution.directories.build == temp_solution / ".build"
        assert solution.directories.projects == temp_solution / ".build/projects"
        assert solution.directories.compose == temp_solution / ".build/compose"

    def test_custom_build_dir_relative(self, tmp_path):
        """build_dir relative to solution root."""
        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig
config = SolutionConfig(build_dir="output")
""")
        solution = load_solution(tmp_path)

        assert solution.directories.build == tmp_path / "output"
        assert solution.directories.projects == tmp_path / "output/projects"
        assert solution.directories.compose == tmp_path / "output/compose"

    def test_custom_build_dir_absolute(self, tmp_path):
        """build_dir given as absolute path."""
        abs_build = str(tmp_path / "abs-build")
        (tmp_path / CONFIG_FILE).write_text(f"""\
from localbox.models import SolutionConfig
config = SolutionConfig(build_dir="{abs_build}")
""")
        solution = load_solution(tmp_path)

        assert solution.directories.build == tmp_path / "abs-build"
        assert solution.directories.projects == tmp_path / "abs-build/projects"

    def test_custom_project_dir_relative(self, tmp_path):
        """project_dir relative to build_dir."""
        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig
config = SolutionConfig(build_dir=".build", project_dir="repos")
""")
        solution = load_solution(tmp_path)

        assert solution.directories.build == tmp_path / ".build"
        assert solution.directories.projects == tmp_path / ".build/repos"
        assert solution.directories.compose == tmp_path / ".build/compose"

    def test_custom_project_dir_absolute(self, tmp_path):
        """project_dir given as absolute path."""
        abs_repos = str(tmp_path / "my-repos")
        (tmp_path / CONFIG_FILE).write_text(f"""\
from localbox.models import SolutionConfig
config = SolutionConfig(project_dir="{abs_repos}")
""")
        solution = load_solution(tmp_path)

        assert solution.directories.projects == tmp_path / "my-repos"
        # build and compose are unaffected
        assert solution.directories.build == tmp_path / ".build"
        assert solution.directories.compose == tmp_path / ".build/compose"

    def test_project_dir_independent_of_build_dir(self, tmp_path):
        """Changing build_dir must not affect an absolute project_dir."""
        abs_repos = str(tmp_path / "shared-repos")
        (tmp_path / CONFIG_FILE).write_text(f"""\
from localbox.models import SolutionConfig
config = SolutionConfig(build_dir="custom-build", project_dir="{abs_repos}")
""")
        solution = load_solution(tmp_path)

        assert solution.directories.build == tmp_path / "custom-build"
        assert solution.directories.projects == tmp_path / "shared-repos"

    def test_override_sets_project_dir(self, tmp_path):
        """solution-override.py can set project_dir."""
        abs_repos = str(tmp_path / "dev-repos")
        (tmp_path / CONFIG_FILE).write_text("""\
from localbox.models import SolutionConfig
config = SolutionConfig()
""")
        (tmp_path / "solution-override.py").write_text(
            f'import solution\nsolution.config.project_dir = "{abs_repos}"\n'
        )
        solution = load_solution(tmp_path)

        assert solution.directories.projects == tmp_path / "dev-repos"
        assert solution.directories.build == tmp_path / ".build"


class TestEnvToDict:
    """Tests for _env_to_dict helper."""

    def test_dict_env_passthrough(self):
        """Should return a copy of a dict env unchanged."""
        from localbox.config import _env_to_dict

        env = {"DB_HOST": "localhost", "DB_PASS": None}
        result = _env_to_dict(env)
        assert result == {"DB_HOST": "localhost", "DB_PASS": None}

    def test_class_env_extracts_attributes(self):
        """Should extract class-level attributes from an Env class instance."""
        from localbox.config import _env_to_dict

        class Env:
            DB_HOST: str = "localhost"
            DB_PASS: str | None = None

        result = _env_to_dict(Env())
        assert result == {"DB_HOST": "localhost", "DB_PASS": None}

    def test_class_env_instance_override(self):
        """Instance attributes should override class-level defaults."""
        from localbox.config import _env_to_dict

        class Env:
            DB_PASS: str | None = None

        instance = Env()
        instance.DB_PASS = "secret"
        result = _env_to_dict(instance)
        assert result["DB_PASS"] == "secret"

    def test_class_env_skips_callables(self):
        """Methods on the Env class should not appear in the dict."""
        from localbox.config import _env_to_dict

        class Env:
            DB_HOST: str = "localhost"

            def helper(self):
                pass

        result = _env_to_dict(Env())
        assert "helper" not in result
        assert result["DB_HOST"] == "localhost"

    def test_class_env_preserves_case(self):
        """Field names should be preserved exactly as written (1:1 mapping)."""
        from localbox.config import _env_to_dict

        class Env:
            MaIn_Db_NaMe: str = "value"

        result = _env_to_dict(Env())
        assert "MaIn_Db_NaMe" in result


class TestSolutionOverrideFile:
    """Tests for solution-override.py loading."""

    def test_override_file_mutates_config_env_dict(self, tmp_path):
        """solution-override.py should be able to mutate dict-based config.env."""
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\n"
            'config = SolutionConfig(env={"DB_PASS": None, "DB_HOST": "localhost"})\n'
        )
        (tmp_path / "solution-override.py").write_text(
            'import solution\nsolution.config.env["DB_PASS"] = "secret"\n'
        )

        solution = load_solution(tmp_path)
        assert solution.config.env["DB_PASS"] == "secret"
        assert solution.config.env["DB_HOST"] == "localhost"

    def test_override_file_mutates_class_env(self, tmp_path):
        """solution-override.py should be able to mutate class-based config.env."""
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\n"
            "class Env:\n"
            '    DB_HOST: str = "localhost"\n'
            "    DB_PASS: str = None\n"
            "config = SolutionConfig(env=Env())\n"
        )
        (tmp_path / "solution-override.py").write_text(
            'import solution\nsolution.config.env.DB_PASS = "secret"\n'
        )

        solution = load_solution(tmp_path)
        assert solution.config.env.DB_PASS == "secret"
        assert solution.config.env.DB_HOST == "localhost"

    def test_override_file_mutates_project_branch(self, tmp_path):
        """solution-override.py should be able to mutate project branch."""
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig, Project\n"
            "config = SolutionConfig()\n"
            'myproject = Project("myproject", repo="git@github.com:org/repo.git", branch="dev")\n'
        )
        (tmp_path / "solution-override.py").write_text(
            'import solution\nsolution.config.build_dir = ".my-build"\n'
        )

        solution = load_solution(tmp_path)
        assert solution.directories.build == tmp_path / ".my-build"

    def test_no_override_file_is_fine(self, temp_solution):
        """Loading should succeed when solution-override.py does not exist."""
        solution = load_solution(temp_solution)
        assert solution is not None


class TestProjectPath:
    """Tests for Project.path field."""

    def test_project_path_default_none(self, tmp_path):
        """Project.path should default to None."""
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig, Project\n"
            "config = SolutionConfig()\n"
            'myproject = Project("myproject", repo="git@github.com:org/repo.git")\n'
        )
        solution = load_solution(tmp_path)
        assert solution.projects["myproject"].path is None

    def test_override_sets_project_path(self, tmp_path):
        """solution-override.py should be able to set project.path."""
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig, Project\n"
            "config = SolutionConfig()\n"
            'myproject = Project("myproject", repo="git@github.com:org/repo.git")\n'
        )
        (tmp_path / "solution-override.py").write_text(
            "import solution\n"
            "from solution import myproject\n"
            'myproject.path = "/home/dev/my-checkout"\n'
        )
        solution = load_solution(tmp_path)
        assert solution.projects["myproject"].path == "/home/dev/my-checkout"


class TestServiceImageTag:
    """Tests for Solution.service_image_tag()."""

    def test_without_registry(self, tmp_path):
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\nconfig = SolutionConfig(name='mysol')\n"
        )
        solution = load_solution(tmp_path)
        assert solution.service_image_tag("db/main") == "mysol/service/db/main:latest"

    def test_with_registry(self, tmp_path):
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\n"
            "config = SolutionConfig(name='mysol', registry='registry.io/myteam')\n"
        )
        solution = load_solution(tmp_path)
        assert (
            solution.service_image_tag("db/main")
            == "registry.io/myteam/mysol/service/db/main:latest"
        )

    def test_registry_via_override(self, tmp_path):
        (tmp_path / CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\nconfig = SolutionConfig(name='mysol')\n"
        )
        (tmp_path / "solution-override.py").write_text(
            "import solution\nsolution.config.registry = 'registry.io/team'\n"
        )
        solution = load_solution(tmp_path)
        assert solution.registry == "registry.io/team"
        assert solution.service_image_tag("api") == "registry.io/team/mysol/service/api:latest"


class TestCreateDefaultSolution:
    """Tests for create_default_solution function."""

    def test_creates_valid_python(self):
        """Should create valid Python content that can be compiled."""
        content = create_default_solution()
        # Should be valid Python syntax
        compile(content, "<solution.py>", "exec")

    def test_contains_solution_config(self):
        """Should include SolutionConfig definition."""
        content = create_default_solution()
        assert "SolutionConfig" in content
        assert "config = SolutionConfig[Env](" in content
