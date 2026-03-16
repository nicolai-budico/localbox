"""CLI entry point for localbox."""

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


def complete_targets(ctx: click.Context, param: click.Parameter, incomplete: str) -> list[str]:
    """Shell completion for targets."""
    try:
        solution = load_solution()
        suggestions = []

        suggestions.append("projects")
        suggestions.append("services")

        for g in solution.get_project_groups():
            suggestions.append(f"projects:{g}")

        for p in solution.projects.values():
            suggestions.append(f"projects:{p.name}")

        for g in solution.get_service_groups():
            suggestions.append(f"services:{g}")

        for s in solution.services.values():
            suggestions.append(f"services:{s.name}")

        return [s for s in suggestions if s.startswith(incomplete)]

    except Exception:
        return []


@click.group(invoke_without_command=True)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, version: bool) -> None:
    """Localbox - Development environment orchestrator.

    Manage Git repositories, Docker builds, and service orchestration.
    """
    ctx.ensure_object(LocalboxContext)
    ctx.obj.verbose = verbose

    if version:
        console.print(f"localbox version {__version__}")
        sys.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =============================================================================
# Utility Commands
# =============================================================================


@cli.command()
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config")
def init(force: bool) -> None:
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
@click.option(
    "--build",
    "clean_build",
    is_flag=True,
    help="Remove entire .build/ directory (all caches)",
)
@click.option(
    "--compose", "clean_compose", is_flag=True, help="Remove generated docker-compose.yml"
)
def clean(clean_build: bool, clean_compose: bool) -> None:
    """Remove build caches and generated files.

    Examples:
        localbox clean --build             # Remove entire .build/ directory (caches)
        localbox clean --compose           # Remove docker-compose.yml
        localbox clean --build --compose   # Remove everything generated
    """
    import shutil

    if not clean_build and not clean_compose:
        console.print("[yellow]Nothing to clean. Use --build / --compose.[/yellow]")
        console.print("Run [bold]localbox clean --help[/bold] for usage.")
        return

    solution = load_solution_or_exit()

    # --- Entire .build/ directory ---
    if clean_build:
        build_dir = solution.directories.build
        if build_dir.exists():
            shutil.rmtree(build_dir)
            console.print(f"[green]Removed[/green] {build_dir.relative_to(solution.root)}/")
        else:
            console.print("[yellow]Skip[/yellow] .build/ (does not exist)")

    # --- Generated docker-compose.yml ---
    if clean_compose:
        compose_file = solution.root / "docker-compose.yml"
        if compose_file.exists():
            compose_file.unlink()
            console.print("[green]Removed[/green] docker-compose.yml")
        else:
            console.print("[yellow]Skip[/yellow] docker-compose.yml (does not exist)")


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


@cli.command("init-override")
@click.option("--force", "-f", is_flag=True, help="Regenerate and merge existing values.")
def init_override(force: bool) -> None:
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
        solution = load_solution(solution_root)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    override_path.write_text(_generate_override_template(solution, old=old))
    console.print(f"[green]Created[/green] {OVERRIDE_FILE}")

    # Add to .gitignore
    gitignore = solution.root / ".gitignore"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if OVERRIDE_FILE not in existing:
        with open(gitignore, "a") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(f"{OVERRIDE_FILE}\n")
        console.print("[green]Updated[/green] .gitignore")


def _generate_override_template(solution: Solution, old: _ParsedOverride | None = None) -> str:
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
        "# Run `localbox init-override --force` to regenerate and merge.",
        "",
        "import solution",
    ]

    if solution.projects:
        lines.append("import projects as p")

    # Detect env style: class-based or dict-based
    raw_env = solution.config.env if solution.config else {}
    is_class_env = not isinstance(raw_env, dict)

    # Solution settings
    build_dir = solution.config.build_dir if solution.config else ".build"
    default_branch = solution.config.default_branch if solution.config else "dev"
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
    if solution.projects:
        lines += [
            "",
            "# ── Project source paths ───────────────────────────────────────────────",
            "# Override if a project is in a non-standard location:",
        ]
        for proj_name in sorted(solution.projects):
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
        for proj_name in sorted(solution.projects):
            proj = solution.projects[proj_name]
            attr = proj_name.replace(":", ".").replace("-", "_")
            ref = f"p.{attr}"
            old_branch = old.projects.get(ref, {}).get("branch") if old else None
            if old_branch is not None:
                lines.append(f"{ref}.branch = {old_branch}")
            else:
                branch = (
                    proj.git.branch if proj.git and proj.git.branch else solution.default_branch
                )
                lines.append(f'# {ref}.branch = "{branch}"')

    lines.append("")
    return "\n".join(lines)


@cli.command()
def config() -> None:
    """Show current solution configuration."""
    solution = load_solution_or_exit()

    console.print(f"[bold]Solution:[/bold] {solution.root}")
    console.print(f"[bold]Default branch:[/bold] {solution.default_branch}")
    console.print()

    console.print("[bold]Directories:[/bold]")
    console.print(f"  Build:      {solution.directories.build}")
    console.print(f"  Projects:   {solution.directories.projects}")
    console.print()

    console.print("[bold]Docker:[/bold]")
    console.print(f"  Compose project: {solution.docker.compose_project}")
    console.print(f"  Network:         {solution.docker.network}")
    console.print()

    console.print(f"[bold]Projects:[/bold] {len(solution.projects)}")
    console.print(f"[bold]Services:[/bold] {len(solution.services)}")


@cli.command("list")
@click.argument("target_type", type=click.Choice(["projects", "services"]))
def list_cmd(target_type: str) -> None:
    """List all projects or services."""
    solution = load_solution_or_exit()

    if target_type == "projects":
        list_projects(solution)
    else:
        list_services(solution)


