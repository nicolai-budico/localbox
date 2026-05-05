"""Manifest command implementations."""

import json
import subprocess
from pathlib import Path

from loguru import logger
from rich.console import Console

from localbox.config import Solution

console = Console()


def _git_sha(path: Path) -> str:
    return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()


def _git_remote(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "remote", "get-url", "origin"], text=True
    ).strip()


def generate_manifest(
    solution: Solution,
    manifest_path: Path,
    tag: str,
    registry: str,
    extra: dict[str, str],
) -> None:
    """Generate a manifest JSON recording current repo SHAs for all projects."""
    projects_dir = solution.directories.projects

    missing = [
        p.path_name
        for p in solution.projects.values()
        if not p.resolve_source_dir(projects_dir).exists()
    ]
    if missing:
        for name in missing:
            console.print(f"[red]Error:[/red] project source directory missing: {name}")
        raise SystemExit(1)

    repositories: dict[str, dict[str, str]] = {}
    for project in solution.projects.values():
        src = project.resolve_source_dir(projects_dir)
        logger.info("manifest: reading {} at {}", project.path_name, src)
        repositories[project.path_name] = {
            "commit": _git_sha(src),
            "remote": _git_remote(src),
        }

    manifest: dict[str, object] = {
        "tag": tag,
        "registry": registry,
        "repositories": repositories,
    }
    if extra:
        manifest["extra"] = extra

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    console.print(f"[green]Manifest written:[/green] {manifest_path}")
