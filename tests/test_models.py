"""Tests for data models."""

import pytest

from localbox.models.builder import (
    BindVolume,
    Builder,
    CacheVolume,
    NamedVolume,
    bind_volume,
    cache_volume,
    gradle,
    maven,
    named_volume,
    node,
)
from localbox.models.docker_image import DockerImage
from localbox.models.jdk import JDK, JDKProvider, corretto, graalvm, temurin
from localbox.models.project import (
    GitConfig,
    JavaProject,
    Project,
)
from localbox.models.service import (
    ComposeConfig,
    Service,
)


class TestDockerImage:
    """Tests for DockerImage dataclass."""

    def test_image_only(self):
        """DockerImage with just image name (pre-built)."""
        di = DockerImage(name="test", image="postgres:14")
        assert di.name == "test"
        assert di.image == "postgres:14"
        assert di.dockerfile is None

    def test_image_with_dockerfile(self):
        """DockerImage with image and dockerfile (build and tag)."""
        di = DockerImage(name="myapp", image="myapp:latest", dockerfile="Dockerfile")
        assert di.name == "myapp"
        assert di.image == "myapp:latest"
        assert di.dockerfile == "Dockerfile"

    def test_dockerfile_only(self):
        """DockerImage with just dockerfile (auto-generate tag)."""
        di = DockerImage(name="builder", dockerfile="Dockerfile")
        assert di.name == "builder"
        assert di.image is None
        assert di.dockerfile == "Dockerfile"

    def test_defaults(self):
        """DockerImage with all defaults."""
        di = DockerImage()
        assert di.name == ""
        assert di.image is None
        assert di.dockerfile is None


class TestBuilder:
    """Tests for Builder dataclass."""

    def test_maven_builder(self):
        """Maven builder should have correct command and volumes."""
        b = maven("3.9")
        # Image is resolved using JDK from project
        assert b.resolve_image_tag(JDK(8)) == "maven:3.9-amazoncorretto-8"
        assert b.command_list is not None
        assert "mvn" in b.command_list
        assert "install" in b.command_list
        assert "-Dmaven.test.skip=true" in b.command_list
        assert b.entrypoint == ""
        assert len(b.volumes) == 1
        assert isinstance(b.volumes[0], CacheVolume)
        assert b.volumes[0].name == "maven"

    def test_maven_builder_jdk17(self):
        """Maven builder with JDK 17 should resolve correct image."""
        b = maven("4.0")
        assert b.resolve_image_tag(JDK(17)) == "maven:4.0-amazoncorretto-17"

    def test_maven_builder_temurin(self):
        """Maven builder with Temurin JDK."""
        b = maven("3.9")
        assert b.resolve_image_tag(temurin(17)) == "maven:3.9-eclipse-temurin-17"

    def test_gradle_builder(self):
        """Gradle builder should have correct command and volumes."""
        b = gradle("8.14")
        # Image is resolved using JDK from project
        assert b.resolve_image_tag(JDK(21)) == "gradle:8.14-jdk21"
        assert b.command_list is not None
        assert "gradle" in b.command_list
        assert "build" in b.command_list
        assert "--no-daemon" in b.command_list
        assert "-Dmaven.repo.local=/var/maven/.m2/repository" in b.command_list
        assert b.environment.get("GRADLE_USER_HOME") == "/var/gradle"
        assert b.environment.get("MAVEN_LOCAL_REPO") == "/var/maven/.m2/repository"
        assert len(b.volumes) == 2
        names = [v.name for v in b.volumes]
        assert "gradle" in names
        assert "maven" in names

    def test_gradle_builder_graalvm(self):
        """Gradle builder with GraalVM JDK."""
        b = gradle("8.14")
        assert b.resolve_image_tag(graalvm(21)) == "gradle:8.14-jdk21-graal"

    def test_node_builder(self):
        """Node builder should have correct image and command."""
        b = node(20)
        assert b.docker_image.image == "node:20"
        assert b.docker_image.name == "node-20"
        assert b.command == "npm ci && npm run build"
        assert b.command_list is None
        assert b.environment.get("npm_config_cache") == "/home/node/.npm"
        assert len(b.volumes) == 1
        assert isinstance(b.volumes[0], CacheVolume)
        assert b.volumes[0].name == "node"

    def test_node_builder_version_22(self):
        """Node builder with version 22."""
        b = node(22)
        assert b.docker_image.image == "node:22"
        assert b.docker_image.name == "node-22"

    def test_volumes_single_instance(self):
        """volumes= should accept a single Volume and normalize to list."""
        b = Builder(
            docker_image=DockerImage(name="test", image="test"),
            volumes=cache_volume("maven", "/var/maven/.m2"),
        )
        assert isinstance(b.volumes, list)
        assert len(b.volumes) == 1
        assert isinstance(b.volumes[0], CacheVolume)

    def test_custom_builder_image(self):
        """Custom builder with image."""
        b = Builder(
            docker_image=DockerImage(name="custom", image="my-custom-image:latest"),
            command="make build",
        )
        assert b.docker_image.image == "my-custom-image:latest"
        assert b.resolve_image_tag() == "my-custom-image:latest"
        assert not b.uses_dockerfile

    def test_custom_builder_dockerfile(self):
        """Custom builder with Dockerfile."""
        b = Builder(docker_image=DockerImage(name="custom", dockerfile="./Dockerfile"))
        assert b.uses_dockerfile is True
        with pytest.raises(ValueError):
            b.resolve_image_tag()

    def test_builder_workdir_default(self):
        """Builder default workdir should be /var/src."""
        b = Builder(docker_image=DockerImage(name="test", image="test"))
        assert b.workdir == "/var/src"

    def test_cache_volume(self):
        """CacheVolume should store name and container."""
        v = CacheVolume(name="maven", container="/var/maven/.m2")
        assert v.name == "maven"
        assert v.container == "/var/maven/.m2"
        assert v.readonly is False

    def test_bind_volume(self):
        """BindVolume should store host path and container."""
        v = BindVolume(host="./assets/html", container="/var/nginx/html", readonly=True)
        assert v.host == "./assets/html"
        assert v.container == "/var/nginx/html"
        assert v.readonly is True

    def test_named_volume(self):
        """NamedVolume should store Docker volume name and container."""
        v = NamedVolume(name="postgresql_data", container="/var/lib/postgresql/data")
        assert v.name == "postgresql_data"
        assert v.container == "/var/lib/postgresql/data"
        assert v.readonly is False


