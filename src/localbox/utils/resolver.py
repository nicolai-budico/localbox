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
    Resolve colon-separated targets to actual project/service objects.

    Args:
        solution: The loaded solution configuration.
        targets: Tuple of target strings (e.g., "projects:processor", "services:db").
        target_type: Expected type ("projects" or "services").

    Returns:
        List of resolved Project or Service objects.

    Raises:
        TargetError: If a target cannot be resolved.

    Examples:
        "projects" -> all projects
        "projects:processor" -> single project named "processor"
        "projects:libs" -> all projects in "libs" group
        "projects:libs:utils" -> single project "libs:utils"
        "services:db" -> all services in "db" group
        "services:db:main" -> single service "db:main"
    """
    results: list[Project | Service] = []

    for target in targets:
        parts = target.split(":")

        if len(parts) == 1:
            # "projects" or "services" -> all
            if parts[0] != target_type:
                raise TargetError(
                    f"Invalid target '{target}': expected '{target_type}' prefix"
                )
            results.extend(get_all(solution, target_type))

        elif len(parts) == 2:
            # "projects:processor" or "projects:libs" or "services:db"
            prefix, name_or_group = parts
            if prefix != target_type:
                raise TargetError(
                    f"Invalid target '{target}': expected '{target_type}' prefix"
                )

            if is_group(solution, target_type, name_or_group):
                results.extend(get_group(solution, target_type, name_or_group))
            else:
                item = get_single(solution, target_type, name_or_group)
                if item:
                    results.append(item)
                else:
                    raise TargetError(
                        f"Unknown {target_type[:-1]} or group: '{name_or_group}'"
                    )

        elif len(parts) == 3:
            # "projects:libs:utils" or "services:db:main"
            prefix, group, name = parts
            if prefix != target_type:
                raise TargetError(
                    f"Invalid target '{target}': expected '{target_type}' prefix"
                )
            qualified_name = f"{group}:{name}"
            item = get_single(solution, target_type, qualified_name)
            if item:
                results.append(item)
            else:
                raise TargetError(f"Unknown {target_type[:-1]}: '{qualified_name}'")

        else:
            raise TargetError(
                f"Invalid target '{target}': max 1 level of grouping allowed"
            )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[Project | Service] = []
    for item in results:
        if item.name not in seen:
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


def get_group(
    solution: Solution, target_type: str, group: str
) -> list[Project | Service]:
    """Get all items in a group."""
    if target_type == "projects":
        return list(solution.get_projects_in_group(group))
    else:
        return list(solution.get_services_in_group(group))


def get_single(
    solution: Solution, target_type: str, name: str
) -> Project | Service | None:
    """Get a single project or service by name."""
    if target_type == "projects":
        return solution.get_project(name)
    else:
        return solution.get_service(name)


def parse_target(target: str) -> tuple[str, str | None, str | None]:
    """
    Parse a target string into (type, group, name).

    Returns:
        (target_type, group, name) where group and name may be None.

    Examples:
        "projects" -> ("projects", None, None)
        "projects:processor" -> ("projects", None, "processor") or \
            ("projects", "processor", None) if group
        "projects:libs:utils" -> ("projects", "libs", "utils")
    """
    parts = target.split(":")

    if len(parts) == 1:
        return (parts[0], None, None)
    elif len(parts) == 2:
        return (parts[0], None, parts[1])  # Could be group or name
    elif len(parts) == 3:
        return (parts[0], parts[1], parts[2])
    else:
        raise TargetError(f"Invalid target format: {target}")
