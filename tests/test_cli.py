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

    def test_top_level_help_lists_domains(self):
        result = _runner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        for domain in ("projects", "services", "compose", "override", "solution"):
            assert domain in result.output

    def test_legacy_top_level_verb_rejected(self):
        """Legacy `localbox clone projects:api` must fail at the top level."""
        result = _runner().invoke(cli, ["clone", "projects:api"])
        assert result.exit_code != 0
        assert "No such command" in result.output

    def test_unknown_domain_rejected(self):
        result = _runner().invoke(cli, ["widgets", "list"])
        assert result.exit_code != 0
        assert "No such command" in result.output


# ---------------------------------------------------------------------------
# localbox solution init
# ---------------------------------------------------------------------------


class TestSolutionInit:
    def test_init_creates_solution_py(self):
        runner = _runner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["solution", "init"])
            assert result.exit_code == 0
            assert Path(CONFIG_FILE).exists()

    def test_init_creates_gitignore_entries(self):
        runner = _runner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["solution", "init"])
            gitignore = Path(".gitignore").read_text()
            assert ".build/" in gitignore
            assert "solution-override.py" in gitignore

    def test_init_refuses_to_overwrite_without_force(self):
        runner = _runner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["solution", "init"])
            result = runner.invoke(cli, ["solution", "init"])
            assert result.exit_code != 0
            assert "already exists" in result.output

    def test_init_force_overwrites(self):
        runner = _runner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["solution", "init"])
            result = runner.invoke(cli, ["solution", "init", "--force"])
            assert result.exit_code == 0


# ---------------------------------------------------------------------------
# localbox override init
# ---------------------------------------------------------------------------


class TestOverrideInit:
    """Tests for the override init command."""

    def _setup(self, runner: CliRunner) -> None:
        """Create a minimal solution.py so override init can load a solution."""
        Path(CONFIG_FILE).write_text(
            "from localbox.models import SolutionConfig\nconfig = SolutionConfig()\n"
        )

    def test_creates_override_file(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            result = runner.invoke(cli, ["override", "init"])
            assert result.exit_code == 0
            assert Path("solution-override.py").exists()

    def test_contains_project_dir_hint(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["override", "init"])
            content = Path("solution-override.py").read_text()
            assert "project_dir" in content

    def test_refuses_to_overwrite_without_force(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["override", "init"])
            result = runner.invoke(cli, ["override", "init"])
            assert result.exit_code != 0
            assert "already exists" in result.output
            assert "--force" in result.output

    def test_force_overwrites(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["override", "init"])
            Path("solution-override.py").write_text("# old content\n")
            result = runner.invoke(cli, ["override", "init", "--force"])
            assert result.exit_code == 0
            content = Path("solution-override.py").read_text()
            assert "# old content" not in content

    def test_force_short_flag(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["override", "init"])
            result = runner.invoke(cli, ["override", "init", "-f"])
            assert result.exit_code == 0

    def test_force_creates_backup(self):
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["override", "init"])
            runner.invoke(cli, ["override", "init", "--force"])
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
            runner.invoke(cli, ["override", "init"])
            # Simulate developer setting the required value
            Path("solution-override.py").write_text(
                "import solution\n"
                'solution.config.env["DB_PASS"] = "secret"\n'
                '# solution.config.env["DB_HOST"] = "localhost"\n'
            )
            runner.invoke(cli, ["override", "init", "--force"])
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
            runner.invoke(cli, ["override", "init"])
            Path("solution-override.py").write_text(
                "import solution\nimport projects as p\n"
                'p.myproject.path = "/home/dev/repos/myproject"\n'
            )
            runner.invoke(cli, ["override", "init", "--force"])
            content = Path("solution-override.py").read_text()
            assert 'p.myproject.path = "/home/dev/repos/myproject"' in content

    def test_force_merges_config_setting(self):
        """solution.config settings set in old override should be carried into new template."""
        runner = _runner()
        with runner.isolated_filesystem():
            self._setup(runner)
            runner.invoke(cli, ["override", "init"])
            Path("solution-override.py").write_text(
                'import solution\nsolution.config.build_dir = ".my-build"\n'
            )
            runner.invoke(cli, ["override", "init", "--force"])
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
            runner.invoke(cli, ["override", "init"])
            Path("solution-override.py").write_text(
                "import solution\n"
                'solution.config.env["DB_PASS"] = "5$6!#Q_0yw$^"  # REQUIRED — set a value\n'
            )
            runner.invoke(cli, ["override", "init", "--force"])
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

    def test_projects_list_outside_solution(self):
        result = self._invoke_outside("projects", "list")
        assert result.exit_code == 1
        assert "solution" in result.output.lower()

    def test_compose_generate_outside_solution(self):
        result = self._invoke_outside("compose", "generate")
        assert result.exit_code == 1
        assert "solution" in result.output.lower()

    def test_projects_clone_outside_solution(self):
        result = self._invoke_outside("projects", "clone")
        assert result.exit_code == 1

    def test_projects_status_outside_solution(self):
        result = self._invoke_outside("projects", "status")
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# localbox projects list / services list
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
            result = _runner().invoke(cli, ["projects", "list"])
        assert result.exit_code == 0
        assert "standalone" in result.output
        assert "utils" in result.output

    def test_list_services(self, tmp_path):
        sol = self._solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["services", "list"])
        assert result.exit_code == 0
        assert "proxy" in result.output
        assert "primary" in result.output

    def test_list_empty_projects(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["projects", "list"])
        assert result.exit_code == 0
        assert "No projects" in result.output

    def test_list_empty_services(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["services", "list"])
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
# localbox projects clean
# ---------------------------------------------------------------------------