class TestProject:
    """Tests for Project class."""

    def test_simple_constructor(self):
        """Project with repo convenience param."""
        p = Project("test", repo="git@example.com/test.git")
        assert p.name == "test"
        assert p.git is not None
        assert p.git.url == "git@example.com/test.git"

    def test_full_constructor(self):
        """Project with explicit GitConfig."""
        p = Project("test", git=GitConfig(url="git@example.com/test.git", branch="main"))
        assert p.git.url == "git@example.com/test.git"
        assert p.git.branch == "main"

    def test_convenience_branch(self):
        """Convenience params for branch."""
        p = Project("test", repo="git@example.com/test.git", branch="dev")
        assert p.git.branch == "dev"

    def test_deps_object_references(self):
        """deps param should store Project objects."""
        a = Project("lib-a", repo="git@example.com/a.git")
        b = Project("lib-b", repo="git@example.com/b.git")
        c = Project("app", repo="git@example.com/app.git", deps=[a, b])
        assert c.depends_on == [a, b]

    def test_get_patches_dir(self, tmp_path):
        """Should find patches in ./patches/<local_name>/."""
        patches_dir = tmp_path / "patches" / "test"
        patches_dir.mkdir(parents=True)

        project = Project(
            name="test",
            git=GitConfig(url="git@example.com/test.git"),
            local_name="test",
        )

        result = project.get_patches_dir(tmp_path)
        assert result == patches_dir

    def test_get_patches_dir_none(self, tmp_path):
        """Should return None when no patches directory exists."""
        project = Project(
            name="test",
            git=GitConfig(url="git@example.com/test.git"),
            local_name="test",
        )

        result = project.get_patches_dir(tmp_path)
        assert result is None

    def test_resolve_source_dir_default(self, tmp_path):
        """No path set: returns projects_dir / repo base name."""
        p = Project("libs:utils", repo="git@example.com/utils.git")
        result = p.resolve_source_dir(tmp_path)
        assert result == tmp_path / "utils"

    def test_resolve_source_dir_uses_repo_name(self, tmp_path):
        """Repo base name takes precedence over project path_name."""
        p = Project("portal", repo="git@bitbucket.org:viveka-health-dev/employer-portal.git")
        result = p.resolve_source_dir(tmp_path)
        assert result == tmp_path / "employer-portal"

    def test_resolve_source_dir_no_git(self, tmp_path):
        """No git config: falls back to path_name."""
        p = Project("libs:utils")
        result = p.resolve_source_dir(tmp_path)
        assert result == tmp_path / "utils"

    def test_resolve_source_dir_relative(self, tmp_path):
        """Relative path: resolved relative to projects_dir."""
        p = Project("libs:utils", repo="git@example.com/utils.git", path="custom/utils")
        result = p.resolve_source_dir(tmp_path)
        assert result == tmp_path / "custom/utils"

    def test_resolve_source_dir_absolute(self, tmp_path):
        """Absolute path: returned as-is, ignoring projects_dir."""
        abs_path = str(tmp_path / "my-checkout" / "utils")
        p = Project("libs:utils", repo="git@example.com/utils.git", path=abs_path)
        result = p.resolve_source_dir(tmp_path / "projects")
        assert result == tmp_path / "my-checkout" / "utils"


