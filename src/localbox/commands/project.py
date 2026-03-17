"""Project commands implementation."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Union

from loguru import logger
from rich.console import Console
from rich.table import Table
from toposort import CircularDependencyError, toposort_flatten

from localbox.config import Solution
from localbox.models.project import Project

if TYPE_CHECKING:
    from localbox.models.service import Service

console = Console()

_LAST_BUILD_FILE = ".last-build"


def _write_last_build(source_dir: Path) -> None:
    """Write current UTC timestamp to .last-build in the project directory."""
    (source_dir / _LAST_BUILD_FILE).write_text(datetime.now(timezone.utc).isoformat())


def _read_last_build(source_dir: Path) -> datetime | None:
    """Read last build timestamp from .last-build, returns None if absent or unreadable."""
    marker = source_dir / _LAST_BUILD_FILE
    if not marker.exists():
        return None
    try:
        return datetime.fromisoformat(marker.read_text().strip())
    except ValueError:
        return None


def _format_age(dt: datetime) -> str:
    """Format a UTC datetime as a human-readable age string (e.g. '2h ago')."""
    delta = datetime.now(timezone.utc) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def clone_projects(
    solution: Solution,
    projects: list[Union[Project, "Service"]],
    verbose: bool = False,
) -> None:
    """Clone project repositories."""
    results: list[tuple[str, str]] = []
    for project in projects:
        if not isinstance(project, Project):
            continue

        status = clone_project(solution, project, verbose=verbose)
        results.append((project.name or "", status))
    if len(results) > 1 or any(s == "failed" for _, s in results):
        _print_summary(results, "Clone Summary")


def clone_project(solution: Solution, project: Project, verbose: bool = False) -> str:
    """Clone a single project repository."""
    target_dir = project.resolve_source_dir(solution.directories.projects)

    if target_dir.exists():
        logger.debug("clone skip {}: already exists at {}", project.name, target_dir)
        console.print(f"[yellow]Skip[/yellow] {project.name} (already exists)")
        return "skipped"

    logger.info("clone {}", project.name)
    console.print(f"[blue]Cloning[/blue] {project.name}...")

    if project.git is None:
        logger.error("clone {}: no git configuration", project.name)
        console.print(f"[red]Error:[/red] Project {project.name} has no git configuration")
        return "failed"

    # Clone
    cmd = ["git", "clone", project.git.url, str(target_dir)]
    logger.debug("$ {}", " ".join(cmd))
    if verbose:
        console.print(f"  $ {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=not verbose)
    if result.returncode != 0:
        stderr = result.stderr.decode() if result.stderr else ""
        logger.error("clone {} failed (exit {}): {}", project.name, result.returncode, stderr)
        console.print(f"[red]Failed[/red] to clone {project.name}")
        if not verbose and stderr:
            console.print(stderr)
        return "failed"

    # Checkout branch
    branch = project.git.branch or solution.default_branch
    cmd = ["git", "-C", str(target_dir), "checkout", branch]
    logger.debug("$ {}", " ".join(cmd))
    if verbose:
        console.print(f"  $ {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=not verbose)
    if result.returncode != 0:
        logger.warning("clone {}: could not checkout branch {}", project.name, branch)
        console.print(f"[yellow]Warning[/yellow] Could not checkout branch {branch}")

    # Apply patches automatically if directory exists
    patches_dir = project.get_patches_dir(solution.root)
    if patches_dir and patches_dir.exists():
        apply_patches(target_dir, patches_dir, verbose=verbose)

    logger.info("clone {} completed", project.name)
    console.print(f"[green]Cloned[/green] {project.name}")
    return "cloned"


def apply_patches(target_dir: Path, patches_dir: Path, verbose: bool = False) -> None:
    """Apply git patches to a repository."""
    patches = sorted(patches_dir.glob("*.patch"))

    for patch in patches:
        console.print(f"  Applying patch: {patch.name}")
        cmd = ["git", "-C", str(target_dir), "apply", str(patch)]
        logger.debug("$ {}", " ".join(cmd))
        if verbose:
            console.print(f"    $ {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            stderr = result.stderr.decode() if result.stderr else ""
            logger.warning("patch {} failed: {}", patch.name, stderr)
            console.print(f"  [yellow]Warning[/yellow] Patch {patch.name} failed")
            if verbose and stderr:
                console.print(stderr)


def fetch_projects(
    solution: Solution,
    projects: list[Union[Project, "Service"]],
    verbose: bool = False,
) -> None:
    """Fetch (git pull) project repositories."""
    results: list[tuple[str, str]] = []
    for project in projects:
        if not isinstance(project, Project):
            continue

        status = fetch_project(solution, project, verbose=verbose)
        results.append((project.name or "", status))
    if len(results) > 1 or any(s == "failed" for _, s in results):
        _print_summary(results, "Fetch Summary")


def fetch_project(solution: Solution, project: Project, verbose: bool = False) -> str:
    """Fetch a single project repository."""
    target_dir = project.resolve_source_dir(solution.directories.projects)

    if not target_dir.exists():
        logger.debug("fetch skip {}: not cloned", project.name)
        console.print(f"[yellow]Skip[/yellow] {project.name} (not cloned)")
        return "skipped"

    logger.info("fetch {}", project.name)
    console.print(f"[blue]Fetching[/blue] {project.name}...")

    cmd = ["git", "-C", str(target_dir), "pull", "--rebase"]
    logger.debug("$ {}", " ".join(cmd))
    if verbose:
        console.print(f"  $ {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=not verbose)
    if result.returncode != 0:
        stderr = result.stderr.decode() if result.stderr else ""
        logger.error("fetch {} failed (exit {}): {}", project.name, result.returncode, stderr)
        console.print(f"[red]Failed[/red] to fetch {project.name}")
        if not verbose and stderr:
            console.print(stderr)
        return "failed"

    logger.info("fetch {} completed", project.name)
    console.print(f"[green]Fetched[/green] {project.name}")
    return "fetched"


def switch_projects(
    solution: Solution,
    projects: list[Union[Project, "Service"]],
    branch: str | None = None,
    verbose: bool = False,
) -> None:
    """Switch branches for projects."""
    results: list[tuple[str, str]] = []
    for project in projects:
        if not isinstance(project, Project):
            continue

        status = switch_project(solution, project, branch=branch, verbose=verbose)
        results.append((project.name or "", status))
    if len(results) > 1 or any(s == "failed" for _, s in results):
        _print_summary(results, "Switch Summary")


def switch_project(
    solution: Solution,
    project: Project,
    branch: str | None = None,
    verbose: bool = False,
) -> str:
    """Switch branch for a single project."""
    target_dir = project.resolve_source_dir(solution.directories.projects)

    if not target_dir.exists():
        logger.debug("switch skip {}: not cloned", project.name)
        console.print(f"[yellow]Skip[/yellow] {project.name} (not cloned)")
        return "skipped"

    if project.git is None:
        logger.error("switch {}: no git configuration", project.name)
        console.print(f"[red]Error:[/red] Project {project.name} has no git configuration")
        return "failed"

    target_branch = branch or project.git.branch or solution.default_branch
    logger.info("switch {} → {}", project.name, target_branch)
    console.print(f"[blue]Switching[/blue] {project.name} to {target_branch}...")

    cmd = ["git", "-C", str(target_dir), "checkout", target_branch]
    logger.debug("$ {}", " ".join(cmd))
    if verbose:
        console.print(f"  $ {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=not verbose)
    if result.returncode != 0:
        stderr = result.stderr.decode() if result.stderr else ""
        logger.error("switch {} failed (exit {}): {}", project.name, result.returncode, stderr)
        console.print(f"[red]Failed[/red] to switch {project.name}")
        if not verbose and stderr:
            console.print(stderr)
        return "failed"

    logger.info("switch {} completed", project.name)
    console.print(f"[green]Switched[/green] {project.name} to {target_branch}")
    return "switched"


def _last_log_line(log_path: Path | None) -> str | None:
    """Return last non-empty line from log file, truncated to 80 chars."""
    if log_path is None or not log_path.exists():
        return None
    lines = log_path.read_text(errors="replace").splitlines()
    for line in reversed(lines):
        stripped = line.strip()
        if stripped:
            return stripped[:80]
    return None


def _print_summary(results: list[tuple[str, str]], title: str) -> None:
    """Print a generic 2-column summary table (Name, Status)."""
    table = Table(title=title)
    table.add_column("Name", style="cyan")
    table.add_column("Status", justify="center")

    for name, status in results:
        if status == "failed":
            table.add_row(name, "[red]Failed[/red]")
        elif status == "skipped":
            table.add_row(name, "[yellow]Skipped[/yellow]")
        else:
            table.add_row(name, f"[green]{status.title()}[/green]")

    console.print(table)

    succeeded = sum(1 for _, s in results if s not in ("failed", "skipped"))
    skipped = sum(1 for _, s in results if s == "skipped")
    failed = sum(1 for _, s in results if s == "failed")

    if failed:
        parts = []
        if succeeded:
            parts.append(f"{succeeded} succeeded")
        if skipped:
            parts.append(f"{skipped} skipped")
        parts.append(f"[red]{failed} failed[/red]")
        console.print(f"[bold]{', '.join(parts)}[/bold]")
    else:
        parts = [f"{succeeded} succeeded"]
        if skipped:
            parts.append(f"{skipped} skipped")
        console.print(f"[bold green]{', '.join(parts)}[/bold green]")


def _print_build_summary(results: list[tuple[str, str, Path | None]]) -> None:
    """Print a build summary table."""
    table = Table(title="Build Summary")
    table.add_column("Project", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Info", style="dim")

    for name, status, log_path in results:
        if status == "built":
            table.add_row(name, "[green]Built[/green]", "")
        elif status == "skipped":
            table.add_row(name, "[yellow]Skipped[/yellow]", "not cloned")
        else:
            info = _last_log_line(log_path) or (str(log_path) if log_path else "")
            table.add_row(name, "[red]Failed[/red]", info)

    console.print(table)

    built = sum(1 for _, s, _ in results if s == "built")
    failed = sum(1 for _, s, _ in results if s == "failed")
    if failed:
        console.print(f"[bold]{built} built, [red]{failed} failed[/red][/bold]")
    else:
        console.print(f"[bold green]{built} built successfully[/bold green]")


def build_projects(
    solution: Solution,
    projects: list[Union[Project, "Service"]],
    verbose: bool = False,
    no_cache: bool = False,
    keep_going: bool = False,
) -> None:
    """Build projects in dependency order."""
    # Filter to actual projects
    project_list = [p for p in projects if isinstance(p, Project)]

    # Build dependency graph
    try:
        ordered = resolve_build_order(solution, project_list)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    console.print(f"[bold]Building {len(ordered)} projects in dependency order[/bold]")

    results: list[tuple[str, str, Path | None]] = []
    for project in ordered:
        status, log_path = build_project(solution, project, verbose=verbose, no_cache=no_cache)
        results.append((project.name or "", status, log_path))
        if status == "failed" and not keep_going:
            break

    if len(ordered) > 1 or (results and results[0][1] == "failed"):
        _print_build_summary(results)


def resolve_build_order(solution: Solution, projects: list[Project]) -> list[Project]:
    """Resolve build order using topological sort."""
    # Build dependency graph
    # Each project maps to its dependencies
    graph: dict[str, set[str]] = {}

    for project in projects:
        assert project.name is not None, "Project has no name — config loading bug"
        deps: set[str] = set()
        for dep in project.depends_on:
            assert dep.name is not None, "Dependency has no name — config loading bug"
            deps.add(dep.name)
        graph[project.name] = deps

    # Topological sort
    try:
        sorted_names = toposort_flatten(graph)
    except CircularDependencyError as e:
        # Extract the cycle description from the exception data
        cycle_parts = " → ".join(str(k) for k in e.data)
        raise ValueError(
            f"Circular dependency detected: {cycle_parts}\n"
            f"Fix the dependency cycle in your project definitions."
        ) from e

    # Map back to projects, including dependencies not in original list
    result: list[Project] = []
    seen: set[str] = set()

    for name in sorted_names:
        if name in seen:
            continue
        seen.add(name)

        # Find project in our input list or in solution
        p = next((p for p in projects if p.name == name), None)
        if p is None:
            # It's a dependency not in the build list - get from solution
            p = solution.get_project(name)

        if p:
            result.append(p)

    return result


def build_project(
    solution: Solution, project: Project, verbose: bool = False, no_cache: bool = False
) -> tuple[str, Path | None]:
    """Build a single project. Returns (status, log_path); status is 'built'/'failed'/'skipped'."""
    source_dir = project.resolve_source_dir(solution.directories.projects)

    if not source_dir.exists():
        logger.debug("build skip {}: not cloned", project.name)
        console.print(f"[yellow]Skip[/yellow] {project.name} (not cloned)")
        return "skipped", None

    logger.info("build {} (no_cache={})", project.name, no_cache)
    console.print(f"[blue]Building[/blue] {project.name}...")

    from localbox.builders.build import run_builder

    logs_dir = solution.directories.build / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_name = project.path_name.replace(":", "-")
    log_path = logs_dir / f"{log_name}.log"

    success = run_builder(
        solution, project, source_dir, verbose=verbose, no_cache=no_cache, log_path=log_path
    )

    if success:
        _write_last_build(source_dir)
        logger.info("build {} completed", project.name)
        console.print(f"[green]Built[/green] {project.name}")
        return "built", log_path
    else:
        logger.error("build {} failed", project.name)
        console.print(f"[red]Failed[/red] to build {project.name}")
        console.print(f"[dim]  Log: {log_path}[/dim]")
        return "failed", log_path


def show_project_status(
    solution: Solution,
    projects: list[Union[Project, "Service"]],
) -> None:
    """Show status of projects."""
    table = Table(title="Project Status")
    table.add_column("Project", style="cyan")
    table.add_column("Cloned", justify="center")
    table.add_column("Branch", style="yellow")
    table.add_column("Last Build", style="dim")

    for project in projects:
        if not isinstance(project, Project):
            continue

        project_dir = project.resolve_source_dir(solution.directories.projects)
        cloned = project_dir.exists()

        # Branch
        branch = "-"
        if cloned:
            result = subprocess.run(
                ["git", "-C", str(project_dir), "branch", "--show-current"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()

        # Last build
        if cloned:
            last_build_dt = _read_last_build(project_dir)
            last_build = _format_age(last_build_dt) if last_build_dt else "never"
        else:
            last_build = "-"

        table.add_row(
            project.name,
            "[green]Yes[/green]" if cloned else "[dim]No[/dim]",
            branch,
            last_build,
        )

    console.print(table)
