"""Tests for manifest-flow: manifest generate, projects switch --manifest,
services build --manifest, services push --manifest, compose generate flags."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from localbox.cli import cli
from localbox.config import DirectoriesConfig, DockerSettings, Solution
from localbox.models.docker_image import DockerImage
from localbox.models.project import Project
from localbox.models.service import ComposeConfig, Service
from localbox.models.solution_config import SolutionConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_solution(
    tmp_path: Path,
    projects: list[Project] | None = None,
    services: list[Service] | None = None,
    registry: str | None = None,
) -> Solution:
    build = tmp_path / ".build"
    config = SolutionConfig(
        name="test", compose_project="test", network="test-net", registry=registry
    )
    return Solution(
        root=tmp_path,
        name="test",
        registry=registry,
        directories=DirectoriesConfig(
            build=build,
            projects=build / "projects",
            compose=tmp_path,
        ),
        docker=DockerSettings(compose_project="test", network="test-net"),
        config=config,
        projects={p.name: p for p in (projects or [])},
        services={s.name: s for s in (services or [])},
    )


def _runner() -> CliRunner:
    return CliRunner()


def _make_project(name: str) -> Project:
    return Project(name=name, repo="git@example.com:org/repo.git")


def _make_service(name: str) -> Service:
    return Service(name=name, image=DockerImage(name=name), compose=ComposeConfig())


# ---------------------------------------------------------------------------
# manifest generate — unit tests (commands/manifest.py)
# ---------------------------------------------------------------------------


class TestManifestGenerateCommand:
    def test_happy_path_writes_manifest(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry="reg.example.com")
        src = proj.resolve_source_dir(sol.directories.projects)
        src.mkdir(parents=True)

        out = tmp_path / "out.json"

        with (
            patch("localbox.commands.manifest._git_sha", return_value="abc123"),
            patch(
                "localbox.commands.manifest._git_remote", return_value="git@example.com:org/api.git"
            ),
        ):
            with patch("localbox.cli.load_solution_or_exit", return_value=sol):
                result = _runner().invoke(
                    cli,
                    [
                        "manifest",
                        "generate",
                        "--manifest",
                        str(out),
                        "--tag",
                        "v1",
                        "--registry",
                        "reg.example.com",
                    ],
                )

        assert result.exit_code == 0, result.output
        data = json.loads(out.read_text())
        assert data["tag"] == "v1"
        assert data["registry"] == "reg.example.com"
        assert "api" in data["repositories"]
        assert data["repositories"]["api"]["commit"] == "abc123"
        assert data["repositories"]["api"]["remote"] == "git@example.com:org/api.git"

    def test_uses_solution_registry_fallback(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry="fallback.example.com")
        src = proj.resolve_source_dir(sol.directories.projects)
        src.mkdir(parents=True)
        out = tmp_path / "out.json"

        with (
            patch("localbox.commands.manifest._git_sha", return_value="abc"),
            patch("localbox.commands.manifest._git_remote", return_value="git@x.com/r.git"),
        ):
            with patch("localbox.cli.load_solution_or_exit", return_value=sol):
                result = _runner().invoke(
                    cli,
                    [
                        "manifest",
                        "generate",
                        "--manifest",
                        str(out),
                        "--tag",
                        "v1",
                    ],
                )

        assert result.exit_code == 0
        data = json.loads(out.read_text())
        assert data["registry"] == "fallback.example.com"

    def test_fails_when_no_registry(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry=None)
        src = proj.resolve_source_dir(sol.directories.projects)
        src.mkdir(parents=True)
        out = tmp_path / "out.json"

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(
                cli,
                [
                    "manifest",
                    "generate",
                    "--manifest",
                    str(out),
                    "--tag",
                    "v1",
                ],
            )

        assert result.exit_code != 0

    def test_fails_when_project_source_missing(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry="reg.example.com")
        # do NOT create the source directory
        out = tmp_path / "out.json"

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(
                cli,
                [
                    "manifest",
                    "generate",
                    "--manifest",
                    str(out),
                    "--tag",
                    "v1",
                    "--registry",
                    "reg.example.com",
                ],
            )

        assert result.exit_code != 0
        assert not out.exists()

    def test_creates_parent_directories(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry="reg.example.com")
        src = proj.resolve_source_dir(sol.directories.projects)
        src.mkdir(parents=True)
        out = tmp_path / "assembles" / "v1.json"

        with (
            patch("localbox.commands.manifest._git_sha", return_value="abc"),
            patch("localbox.commands.manifest._git_remote", return_value="git@x.com/r.git"),
        ):
            with patch("localbox.cli.load_solution_or_exit", return_value=sol):
                result = _runner().invoke(
                    cli,
                    [
                        "manifest",
                        "generate",
                        "--manifest",
                        str(out),
                        "--tag",
                        "v1",
                        "--registry",
                        "reg.example.com",
                    ],
                )

        assert result.exit_code == 0
        assert out.exists()

    def test_extra_pairs_stored(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry="reg.example.com")
        src = proj.resolve_source_dir(sol.directories.projects)
        src.mkdir(parents=True)
        out = tmp_path / "out.json"

        with (
            patch("localbox.commands.manifest._git_sha", return_value="abc"),
            patch("localbox.commands.manifest._git_remote", return_value="git@x.com/r.git"),
        ):
            with patch("localbox.cli.load_solution_or_exit", return_value=sol):
                result = _runner().invoke(
                    cli,
                    [
                        "manifest",
                        "generate",
                        "--manifest",
                        str(out),
                        "--tag",
                        "v1",
                        "--registry",
                        "reg.example.com",
                        "--extra",
                        "pr_number=42",
                        "--extra",
                        "run_id=abc",
                    ],
                )

        assert result.exit_code == 0
        data = json.loads(out.read_text())
        assert data["extra"] == {"pr_number": "42", "run_id": "abc"}

    def test_no_extra_key_absent(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj], registry="reg.example.com")
        src = proj.resolve_source_dir(sol.directories.projects)
        src.mkdir(parents=True)
        out = tmp_path / "out.json"

        with (
            patch("localbox.commands.manifest._git_sha", return_value="abc"),
            patch("localbox.commands.manifest._git_remote", return_value="git@x.com/r.git"),
        ):
            with patch("localbox.cli.load_solution_or_exit", return_value=sol):
                _runner().invoke(
                    cli,
                    [
                        "manifest",
                        "generate",
                        "--manifest",
                        str(out),
                        "--tag",
                        "v1",
                        "--registry",
                        "reg.example.com",
                    ],
                )

        data = json.loads(out.read_text())
        assert "extra" not in data

    def test_tag_required(self, tmp_path):
        sol = _make_solution(tmp_path, registry="reg.example.com")
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(
                cli,
                [
                    "manifest",
                    "generate",
                    "--manifest",
                    str(tmp_path / "out.json"),
                    "--registry",
                    "reg.example.com",
                ],
            )
        assert result.exit_code != 0
        assert "--tag" in result.output


# ---------------------------------------------------------------------------
# projects switch --manifest
# ---------------------------------------------------------------------------


class TestProjectsSwitchManifest:
    def _manifest(self, tmp_path: Path, repos: dict[str, str]) -> Path:
        m = tmp_path / "manifest.json"
        m.write_text(
            json.dumps(
                {
                    "tag": "v1",
                    "registry": "reg.example.com",
                    "repositories": {
                        k: {"commit": v, "remote": "git@x.com/r.git"} for k, v in repos.items()
                    },
                }
            )
        )
        return m

    def test_checks_out_recorded_commits(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj])
        mf = self._manifest(tmp_path, {"api": "abc1234"})

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.commands.project.subprocess.run") as mock_run,
            patch("localbox.commands.project.subprocess.check_call"),
        ):
            mock_run.return_value = MagicMock(returncode=0, stderr=b"")
            result = _runner().invoke(cli, ["projects", "switch", "--manifest", str(mf)])

        assert result.exit_code == 0

    def test_fails_on_unmatched_repo_key(self, tmp_path):
        proj = _make_project("api")
        sol = _make_solution(tmp_path, projects=[proj])
        mf = self._manifest(tmp_path, {"api": "abc", "unknown-svc": "def"})

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["projects", "switch", "--manifest", str(mf)])

        assert result.exit_code != 0
        assert "unknown-svc" in result.output

    def test_mutual_exclusion_with_targets(self, tmp_path):
        sol = _make_solution(tmp_path)
        mf = self._manifest(tmp_path, {})

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["projects", "switch", "api", "--manifest", str(mf)])

        assert result.exit_code != 0
        assert "--manifest" in result.output

    def test_mutual_exclusion_with_branch(self, tmp_path):
        sol = _make_solution(tmp_path)
        mf = self._manifest(tmp_path, {})

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(
                cli, ["projects", "switch", "--manifest", str(mf), "-b", "main"]
            )

        assert result.exit_code != 0
        assert "--manifest" in result.output


# ---------------------------------------------------------------------------
# services build --manifest
# ---------------------------------------------------------------------------


class TestServicesBuildManifest:
    def _manifest(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "tag": "v1",
                    "registry": "reg.example.com",
                    "repositories": {},
                }
            )
        )
        return path

    def test_applies_remote_tag(self, tmp_path):
        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])
        mf = self._manifest(tmp_path / "manifest.json")

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.commands.service.do_build", return_value=True),
            patch("localbox.commands.service.subprocess.check_call") as mock_cc,
        ):
            result = _runner().invoke(cli, ["services", "build", "--manifest", str(mf)])

        assert result.exit_code == 0
        calls = [c.args[0] for c in mock_cc.call_args_list]
        # Only one tag call: latest (built directly) → versioned
        assert [
            "docker",
            "tag",
            sol.service_remote_tag("api", "latest", "reg.example.com"),
            sol.service_remote_tag("api", "v1", "reg.example.com"),
        ] in calls
        # Old solution-registry tag (no registry prefix) must NOT appear as a docker tag source
        assert not any(sol.service_image_tag("api") in c for c in calls)
        # No digest written to manifest
        data = json.loads(mf.read_text())
        assert "images" not in data

    def test_no_manifest_no_remote_tag(self, tmp_path):
        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.commands.service.do_build", return_value=True),
            patch("localbox.commands.service.subprocess.check_call") as mock_cc,
        ):
            result = _runner().invoke(cli, ["services", "build"])

        assert result.exit_code == 0
        mock_cc.assert_not_called()

    def test_partial_failure_stops_after_first_failed(self, tmp_path):
        svc_a = _make_service("api")
        svc_b = _make_service("worker")
        sol = _make_solution(tmp_path, services=[svc_a, svc_b])
        mf = self._manifest(tmp_path / "manifest.json")

        build_results = [True, False]

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.commands.service.do_build", side_effect=build_results),
            patch("localbox.commands.service.subprocess.check_call"),
        ):
            _runner().invoke(cli, ["services", "build", "--manifest", str(mf)])

        # Stops on first failure — no digest or images key written
        data = json.loads(mf.read_text())
        assert "images" not in data


# ---------------------------------------------------------------------------
# services push --manifest
# ---------------------------------------------------------------------------


class TestServicesPushManifest:
    def _manifest(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "tag": "v1",
                    "registry": "reg.example.com",
                    "repositories": {},
                }
            )
        )
        return path

    def test_pushes_all_services(self, tmp_path):
        svc_a = _make_service("api")
        svc_b = _make_service("worker")
        sol = _make_solution(tmp_path, services=[svc_a, svc_b])
        mf = self._manifest(tmp_path / "manifest.json")

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.commands.service.subprocess.check_call") as mock_cc,
        ):
            result = _runner().invoke(cli, ["services", "push", "--manifest", str(mf)])

        assert result.exit_code == 0
        pushed = [c.args[0] for c in mock_cc.call_args_list]
        assert ["docker", "push", sol.service_remote_tag("api", "v1", "reg.example.com")] in pushed
        assert [
            "docker",
            "push",
            sol.service_remote_tag("worker", "v1", "reg.example.com"),
        ] in pushed

    def test_manifest_required(self, tmp_path):
        sol = _make_solution(tmp_path)
        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["services", "push"])
        assert result.exit_code != 0
        assert "--manifest" in result.output


# ---------------------------------------------------------------------------
# compose generate --manifest / --tag / --registry
# ---------------------------------------------------------------------------


class TestComposeGenerateManifest:
    def _manifest(self, path: Path) -> Path:
        path.write_text(
            json.dumps(
                {
                    "tag": "v1",
                    "registry": "reg.example.com",
                }
            )
        )
        return path

    def test_manifest_passes_tag_and_registry(self, tmp_path):
        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])
        mf = self._manifest(tmp_path / "manifest.json")

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.builders.compose.generate_compose_file") as mock_gen,
        ):
            mock_gen.return_value = tmp_path / "docker-compose.yml"
            _runner().invoke(cli, ["compose", "generate", "--manifest", str(mf)])

        mock_gen.assert_called_once_with(sol, image_tag="v1", registry="reg.example.com")

    def test_explicit_flags_pass_tag_and_registry(self, tmp_path):
        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.builders.compose.generate_compose_file") as mock_gen,
        ):
            mock_gen.return_value = tmp_path / "docker-compose.yml"
            _runner().invoke(
                cli, ["compose", "generate", "--tag", "v1", "--registry", "reg.example.com"]
            )

        mock_gen.assert_called_once_with(sol, image_tag="v1", registry="reg.example.com")

    def test_explicit_tag_uses_solution_registry_fallback(self, tmp_path):
        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc], registry="fallback.example.com")

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.builders.compose.generate_compose_file") as mock_gen,
        ):
            mock_gen.return_value = tmp_path / "docker-compose.yml"
            _runner().invoke(cli, ["compose", "generate", "--tag", "v1"])

        mock_gen.assert_called_once_with(sol, image_tag="v1", registry="fallback.example.com")

    def test_manifest_and_tag_together_is_error(self, tmp_path):
        sol = _make_solution(tmp_path)
        mf = self._manifest(tmp_path / "manifest.json")

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(
                cli,
                [
                    "compose",
                    "generate",
                    "--manifest",
                    str(mf),
                    "--tag",
                    "v1",
                ],
            )

        assert result.exit_code != 0

    def test_tag_without_registry_and_no_solution_registry_is_error(self, tmp_path):
        sol = _make_solution(tmp_path, registry=None)

        with patch("localbox.cli.load_solution_or_exit", return_value=sol):
            result = _runner().invoke(cli, ["compose", "generate", "--tag", "v1"])

        assert result.exit_code != 0

    def test_no_flags_preserves_local_tag_behavior(self, tmp_path):
        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])

        with (
            patch("localbox.cli.load_solution_or_exit", return_value=sol),
            patch("localbox.builders.compose.generate_compose_file") as mock_gen,
        ):
            mock_gen.return_value = tmp_path / "docker-compose.yml"
            _runner().invoke(cli, ["compose", "generate"])

        mock_gen.assert_called_once_with(sol, image_tag=None, registry=None)


# ---------------------------------------------------------------------------
# generate_compose_file image_tag/registry integration
# ---------------------------------------------------------------------------


class TestComposeGenerateFileImageOverride:
    def test_registry_image_ref_written(self, tmp_path):
        from localbox.builders.compose import generate_compose_file

        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])
        (tmp_path).mkdir(parents=True, exist_ok=True)

        generate_compose_file(sol, image_tag="v1", registry="reg.example.com")

        import yaml

        compose_file = tmp_path / "docker-compose.yml"
        data = yaml.safe_load(compose_file.read_text())
        service_images = [s["image"] for s in data["services"].values()]
        assert any(
            sol.service_remote_tag("api", "v1", "reg.example.com") == img for img in service_images
        )

    def test_local_tag_when_no_override(self, tmp_path):
        from localbox.builders.compose import generate_compose_file

        svc = _make_service("api")
        sol = _make_solution(tmp_path, services=[svc])

        generate_compose_file(sol)

        import yaml

        data = yaml.safe_load((tmp_path / "docker-compose.yml").read_text())
        service_images = [s["image"] for s in data["services"].values()]
        assert all("reg.example.com" not in img for img in service_images)
