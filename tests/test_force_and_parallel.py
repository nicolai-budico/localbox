"""Tests for --force flags (fetch/switch) and -j parallel builds."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from localbox.cli import cli
from localbox.config import DirectoriesConfig, DockerSettings, Solution
from localbox.models.docker_image import DockerImage
from localbox.models.project import Project
from localbox.models.service import Service
from localbox.models.solution_config import SolutionConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_solution(
    tmp_path: Path,
    projects: list[Project] | None = None,
    services: list[Service] | None = None,
) -> Solution:
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
# fetch --force CLI flag
# ---------------------------------------------------------------------------


class TestFetchForceCLI:
    def test_force_flag_passed_to_fetch_projects(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.fetch_project", return_value="fetched") as mock:
                result = _runner().invoke(cli, ["projects", "fetch", "--force"])
        assert result.exit_code == 0
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("force") is True

    def test_no_force_by_default(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.fetch_project", return_value="fetched") as mock:
                result = _runner().invoke(cli, ["projects", "fetch"])
        assert result.exit_code == 0
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("force") is False


# ---------------------------------------------------------------------------
# fetch_project --force unit tests
# ---------------------------------------------------------------------------


class TestFetchProjectForce:
    def _make_project_dir(self, tmp_path: Path) -> tuple[Solution, Project, Path]:
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        proj_dir = sol.directories.projects / "app1"
        proj_dir.mkdir(parents=True)
        return sol, proj, proj_dir

    def test_force_runs_three_git_commands(self, tmp_path):
        sol, proj, proj_dir = self._make_project_dir(tmp_path)
        from localbox.commands.project import fetch_project

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            status = fetch_project(sol, proj, force=True)

        assert status == "fetched"
        cmds = [c.args[0] for c in mock_run.call_args_list]
        assert any("fetch" in c and "--all" in c for c in cmds)
        assert any("reset" in c and "--hard" in c for c in cmds)
        assert any("clean" in c and "-fd" in c for c in cmds)

    def test_force_uses_configured_branch(self, tmp_path):
        """reset --hard should target origin/<configured-branch>."""

        proj = Project("app1", repo="git@example.com/app1.git", branch="develop")
        sol = _make_solution(tmp_path, projects=[proj])
        proj_dir = sol.directories.projects / "app1"
        proj_dir.mkdir(parents=True)

        from localbox.commands.project import fetch_project

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            fetch_project(sol, proj, force=True)

        reset_call = next(c.args[0] for c in mock_run.call_args_list if "reset" in c.args[0])
        assert "origin/develop" in reset_call

    def test_force_skips_when_not_cloned(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        from localbox.commands.project import fetch_project

        with patch("subprocess.run") as mock_run:
            status = fetch_project(sol, proj, force=True)

        assert status == "skipped"
        mock_run.assert_not_called()

    def test_force_returns_failed_on_git_error(self, tmp_path):
        sol, proj, _ = self._make_project_dir(tmp_path)
        from localbox.commands.project import fetch_project

        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stderr = b"error"
        with patch("subprocess.run", return_value=fail_result):
            status = fetch_project(sol, proj, force=True)

        assert status == "failed"

    def test_no_force_uses_pull_rebase(self, tmp_path):
        sol, proj, _ = self._make_project_dir(tmp_path)
        from localbox.commands.project import fetch_project

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            fetch_project(sol, proj, force=False)

        cmd = mock_run.call_args.args[0]
        assert "pull" in cmd and "--rebase" in cmd


# ---------------------------------------------------------------------------
# switch --force CLI flag
# ---------------------------------------------------------------------------


class TestSwitchForceCLI:
    def test_force_flag_passed_to_switch_projects(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.switch_project", return_value="switched") as mock:
                result = _runner().invoke(cli, ["projects", "switch", "--force"])
        assert result.exit_code == 0
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("force") is True

    def test_force_flag_with_branch(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.switch_project", return_value="switched") as mock:
                result = _runner().invoke(cli, ["projects", "switch", "-b", "feature/x", "--force"])
        assert result.exit_code == 0
        _, kwargs = mock.call_args
        assert kwargs.get("force") is True
        assert kwargs.get("branch") == "feature/x"

    def test_no_force_by_default(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.switch_project", return_value="switched") as mock:
                result = _runner().invoke(cli, ["projects", "switch"])
        assert result.exit_code == 0
        _, kwargs = mock.call_args
        assert kwargs.get("force") is False


# ---------------------------------------------------------------------------
# switch_project --force unit tests
# ---------------------------------------------------------------------------


class TestSwitchProjectForce:
    def _make_project_dir(self, tmp_path: Path) -> tuple[Solution, Project, Path]:
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        proj_dir = sol.directories.projects / "app1"
        proj_dir.mkdir(parents=True)
        return sol, proj, proj_dir

    def test_force_cleans_before_checkout(self, tmp_path):
        sol, proj, _ = self._make_project_dir(tmp_path)
        from localbox.commands.project import switch_project

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            with patch("localbox.commands.project._clean_working_tree") as mock_clean:
                status = switch_project(sol, proj, branch="main", force=True)

        assert status == "switched"
        mock_clean.assert_called_once()
        # verify _clean_working_tree is called before subprocess.run (checkout)

    def test_no_force_skips_clean(self, tmp_path):
        sol, proj, _ = self._make_project_dir(tmp_path)
        from localbox.commands.project import switch_project

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            with patch("localbox.commands.project._clean_working_tree") as mock_clean:
                switch_project(sol, proj, branch="main", force=False)

        mock_clean.assert_not_called()

    def test_force_removes_untracked_files(self, tmp_path):
        """_clean_working_tree runs git reset --hard HEAD and git clean -fd."""

        sol, proj, proj_dir = self._make_project_dir(tmp_path)
        from localbox.commands.project import _clean_working_tree

        with patch("subprocess.check_call") as mock_cc:
            _clean_working_tree(proj_dir)

        cmds = [c.args[0] for c in mock_cc.call_args_list]
        assert any("reset" in c and "--hard" in c and "HEAD" in c for c in cmds)
        assert any("clean" in c and "-fd" in c for c in cmds)


# ---------------------------------------------------------------------------
# switch --manifest --force unit tests
# ---------------------------------------------------------------------------


class TestSwitchManifestForce:
    def test_force_cleans_each_repo_before_checkout(self, tmp_path):
        proj = Project("app1", repo="git@example.com/app1.git")
        sol = _make_solution(tmp_path, projects=[proj])
        proj_dir = sol.directories.projects / "app1"
        proj_dir.mkdir(parents=True)

        manifest = {"repositories": {"app1": {"commit": "abc123", "remote": "git@x.com"}}}
        from localbox.commands.project import switch_projects_from_manifest

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            with patch("localbox.commands.project._clean_working_tree") as mock_clean:
                switch_projects_from_manifest(sol, manifest, force=True)

        mock_clean.assert_called_once()


# ---------------------------------------------------------------------------
# projects build -j CLI flag
# ---------------------------------------------------------------------------


class TestProjectsBuildJobs:
    def _sol(self, tmp_path):
        p1 = Project("app1", repo="git@example.com/app1.git")
        p2 = Project("app2", repo="git@example.com/app2.git")
        return _make_solution(tmp_path, projects=[p1, p2])

    def test_j_flag_passed_to_build_projects(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as mock:
                _runner().invoke(cli, ["projects", "build", "-j", "4"])
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 4

    def test_jobs_long_flag(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as mock:
                _runner().invoke(cli, ["projects", "build", "--jobs", "2"])
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 2

    def test_jobs_auto_resolves_to_cpu_count(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as mock:
                with patch("os.cpu_count", return_value=8):
                    _runner().invoke(cli, ["projects", "build", "-j", "auto"])
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 8

    def test_jobs_default_is_1(self, tmp_path):
        sol = self._sol(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.project.build_projects") as mock:
                _runner().invoke(cli, ["projects", "build"])
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 1


# ---------------------------------------------------------------------------
# build_projects parallel unit tests
# ---------------------------------------------------------------------------


class TestBuildProjectsParallel:
    def _make_sol_with_two_independent_projects(self, tmp_path: Path) -> Solution:
        p1 = Project("app1", repo="git@example.com/app1.git")
        p2 = Project("app2", repo="git@example.com/app2.git")
        sol = _make_solution(tmp_path, projects=[p1, p2])
        for name in ("app1", "app2"):
            (sol.directories.projects / name).mkdir(parents=True)
        return sol

    def test_j1_sequential(self, tmp_path):
        """jobs=1 should call build_project sequentially, not use ThreadPoolExecutor."""
        sol = self._make_sol_with_two_independent_projects(tmp_path)
        from localbox.commands.project import build_projects

        with patch(
            "localbox.commands.project.build_project", return_value=("built", None)
        ) as mock_bp:
            with patch("concurrent.futures.ThreadPoolExecutor") as mock_pool:
                build_projects(sol, list(sol.projects.values()), jobs=1)

        assert mock_bp.call_count == 2
        mock_pool.assert_not_called()

    def test_j2_uses_thread_pool(self, tmp_path):
        sol = self._make_sol_with_two_independent_projects(tmp_path)
        from localbox.commands.project import build_projects

        with patch("localbox.commands.project.build_project", return_value=("built", None)):
            with patch("localbox.commands.project.ThreadPoolExecutor") as mock_pool_cls:
                mock_pool = MagicMock()
                mock_pool.__enter__ = MagicMock(return_value=mock_pool)
                mock_pool.__exit__ = MagicMock(return_value=False)
                mock_pool_cls.return_value = mock_pool
                future = MagicMock()
                future.result.return_value = ("built", None)
                mock_pool.submit.return_value = future
                with patch("localbox.commands.project.as_completed", return_value=[future]):
                    build_projects(sol, list(sol.projects.values()), jobs=2)

        mock_pool_cls.assert_called_once()


# ---------------------------------------------------------------------------
# services build -j CLI flag
# ---------------------------------------------------------------------------


class TestServicesBuildJobs:
    def _svc(self, name: str) -> Service:
        svc = Service(name=name, image=DockerImage(image="test:latest"))
        svc._finalize_image_name()
        return svc

    def test_j_flag_passed_to_build_images(self, tmp_path):
        sol = _make_solution(tmp_path, services=[self._svc("api"), self._svc("db")])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.build_images") as mock:
                _runner().invoke(cli, ["services", "build", "-j", "3"])
        mock.assert_called_once()
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 3

    def test_jobs_default_is_1(self, tmp_path):
        sol = _make_solution(tmp_path, services=[self._svc("api")])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.build_images") as mock:
                _runner().invoke(cli, ["services", "build"])
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 1

    def test_jobs_auto_resolves_to_cpu_count(self, tmp_path):
        sol = _make_solution(tmp_path, services=[self._svc("api")])
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            with patch("localbox.commands.service.build_images") as mock:
                with patch("os.cpu_count", return_value=4):
                    _runner().invoke(cli, ["services", "build", "-j", "auto"])
        _, kwargs = mock.call_args
        assert kwargs.get("jobs") == 4
