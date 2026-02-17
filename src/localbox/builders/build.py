"""Unified project builder using Builder model."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from rich.console import Console

from localbox.models.builder import (
    BindVolume,
    Builder,
    CacheVolume,
    JavaBuilder,
    NamedVolume,
    Volume,
)
from localbox.models.project import JavaProject, Project

if TYPE_CHECKING:
    from localbox.config import Solution

console = Console()


def _kill_container(container_name: str) -> None:
    """Best-effort container kill (ignores errors)."""
    subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10)


def _run_docker_with_cleanup(
    cmd: list[str],
    container_name: str,
    log_path: Path | None = None,
    timeout_minutes: int | None = None,
) -> int:
    """Run docker command, tee output to log file, and kill container on interrupt or timeout.

    Args:
        cmd: Docker command to run.
        container_name: Name of the container (for cleanup on interrupt/timeout).
        log_path: Optional path to save build output (overwritten each run).
        timeout_minutes: Kill the container and return exit code 124 after this
                         many minutes. None means no timeout.
    """
    log_file = open(log_path, "w") if log_path else None

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    def _reader() -> None:
        """Stream process output to stdout and optionally to log file."""
        if process.stdout:
            for raw_line in process.stdout:
                text = raw_line.decode(errors="replace")
                sys.stdout.write(text)
                sys.stdout.flush()
                if log_file:
                    log_file.write(text)

    reader_thread = threading.Thread(target=_reader, daemon=True)
    reader_thread.start()

    def cleanup(signum, frame) -> None:
        console.print("\n[yellow]Interrupted, stopping container...[/yellow]")
        _kill_container(container_name)
        process.terminate()
        raise KeyboardInterrupt()

    old_handler = signal.signal(signal.SIGINT, cleanup)
    timeout_seconds = timeout_minutes * 60 if timeout_minutes is not None else None

    try:
        process.wait(timeout=timeout_seconds)
        reader_thread.join(timeout=5)
        return process.returncode
    except subprocess.TimeoutExpired:
        console.print(
            f"\n[red]Build timed out after {timeout_minutes} minute(s).[/red] "
            f"Stopping container..."
        )
        _kill_container(container_name)
        process.kill()
        reader_thread.join(timeout=5)
        return 124  # Standard POSIX timeout exit code
    finally:
        if log_file:
            log_file.close()
        signal.signal(signal.SIGINT, old_handler)


def run_builder(
    solution: Solution,
    project: Project,
    source_dir: Path,
    verbose: bool = False,
    no_cache: bool = False,
    log_path: Path | None = None,
) -> bool:
    """Run a project's builder in Docker.

    1. Ensure the builder image is ready (build from Dockerfile or pull).
    2. Run the image with project sources mounted at builder.workdir.

    Returns True on success, False on failure.
    """
    builder = project.builder
    if builder is None:
        console.print(f"[red]Error:[/red] No builder configured for {project.name}")
        return False

    # Step 1: Resolve Docker image
    # Tag name: <group>/<local_name> (e.g., backend/fs-s3-storage)
    if project.group:
        tag_name = f"{project.group}/{project.local_name}"
    else:
        tag_name = project.local_name or project.name

    try:
        image_tag = _resolve_builder_image(solution, project, builder, tag_name, verbose, no_cache)
    except Exception as e:
        logger.exception("Error preparing builder image for {}", project.name)
        console.print(f"[red]Error preparing builder image:[/red] {e}")
        return False

    # Step 2: Resolve build command
    build_cmd = _resolve_build_command(builder, project, solution)
    if build_cmd is None:
        return False

    # Step 3: Run the builder container
    uid = os.getuid()
    gid = os.getgid()
    container_name = f"localbox-build-{uuid.uuid4().hex[:8]}"

    docker_cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--user", f"{uid}:{gid}",
        "-v", f"{source_dir}:{builder.workdir}",
        "-w", builder.workdir,
    ]

    # Entrypoint override
    if builder.entrypoint is not None:
        docker_cmd.extend(["--entrypoint", builder.entrypoint])

    # Resolve and add volume mounts
    for vol in builder.volumes:
        docker_cmd.extend(_build_volume_args(vol, solution))

    # Environment variables
    for key, value in builder.environment.items():
        docker_cmd.extend(["-e", f"{key}={value}"])

    # Script mount
    if builder.script:
        script_path = project.get_script_path(builder.script, solution.root)
        if script_path and script_path.exists():
            docker_cmd.extend(["-v", f"{script_path}:/build.sh:ro"])
        else:
            console.print(f"[red]Error:[/red] Build script not found: {builder.script}")
            return False

    docker_cmd.append(image_tag)
    docker_cmd.extend(build_cmd)

    logger.debug("$ {}", " ".join(docker_cmd))
    if verbose:
        console.print(f"  $ {' '.join(docker_cmd)}")

    returncode = _run_docker_with_cleanup(
        docker_cmd, container_name,
        log_path=log_path,
        timeout_minutes=builder.timeout,
    )

    if returncode != 0:
        logger.error("docker run exited {} for {}", returncode, project.name)
    return returncode == 0


def _resolve_builder_image(
    solution: Solution,
    project: Project,
    builder: Builder,
    tag_name: str,
    verbose: bool,
    no_cache: bool = False,
) -> str:
    """Resolve and prepare the builder Docker image.

    For JavaBuilder + JavaProject: uses project's JDK to resolve image.
    For regular Builder: uses docker_image directly.

    Returns the image tag to use.
    """
    from localbox.builders.image_builder import pull_and_tag_image

    # Determine source image
    if isinstance(builder, JavaBuilder) and isinstance(project, JavaProject):
        # JavaBuilder resolves image using project's JDK
        source_image = builder.resolve_image_tag(project.jdk)
    elif builder.docker_image and builder.docker_image.image:
        source_image = builder.docker_image.image
    elif builder.uses_dockerfile:
        # Handle Dockerfile-based builders
        from localbox.builders.image_builder import build_image
        target_tag = f"{solution.name}/builder/{tag_name}:latest"
        build_image(
            solution, builder.docker_image, target_tag, "builder", [project], verbose, no_cache
        )
        return target_tag
    else:
        raise ValueError(f"Builder for {project.name} has no image configured")

    # Pull and tag the image
    target_tag = f"{solution.name}/builder/{tag_name}:latest"
    pull_and_tag_image(source_image, target_tag, verbose)

    return target_tag


def _resolve_build_command(
    builder: Builder, project: Project, solution: Solution
) -> list[str] | None:
    """Determine the build command to run."""
    if builder.script:
        return ["sh", "/build.sh"]
    elif builder.command:
        return ["sh", "-c", builder.command]
    elif builder.command_list:
        return builder.command_list
    else:
        console.print(f"[red]Error:[/red] Builder for {project.name} has no command")
        return None


def _build_volume_args(vol: Volume, solution: Solution) -> list[str]:
    """Build docker -v arguments for a volume mount."""
    if isinstance(vol, CacheVolume):
        host = solution.directories.build / vol.name
        host.mkdir(parents=True, exist_ok=True)
        mount = f"{host}:{vol.container}"
    elif isinstance(vol, BindVolume):
        host = Path(vol.host)
        if not host.is_absolute():
            host = solution.root / host
        mount = f"{host}:{vol.container}"
    elif isinstance(vol, NamedVolume):
        mount = f"{vol.name}:{vol.container}"
    else:
        raise ValueError(f"Unknown volume type: {type(vol)}")
    if vol.readonly:
        mount += ":ro"
    return ["-v", mount]
