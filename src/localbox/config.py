"""Configuration loading and solution detection."""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from loguru import logger

from localbox.models.base_env import BaseEnv, EnvField
from localbox.models.project import Project
from localbox.models.service import Service
from localbox.models.solution_config import SolutionConfig

CONFIG_FILE = "solution.py"
OVERRIDE_FILE = "solution-override.py"


class SolutionNotFoundError(Exception):
    """Raised when solution.py cannot be found."""

    pass


def _env_to_dict(env: Any) -> dict[str, str | None]:
    """Convert env (dict or class instance) to a flat dict.

    Supports both dict-based and class-based env definitions:
        env = {"DB_PASS": None}        # dict — returned as-is
        env = Env()                    # BaseEnv instance — instance attrs only
        env = Env()                    # legacy class instance — merged attrs
    """
    if isinstance(env, dict):
        return dict(env)

    if isinstance(env, BaseEnv):
        # Instance attrs only — class-level attrs are EnvField sentinels, not values
        return {
            k: (None if isinstance(v, EnvField) else v)
            for k, v in vars(env).items()
            if not k.startswith("_")
        }

    # Legacy: class-based env (not BaseEnv) — current behaviour
    result: dict[str, str | None] = {}

    for key, val in vars(type(env)).items():
        if key.startswith("_") or callable(val) or isinstance(
            val, (classmethod, staticmethod, property)
        ):
            continue
        result[key] = val

    # Instance attributes override class-level defaults
    for key, val in vars(env).items():
        if not key.startswith("_"):
            result[key] = val

    return result


@dataclass
class DirectoriesConfig:
    """Directory paths configuration."""

    build: Path
    projects: Path
    compose: Path

    @classmethod
    def from_config(cls, config: SolutionConfig, solution_root: Path) -> "DirectoriesConfig":
        """Create from SolutionConfig, resolving relative paths."""
        build_dir = config.build_dir

        def resolve(rel_path: str) -> Path:
            path = Path(rel_path)
            if not path.is_absolute():
                path = solution_root / path
            return path

        return cls(
            build=resolve(build_dir),
            projects=resolve(f"{build_dir}/projects"),
            compose=resolve(f"{build_dir}/compose"),
        )


@dataclass
class DockerSettings:
    """Docker/Compose settings."""

    compose_project: str = "localbox"
    network: str = "localbox"


@dataclass
class Solution:
    """Complete solution configuration."""

    root: Path
    name: str
    default_branch: str = "dev"
    directories: DirectoriesConfig = None  # type: ignore
    docker: DockerSettings = field(default_factory=DockerSettings)
    config: SolutionConfig | None = field(default=None, repr=False)

    # Loaded projects and services
    projects: dict[str, Project] = field(default_factory=dict)
    services: dict[str, Service] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.directories is None:
            self.directories = DirectoriesConfig.from_config(SolutionConfig(), self.root)

    def get_project(self, name: str) -> Project | None:
        """Get project by qualified name."""
        return self.projects.get(name)

    def get_service(self, name: str) -> Service | None:
        """Get service by qualified name."""
        return self.services.get(name)

    def get_projects_in_group(self, group: str) -> list[Project]:
        """Get all projects in a group."""
        return [p for p in self.projects.values() if p.group == group]

    def get_services_in_group(self, group: str) -> list[Service]:
        """Get all services in a group."""
        return [s for s in self.services.values() if s.group == group]

    def get_project_groups(self) -> set[str]:
        """Get all project group names."""
        return {p.group for p in self.projects.values() if p.group}

    def get_service_groups(self) -> set[str]:
        """Get all service group names."""
        return {s.group for s in self.services.values() if s.group}


