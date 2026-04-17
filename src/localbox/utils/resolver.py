"""Target resolution for CLI commands."""

from localbox.config import Solution
from localbox.models.project import Project
from localbox.models.service import Service


class TargetError(Exception):
    """Error resolving a target."""

    pass


def resolve_targets(
    solution: Solution,
    targets: tuple[str, ...],
    target_type: str,
) -> list[Project | Service]:
    """
    Resolve short-form tokens to actual project/service objects within a domain.

    Under the domain-first CLI grammar, commands already know which domain they
    operate on and pass it via ``target_type``. Tokens are therefore bare
    ``<group>[:<name>]`` (or ``<name>`` for ungrouped items); the redundant
    ``projects:`` / ``services:`` prefix is rejected.

    Args:
        solution: The loaded solution configuration.
        targets: Tuple of short-form target strings. An empty tuple means
            "all items of target_type".
        target_type: Domain, either ``"projects"`` or ``"services"``.

    Returns:
        List of resolved Project or Service objects (deduplicated, order-preserving).

    Raises:
        TargetError: If a target cannot be resolved.

    Examples:
        ()                -> all items of target_type
        ("api",)          -> single item or group named "api"
        ("libs:utils",)   -> single grouped item "libs:utils"
        ("libs",)         -> all items in group "libs"
    """
    if not targets:
        results: list[Project | Service] = list(get_all(solution, target_type))
    else:
        results = []
        for target in targets:
            parts = target.split(":")

            if len(parts) == 1:
                # Bare name: either a group or an ungrouped item.
                name_or_group = parts[0]
                if name_or_group in (target_type, "projects", "services"):
                    raise TargetError(
                        f"Invalid target '{target}': domain-prefixed tokens are not allowed "
                        f"under '{target_type}'. Use a bare '<group>[:<name>]' or '<name>'."
                    )
                if is_group(solution, target_type, name_or_group):
                    results.extend(get_group(solution, target_type, name_or_group))
                else:
                    item = get_single(solution, target_type, name_or_group)
                    if item:
                        results.append(item)
                    else:
                        raise TargetError(f"Unknown {target_type[:-1]} or group: '{name_or_group}'")

            elif len(parts) == 2:
                # "group:name" — reject accidental "projects:foo" / "services:foo".
                first, second = parts
                if first in ("projects", "services"):
                    raise TargetError(
                        f"Invalid target '{target}': domain-prefixed tokens are not allowed "
                        f"under '{target_type}'. Use '{second}' or '<group>:<name>'."
                    )
                qualified_name = f"{first}:{second}"
                item = get_single(solution, target_type, qualified_name)
                if item:
                    results.append(item)
                else:
                    raise TargetError(f"Unknown {target_type[:-1]}: '{qualified_name}'")

            else:
                raise TargetError(f"Invalid target '{target}': max 1 level of grouping allowed")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[Project | Service] = []
    for item in results:
        if item.name not in seen:
            assert item.name is not None, "Item has no name — config loading bug"
            seen.add(item.name)
            unique.append(item)

    return unique


def get_all(solution: Solution, target_type: str) -> list[Project | Service]:
    """Get all projects or services."""
    if target_type == "projects":
        return list(solution.projects.values())
    else:
        return list(solution.services.values())


def is_group(solution: Solution, target_type: str, name: str) -> bool:
    """Check if name is a group (not a direct project/service name)."""
    if target_type == "projects":
        # It's a group if there are projects with this group
        # and no project with exactly this name
        has_group = any(p.group == name for p in solution.projects.values())
        has_exact = name in solution.projects
        return has_group and not has_exact
    else:
        # For services, groups are always explicit (db, be, fe)
        has_group = any(s.group == name for s in solution.services.values())
        has_exact = name in solution.services
        return has_group and not has_exact


def get_group(solution: Solution, target_type: str, group: str) -> list[Project | Service]:
    """Get all items in a group."""
    if target_type == "projects":
        return list(solution.get_projects_in_group(group))
    else:
        return list(solution.get_services_in_group(group))


def get_single(solution: Solution, target_type: str, name: str) -> Project | Service | None:
    """Get a single project or service by name."""
    if target_type == "projects":
        return solution.get_project(name)
    else:
        return solution.get_service(name)
