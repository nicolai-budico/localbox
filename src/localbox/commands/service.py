"""Service commands implementation."""

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
) -> None:
    """Build Docker images for services."""
    from localbox.commands.project import _print_summary

    results: list[tuple[str, str]] = []
    for service in services:
        if not isinstance(service, Service):
            continue

        logger.info("build-image {} (no_cache={})", service.name, no_cache)
        console.print(f"[blue]Building image[/blue] {service.name}...")
        success = do_build(solution, service, verbose=verbose, no_cache=no_cache)
        results.append((service.name or "", "built" if success else "failed"))

        if success:
            logger.info("build-image {} completed", service.name)
            console.print(f"[green]Built[/green] {service.name}")
        else:
            logger.error("build-image {} failed", service.name)
            console.print(f"[red]Failed[/red] to build {service.name}")
            if len(results) > 1 or any(s == "failed" for _, s in results):
                _print_summary(results, "Image Build Summary")
            return
    if len(results) > 1 or any(s == "failed" for _, s in results):
        _print_summary(results, "Image Build Summary")
