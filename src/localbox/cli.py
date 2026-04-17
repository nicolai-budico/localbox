"""CLI entry point for localbox.

The CLI uses a domain-first grammar: ``localbox <domain> <command> [args…]``,
where ``<domain>`` is one of ``projects``, ``services``, ``compose``,
``override``, ``solution``. Utility commands that are not scoped to a
single domain (``doctor``, ``config``, ``completion``, ``purge``, ``prune``)
remain top-level.
"""

import ast
import re
import sys
from datetime import datetime, timezone
from importlib.metadata import entry_points
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.tree import Tree

from localbox import __version__
from localbox.config import (
    CONFIG_FILE,
    OVERRIDE_FILE,
    Solution,
    SolutionNotFoundError,
    _env_to_dict,
    create_default_solution,
    find_solution_root,
    load_solution,
)
from localbox.models.builder import CacheVolume
from localbox.models.project import Project
from localbox.models.service import Service
from localbox.utils.resolver import TargetError, resolve_targets

console = Console()

# Store solution in context
pass_solution = click.make_pass_decorator(Solution, ensure=True)


class LocalboxContext:
    """Context object for CLI commands."""

    def __init__(self) -> None:
        self.solution: Solution | None = None
        self.verbose: bool = False


pass_context = click.make_pass_decorator(LocalboxContext, ensure=True)


def load_solution_or_exit() -> Solution:
    """Load solution or exit with error message."""
    from localbox.log import setup_logging

    try:
        solution = load_solution()
        setup_logging(solution.root)
        logger.info("localbox {}", " ".join(sys.argv[1:]))
        return solution
    except SolutionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _complete_domain_targets(incomplete: str, domain: str) -> list[str]:
    """Shared completion helper: emit short-form tokens for one domain."""
    try:
        solution = load_solution()
    except Exception:
        return []

    suggestions: list[str] = []
    if domain == "projects":
        for g in solution.get_project_groups():
            suggestions.append(g)
        for p in solution.projects.values():
            if p.group:
                suggestions.append(f"{p.group}:{p.local_name}")
            else:
                suggestions.append(p.name or "")
    elif domain == "services":
        for g in solution.get_service_groups():
            suggestions.append(g)
        for s in solution.services.values():
            if s.group:
                suggestions.append(f"{s.group}:{s.local_name}")
            else:
                suggestions.append(s.name or "")
    return [s for s in suggestions if s and s.startswith(incomplete)]


