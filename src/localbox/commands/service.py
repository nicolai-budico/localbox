"""Service commands implementation."""

import json
import subprocess
from pathlib import Path

from loguru import logger
from rich.console import Console

from localbox.builders.docker import build_service_image as do_build
from localbox.config import Solution
from localbox.models.project import Project
from localbox.models.service import Service

console = Console()


def build_images(
    solution: Solution,
    services: list[Project | Service],
    verbose: bool = False,
    no_cache: bool = False,
    manifest_path: Path | None = None,
) -> None:
    """Build Docker images for services."""
    from localbox.commands.project import _print_summary

    manifest: dict[str, object] | None = None
    if manifest_path:
        manifest = json.loads(manifest_path.read_text())

    results: list[tuple[str, str]] = []
    for service in services:
        if not isinstance(service, Service):
            continue

        logger.info("build-image {} (no_cache={})", service.name, no_cache)
        console.print(f"[blue]Building image[/blue] {service.name}...")

        build_target_tag: str | None = None
        if manifest is not None and service.image.name:
            registry = str(manifest["registry"])
            build_target_tag = solution.service_remote_tag(service.image.name, "latest", registry)

        success = do_build(
            solution, service, verbose=verbose, no_cache=no_cache, target_tag=build_target_tag
        )
        results.append((service.name or "", "built" if success else "failed"))

        if success:
            logger.info("build-image {} completed", service.name)
            console.print(f"[green]Built[/green] {service.name}")

            if manifest is not None and manifest_path is not None and service.image.name:
                registry = str(manifest["registry"])
                tag = str(manifest["tag"])
                # build_target_tag is the `:latest` tag with manifest registry
                latest_tag = solution.service_remote_tag(service.image.name, "latest", registry)
                remote_tag = solution.service_remote_tag(service.image.name, tag, registry)

                subprocess.check_call(["docker", "tag", latest_tag, remote_tag])
                console.print(f"[dim]Tagged[/dim] {remote_tag}")
        else:
            logger.error("build-image {} failed", service.name)
            console.print(f"[red]Failed[/red] to build {service.name}")
            if len(results) > 1 or any(s == "failed" for _, s in results):
                _print_summary(results, "Image Build Summary")
            return
    if len(results) > 1 or any(s == "failed" for _, s in results):
        _print_summary(results, "Image Build Summary")


def push_images(
    solution: Solution,
    manifest_path: Path,
    verbose: bool = False,
) -> None:
    """Push all service images to registry using coordinates from the manifest."""
    manifest = json.loads(manifest_path.read_text())
    registry = manifest["registry"]
    tag = manifest["tag"]

    for service in solution.services.values():
        if not service.image.name:
            continue
        remote_tag = solution.service_remote_tag(service.image.name, tag, registry)
        if verbose:
            console.print(f"  $ docker push {remote_tag}")
        console.print(f"[blue]Pushing[/blue] {remote_tag}...")
        try:
            subprocess.check_call(["docker", "push", remote_tag])
        except subprocess.CalledProcessError:
            logger.error("push failed for {}", remote_tag)
            console.print(f"[red]Failed[/red] to push {remote_tag}")
            raise SystemExit(1)
        console.print(f"[green]Pushed:[/green] {remote_tag}")
