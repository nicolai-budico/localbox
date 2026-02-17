"""Docker image builder for services."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from loguru import logger
from rich.console import Console

from localbox.builders.image_builder import prepare_docker_image
from localbox.config import Solution
from localbox.models.service import Service

console = Console()


@runtime_checkable
class _DockerfileService(Protocol):
    """Structural protocol for services that build from a generated Dockerfile.

    Any library service that implements both methods automatically satisfies
    this protocol — no explicit inheritance or registration required.

    ``build_contexts`` must return a non-empty list for the Dockerfile path
    to be used; an empty list signals "no custom build needed" (e.g. a
    TomcatService with no webapps configured).
    """

    def generate_dockerfile(self, solution: Solution) -> str: ...
    def build_contexts(self, solution: Solution) -> list[tuple[str, Path]]: ...


def build_service_image(
    solution: Solution,
    service: Service,
    verbose: bool = False,
    no_cache: bool = False,
) -> bool:
    """Build or pull Docker image for a service."""
    try:
        # Services that generate their own Dockerfile (TomcatService,
        # SpringBootService, or any future library type) are handled by a
        # single generic path.  No isinstance checks against library types.
        if isinstance(service, _DockerfileService):
            contexts = service.build_contexts(solution)
            if contexts:
                return _build_dockerfile_service(
                    solution, service, contexts, verbose, no_cache
                )

        prepare_docker_image(
            solution,
            service.image,
            image_type="service",
            projects=service.all_projects,
            verbose=verbose,
            no_cache=no_cache,
        )
        return True
    except Exception as e:
        logger.exception("Error building service image for {}", service.name)
        console.print(f"[red]Error building service image:[/red] {e}")
        return False


def _build_dockerfile_service(
    solution: Solution,
    service: _DockerfileService,
    contexts: list[tuple[str, Path]],
    verbose: bool,
    no_cache: bool = False,
) -> bool:
    """Build a service image from a service-generated Dockerfile.

    Accepts pre-computed ``contexts`` (from ``service.build_contexts()``) so
    they are not evaluated twice.
    """
    dockerfile_content = service.generate_dockerfile(solution)

    if verbose:
        console.print("[dim]Generated Dockerfile:[/dim]")
        for line in dockerfile_content.split("\n"):
            console.print(f"  {line}")

    with tempfile.TemporaryDirectory() as tmpdir:
        dockerfile_path = Path(tmpdir) / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)

        target_tag = f"{solution.name}/service/{service.image.name}:latest"

        cmd = [
            "docker", "buildx", "build",
            "--load",
            "-t", target_tag,
            "-f", str(dockerfile_path),
        ]

        if no_cache:
            cmd.append("--no-cache")

        for context_name, context_path in contexts:
            cmd.extend(["--build-context", f"{context_name}={context_path}"])

        cmd.append(tmpdir)

        logger.debug("$ {}", " ".join(cmd))
        if verbose:
            console.print(f"  $ {' '.join(cmd)}")

        subprocess.check_call(cmd)

    return True