class TestProjectsClean:
    def test_help(self, tmp_path):
        """projects clean help lists its usage."""
        result = _runner().invoke(cli, ["projects", "clean", "--help"])
        assert result.exit_code == 0
        assert "clean" in result.output.lower()

    def test_calls_run_builder_clean(self, tmp_path):
        """projects clean invokes run_builder_clean for each cloned project."""
        proj = Project("myapp", repo="git@example.com/myapp.git")
        sol = _make_solution(tmp_path, projects=[proj])
        source_dir = sol.directories.projects / "myapp"
        source_dir.mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch(
                "localbox.builders.build.run_builder_clean", return_value=True
            ) as mock_clean:
                result = _runner().invoke(cli, ["projects", "clean"])
        assert result.exit_code == 0
        assert mock_clean.called

    def test_skips_uncloned(self, tmp_path):
        """projects clean prints skip when source_dir does not exist."""
        proj = Project("myapp", repo="git@example.com/myapp.git")
        sol = _make_solution(tmp_path, projects=[proj])
        # Do NOT create source_dir
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["projects", "clean"])
        assert result.exit_code == 0
        assert "Skip" in result.output
        assert "not cloned" in result.output

    def test_summary_shown_for_multiple(self, tmp_path):
        """projects clean shows summary table when multiple projects are processed."""
        proj1 = Project("app1", repo="git@example.com/app1.git")
        proj2 = Project("app2", repo="git@example.com/app2.git")
        sol = _make_solution(tmp_path, projects=[proj1, proj2])
        for p in [proj1, proj2]:
            (sol.directories.projects / p.name).mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.builders.build.run_builder_clean", return_value=True):
                result = _runner().invoke(cli, ["projects", "clean"])
        assert result.exit_code == 0
        assert "Clean Summary" in result.output

    def test_summary_shown_on_failure(self, tmp_path):
        """projects clean shows summary and exits 1 on failure."""
        proj = Project("myapp", repo="git@example.com/myapp.git")
        sol = _make_solution(tmp_path, projects=[proj])
        (sol.directories.projects / "myapp").mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.builders.build.run_builder_clean", return_value=False):
                result = _runner().invoke(cli, ["projects", "clean"])
        assert result.exit_code == 1
        assert "Clean Summary" in result.output
        assert "Failed" in result.output


# ---------------------------------------------------------------------------
# Summary table tests — clone / fetch / switch / build services
# ---------------------------------------------------------------------------


