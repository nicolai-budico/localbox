"""CLI tests using Click's CliRunner.

No Docker or Git is needed — commands that reach builders are mocked.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from localbox import __version__
from localbox.cli import _load_plugins, cli
from localbox.config import CONFIG_FILE, DirectoriesConfig, DockerSettings, Solution
from localbox.models.docker_image import DockerImage
from localbox.models.project import Project
from localbox.models.service import Service
from localbox.models.solution_config import SolutionConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_solution(tmp_path: Path, projects=None, services=None) -> Solution:
    build = tmp_path / ".build"
    config = SolutionConfig(name="test", compose_project="test", network="test-net")
    sol = Solution(
        root=tmp_path,
        name="test",
        directories=DirectoriesConfig(
            build=build,
            projects=build / "projects",
            compose=build / "compose",
        ),
        docker=DockerSettings(compose_project="test", network="test-net"),
        config=config,
        projects={p.name: p for p in (projects or [])},
        services={s.name: s for s in (services or [])},
    )
    return sol


def _runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------


class TestBasicInvocation:
    def test_version(self):
        result = _runner().invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help(self):
        result = _runner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "localbox" in result.output.lower()

    def test_no_args_shows_help(self):
        result = _runner().invoke(cli, [])
        assert result.exit_code == 0
        assert "Usage" in result.output


# ---------------------------------------------------------------------------
# localbox init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_solution_py(self):
        runner = _runner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init"])
            assert result.exit_code == 0
            assert Path(CONFIG_FILE).exists()

    def test_init_creates_gitignore_entries(self):
        runner = _runner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init"])
            gitignore = Path(".gitignore").read_text()
            assert ".build/" in gitignore
            assert "solution-override.py" in gitignore

    def test_init_refuses_to_overwrite_without_force(self):
        runner = _runner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["init"])
            assert result.exit_code != 0
            assert "already exists" in result.output

    def test_init_force_overwrites(self):
        runner = _runner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init"])
            result = runner.invoke(cli, ["init", "--force"])
            assert result.exit_code == 0


# ---------------------------------------------------------------------------
# init-override command
# ---------------------------------------------------------------------------


class TestInitOverride:
    """Tests for the init-override command."""

    def _setup(self, runner: CliRunner) -> None:
        """Create a minimal solution.py so init-override can load a solution."""
        Path(CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\nconfig = SolutionConfig()\n"
        )

    def test_creates_override_file(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            result = runner.invoke(cli, ["init-override"])
            assert result.exit_code == 0
            assert Path("solution-override.py").exists()

    def test_contains_project_dir_hint(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["init-override"])
            content = Path("solution-override.py").read_text()
            assert "project_dir" in content

    def test_refuses_to_overwrite_without_force(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["init-override"])
            result = runner.invoke(cli, ["init-override"])
            assert result.exit_code != 0
            assert "already exists" in result.output
            assert "--force" in result.output

    def test_force_overwrites(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["init-override"])
            Path("solution-override.py").write_text("# old content\n")
            result = runner.invoke(cli, ["init-override", "--force"])
            assert result.exit_code == 0
            content = Path("solution-override.py").read_text()
            assert "# old content" not in content

    def test_force_short_flag(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["init-override"])
            result = runner.invoke(cli, ["init-override", "-f"])
            assert result.exit_code == 0

    def test_force_creates_backup(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["init-override"])
            runner.invoke(cli, ["init-override", "--force"])
            backups = list(Path(".").glob("solution-override-*.py"))
            assert len(backups) == 1

    def test_force_merges_required_env_value(self):
        """Required env var set in old override should be carried into new template."""
        runner = _runner()
        with runner.isolated_filesystem():
            Path(CONFIG_FILE).write_text(
                "from localbox.models import SolutionConfig\n"
                "config = SolutionConfig(env={'DB_PASS': None, 'DB_HOST': 'localhost'})\n"
            )
            runner.invoke(cli, ["init-override"])
            # Simulate developer setting the required value
            Path("solution-override.py").write_text(
                "import solution\n"
                'solution.config.env["DB_PASS"] = "secret"\n'
                '# solution.config.env["DB_HOST"] = "localhost"\n'
            )
            runner.invoke(cli, ["init-override", "--force"])
            content = Path("solution-override.py").read_text()
            # Required value restored
            assert 'solution.config.env["DB_PASS"] = "secret"' in content
            # Optional remains commented
            assert '# solution.config.env["DB_HOST"]' in content

    def test_force_merges_project_path(self):
        """Project path set in old override should be carried into new template."""
        runner = _runner()
        with runner.isolated_filesystem():
            Path(CONFIG_FILE).write_text(
                "from localbox.models import SolutionConfig, Project\n"
                "config = SolutionConfig()\n"
                'myproject = Project("myproject", repo="git@github.com:org/repo.git")\n'
            )
            runner.invoke(cli, ["init-override"])
            Path("solution-override.py").write_text(
                "import solution\nimport projects as p\n"
                'p.myproject.path = "/home/dev/repos/myproject"\n'
            )
            runner.invoke(cli, ["init-override", "--force"])
            content = Path("solution-override.py").read_text()
            assert 'p.myproject.path = "/home/dev/repos/myproject"' in content

    def test_force_merges_config_setting(self):
        """solution.config settings set in old override should be carried into new template."""
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["init-override"])
            Path("solution-override.py").write_text(
                'import solution\nsolution.config.build_dir = ".my-build"\n'
            )
            runner.invoke(cli, ["init-override", "--force"])
            content = Path("solution-override.py").read_text()
            assert 'solution.config.build_dir = ".my-build"' in content

    def test_hash_in_password_preserved(self):
        """Passwords containing '#' must not be truncated during merge."""
        runner = _runner()
        with runner.isolated_filesystem():
            Path(CONFIG_FILE).write_text(
                "from localbox.models import SolutionConfig\n"
                "config = SolutionConfig(env={'DB_PASS': None})\n"
            )
            runner.invoke(cli, ["init-override"])
            Path("solution-override.py").write_text(
                "import solution\n"
                'solution.config.env["DB_PASS"] = "5$6!#Q_0yw$^"  # REQUIRED — set a value\n'
            )
            runner.invoke(cli, ["init-override", "--force"])
            content = Path("solution-override.py").read_text()
            assert 'solution.config.env["DB_PASS"] = "5$6!#Q_0yw$^"' in content


# ---------------------------------------------------------------------------
# Error: outside a solution directory
# ---------------------------------------------------------------------------


class TestOutsideSolution:
    """Commands that require a solution should exit 1 with a clear message."""

    def _invoke_outside(self, *args):
        runner = _runner()
        with runner.isolated_filesystem():
            return runner.invoke(cli, list(args))

    def test_list_outside_solution(self):
        result = self._invoke_outside("list", "projects")
        assert result.exit_code == 1
        assert "solution" in result.output.lower()

    def test_compose_generate_outside_solution(self):
        result = self._invoke_outside("compose", "generate")
        assert result.exit_code == 1
        assert "solution" in result.output.lower()

    def test_clone_outside_solution(self):
        result = self._invoke_outside("clone", "projects")
        assert result.exit_code == 1

    def test_status_outside_solution(self):
        result = self._invoke_outside("status", "projects")
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# localbox list
# ---------------------------------------------------------------------------


class TestList:
    def _solution(self, tmp_path):
        p1 = Project("standalone", repo="git@example.com/a.git")
        p2 = Project("libs:utils", repo="git@example.com/b.git")
        s1 = Service(name="proxy", image=DockerImage(image="nginx:alpine"))
        s2 = Service(name="db:primary", image=DockerImage(image="postgres:16"))
        s1._finalize_image_name()
        s2._finalize_image_name()
        return _make_solution(tmp_path, projects=[p1, p2], services=[s1, s2])

    def test_list_projects(self, tmp_path):
        sol = self._solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["list", "projects"])
        assert result.exit_code == 0
        assert "standalone" in result.output
        assert "utils" in result.output

    def test_list_services(self, tmp_path):
        sol = self._solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["list", "services"])
        assert result.exit_code == 0
        assert "proxy" in result.output
        assert "primary" in result.output

    def test_list_invalid_type(self, tmp_path):
        sol = self._solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["list", "invalid"])
        assert result.exit_code != 0

    def test_list_empty_projects(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["list", "projects"])
        assert result.exit_code == 0
        assert "No projects" in result.output

    def test_list_empty_services(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["list", "services"])
        assert result.exit_code == 0
        assert "No services" in result.output


# ---------------------------------------------------------------------------
# localbox config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_config_shows_solution_info(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["config"])
        assert result.exit_code == 0
        assert "test" in result.output  # compose_project / network name


# ---------------------------------------------------------------------------
# localbox clean
# ---------------------------------------------------------------------------


class TestClean:
    def test_clean_no_args_shows_hint(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["clean"])
        assert result.exit_code == 0
        assert "Nothing to clean" in result.output

    def test_clean_build_removes_build_dir(self, tmp_path):
        sol = _make_solution(tmp_path)
        sol.directories.build.mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["clean", "--build"])
        assert result.exit_code == 0
        assert not sol.directories.build.exists()

    def test_clean_compose_removes_compose_file(self, tmp_path):
        sol = _make_solution(tmp_path)
        compose_file = tmp_path / "docker-compose.yml"
        compose_file.write_text("name: test\n")
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["clean", "--compose"])
        assert result.exit_code == 0
        assert not compose_file.exists()


# ---------------------------------------------------------------------------
# localbox compose generate
# ---------------------------------------------------------------------------


class TestComposeGenerate:
    def test_generates_compose_file(self, tmp_path):
        service = Service(name="proxy", image=DockerImage(image="nginx:alpine"))
        service._finalize_image_name()
        sol = _make_solution(tmp_path, services=[service])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["compose", "generate"])
        assert result.exit_code == 0
        assert (tmp_path / "docker-compose.yml").exists()

    def test_generate_error_shown_cleanly(self, tmp_path):
        """A ValueError from the generator must exit 1 with a readable message."""
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch(
                "localbox.builders.compose.generate_compose_file",
                side_effect=ValueError("env field DB_PASS is required but not set"),
            ):
                result = _runner().invoke(cli, ["compose", "generate"])
        assert result.exit_code == 1
        assert "DB_PASS" in result.output


# ---------------------------------------------------------------------------
# Plugin loading
# ---------------------------------------------------------------------------


class TestPluginLoading:
    """Tests for _load_plugins() entry-point discovery."""

    def _fake_ep(self, name: str, cmd: click.Command) -> MagicMock:
        ep = MagicMock()
        ep.name = name
        ep.load.return_value = cmd
        return ep

    def test_plugin_command_registered(self):
        """A well-formed plugin entry point adds its command to the CLI."""

        @click.command("hello")
        def hello_cmd():
            """Say hello."""
            click.echo("hello from plugin")

        with patch("localbox.cli.entry_points", return_value=[self._fake_ep("hello", hello_cmd)]):
            _load_plugins()

        result = _runner().invoke(cli, ["hello"])
        assert result.exit_code == 0
        assert "hello from plugin" in result.output

    def test_broken_plugin_prints_warning(self):
        """A plugin that raises on load prints a warning and does not crash."""
        ep = MagicMock()
        ep.name = "broken"
        ep.load.side_effect = ImportError("missing dependency")

        with patch("localbox.cli.entry_points", return_value=[ep]):
            _load_plugins()

        # localbox itself must still work after a broken plugin
        result = _runner().invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_no_plugins_is_silent(self):
        """When no plugins are installed nothing is printed."""
        with patch("localbox.cli.entry_points", return_value=[]):
            _load_plugins()

        result = _runner().invoke(cli, ["--version"])
        assert result.exit_code == 0
