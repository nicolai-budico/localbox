"""Tests for quiet build output mode and --verbose flag."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from localbox.cli import cli
from localbox.config import DirectoriesConfig, DockerSettings, Solution
from localbox.models.builder import Builder
from localbox.models.docker_image import DockerImage
from localbox.models.project import Project
from localbox.models.solution_config import SolutionConfig


def _make_solution(tmp_path: Path, projects: list[Project] | None = None) -> Solution:
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
        projects={p.name: p for p in (projects or [])},
        services={},
    )


def _runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# _run_docker_with_cleanup quiet/verbose output
# ---------------------------------------------------------------------------


class TestRunDockerWithCleanup:
    def _make_fake_process(self, lines: list[bytes]):
        proc = MagicMock()
        proc.stdout = iter(lines)
        proc.returncode = 0

        def _wait(timeout=None):
            return None

        proc.wait.side_effect = _wait
        return proc

    def test_quiet_suppresses_stdout(self, tmp_path):
        """quiet=True: output goes to log file only, not stdout."""
        from localbox.builders.build import _run_docker_with_cleanup

        log_path = tmp_path / "out.log"
        stdout_written: list[str] = []

        def fake_popen(cmd, stdout, stderr):
            proc = MagicMock()
            proc.stdout = iter([b"line one\n", b"line two\n"])
            proc.returncode = 0
            proc.wait.return_value = None
            return proc

        def capturing_write(text: str) -> int:
            stdout_written.append(text)
            return len(text)

        with (
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("subprocess.run"),
            patch.object(sys.stdout, "write", side_effect=capturing_write),
        ):
            # Use real threading so _reader runs normally
            _run_docker_with_cleanup(["docker", "run", "img"], "c1", log_path=log_path, quiet=True)

        assert not any("line one" in s for s in stdout_written)
        log_content = log_path.read_text()
        assert "line one" in log_content

    def test_verbose_writes_to_stdout(self, tmp_path):
        """quiet=False: output is written to stdout."""
        from localbox.builders.build import _run_docker_with_cleanup

        stdout_written: list[str] = []

        def fake_popen(cmd, stdout, stderr):
            proc = MagicMock()
            proc.stdout = iter([b"hello\n", b"world\n"])
            proc.returncode = 0
            proc.wait.return_value = None
            return proc

        def capturing_write(text: str) -> int:
            stdout_written.append(text)
            return len(text)

        with (
            patch("subprocess.Popen", side_effect=fake_popen),
            patch("subprocess.run"),
            patch.object(sys.stdout, "write", side_effect=capturing_write),
        ):
            _run_docker_with_cleanup(["docker", "run", "img"], "c1", log_path=None, quiet=False)

        assert any("hello" in s for s in stdout_written)


# ---------------------------------------------------------------------------
# run_builder quiet status lines
# ---------------------------------------------------------------------------


class TestRunBuilderQuietMode:
    def _minimal_solution(self, tmp_path: Path) -> Solution:
        return _make_solution(tmp_path)

    def test_quiet_prints_status_lines(self, tmp_path, capsys):
        """In quiet mode, run_builder should print [name] Building... and [name] OK/FAILED."""
        from localbox.builders.build import run_builder

        sol = self._minimal_solution(tmp_path)
        project = Project(name="mylib", repo="https://example.com/repo.git")
        project.builder = Builder(
            docker_image=DockerImage(image="alpine:latest"),
            build_command="echo hi",
        )
        source_dir = tmp_path / "mylib"
        source_dir.mkdir()

        with (
            patch("localbox.builders.build._resolve_builder_image", return_value="alpine:latest"),
            patch("localbox.builders.build._run_docker_with_cleanup", return_value=0),
        ):
            result = run_builder(sol, project, source_dir, verbose=False)

        assert result is True
        captured = capsys.readouterr()
        assert "mylib" in captured.out
        assert "Building" in captured.out
        assert "OK" in captured.out

    def test_quiet_creates_log_file(self, tmp_path):
        """In quiet mode with no log_path, run_builder auto-generates .build/logs/<name>.log."""
        from localbox.builders.build import run_builder

        sol = self._minimal_solution(tmp_path)
        project = Project(name="mylib", repo="https://example.com/repo.git")
        project.builder = Builder(
            docker_image=DockerImage(image="alpine:latest"),
            build_command="echo hi",
        )
        source_dir = tmp_path / "mylib"
        source_dir.mkdir()

        captured_log_path = None

        def fake_run(cmd, container_name, log_path=None, timeout_minutes=None, quiet=False):
            nonlocal captured_log_path
            captured_log_path = log_path
            return 0

        with (
            patch("localbox.builders.build._resolve_builder_image", return_value="alpine:latest"),
            patch("localbox.builders.build._run_docker_with_cleanup", side_effect=fake_run),
        ):
            run_builder(sol, project, source_dir, verbose=False, log_path=None)

        assert captured_log_path is not None
        assert str(captured_log_path).endswith("mylib.log")
        assert ".build/logs" in str(captured_log_path)

    def test_verbose_suppresses_status_lines(self, tmp_path, capsys):
        """In verbose mode, run_builder must NOT print [name] Building.../OK/FAILED lines."""
        from localbox.builders.build import run_builder

        sol = self._minimal_solution(tmp_path)
        project = Project(name="mylib", repo="https://example.com/repo.git")
        project.builder = Builder(
            docker_image=DockerImage(image="alpine:latest"),
            build_command="echo hi",
        )
        source_dir = tmp_path / "mylib"
        source_dir.mkdir()

        with (
            patch("localbox.builders.build._resolve_builder_image", return_value="alpine:latest"),
            patch("localbox.builders.build._run_docker_with_cleanup", return_value=0),
        ):
            run_builder(sol, project, source_dir, verbose=True)

        captured = capsys.readouterr()
        assert "Building..." not in captured.out
        assert " OK " not in captured.out
        assert "FAILED" not in captured.out


# ---------------------------------------------------------------------------
# CLI --verbose flag propagation
# ---------------------------------------------------------------------------


class TestVerboseFlagCLI:
    def test_projects_build_verbose_flag(self, tmp_path):
        """--verbose on projects build should pass verbose=True to build_projects."""
        with (
            patch("localbox.cli.load_solution_or_exit") as mock_sol,
            patch("localbox.commands.project.build_projects") as mock_build,
        ):
            mock_sol.return_value = MagicMock(projects={"p": MagicMock(name="p")}, services={})
            with patch("localbox.cli.resolve_targets", return_value=[MagicMock()]):
                _runner().invoke(cli, ["projects", "build", "--verbose"])
            call_kwargs = mock_build.call_args
            assert call_kwargs is not None
            verbose_val = (
                call_kwargs.kwargs.get("verbose")
                if call_kwargs.kwargs
                else call_kwargs[1].get("verbose")
            )
            assert verbose_val is True

    def test_projects_build_default_is_quiet(self, tmp_path):
        """Without --verbose, build_projects receives verbose=False."""
        with (
            patch("localbox.cli.load_solution_or_exit") as mock_sol,
            patch("localbox.commands.project.build_projects") as mock_build,
        ):
            mock_sol.return_value = MagicMock(projects={"p": MagicMock(name="p")}, services={})
            with patch("localbox.cli.resolve_targets", return_value=[MagicMock()]):
                _runner().invoke(cli, ["projects", "build"])
            call_kwargs = mock_build.call_args
            assert call_kwargs is not None
            verbose_val = (
                call_kwargs.kwargs.get("verbose")
                if call_kwargs.kwargs
                else call_kwargs[1].get("verbose")
            )
            assert verbose_val is False