class TestComposeConfigPorts:
    """Tests for ComposeConfig ports field."""

    def test_default_empty(self):
        """ComposeConfig ports should default to empty list."""
        c = ComposeConfig()
        assert c.ports == []

    def test_ports_set(self):
        """ComposeConfig with explicit ports."""
        c = ComposeConfig(ports=["8080:8080", "9090:9090"])
        assert c.ports == ["8080:8080", "9090:9090"]

    def test_volumes_single_instance(self):
        """volumes= should accept a single Volume and normalize to list."""
        c = ComposeConfig(volumes=named_volume("pg_data", "/var/lib/postgresql/data"))
        assert isinstance(c.volumes, list)
        assert len(c.volumes) == 1
        assert isinstance(c.volumes[0], NamedVolume)

    def test_volumes_list(self):
        """volumes= should accept a list of Volume instances."""
        c = ComposeConfig(
            volumes=[
                named_volume("pg_data", "/var/lib/postgresql/data"),
                bind_volume("./init.sql", "/docker-entrypoint-initdb.d/init.sql", readonly=True),
            ]
        )
        assert len(c.volumes) == 2
        assert isinstance(c.volumes[0], NamedVolume)
        assert isinstance(c.volumes[1], BindVolume)


class TestService:
    """Tests for Service class."""

    def test_container_name(self):
        """Should generate correct container name."""
        service = Service(name="db:main")
        assert service.container_name("localbox") == "localbox-db-main"

    def test_get_dockerfile_path_root(self, tmp_path):
        """Should find Dockerfile relative to solution root."""
        dockerfile = tmp_path / "Dockerfile"
        dockerfile.write_text("FROM postgres:14")

        service = Service(
            name="db:main",
            image=DockerImage(name="db", dockerfile="Dockerfile"),
        )

        result = service.get_dockerfile_path(tmp_path)
        assert result == dockerfile

    def test_group_derivation(self):
        """Should auto-derive group and local_name from name."""
        service = Service(name="db:main")
        assert service.group == "db"
        assert service.local_name == "main"

    def test_no_group(self):
        """Service without group should have local_name == name."""
        service = Service(name="standalone")
        assert service.group is None
        assert service.local_name == "standalone"

    def test_all_projects(self):
        """Should combine project and projects."""
        p1 = Project("p1", repo="repo1")
        p2 = Project("p2", repo="repo2")
        p3 = Project("p3", repo="repo3")

        s = Service(name="s", project=p1, projects=[p2, p3])
        assert s.all_projects == [p1, p2, p3]

    def test_image_name_defaulting(self):
        """Should default image.name to group/local_name for unique tagging."""
        s = Service(name="db:main")
        s._finalize_image_name()  # Called during solution loading
        assert s.image.name == "db/main"  # Includes group for unique tags


