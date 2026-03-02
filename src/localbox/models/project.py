"""Project data models."""

from __future__ import annotations

import re
from dataclasses import InitVar, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from localbox.models.builder import Builder

if TYPE_CHECKING:
    from localbox.models.jdk import JDK


@dataclass
class GitConfig:
    """Git repository configuration."""

    url: str
    branch: str | None = None


def extract_repo_name(url: str) -> str:
    """Extract repository name from git URL.

    Examples:
        git@bitbucket.org:org/fs-s3-storage.git -> fs-s3-storage
        https://github.com/org/repo.git -> repo
        git@github.com:org/repo -> repo
    """
    # Remove .git suffix if present
    url = re.sub(r"\.git$", "", url)
    # Extract last path component
    match = re.search(r"[/:]([^/:]+)$", url)
    return match.group(1) if match else url


@dataclass
class Project:
    """Base project definition.

    Usage:
        # Explicit name
        Project("backend:api", repo="git@...", deps=[other_project])

        # Auto-generated name (from module path + repo name)
        Project(repo="git@.../api.git")  # name derived during loading

    Patches are automatically applied if a directory exists at
    ./patches/<project_local_name>/ containing *.patch files.
    """

    name: str | None = None  # None = auto-generate from module path + repo name
    git: GitConfig | None = None
    builder: Builder | None = None
    depends_on: list[Project] = field(default_factory=list)

    # Init-only convenience params
    repo: InitVar[str | None] = None
    branch: InitVar[str | None] = None
    deps: InitVar[list[Project] | None] = None

    # Per-developer override: absolute path or relative to solution root.
    # Set in solution-override.py when project is in a non-standard location.
    path: str | None = None

    # Internal: set during loading
    config_path: Path | None = field(default=None, repr=False)
    base_dir: Path | None = field(default=None, repr=False)
    group: str | None = field(default=None, repr=False)
    local_name: str | None = field(default=None, repr=False)

    def __post_init__(
        self, repo: str | None, branch: str | None, deps: list[Project] | None
    ) -> None:
        # Build GitConfig from convenience params if needed
        if self.git is None and repo is not None:
            self.git = GitConfig(url=repo, branch=branch)

        # Store dependencies
        if deps is not None:
            self.depends_on = deps

        # Auto-derive group/local_name from name if name is set
        if self.name is not None:
            if self.group is None and ":" in self.name:
                self.group, self.local_name = self.name.split(":", 1)
            elif self.local_name is None:
                self.local_name = self.name

    @property
    def path_name(self) -> str:
        """Short filesystem-safe name: local_name if grouped, else name.

        Raises ValueError if both are None (the project was never loaded/named).
        """
        name = self.local_name or self.name
        if name is None:
            raise ValueError("Project has no name — this is a config loading bug")
        return name

    def resolve_source_dir(self, projects_dir: Path) -> Path:
        """Resolve the local source directory for this project.

        If ``path`` is set, it is used as-is (absolute) or relative to
        ``projects_dir``.  Otherwise defaults to ``projects_dir / path_name``.
        """
        if self.path is not None:
            p = Path(self.path)
            return p if p.is_absolute() else projects_dir / p
        return projects_dir / self.path_name

    def get_patches_dir(self, solution_root: Path) -> Path | None:
        """Return patches dir: ./patches/<local_name>/."""
        patches_dir = solution_root / "patches" / self.path_name
        return patches_dir if patches_dir.exists() else None

    def get_script_path(self, script_name: str, solution_root: Path) -> Path | None:
        """Return script path: project-local first, then assets/scripts/."""
        if self.base_dir:
            local = self.base_dir / script_name
            if local.exists():
                return local
        shared = solution_root / script_name
        return shared if shared.exists() else None


@dataclass
class JavaArtifact:
    """Reference to a built artifact from a JavaProject.

    Used in TomcatService.webapps to specify which artifact to deploy.

    Usage:
        webapps={
            # Auto-detect artifact (fails if multiple found)
            "processor": backend.processor.artifact(),

            # Explicit path (relative to project root)
            "authserver": backend.auth_server.artifact("auth-server/target/oauth2-auth-server.war"),
        }
    """

    project: JavaProject
    path: str | None = None  # None = auto-detect at build time


@dataclass
class JavaProject(Project):
    """Java project with JDK requirements.

    The JDK version is a project property (source code requirement).
    The builder (Maven/Gradle) uses this to resolve the appropriate Docker image.

    Usage:
        # Simple Maven project with JDK 8
        utils = JavaProject(
            "libs:utils",
            repo="git@...",
            jdk=8,
            builder=maven(),
        )

        # With explicit JDK provider
        portal = JavaProject(
            "backend:portal",
            repo="git@...",
            jdk=temurin(17),
            builder=maven(),
        )

        # Gradle project
        app = JavaProject(
            "backend:app",
            repo="git@...",
            jdk=21,
            builder=gradle(),
        )

        # Auto-named (from module path + repo URL)
        api = JavaProject(repo="git@.../api.git", jdk=17, builder=maven())
    """

    jdk: JDK | int = 8

    def __post_init__(
        self,
        repo: str | None,
        branch: str | None,
        deps: list[Project] | None,
    ) -> None:
        super().__post_init__(repo, branch, deps)

        # Normalize jdk to JDK instance
        if isinstance(self.jdk, int):
            from localbox.models.jdk import JDK

            self.jdk = JDK(self.jdk)

    def artifact(self, path: str = "") -> JavaArtifact:
        """Get artifact reference for deployment.

        Args:
            path: Explicit path relative to project root (e.g., "target/app.war").
                  If empty, auto-detects using builder. Raises if multiple found.

        Returns:
            JavaArtifact for use in TomcatService.webapps
        """
        return JavaArtifact(project=self, path=path or None)


@dataclass
class NodeProject(Project):
    """Node.js project.

    Uses the node() builder by default. The `output_dir` field records where the
    build places its output (e.g. 'dist/'), which service Dockerfiles can reference
    via COPY --from.

    Usage:
        ui = NodeProject(
            "frontend:ui",
            repo="git@github.com:org/ui.git",
        )

        # Custom output directory or Node version
        app = NodeProject(
            "frontend:app",
            repo="git@github.com:org/app.git",
            output_dir="build",
            builder=node(22),
        )
    """

    output_dir: str = "dist"

    def __post_init__(
        self,
        repo: str | None,
        branch: str | None,
        deps: list[Project] | None,
    ) -> None:
        super().__post_init__(repo, branch, deps)

        # Set default builder if none provided
        if self.builder is None:
            from localbox.models.builder import node

            self.builder = node()