def _project_sort_key(p: Project) -> str:
    return p.path_name


def _service_sort_key(s: Service) -> str:
    return s.path_name


def list_projects(solution: Solution) -> None:
    """Display projects as a tree."""
    if not solution.projects:
        console.print("[yellow]No projects defined.[/yellow]")
        return

    tree = Tree("[bold]Projects[/bold]")

    ungrouped = [p for p in solution.projects.values() if not p.group]
    groups = solution.get_project_groups()

    for project in sorted(ungrouped, key=_project_sort_key):
        add_project_to_tree(tree, project)

    for group in sorted(groups):
        group_tree = tree.add(f"[bold cyan]{group}/[/bold cyan]")
        projects = sorted(solution.get_projects_in_group(group), key=_project_sort_key)
        for project in projects:
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


def list_services(solution: Solution) -> None:
    """Display services as a tree."""
    if not solution.services:
        console.print("[yellow]No services defined.[/yellow]")
        return

    tree = Tree("[bold]Services[/bold]")

    ungrouped = [s for s in solution.services.values() if not s.group]
    for service in sorted(ungrouped, key=_service_sort_key):
        add_service_to_tree(tree, service)

    for group in sorted(solution.get_service_groups()):
        group_tree = tree.add(f"[bold cyan]{group}/[/bold cyan]")
        services = sorted(solution.get_services_in_group(group), key=_service_sort_key)
        for service in services:
            add_service_to_tree(group_tree, service)

    console.print(tree)


def add_service_to_tree(tree: Tree, service: Service) -> None:
    """Add a service to the tree display."""
    name = service.local_name or service.name
    image_info = service.image.image or service.image.name or ""

    tree.add(f"{name} [dim]{image_info}[/dim]")


# =============================================================================
# Project Commands
# =============================================================================


@cli.command()
@click.argument("targets", nargs=-1, required=True, shell_complete=complete_targets)
@pass_context
def clone(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Clone project repositories."""
    solution = load_solution_or_exit()

    try:
        projects = resolve_targets(solution, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projects:
        console.print("[yellow]No projects to clone.[/yellow]")
        return

    from localbox.commands.project import clone_projects

    clone_projects(solution, projects, verbose=ctx.verbose)


@cli.command()
@click.argument("targets", nargs=-1, required=True, shell_complete=complete_targets)
@pass_context
def fetch(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Fetch (git pull) project repositories."""
    solution = load_solution_or_exit()

    try:
        projects = resolve_targets(solution, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projects:
        console.print("[yellow]No projects to fetch.[/yellow]")
        return

    from localbox.commands.project import fetch_projects

    fetch_projects(solution, projects, verbose=ctx.verbose)


@cli.command("switch")
@click.argument("targets", nargs=-1, required=True, shell_complete=complete_targets)
@click.option("--branch", "-b", help="Branch to switch to (default: solution default)")
@pass_context
def switch_branch(ctx: LocalboxContext, targets: tuple[str, ...], branch: str | None) -> None:
    """Switch project branches."""
    solution = load_solution_or_exit()

    try:
        projects = resolve_targets(solution, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if not projects:
        console.print("[yellow]No projects to switch.[/yellow]")
        return

    from localbox.commands.project import switch_projects

    switch_projects(solution, projects, branch=branch, verbose=ctx.verbose)


@cli.command()
@click.argument("targets", nargs=-1, required=True, shell_complete=complete_targets)
@click.option("--no-cache", is_flag=True, help="Build without Docker layer cache")
@click.option(
    "--keep-going",
    "-k",
    is_flag=True,
    help="Continue building remaining projects after a failure (default: stop on first error)",
)
@pass_context
def build(ctx: LocalboxContext, targets: tuple[str, ...], no_cache: bool, keep_going: bool) -> None:
    """Build projects or service images.

    Examples:
        localbox build projects           # Build all projects
        localbox build projects:backend   # Build backend projects
        localbox build services           # Build all service images
        localbox build services:be        # Build backend service images
    """
    solution = load_solution_or_exit()

    first_target = targets[0]
    if first_target.startswith("projects"):
        try:
            projects = resolve_targets(solution, targets, "projects")
        except TargetError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

        if not projects:
            console.print("[yellow]No projects to build.[/yellow]")
            return

        from localbox.commands.project import build_projects

        build_projects(
            solution, projects, verbose=ctx.verbose, no_cache=no_cache, keep_going=keep_going
        )

    elif first_target.startswith("services"):
        try:
            services = resolve_targets(solution, targets, "services")
        except TargetError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)

        if not services:
            console.print("[yellow]No services to build.[/yellow]")
            return

        from localbox.commands.service import build_images

        build_images(solution, services, verbose=ctx.verbose, no_cache=no_cache)

    else:
        console.print(
            f"[red]Error:[/red] Target must start with 'projects' or 'services': {first_target}"
        )
        sys.exit(1)


@cli.command()
@click.argument("targets", nargs=-1, required=True, shell_complete=complete_targets)
@pass_context
def status(ctx: LocalboxContext, targets: tuple[str, ...]) -> None:
    """Show git status of projects."""
    solution = load_solution_or_exit()

    try:
        projects = resolve_targets(solution, targets, "projects")
    except TargetError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    from localbox.commands.project import show_project_status

    show_project_status(solution, projects)


# =============================================================================
# Compose Commands
# =============================================================================


@cli.group()
def compose() -> None:
    """Docker Compose operations."""
    pass


@compose.command("generate")
def compose_generate() -> None:
    """Generate docker-compose.yml from service definitions."""
    solution = load_solution_or_exit()

    from localbox.builders.compose import generate_compose_file

    try:
        generate_compose_file(solution)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


# =============================================================================
# Completion
# =============================================================================


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