@pytest.mark.skip(reason="Profiles temporarily disabled in compose generation")
class TestComposeProfiles:
    """Tests for Docker Compose profiles support."""

    def _make_solution(self, services: list):
        """Build a minimal Solution with given services."""
        from pathlib import Path

        from localbox.config import DirectoriesConfig, DockerSettings, Solution
        from localbox.models.solution_config import SolutionConfig

        root = Path("/fake/solution")
        config = SolutionConfig(name="test")
        sol = Solution(
            root=root,
            name="test",
            directories=DirectoriesConfig(
                build=root / ".build",
                projects=root / ".build/projects",
                compose=root / ".build/compose",
            ),
            docker=DockerSettings(compose_project="test", network="test"),
            config=config,
            services={s.name: s for s in services},
        )
        return sol

    def test_no_group_no_profile(self):
        """Services without a group have no profiles — always start."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="proxy",
            image=DockerImage(image="nginx:alpine"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol = self._make_solution([service])
        defn = generate_service_definition(sol, service)
        assert "profiles" not in defn

    def test_group_becomes_profile(self):
        """Service group is automatically used as the Compose profile."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="db:main",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol = self._make_solution([service])
        defn = generate_service_definition(sol, service)
        assert defn["profiles"] == ["db"]

    def test_multilevel_group_uses_dashes(self):
        """Multi-level group colons are replaced with dashes in profile name."""
        from localbox.builders.compose import generate_service_definition

        service = Service(
            name="be:payments:transfer",
            image=DockerImage(image="myapp:latest"),
            compose=ComposeConfig(),
        )
        # Manually set group to simulate multi-level
        service.group = "be:payments"
        service._finalize_image_name()
        sol = self._make_solution([service])
        defn = generate_service_definition(sol, service)
        assert defn["profiles"] == ["be-payments"]


class TestJDK:
    """Tests for JDK model."""

    def test_default_provider(self):
        """JDK should default to Corretto provider."""
        jdk = JDK(17)
        assert jdk.version == 17
        assert jdk.provider == JDKProvider.CORRETTO

    def test_explicit_provider(self):
        """JDK with explicit provider."""
        jdk = JDK(21, JDKProvider.TEMURIN)
        assert jdk.version == 21
        assert jdk.provider == JDKProvider.TEMURIN

    def test_maven_image_suffix_corretto(self):
        """Corretto JDK should produce correct Maven image suffix."""
        jdk = corretto(8)
        assert jdk.maven_image_suffix() == "amazoncorretto-8"

    def test_maven_image_suffix_temurin(self):
        """Temurin JDK should produce correct Maven image suffix."""
        jdk = temurin(17)
        assert jdk.maven_image_suffix() == "eclipse-temurin-17"

    def test_gradle_image_suffix(self):
        """Corretto/Temurin JDK should produce jdkN suffix for Gradle."""
        jdk = JDK(21)
        assert jdk.gradle_image_suffix() == "jdk21"

    def test_gradle_image_suffix_graalvm(self):
        """GraalVM JDK should produce jdkN-graal suffix for Gradle."""
        jdk = graalvm(21)
        assert jdk.gradle_image_suffix() == "jdk21-graal"

    def test_factory_functions(self):
        """Factory functions should create correct JDK instances."""
        assert corretto(8).provider == JDKProvider.CORRETTO
        assert temurin(17).provider == JDKProvider.TEMURIN
        assert graalvm(21).provider == JDKProvider.GRAALVM


class TestJavaProject:
    """Tests for JavaProject model."""

    def test_jdk_int_conversion(self):
        """JavaProject should convert int jdk to JDK instance."""
        p = JavaProject("test", repo="git@example.com/test.git", jdk=17)
        assert isinstance(p.jdk, JDK)
        assert p.jdk.version == 17
        assert p.jdk.provider == JDKProvider.CORRETTO

    def test_jdk_explicit(self):
        """JavaProject with explicit JDK instance."""
        p = JavaProject("test", repo="git@example.com/test.git", jdk=temurin(21))
        assert p.jdk.version == 21
        assert p.jdk.provider == JDKProvider.TEMURIN

    def test_jdk_default(self):
        """JavaProject should default to JDK 8."""
        p = JavaProject("test", repo="git@example.com/test.git")
        assert p.jdk.version == 8

    def test_inherits_project_features(self):
        """JavaProject should inherit Project features."""
        p = JavaProject("backend:app", repo="git@example.com/app.git")
        assert p.group == "backend"
        assert p.local_name == "app"
        assert p.git is not None
        assert p.git.url == "git@example.com/app.git"
