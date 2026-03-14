"""Solution configuration model."""

from dataclasses import dataclass, field
from typing import Generic, TypeVar

EnvT = TypeVar("EnvT")


@dataclass
class SolutionConfig(Generic[EnvT]):
    """Solution-level configuration.

    Define in solution.py to customize settings:

        # Dict-based env (simple)
        config = SolutionConfig(name="myproject", env={"DB_PASS": None})

        # Class-based env (PyCharm completion in solution-override.py)
        class Env:
            DB_HOST: str      = "localhost"
            DB_PASS: str|None = None  # REQUIRED

        config = SolutionConfig(name="myproject", env=Env())
    """

    name: str | None = None
    default_branch: str = "dev"
    build_dir: str = ".build"
    project_dir: str | None = None  # None → "{build_dir}/projects"
    compose_project: str | None = None  # Defaults to solution name
    network: str | None = None  # Defaults to solution name
    registry: str | None = None  # Docker registry prefix, e.g. "registry.io/myteam"
    env: EnvT = field(default_factory=dict)  # type: ignore[assignment]