def complete_project_targets(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[str]:
    """Shell completion for short-form project targets."""
    return _complete_domain_targets(incomplete, "projects")


def complete_service_targets(
    ctx: click.Context, param: click.Parameter, incomplete: str
) -> list[str]:
    """Shell completion for short-form service targets."""
    return _complete_domain_targets(incomplete, "services")


@click.group(invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, version: bool) -> None:
    """Localbox - Development environment orchestrator.

    Manage Git repositories, Docker builds, and service orchestration.

    The CLI uses domain-first grammar: `localbox <domain> <command> [args…]`.
    Domains: projects, services, compose, override, solution.
    """
    ctx.ensure_object(LocalboxContext)
    ctx.obj.verbose = verbose

    if version:
        console.print(f"localbox version {__version__}")
        sys.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =============================================================================
# Domain groups
# =============================================================================


@cli.group()
def projects() -> None:
    """Manage project repositories and builds."""
    pass


@cli.group()
def services() -> None:
    """Manage service images."""
    pass


@cli.group()
def compose() -> None:
    """Docker Compose operations."""
    pass


@cli.group()
def override() -> None:
    """Manage per-developer solution-override.py."""
    pass


@cli.group()
def solution() -> None:
    """Manage the solution scaffold."""
    pass


# =============================================================================
# Top-level utility commands
# =============================================================================


@cli.command()
def doctor() -> None:
    """Check system requirements for localbox."""
    import re
    import shutil
    import subprocess

    all_ok = True

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {icon} {label}: {detail}")
        if not ok:
            all_ok = False

    console.print("[bold]Checking system requirements...[/bold]")
    console.print()

    # Python version
    vi = sys.version_info
    py_version = f"{vi.major}.{vi.minor}.{vi.micro}"
    check("Python", vi >= (3, 10), py_version + ("" if vi >= (3, 10) else " — requires 3.10+"))

    # Git
    if shutil.which("git"):
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        raw = result.stdout.strip()  # "git version 2.43.0"
        m = re.search(r"(\d+)\.(\d+)", raw)
        if m:
            major, minor = int(m.group(1)), int(m.group(2))
            ok = (major, minor) >= (2, 0)
            check("Git", ok, f"{major}.{minor}" + ("" if ok else " — requires 2.0+"))
        else:
            check("Git", False, f"could not parse version from: {raw!r}")
    else:
        check("Git", False, "not found in PATH")

    # Docker CLI
    if shutil.which("docker"):
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        raw = result.stdout.strip()  # "Docker version 27.3.1, build ..."
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", raw)
        if m:
            major, minor = int(m.group(1)), int(m.group(2))
            ok = (major, minor) >= (20, 10)
            check("Docker Engine", ok, f"{m.group(0)}" + ("" if ok else " — requires 20.10+"))
        else:
            check("Docker Engine", False, f"could not parse version from: {raw!r}")

        # Docker daemon running
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        daemon_ok = result.returncode == 0
        check(
            "Docker daemon",
            daemon_ok,
            "running" if daemon_ok else "not running — start Docker and retry",
        )

        # Docker Compose V2
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        if result.returncode == 0:
            raw = result.stdout.strip()  # "Docker Compose version v2.27.0"
            m = re.search(r"v?(\d+\.\d+\.\d+)", raw)
            version_str = m.group(1) if m else raw
            check("Docker Compose V2", True, version_str)
        else:
            check("Docker Compose V2", False, "not found — install the Compose plugin")

        # BuildKit / buildx
        result = subprocess.run(["docker", "buildx", "version"], capture_output=True, text=True)
        if result.returncode == 0:
            raw = result.stdout.strip().splitlines()[0]
            m = re.search(r"v?(\d+\.\d+\.\d+)", raw)
            version_str = m.group(1) if m else raw
            check("BuildKit (buildx)", True, version_str)
        else:
            check("BuildKit (buildx)", False, "not found — enable BuildKit or update Docker")
    else:
        check("Docker Engine", False, "not found in PATH")
        check("Docker daemon", False, "skipped (Docker not found)")
        check("Docker Compose V2", False, "skipped (Docker not found)")
        check("BuildKit (buildx)", False, "skipped (Docker not found)")

    console.print()
    if all_ok:
        console.print("[green bold]All checks passed.[/green bold]")
    else:
        console.print(
            "[red bold]Some checks failed. Fix the issues above before using localbox.[/red bold]"
        )
        sys.exit(1)


@cli.command()
def config() -> None:
    """Show current solution configuration."""
    sol = load_solution_or_exit()

    console.print(f"[bold]Solution:[/bold] {sol.root}")
    console.print(f"[bold]Default branch:[/bold] {sol.default_branch}")
    console.print()

    console.print("[bold]Directories:[/bold]")
    console.print(f"  Build:      {sol.directories.build}")
    console.print(f"  Projects:   {sol.directories.projects}")
    console.print()

    console.print("[bold]Docker:[/bold]")
    console.print(f"  Compose project: {sol.docker.compose_project}")
    console.print(f"  Network:         {sol.docker.network}")
    console.print()

    console.print(f"[bold]Projects:[/bold] {len(sol.projects)}")
    console.print(f"[bold]Services:[/bold] {len(sol.services)}")


@cli.command("completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]), default="bash")
def completion(shell: str) -> None:
    """Generate shell completion script.

    Install with:
        localbox completion bash > ~/.local/share/bash-completion/completions/localbox
        source ~/.local/share/bash-completion/completions/localbox
    """
    import os
    import subprocess
    from importlib.resources import files

    if shell == "bash":
        script_path = files("localbox.completions").joinpath("localbox.bash")
        print(script_path.read_text())
    elif shell == "zsh":
        result = subprocess.run(
            ["localbox"],
            env={**os.environ, "_LOCALBOX_COMPLETE": "zsh_source"},
            capture_output=True,
            text=True,
        )
        print(result.stdout)
    elif shell == "fish":
        result = subprocess.run(
            ["localbox"],
            env={**os.environ, "_LOCALBOX_COMPLETE": "fish_source"},
            capture_output=True,
            text=True,
        )
        print(result.stdout)


@cli.command()
def purge() -> None:
    """Remove entire .build/ directory (caches, logs, all build artifacts)."""
    import shutil

    sol = load_solution_or_exit()
    build_dir = sol.directories.build
    if build_dir.exists():
        shutil.rmtree(build_dir)
        console.print("[green]Removed[/green] .build/")
    else:
        console.print("[yellow]Skip[/yellow] .build/ (does not exist)")


# =============================================================================
# Prune group (top-level)
# =============================================================================


@cli.group()
def prune() -> None:
    """Remove localbox-managed artifacts."""
    pass


@prune.command("caches")
@click.argument("names", nargs=-1)
def prune_caches(names: tuple[str, ...]) -> None:
    """Remove builder cache directories. Optionally specify names (maven, gradle, node).

    Examples:
        localbox prune caches              # remove all caches
        localbox prune caches maven        # remove only maven cache
        localbox prune caches gradle node  # remove gradle and node, keep maven
    """
    import shutil

    sol = load_solution_or_exit()
    build_dir = sol.directories.build

    if names:
        targets_to_remove = list(names)
    else:
        seen: set[str] = set()
        for project in sol.projects.values():
            if project.builder:
                for vol in project.builder.volumes:
                    if isinstance(vol, CacheVolume):
                        seen.add(vol.name)
        targets_to_remove = sorted(seen)

    if not targets_to_remove:
        console.print("[yellow]No caches found.[/yellow]")
        return

    for name in targets_to_remove:
        cache_dir = build_dir / name
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            console.print(f"[green]Removed[/green] .build/{name}")
        else:
            console.print(f"[yellow]Skip[/yellow] .build/{name} (does not exist)")


@prune.command("builders")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@pass_context
def prune_builders(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Remove builder Docker images.

    Examples:
        localbox prune builders          # remove all builder images
        localbox prune builders api      # remove image for a specific project
        localbox prune builders libs     # remove images for all projects in 'libs'
    """
    sol = load_solution_or_exit()
    _prune_docker_images(sol, "builder", targets, verbose=ctx.verbose)


@prune.command("images")
@click.argument("targets", nargs=-1, shell_complete=complete_service_targets)
@pass_context
def prune_images(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Remove service Docker images.

    Examples:
        localbox prune images            # remove all service images
        localbox prune images db         # remove images for all services in 'db'
        localbox prune images db:primary # remove one specific service image
    """
    sol = load_solution_or_exit()
    _prune_docker_images(sol, "service", targets, verbose=ctx.verbose)


@prune.command("all")
@click.pass_context
def prune_all(ctx: click.Context) -> None:
    """Remove all caches, builder images, and service images."""
    ctx.invoke(prune_caches)
    ctx.invoke(prune_builders)
    ctx.invoke(prune_images)


def _prune_docker_images(
    sol: Solution, image_type: str, targets: tuple[str, ...], verbose: bool = False
) -> None:
    """Remove Docker images of the given type (builder or service)."""
    import subprocess

    reference = f"{sol.name}/{image_type}/*"
    ls_cmd = [
        "docker",
        "image",
        "ls",
        "--filter",
        f"reference={reference}",
        "--format",
        "{{.Repository}}:{{.Tag}}",
    ]
    if verbose:
        console.print(f"  $ {' '.join(ls_cmd)}")
    result = subprocess.run(ls_cmd, capture_output=True, text=True)
    all_images = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    if targets:
        try:
            items = resolve_targets(
                sol,
                targets,
                "projects" if image_type == "builder" else "services",
            )
        except TargetError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
        fragments = {f"/{image_type}/{item.path_name}:" for item in items}
        images = [img for img in all_images if any(f in img for f in fragments)]
    else:
        images = all_images

    if not images:
        console.print(f"[yellow]No {image_type} images found.[/yellow]")
        return

    for image in images:
        r = subprocess.run(["docker", "image", "rm", image], capture_output=True, text=True)
        if r.returncode == 0:
            console.print(f"[green]Removed[/green] {image}")
        else:
            console.print(f"[red]Failed[/red] {image}: {r.stderr.strip()}")


# =============================================================================
# projects domain
# =============================================================================


def _project_sort_key(p: Project) -> str:
    return p.path_name


def _service_sort_key(s: Service) -> str:
    return s.path_name


def list_projects(sol: Solution) -> None:
    """Display projects as a tree."""
    if not sol.projects:
        console.print("[yellow]No projects defined.[/yellow]")
        return

    tree = Tree("[bold]Projects[/bold]")

    ungrouped = [p for p in sol.projects.values() if not p.group]
    groups = sol.get_project_groups()

    for project in sorted(ungrouped, key=_project_sort_key):
        add_project_to_tree(tree, project)

    for group in sorted(groups):
        group_tree = tree.add(f"[bold cyan]{group}/[/bold cyan]")
        projs = sorted(sol.get_projects_in_group(group), key=_project_sort_key)
        for project in projs:
            add_project_to_tree(group_tree, project)

    console.print(tree)


def add_project_to_tree(tree: Tree, project: Project) -> None:
    """Add a project to the tree display."""
    name = project.local_name or project.name

    details = ""
    if project.builder and project.builder.docker_image:
        if project.builder.docker_image.image:
            details = project.builder.docker_image.image
        elif project.builder.docker_image.dockerfile:
            details = "Dockerfile"

    tree.add(f"{name} [dim]{details}[/dim]")


def list_services(sol: Solution) -> None:
    """Display services as a tree."""
    if not sol.services:
        console.print("[yellow]No services defined.[/yellow]")
        return

    tree = Tree("[bold]Services[/bold]")

    ungrouped = [s for s in sol.services.values() if not s.group]
    for service in sorted(ungrouped, key=_service_sort_key):
        add_service_to_tree(tree, service)

    for group in sorted(sol.get_service_groups()):
        group_tree = tree.add(f"[bold cyan]{group}/[/bold cyan]")
        svcs = sorted(sol.get_services_in_group(group), key=_service_sort_key)
        for service in svcs:
            add_service_to_tree(group_tree, service)

    console.print(tree)


def add_service_to_tree(tree: Tree, service: Service) -> None:
    """Add a service to the tree display."""
    name = service.local_name or service.name
    image_info = service.image.image or service.image.name or ""

    tree.add(f"{name} [dim]{image_info}[/dim]")


@projects.command("list")
def projects_list() -> None:
    """List all projects as a tree."""
    sol = load_solution_or_exit()
    list_projects(sol)


@projects.command("clone")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@pass_context
def projects_clone(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Clone project repositories."""
    sol = load_solution_or_exit()

    try:
        projs = resolve_targets(sol, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projs:
        console.print("[yellow]No projects to clone.[/yellow]")
        return

    from localbox.commands.project import clone_projects

    clone_projects(sol, projs, verbose=ctx.verbose)


@projects.command("fetch")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@pass_context
def projects_fetch(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Fetch (git pull) project repositories."""
    sol = load_solution_or_exit()

    try:
        projs = resolve_targets(sol, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projs:
        console.print("[yellow]No projects to fetch.[/yellow]")
        return

    from localbox.commands.project import fetch_projects

    fetch_projects(sol, projs, verbose=ctx.verbose)


@projects.command("switch")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@click.option("--branch", "-b", help="Branch to switch to (default: solution default)")
@pass_context
def projects_switch(ctx: LocalboxContext, targets: tuple[str, ...], branch: str | None) -> None:
    """Switch project branches."""
    sol = load_solution_or_exit()

    try:
        projs = resolve_targets(sol, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projs:
        console.print("[yellow]No projects to switch.[/yellow]")
        return

    from localbox.commands.project import switch_projects

    switch_projects(sol, projs, branch=branch, verbose=ctx.verbose)


@projects.command("build")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@click.option("--no-cache", is_flag=True, help="Build without Docker layer cache")
@click.option(
    "--keep-going",
    "-k",
    is_flag=True,
    help="Continue building remaining projects after a failure (default: stop on first error)",
)
@pass_context
def projects_build(
    ctx: LocalboxContext,
    targets: tuple[str, ...],
    no_cache: bool,
    keep_going: bool,
) -> None:
    """Build projects.

    Examples:
        localbox projects build                # Build all projects
        localbox projects build api            # Build single project
        localbox projects build be fe          # Build two groups
        localbox projects build be:api workers # Qualified name plus whole group
    """
    sol = load_solution_or_exit()

    try:
        projs = resolve_targets(sol, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projs:
        console.print("[yellow]No projects to build.[/yellow]")
        return

    from localbox.commands.project import build_projects

    build_projects(sol, projs, verbose=ctx.verbose, no_cache=no_cache, keep_going=keep_going)


@projects.command("status")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@pass_context
def projects_status(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Show git status of projects."""
    sol = load_solution_or_exit()

    try:
        projs = resolve_targets(sol, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    from localbox.commands.project import show_project_status

    show_project_status(sol, projs)


@projects.command("clean")
@click.argument("targets", nargs=-1, shell_complete=complete_project_targets)
@pass_context
def projects_clean(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Run builder clean for projects (mvn clean, gradle clean, rm node_modules).

    Examples:
        localbox projects clean          # clean all projects
        localbox projects clean api      # clean single project
        localbox projects clean libs     # clean a whole group
    """
    from localbox.builders.build import run_builder_clean
    from localbox.commands.project import _print_summary

    sol = load_solution_or_exit()
    try:
        projs = resolve_targets(sol, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)
    results: list[tuple[str, str]] = []
    for project in projs:
        if not isinstance(project, Project):
            continue
        source_dir = project.resolve_source_dir(sol.directories.projects)
        if not source_dir.exists():
            console.print(f"[yellow]Skip[/yellow] {project.name} (not cloned)")
            results.append((project.name or "", "skipped"))
            continue
        console.print(f"[bold]Cleaning[/bold] {project.name}")
        ok = run_builder_clean(sol, project, source_dir, verbose=ctx.verbose)
        results.append((project.name or "", "cleaned" if ok else "failed"))
    if len(results) > 1 or any(s == "failed" for _, s in results):
        _print_summary(results, "Clean Summary")
    if any(s == "failed" for _, s in results):
        sys.exit(1)


# =============================================================================
# services domain
# =============================================================================


@services.command("list")
def services_list() -> None:
    """List all services as a tree."""
    sol = load_solution_or_exit()
    list_services(sol)


@services.command("build")
@click.argument("targets", nargs=-1, shell_complete=complete_service_targets)
@click.option("--no-cache", is_flag=True, help="Build without Docker layer cache")
@pass_context
def services_build(ctx: LocalboxContext, targets: tuple[str, ...], no_cache: bool) -> None:
    """Build service Docker images.

    Examples:
        localbox services build              # Build all service images
        localbox services build db:primary   # Build one service image
        localbox services build db cache     # Build two groups
    """
    sol = load_solution_or_exit()

    try:
        svcs = resolve_targets(sol, targets, "services")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not svcs:
        console.print("[yellow]No services to build.[/yellow]")
        return

    from localbox.commands.service import build_images

    build_images(sol, svcs, verbose=ctx.verbose, no_cache=no_cache)


# =============================================================================
# compose domain
# =============================================================================


@compose.command("generate")
def compose_generate() -> None:
    """Generate docker-compose.yml from service definitions."""
    sol = load_solution_or_exit()

    from localbox.builders.compose import generate_compose_file

    try:
        generate_compose_file(sol)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# =============================================================================
# solution domain
# =============================================================================


@solution.command("init")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
def solution_init(force: bool) -> None:
    """Initialize a new localbox solution in the current directory."""
    config_path = Path.cwd() / CONFIG_FILE

    if config_path.exists() and not force:
        console.print(
            f"[yellow]Warning:[/yellow] {CONFIG_FILE} already exists. Use --force to overwrite."
        )
        sys.exit(1)

    config_path.write_text(create_default_solution())
    console.print(f"[green]Created[/green] {CONFIG_FILE}")

    for folder in ["assets", "patches"]:
        folder_path = Path.cwd() / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]Created[/green] {folder}/")

    gitignore = Path.cwd() / ".gitignore"
    ignore_entries = [".logs/", OVERRIDE_FILE, ".build/"]
    existing = gitignore.read_text() if gitignore.exists() else ""
    additions = [e for e in ignore_entries if e not in existing.splitlines()]
    if additions:
        with open(gitignore, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("\n".join(additions) + "\n")
        console.print("[green]Updated[/green] .gitignore")

    console.print("\n[bold]Solution initialized![/bold]")


# =============================================================================
# override domain
# =============================================================================


class _ParsedOverride:
    """Values extracted from an existing solution-override.py."""

    def __init__(self) -> None:
        # env key → literal value string, e.g. '"secret"' or "'pass'"
        self.env: dict[str, str] = {}
        # solution.config.ATTR → literal value string
        self.config: dict[str, str] = {}
        # "p.group.name" → {"path": literal, "branch": literal}
        self.projects: dict[str, dict[str, str]] = {}


def _rhs_source(line: str) -> str | None:
    """Extract the source text of the assignment RHS using the AST.

    Using ast.parse() rather than regex ensures that '#' characters inside
    string literals are never mistaken for comment markers.
    Returns None if the line is not a simple assignment or cannot be parsed.
    """
    try:
        tree = ast.parse(line, mode="exec")
    except SyntaxError:
        return None
    if not tree.body or not isinstance(tree.body[0], ast.Assign):
        return None
    node = tree.body[0].value
    if node.end_col_offset is None:
        return None
    return line[node.col_offset : node.end_col_offset]


def _parse_existing_override(path: Path) -> _ParsedOverride:
    """Extract uncommented, non-None assignments from an existing solution-override.py.

    Only reads lines that were actively set (not commented out and not None),
    so the values can be carried into a freshly generated template.
    """
    result = _ParsedOverride()
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # solution.config.env.KEY = VALUE  (class-based env)
        m = re.match(r"^solution\.config\.env\.(\w+)\s*=", stripped)
        if m:
            val = _rhs_source(stripped)
            if val and val != "None":
                result.env[m.group(1)] = val
            continue

        # solution.config.env["KEY"] = VALUE  (dict-based env)
        m = re.match(r'^solution\.config\.env\["(\w+)"\]\s*=', stripped)
        if m:
            val = _rhs_source(stripped)
            if val and val != "None":
                result.env[m.group(1)] = val
            continue

        # solution.config.ATTR = VALUE  (build_dir, project_dir, default_branch, …)
        m = re.match(r"^solution\.config\.(\w+)\s*=", stripped)
        if m:
            attr = m.group(1)
            if attr != "env":
                val = _rhs_source(stripped)
                if val:
                    result.config[attr] = val
            continue

        # p.group.name.path = VALUE  /  p.group.name.branch = VALUE
        m = re.match(r"^(p(?:\.\w+)+)\.(path|branch)\s*=", stripped)
        if m:
            val = _rhs_source(stripped)
            if val:
                result.projects.setdefault(m.group(1), {})[m.group(2)] = val

    return result


@override.command("init")
@click.option("--force", "-f", is_flag=True, help="Regenerate and merge existing values.")
def override_init(force: bool) -> None:
    """Create solution-override.py with per-developer override template.

    When run with --force on an existing file, values already set in the old file
    are carried into the new template automatically. The old file is preserved as
    solution-override-<timestamp>.py.
    """
    try:
        solution_root = find_solution_root()
    except SolutionNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    override_path = solution_root / OVERRIDE_FILE
    old: _ParsedOverride | None = None

    if override_path.exists():
        if not force:
            console.print(
                f"[yellow]Warning:[/yellow] {OVERRIDE_FILE} already exists. "
                "Use --force to regenerate and merge."
            )
            sys.exit(1)

        # Parse and backup BEFORE loading the solution so the solution is loaded
        # from solution.py only — giving us the clean schema (required vs optional).
        old = _parse_existing_override(override_path)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup = override_path.with_name(f"solution-override-{ts}.py")
        override_path.rename(backup)
        console.print(f"[dim]Backup:[/dim] {backup.name}")

    # Load without the override so env schema (None = required) is preserved.
    try:
        sol = load_solution(solution_root)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    override_path.write_text(_generate_override_template(sol, old=old))
    console.print(f"[green]Created[/green] {OVERRIDE_FILE}")

    # Add to .gitignore
    gitignore = sol.root / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if OVERRIDE_FILE not in existing:
        with open(gitignore, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"{OVERRIDE_FILE}\n")
        console.print("[green]Updated[/green] .gitignore")


def _generate_override_template(sol: Solution, old: _ParsedOverride | None = None) -> str:
    """Generate solution-override.py content from the loaded solution.

    If ``old`` is provided, values previously set in the old override are
    carried into the new template (env vars, solution settings, project paths).
    """

    def _cfg(attr: str, default: str) -> str:
        """Emit a solution.config line: uncommented if old had it set, else commented."""
        if old and attr in old.config:
            return f"solution.config.{attr} = {old.config[attr]}"
        return f"# solution.config.{attr} = {default!r}"

    lines = [
        f"# {OVERRIDE_FILE} — per-developer local overrides. DO NOT COMMIT.",
        "# Run `localbox override init --force` to regenerate and merge.",
        "",
        "import solution",
    ]

    if sol.projects:
        lines.append("import projects as p")

    # Detect env style: class-based or dict-based
    raw_env = sol.config.env if sol.config else {}
    is_class_env = not isinstance(raw_env, dict)

    # Solution settings
    build_dir = sol.config.build_dir if sol.config else ".build"
    default_branch = sol.config.default_branch if sol.config else "dev"
    lines += [
        "",
        "# ── Solution settings ─────────────────────────────────────────────────",
        _cfg("default_branch", default_branch),
        _cfg("build_dir", build_dir),
        _cfg("project_dir", f"{build_dir}/projects")
        + (
            ""
            if (old and "project_dir" in old.config)
            else "  # Override to point all projects to a shared directory"
        ),
        _cfg("registry", "registry.io/myteam")
        + (
            "" if (old and "registry" in old.config) else "  # Docker registry prefix for push/pull"
        ),
    ]

    # Env vars — required (val is None) first, optional (val set) second
    env_dict = _env_to_dict(raw_env)
    if env_dict:
        required = {k: v for k, v in env_dict.items() if v is None}
        optional = {k: v for k, v in env_dict.items() if v is not None}

        if required:
            lines += [
                "",
                "# ── Required environment variables ─────────────────────────────────────",
            ]
            for key in sorted(required):
                merged = old.env.get(key) if old else None
                if merged is not None:
                    # Value was set in old override — restore it
                    if is_class_env:
                        lines.append(f"solution.config.env.{key} = {merged}")
                    else:
                        lines.append(f'solution.config.env["{key}"] = {merged}')
                else:
                    if is_class_env:
                        lines.append(f"solution.config.env.{key} = None  # REQUIRED — set a value")
                    else:
                        lines.append(
                            f'solution.config.env["{key}"] = None  # REQUIRED — set a value'
                        )

        if optional:
            lines += [
                "",
                "# ── Optional environment variables ─────────────────────────────────────",
            ]
            for key in sorted(optional):
                val = optional[key]
                quoted = f'"{val}"' if isinstance(val, str) else repr(val)
                old_val = old.env.get(key) if old else None
                if old_val is not None:
                    # Was explicitly set in old override — restore uncommented
                    if is_class_env:
                        lines.append(f"solution.config.env.{key} = {old_val}")
                    else:
                        lines.append(f'solution.config.env["{key}"] = {old_val}')
                else:
                    if is_class_env:
                        lines.append(f"# solution.config.env.{key} = {quoted}")
                    else:
                        lines.append(f'# solution.config.env["{key}"] = {quoted}')

    # Project path overrides
    if sol.projects:
        lines += [
            "",
            "# ── Project source paths ───────────────────────────────────────────────",
            "# Override if a project is in a non-standard location:",
        ]
        for proj_name in sorted(sol.projects):
            attr = proj_name.replace(":", ".").replace("-", "_")
            ref = f"p.{attr}"
            old_path = old.projects.get(ref, {}).get("path") if old else None
            if old_path is not None:
                lines.append(f"{ref}.path = {old_path}")
            else:
                lines.append(f'# {ref}.path = "/absolute/or/relative/path"')

        lines += [
            "",
            "# Override branch for a specific project (e.g. while on a feature branch):",
        ]
        for proj_name in sorted(sol.projects):
            proj = sol.projects[proj_name]
            attr = proj_name.replace(":", ".").replace("-", "_")
            ref = f"p.{attr}"
            old_branch = old.projects.get(ref, {}).get("branch") if old else None
            if old_branch is not None:
                lines.append(f"{ref}.branch = {old_branch}")
            else:
                branch = proj.git.branch if proj.git and proj.git.branch else sol.default_branch
                lines.append(f'# {ref}.branch = "{branch}"')

    lines.append("")
    return "\n".join(lines)


# =============================================================================
# Plugins
# =============================================================================


def _load_plugins() -> None:
    """Load CLI commands contributed by installed plugins.

    Plugins register commands via the ``localbox.commands`` entry-point group:

    .. code-block:: toml

        # In the plugin's pyproject.toml
        [project.entry-points."localbox.commands"]
        quarkus = "localbox_quarkus.cli:quarkus_cmd"

    Each entry point must resolve to a :class:`click.BaseCommand` instance.
    A broken plugin is reported as a warning and skipped so that localbox
    remains usable even if a plugin fails to import.
    """
    for ep in entry_points(group="localbox.commands"):
        try:
            cmd = ep.load()
            cli.add_command(cmd)
        except Exception as exc:
            console.print(f"[yellow]Warning: plugin '{ep.name}' failed to load: {exc}[/yellow]")


def main() -> None:
    """Main entry point."""
    _load_plugins()
    cli()


if __name__ == "__main__":
    main()