class TestCloneProjectsSummary:
    def _sol(self, tmp_path):
        p1 = Project("app1", repo="git@example.com/app1.git")
        p2 = Project("app2", repo="git@example.com/app2.git")
        return _make_solution(tmp_path, projects=[p1, p2])

    def test_no_summary_for_single_success(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.clone_project", return_value="cloned"):
                result = _runner().invoke(cli, ["projects", "clone"])
        assert result.exit_code == 0
        assert "Clone Summary" not in result.output

    def test_summary_shown_for_multiple(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.clone_project", side_effect=["cloned", "cloned"]):
                result = _runner().invoke(cli, ["projects", "clone"])
        assert result.exit_code == 0
        assert "Clone Summary" in result.output

    def test_summary_shown_on_single_failure(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.clone_project", return_value="failed"):
                result = _runner().invoke(cli, ["projects", "clone"])
        assert result.exit_code == 0
        assert "Clone Summary" in result.output


class TestFetchProjectsSummary:
    def _sol(self, tmp_path):
        p1 = Project("app1", repo="git@example.com/app1.git")
        p2 = Project("app2", repo="git@example.com/app2.git")
        return _make_solution(tmp_path, projects=[p1, p2])

    def test_no_summary_for_single_success(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.fetch_project", return_value="fetched"):
                result = _runner().invoke(cli, ["projects", "fetch"])
        assert result.exit_code == 0
        assert "Fetch Summary" not in result.output

    def test_summary_shown_for_multiple(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch(
                "localbox.commands.project.fetch_project", side_effect=["fetched", "fetched"]
            ):
                result = _runner().invoke(cli, ["projects", "fetch"])
        assert result.exit_code == 0
        assert "Fetch Summary" in result.output

    def test_summary_shown_on_single_failure(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.fetch_project", return_value="failed"):
                result = _runner().invoke(cli, ["projects", "fetch"])
        assert result.exit_code == 0
        assert "Fetch Summary" in result.output


class TestSwitchProjectsSummary:
    def _sol(self, tmp_path):
        p1 = Project("app1", repo="git@example.com/app1.git")
        p2 = Project("app2", repo="git@example.com/app2.git")
        return _make_solution(tmp_path, projects=[p1, p2])

    def test_no_summary_for_single_success(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.switch_project", return_value="switched"):
                result = _runner().invoke(cli, ["projects", "switch"])
        assert result.exit_code == 0
        assert "Switch Summary" not in result.output

    def test_summary_shown_for_multiple(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch(
                "localbox.commands.project.switch_project", side_effect=["switched", "switched"]
            ):
                result = _runner().invoke(cli, ["projects", "switch"])
        assert result.exit_code == 0
        assert "Switch Summary" in result.output

    def test_summary_shown_on_single_failure(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.switch_project", return_value="failed"):
                result = _runner().invoke(cli, ["projects", "switch"])
        assert result.exit_code == 0
        assert "Switch Summary" in result.output


class TestBuildImagesSummary:
    def _svc(self, name: str) -> Service:
        svc = Service(name=name, image=DockerImage(image="test:latest"))
        svc._finalize_image_name()
        return svc

    def test_no_summary_for_single_success(self, tmp_path):
        svc = self._svc("proxy")
        sol = _make_solution(tmp_path, services=[svc])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.do_build", return_value=True):
                result = _runner().invoke(cli, ["services", "build"])
        assert result.exit_code == 0
        assert "Image Build" not in result.output

    def test_summary_shown_for_multiple(self, tmp_path):
        svc1 = self._svc("proxy")
        svc2 = self._svc("db")
        sol = _make_solution(tmp_path, services=[svc1, svc2])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.do_build", side_effect=[True, True]):
                result = _runner().invoke(cli, ["services", "build"])
        assert result.exit_code == 0
        assert "Image Build" in result.output

    def test_summary_shown_on_failure(self, tmp_path):
        svc1 = self._svc("proxy")
        svc2 = self._svc("db")
        sol = _make_solution(tmp_path, services=[svc1, svc2])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.do_build", side_effect=[True, False]):
                result = _runner().invoke(cli, ["services", "build"])
        assert result.exit_code == 0
        assert "Image Build" in result.output
        assert "Failed" in result.output


# ---------------------------------------------------------------------------
# Build domain routing — targets resolve within their own domain
# ---------------------------------------------------------------------------


class TestBuildDomainRouting:
    def test_projects_build_no_targets_builds_all(self, tmp_path):
        """`projects build` with no args iterates every project."""
        p1 = Project("app1", repo="git@example.com/app1.git")
        p2 = Project("app2", repo="git@example.com/app2.git")
        sol = _make_solution(tmp_path, projects=[p1, p2])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as mock_build:
                result = _runner().invoke(cli, ["projects", "build"])
        assert result.exit_code == 0
        args, _kwargs = mock_build.call_args
        resolved = args[1]
        assert {p.name for p in resolved} == {"app1", "app2"}

    def test_projects_build_multiple_short_form_targets(self, tmp_path):
        """Multiple short-form tokens resolve within the projects domain.

        Covers: `projects build be:api fe:api workers`.
        """
        be_api = Project("be:api", repo="git@example.com/be-api.git")
        fe_api = Project("fe:api", repo="git@example.com/fe-api.git")
        w1 = Project("workers:a", repo="git@example.com/wa.git")
        w2 = Project("workers:b", repo="git@example.com/wb.git")
        sol = _make_solution(tmp_path, projects=[be_api, fe_api, w1, w2])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as mock_build:
                result = _runner().invoke(cli, ["projects", "build", "be:api", "fe:api", "workers"])
        assert result.exit_code == 0
        args, _kwargs = mock_build.call_args
        resolved = {p.name for p in args[1]}
        assert resolved == {"be:api", "fe:api", "workers:a", "workers:b"}

    def test_projects_build_rejects_legacy_domain_prefix(self, tmp_path):
        """`projects build projects:api` must be rejected as a domain-prefixed token."""
        p1 = Project("api", repo="git@example.com/api.git")
        sol = _make_solution(tmp_path, projects=[p1])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["projects", "build", "projects:api"])
        assert result.exit_code == 1
        assert "projects" in result.output.lower() or "domain-prefixed" in result.output.lower()

    def test_projects_build_does_not_fall_through_to_services(self, tmp_path):
        """`projects build db` in a solution where db is only a service group must fail."""
        svc = Service(name="db:primary", image=DockerImage(image="postgres:16"))
        svc._finalize_image_name()
        sol = _make_solution(tmp_path, services=[svc])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.build_images") as svc_build:
                result = _runner().invoke(cli, ["projects", "build", "db"])
        assert result.exit_code == 1
        assert not svc_build.called

    def test_services_build_does_not_fall_through_to_projects(self, tmp_path):
        """`services build api` in a solution where api is only a project must fail."""
        proj = Project("api", repo="git@example.com/api.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as proj_build:
                result = _runner().invoke(cli, ["services", "build", "api"])
        assert result.exit_code == 1
        assert not proj_build.called


# ---------------------------------------------------------------------------
# Top-level utility commands stay top-level
# ---------------------------------------------------------------------------


class TestTopLevelUtilities:
    """Lock in that utility commands do NOT move under a domain."""

    def test_completion_bash(self):
        result = _runner().invoke(cli, ["completion", "bash"])
        assert result.exit_code == 0
        assert "_localbox_completion" in result.output or "localbox" in result.output

    def test_doctor_help(self):
        """`doctor --help` is reachable at the top level without a solution."""
        result = _runner().invoke(cli, ["doctor", "--help"])
        assert result.exit_code == 0

    def test_prune_is_top_level_group(self):
        result = _runner().invoke(cli, ["prune", "--help"])
        assert result.exit_code == 0
        for sub in ("caches", "builders", "images", "all"):
            assert sub in result.output

    def test_purge_is_top_level(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["purge"])
        assert result.exit_code == 0

    def test_config_is_top_level(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["config"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# localbox prune
# ---------------------------------------------------------------------------


class TestPrune:
    def test_prune_caches_all(self, tmp_path):
        """prune caches removes all discovered CacheVolume directories."""
        from localbox.models.builder import maven

        proj = Project("myapp", repo="git@example.com/myapp.git")
        proj.builder = maven()
        sol = _make_solution(tmp_path, projects=[proj])
        maven_cache = sol.directories.build / "maven"
        maven_cache.mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["prune", "caches"])
        assert result.exit_code == 0
        assert not maven_cache.exists()
        assert "Removed" in result.output

    def test_prune_caches_named(self, tmp_path):
        """prune caches <name> removes only specified cache directory."""
        from localbox.models.builder import gradle

        proj = Project("myapp", repo="git@example.com/myapp.git")
        proj.builder = gradle()
        sol = _make_solution(tmp_path, projects=[proj])
        gradle_cache = sol.directories.build / "gradle"
        maven_cache = sol.directories.build / "maven"
        gradle_cache.mkdir(parents=True)
        maven_cache.mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["prune", "caches", "gradle"])
        assert result.exit_code == 0
        assert not gradle_cache.exists()
        assert maven_cache.exists()  # not removed

    def test_prune_caches_missing_skipped(self, tmp_path):
        """prune caches prints skip when cache dir does not exist."""
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["prune", "caches", "nonexistent"])
        assert result.exit_code == 0
        assert "Skip" in result.output

    def test_prune_builders_no_images(self, tmp_path):
        """prune builders prints 'No builder images' when docker returns empty."""

        sol = _make_solution(tmp_path)
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("subprocess.run", return_value=mock_result):
                result = _runner().invoke(cli, ["prune", "builders"])
        assert result.exit_code == 0
        assert "No builder images" in result.output

    def test_prune_images_no_images(self, tmp_path):
        """prune images prints 'No service images' when docker returns empty."""
        sol = _make_solution(tmp_path)
        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("subprocess.run", return_value=mock_result):
                result = _runner().invoke(cli, ["prune", "images"])
        assert result.exit_code == 0
        assert "No service images" in result.output


# ---------------------------------------------------------------------------
# localbox purge
# ---------------------------------------------------------------------------


class TestPurge:
    def test_purge_removes_build_dir(self, tmp_path):
        """purge removes the entire .build/ directory."""
        sol = _make_solution(tmp_path)
        sol.directories.build.mkdir(parents=True)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["purge"])
        assert result.exit_code == 0
        assert not sol.directories.build.exists()
        assert "Removed" in result.output

    def test_purge_skips_if_missing(self, tmp_path):
        """purge prints skip when .build/ does not exist."""
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["purge"])
        assert result.exit_code == 0
        assert "Skip" in result.output


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
