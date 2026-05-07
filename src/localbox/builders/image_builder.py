"""Docker image preparation logic."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from localbox.models.docker_image import DockerImage
from localbox.models.project import Project

if TYPE_CHECKING:
    from localbox.config import Solution

console = Console()


def _run_capturing(
    cmd: list[str],
    verbose: bool,
    log_path: Path | None,
) -> None:
    """Run a command, always capturing output to log_path; also print when verbose."""
    result = subprocess.run(cmd, capture_output=True)
    if log_path:
        with open(log_path, "ab") as f:
            if result.stdout:
                f.write(result.stdout)
            if result.stderr:
                f.write(result.stderr)
    if verbose:
        if result.stdout:
            sys.stdout.buffer.write(result.stdout)
            sys.stdout.buffer.flush()
        if result.stderr:
            sys.stderr.buffer.write(result.stderr)
            sys.stderr.buffer.flush()
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)


def prepare_docker_image(
    solution: Solution,
    image: DockerImage,
    image_type: str,  # "builder" or "service"
    projects: list[Project] | None = None,
    tag_name: str | None = None,
    verbose: bool = False,
    no_cache: bool = False,
    target_tag: str | None = None,
    log_path: Path | None = None,
) -> str:
    """Prepare a Docker image (build or pull & tag).

    Args:
        solution: The solution context
        image: DockerImage configuration
        image_type: "builder" or "service"
        projects: List of projects for build contexts
        tag_name: Override for image name in tag. If None, uses image.name.
        verbose: Enable verbose output
        target_tag: Full tag override. If set, skips tag derivation entirely.
        log_path: Path to append image prep output to (always written, regardless of verbose).

    Returns the local tag of the prepared image.
    """
    if projects is None:
        projects = []

    if target_tag is None:
        name = tag_name or image.name
        if image_type == "service":
            target_tag = solution.service_image_tag(name)
        else:
            target_tag = f"{solution.name}/{image_type}/{name}:latest"

    if image.dockerfile:
        build_image(solution, image, target_tag, image_type, projects, verbose, no_cache, log_path)
    elif image.image:
        pull_and_tag_image(image.image, target_tag, verbose, log_path)
    else:
        raise ValueError(f"DockerImage '{image.name}' has neither dockerfile nor image")

    return target_tag


def build_image(
    solution: Solution,
    image: DockerImage,
    target_tag: str,
    image_type: str,
    projects: list[Project],
    verbose: bool,
    no_cache: bool = False,
    log_path: Path | None = None,
) -> None:
    """Build image using buildx with named contexts."""
    if not image.dockerfile:
        raise ValueError("Dockerfile path is required for build")

    dockerfile_path = solution.root / image.dockerfile
    if not dockerfile_path.exists():
        raise FileNotFoundError(f"Dockerfile not found: {dockerfile_path}")

    # Main context: parent of Dockerfile
    context_path = dockerfile_path.parent

    cmd = [
        "docker",
        "buildx",
        "build",
        "--load",  # Load into local docker daemon
        "-t",
        target_tag,
        "-f",
        str(dockerfile_path),
    ]

    if no_cache:
        cmd.append("--no-cache")

    # Inject 'assets' context
    assets_dir = solution.root / "assets"
    if assets_dir.exists():
        cmd.extend(["--build-context", f"assets={assets_dir}"])

    # Inject project contexts
    if image_type == "builder":
        # For builder, usually 1 project (the one being built)
        if projects:
            project = projects[0]
            src_dir = project.resolve_source_dir(solution.directories.projects)
            cmd.extend(["--build-context", f"project={src_dir}"])

            name = project.path_name
            if name != "project":
                cmd.extend(["--build-context", f"{name}={src_dir}"])

    elif image_type == "service":
        # For service, inject all projects by name
        for project in projects:
            src_dir = project.resolve_source_dir(solution.directories.projects)
            name = project.path_name
            cmd.extend(["--build-context", f"{name}={src_dir}"])

    # Append main context
    cmd.append(str(context_path))

    if verbose:
        console.print(f"  $ {' '.join(cmd)}")

    _run_capturing(cmd, verbose, log_path)


def pull_and_tag_image(
    source_image: str,
    target_tag: str,
    verbose: bool,
    log_path: Path | None = None,
) -> None:
    """Pull and tag image."""
    if verbose:
        console.print(f"  $ docker pull {source_image}")
    _run_capturing(["docker", "pull", source_image], verbose, log_path)

    if verbose:
        console.print(f"  $ docker tag {source_image} {target_tag}")
    _run_capturing(["docker", "tag", source_image, target_tag], verbose, log_path)
