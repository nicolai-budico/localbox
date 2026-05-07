"""Service commands implementation."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from rich.console import Console

from localbox.builders.docker import build_service_image as do_build
from localbox.config import Solution
from localbox.models.project import Project
from localbox.models.service import Service

console = Console()


def _build_one_image(
    solution: Solution,
    service: Service,
    manifest: dict[str, object] | None,
    verbose: bool,
    no_cache: bool,
) -> tuple[str, bool]:
    """Build a single service image and apply manifest tags. Returns (name, success)."""
    logger.info("build-image {} (no_cache={})", service.name, no_cache)
    console.print(f"[blue]Building image[/blue] {service.name}...")

    build_target_tag: str | None = None
    if manifest is not None and service.image.name:
        registry = str(manifest["registry"])
        build_target_tag = solution.service_remote_tag(service.image.name, "latest", registry)

    success = do_build(
        solution, service, verbose=verbose, no_cache=no_cache, target_tag=build_target_tag
    )

    if success:
        logger.info("build-image {} completed", service.name)
        console.print(f"[green]Built[/green] {service.name}")

        if manifest is not None and service.image.name:
            registry = str(manifest["registry"])
            tag = str(manifest["tag"])
            latest_tag = solution.service_remote_tag(service.image.name, "latest", registry)
            remote_tag = solution.service_remote_tag(service.image.name, tag, registry)
            subprocess.check_call(["docker", "tag", latest_tag, remote_tag])
            console.print(f"[dim]Tagged[/dim] {remote_tag}")
    else:
        logger.error("build-image {} failed", service.name)
        console.print(f"[red]Failed[/red] to build {service.name}")

    return (service.name or "", success)


def build_images(
    solution: Solution,
    services: list[Project | Service],
    verbose: bool = False,
    no_cache: bool = False,
    manifest_path: Path | None = None,
    jobs: int = 1,
) -> None:
    """Build Docker images for services."""
    from localbox.commands.project import _print_summary

    manifest: dict[str, object] | None = None
    if manifest_path:
        manifest = json.loads(manifest_path.read_text())

    svc_list = [s for s in services if isinstance(s, Service)]

    results: list[tuple[str, str]] = []

    if jobs == 1 or len(svc_list) <= 1:
        for service in svc_list:
            name, success = _build_one_image(solution, service, manifest, verbose, no_cache)
            results.append((name, "built" if success else "failed"))
            if not success:
                if len(results) > 1 or any(s == "failed" for _, s in results):
                    _print_summary(results, "Image Build Summary")
                return
    else:
        workers = min(jobs, len(svc_list))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_svc = {
                pool.submit(_build_one_image, solution, svc, manifest, verbose, no_cache): svc
                for svc in svc_list
            }
            for future in as_completed(future_to_svc):
                name, success = future.result()
                results.append((name, "built" if success else "failed"))

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