def find_solution_root(start_path: Path | None = None) -> Path:
    """Find solution root by walking up directory tree looking for solution.py.

    Args:
        start_path: Directory to start searching from. Defaults to current directory.

    Returns:
        Path to the solution root directory.

    Raises:
        SolutionNotFoundError: If solution.py is not found.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    while current != current.parent:
        config_file = current / CONFIG_FILE
        if config_file.exists():
            return current
        current = current.parent

    # Check root directory as well
    if (current / CONFIG_FILE).exists():
        return current

    raise SolutionNotFoundError(
        f"Not a localbox solution directory ({CONFIG_FILE} not found).\n"
        f"Run 'localbox init' to create a new solution, or navigate to an existing solution."
    )


def _import_python_file(filepath: Path, module_name: str) -> ModuleType:
    """Import a Python file and return the module."""
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import {filepath}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _derive_group_from_module(module: ModuleType) -> str | None:
    """Derive group name from module path.

    Examples:
        projects.backend -> backend
        projects.libs.internal -> libs:internal
        services.db -> db
    """
    module_name = getattr(module, "__name__", "")
    if not module_name:
        return None

    # Check for projects.* or services.* pattern
    for prefix in ("projects.", "services."):
        if module_name.startswith(prefix):
            # Remove prefix and convert dots to colons
            group_path = module_name[len(prefix):]
            return group_path.replace(".", ":") if group_path else None

    return None


def _collect_objects(
    module: ModuleType,
    projects: dict[str, Project],
    services: dict[str, Service],
    visited_modules: set[int] | None = None,
    visited_objects: set[int] | None = None,
) -> SolutionConfig | None:
    """Scan module variables for Project, Service, SolutionConfig instances.

    Also recursively scans imported modules to find nested objects.
    Auto-generates names for projects/services without explicit names.
    Returns SolutionConfig if found, otherwise None.
    """
    if visited_modules is None:
        visited_modules = set()
    if visited_objects is None:
        visited_objects = set()

    # Avoid infinite recursion
    module_id = id(module)
    if module_id in visited_modules:
        return None
    visited_modules.add(module_id)

    # Get group from module path
    group = _derive_group_from_module(module)

    config = None

    # First pass: find SolutionConfig
    for var_name in dir(module):
        if var_name.startswith("_"):
            continue
        obj = getattr(module, var_name)
        if isinstance(obj, SolutionConfig):
            config = obj
            break

    # Second pass: collect projects and services
    for var_name in dir(module):
        if var_name.startswith("_"):
            continue
        obj = getattr(module, var_name)
        obj_id = id(obj)

        if isinstance(obj, Project):
            # Skip if already processed (imported from another module)
            if obj_id in visited_objects:
                continue
            visited_objects.add(obj_id)

            # Determine local_name, group, and full name
            if obj.name is None:
                # Auto-generate from variable name (consistent with services)
                local_name = var_name
                if group:
                    obj.name = f"{group}:{local_name}"
                else:
                    obj.name = local_name
                obj.group = group
            elif ":" in obj.name:
                # Full qualified name provided - derive group from name
                parts = obj.name.split(":", 1)
                obj.group = parts[0]
                local_name = parts[1]
            else:
                # Partial name provided - prefix with module group
                local_name = obj.name
                if group:
                    obj.name = f"{group}:{local_name}"
                obj.group = group

            obj.local_name = local_name
            projects[obj.name] = obj

        elif isinstance(obj, Service):
            # Skip if already processed
            if obj_id in visited_objects:
                continue
            visited_objects.add(obj_id)

            # Determine local_name, group, and full name
            if obj.name is None:
                # Auto-generate from variable name
                local_name = var_name
                if group:
                    obj.name = f"{group}:{local_name}"
                else:
                    obj.name = local_name
                obj.group = group
            elif ":" in obj.name:
                # Full qualified name provided - derive group from name
                parts = obj.name.split(":", 1)
                obj.group = parts[0]
                local_name = parts[1]
            else:
                # Partial name provided - prefix with module group
                local_name = obj.name
                if group:
                    obj.name = f"{group}:{local_name}"
                obj.group = group

            obj.local_name = local_name

            # Finalize image name after service name is set
            obj._finalize_image_name()
            services[obj.name] = obj

    return config


def load_solution(solution_root: Path | None = None) -> Solution:
    """Import solution.py and collect all objects.

    Configuration discovery is driven by imports within solution.py.
    If solution-override.py exists, it is exec'd after solution.py —
    mutations to config.env, project.branch, project.path, etc. are applied.

    Args:
        solution_root: Path to solution root. If None, searches for it.

    Returns:
        Loaded Solution object with all projects and services.

    Raises:
        SolutionNotFoundError: If solution.py is not found.
    """
    if solution_root is None:
        solution_root = find_solution_root()

    logger.debug("Loading solution from {}", solution_root)

    # Add solution root to sys.path so solution.py can import local modules
    root_str = str(solution_root)
    path_added = root_str not in sys.path
    if path_added:
        sys.path.insert(0, root_str)

    try:
        projects: dict[str, Project] = {}
        services: dict[str, Service] = {}
        config: SolutionConfig | None = None
        visited_modules: set[int] = set()
        visited_objects: set[int] = set()

        # 1. Import solution.py (required)
        # Register under "solution" BEFORE exec_module so sub-modules can
        # do `from solution import config` during their own loading.
        solution_file = solution_root / CONFIG_FILE
        _prior_solution_module = sys.modules.get("solution")
        module = _import_python_file(solution_file, "_localbox_solution")
        sys.modules["solution"] = module

        # 2. Auto-import projects/ and services/ packages if they exist
        for pkg_name in ("projects", "services"):
            pkg_dir = solution_root / pkg_name
            if (pkg_dir / "__init__.py").exists() and pkg_name not in sys.modules:
                __import__(pkg_name)

        # 3. Exec solution-override.py if present.
        # Runs after all packages are imported so it can `import projects as p`
        # and mutate project/service/config objects directly.
        override_file = solution_root / OVERRIDE_FILE
        if override_file.exists():
            logger.debug("Applying overrides from {}", override_file)
            _import_python_file(override_file, "_localbox_solution_override")

        # 4. Scan projects.* and services.* modules (reverse order: leaves first)
        for mod_name in sorted(sys.modules.keys(), reverse=True):
            if mod_name.startswith(("projects.", "services.")):
                mod = sys.modules[mod_name]
                if mod is not None:
                    _collect_objects(mod, projects, services, visited_modules, visited_objects)

        # 5. Scan the main solution module for remaining objects and config
        found_config = _collect_objects(
            module, projects, services, visited_modules, visited_objects
        )
        if found_config is not None:
            config = found_config

    finally:
        # Clean up sys.path and loaded modules
        if path_added and root_str in sys.path:
            sys.path.remove(root_str)
        for key in list(sys.modules):
            if key.startswith("_localbox_"):
                del sys.modules[key]
        # Restore or remove the "solution" alias
        if _prior_solution_module is not None:
            sys.modules["solution"] = _prior_solution_module
        elif "solution" in sys.modules:
            del sys.modules["solution"]

    # Build Solution from collected config
    if config is None:
        config = SolutionConfig()

    solution_name = config.name or solution_root.name

    solution = Solution(
        root=solution_root,
        name=solution_name,
        default_branch=config.default_branch,
        directories=DirectoriesConfig.from_config(config, solution_root),
        docker=DockerSettings(
            compose_project=config.compose_project or solution_name,
            network=config.network or solution_name,
        ),
        config=config,
        projects=projects,
        services=services,
    )

    logger.info(
        "Solution '{}' loaded: {} projects, {} services",
        solution.name,
        len(solution.projects),
        len(solution.services),
    )
    return solution


def create_default_solution() -> str:
    """Return template solution.py content."""
    return '''\
"""Localbox solution configuration."""

from dataclasses import dataclass
from localbox.models import BaseEnv, env_field, SolutionConfig

@dataclass
class Env(BaseEnv):
    pass

config = SolutionConfig[Env](
    name=None,  # Defaults to directory name
    env=Env(),
)

# Define projects and services below.
# from localbox.models import JavaProject, maven, Service, DockerImage, ComposeConfig
#
# my_app = JavaProject(
#     "my_app",
#     repo="git@github.com:org/my_app.git",
#     builder=maven("3.9", jdk=17),
# )
#
# db = Service(
#     name="db",
#     image=DockerImage(image="postgres:16"),
#     compose=ComposeConfig(ports=["5432:5432"]),
# )
'''
