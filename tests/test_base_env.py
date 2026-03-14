"""Tests for BaseEnv and EnvField."""

import dataclasses

import pytest

from localbox.models.base_env import BaseEnv, EnvField, env_field, is_env_secret


class TestEnvField:
    """Tests for EnvField sentinel and helpers."""

    def test_not_secret_by_default(self):
        """env_field() should default to is_secret=False."""
        f = env_field()
        assert f.is_secret is False

    def test_is_secret_flag(self):
        """env_field(is_secret=True) should set is_secret=True."""
        f = env_field(is_secret=True)
        assert f.is_secret is True

    def test_is_env_secret_helper(self):
        """is_env_secret() should delegate to .is_secret."""
        assert is_env_secret(env_field()) is False
        assert is_env_secret(env_field(is_secret=True)) is True


class TestBaseEnv:
    """Tests for BaseEnv subclass mechanics."""

    def test_subclass_becomes_dataclass(self):
        """dataclasses.fields() should work on an explicitly decorated subclass."""

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_host: str = env_field()
            db_pass: str = env_field(is_secret=True)

        fields = {f.name for f in dataclasses.fields(Env)}
        assert fields == {"db_host", "db_pass"}

    def test_rejects_plain_default(self):
        """BaseEnv subclass fields without env_field() should raise TypeError."""
        with pytest.raises(TypeError, match="must use env_field"):

            class Env(BaseEnv):
                db_host: str = "localhost"

    def test_rejects_missing_default(self):
        """BaseEnv subclass fields with no default at all should raise TypeError."""
        with pytest.raises(TypeError, match="must use env_field"):

            class Env(BaseEnv):
                db_host: str

    def test_class_attr_is_sentinel(self):
        """Class-level access should return the EnvField sentinel."""

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_pass: str = env_field(is_secret=True)

        assert isinstance(Env.db_pass, EnvField)
        assert Env.db_pass.is_secret is True

    def test_instance_has_correct_values(self):
        """Instance attributes should hold the passed values."""

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_pass: str = env_field(is_secret=True)
            db_name: str = env_field()

        instance = Env(db_pass="secret", db_name="mydb")
        assert instance.db_pass == "secret"
        assert instance.db_name == "mydb"


class TestComposeEnvResolution:
    """Tests for EnvField resolution in compose service definitions.

    Constructs Solution/Service objects directly — no disk I/O.
    """

    def _make_solution(self, env_instance):
        """Create a minimal Solution with the given env instance."""
        from pathlib import Path

        from localbox.config import Solution
        from localbox.models.solution_config import SolutionConfig

        config = SolutionConfig(env=env_instance)
        return Solution(
            root=Path("/tmp/test"),
            name="test",
            config=config,
        )

    def test_envfield_reference_resolved(self):
        """Env.FIELD reference in compose environment should produce ${VAR} reference."""
        from localbox.builders.compose import generate_service_definition
        from localbox.models import ComposeConfig, DockerImage, Service

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_name: str = env_field()

        env_inst = Env(db_name="mydb")
        solution = self._make_solution(env_inst)

        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(
                environment={"POSTGRES_DB": Env.db_name},
            ),
        )
        service._finalize_image_name()

        collector: dict[str, str] = {}
        svc_def = generate_service_definition(solution, service, env_collector=collector)
        assert svc_def["environment"]["POSTGRES_DB"] == "${db_name}"
        assert collector["db_name"] == "mydb"

    def test_unset_required_field_raises(self):
        """A required EnvField that was not set should raise ValueError."""
        from localbox.builders.compose import generate_service_definition
        from localbox.models import ComposeConfig, DockerImage, Service

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_pass: str = env_field(is_secret=True)

        # db_pass not set — stays as EnvField sentinel on the instance
        env_inst = Env(db_pass=Env.db_pass)  # pass sentinel explicitly
        solution = self._make_solution(env_inst)

        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(
                environment={"POSTGRES_PASSWORD": Env.db_pass},
            ),
        )
        service._finalize_image_name()

        with pytest.raises(ValueError, match="required but not set"):
            generate_service_definition(solution, service)

    def test_non_baseenv_with_envfield_raises(self):
        """Using Env.FIELD when env is not a BaseEnv instance should raise ValueError."""
        from localbox.builders.compose import generate_service_definition
        from localbox.models import ComposeConfig, DockerImage, Service

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_name: str = env_field()

        # Solution has a plain dict env, not a BaseEnv instance
        solution = self._make_solution({"DB_NAME": "mydb"})

        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(
                environment={"POSTGRES_DB": Env.db_name},
            ),
        )
        service._finalize_image_name()

        with pytest.raises(ValueError, match="not a BaseEnv instance"):
            generate_service_definition(solution, service)

    def test_plain_string_env_passthrough(self):
        """Regular string values in compose environment pass through as literals, not in .env."""
        from localbox.builders.compose import generate_service_definition
        from localbox.models import ComposeConfig, DockerImage, Service

        solution = self._make_solution({})

        service = Service(
            name="cache",
            image=DockerImage(image="redis:7-alpine"),
            compose=ComposeConfig(
                environment={"REDIS_MAXMEMORY": "256mb"},
            ),
        )
        service._finalize_image_name()

        collector: dict[str, str] = {}
        svc_def = generate_service_definition(solution, service, env_collector=collector)
        assert svc_def["environment"]["REDIS_MAXMEMORY"] == "256mb"
        assert collector == {}

    def _make_solution_at(self, tmp_path, env_instance=None):
        """Create a minimal Solution rooted at tmp_path."""
        from localbox.config import DirectoriesConfig, DockerSettings, Solution
        from localbox.models.solution_config import SolutionConfig

        build = tmp_path / ".build"
        config = SolutionConfig(env=env_instance or {})
        return Solution(
            root=tmp_path,
            name="test",
            directories=DirectoriesConfig(
                build=build,
                projects=build / "projects",
                compose=build / "compose",
            ),
            docker=DockerSettings(compose_project="test", network="test-net"),
            config=config,
        )

    def test_env_file_written(self, tmp_path):
        """generate_compose_file writes .env using SolutionConfig field names as keys."""
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_name: str = env_field()

        env_inst = Env(db_name="mydb")
        sol = self._make_solution_at(tmp_path, env_inst)

        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(environment={"POSTGRES_DB": Env.db_name}),
        )
        service._finalize_image_name()
        sol.services = {"db": service}

        generate_compose_file(sol)

        env_file = tmp_path / ".env"
        assert env_file.exists(), ".env file should be written when EnvField vars are present"
        content = env_file.read_text()
        assert 'db_name="mydb"' in content

    def test_env_file_skipped_when_no_env_vars(self, tmp_path):
        """generate_compose_file does not write .env when no EnvField-backed vars are present.

        Plain string env values are written as literals in docker-compose.yml and do not
        produce a .env entry, so a service with only plain strings also skips .env.
        """
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        service = Service(
            name="cache",
            image=DockerImage(image="redis:7-alpine"),
            compose=ComposeConfig(environment={"REDIS_MAXMEMORY": "256mb"}),
        )
        service._finalize_image_name()

        sol = self._make_solution_at(tmp_path)
        sol.services = {"cache": service}

        generate_compose_file(sol)

        assert not (tmp_path / ".env").exists(), ".env must not be created for plain strings"

    def test_gitignore_entries_added(self, tmp_path):
        """generate_compose_file adds docker-compose.yml and .env to .gitignore."""
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        service = Service(
            name="proxy",
            image=DockerImage(image="nginx:alpine"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()

        sol = self._make_solution_at(tmp_path)
        sol.services = {"proxy": service}

        generate_compose_file(sol)

        gitignore_content = (tmp_path / ".gitignore").read_text()
        assert "docker-compose.yml" in gitignore_content
        assert ".env" in gitignore_content

    def test_gitignore_not_duplicated(self, tmp_path):
        """Entries already in .gitignore are not duplicated on second run."""
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        # Pre-populate .gitignore with one of the entries
        (tmp_path / ".gitignore").write_text("docker-compose.yml\n")

        service = Service(
            name="proxy",
            image=DockerImage(image="nginx:alpine"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()

        sol = self._make_solution_at(tmp_path)
        sol.services = {"proxy": service}

        generate_compose_file(sol)
        generate_compose_file(sol)  # second run should not duplicate

        content = (tmp_path / ".gitignore").read_text()
        assert content.count("docker-compose.yml") == 1
        assert content.count(".env") == 1

    def test_secret_in_env_file(self, tmp_path):
        """Secret fields (is_secret=True) are still written to .env (file is gitignored)."""
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_pass: str = env_field(is_secret=True)

        env_inst = Env(db_pass="s3cr3t!")
        sol = self._make_solution_at(tmp_path, env_inst)

        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(environment={"POSTGRES_PASSWORD": Env.db_pass}),
        )
        service._finalize_image_name()
        sol.services = {"db": service}

        generate_compose_file(sol)

        env_file = tmp_path / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert 'db_pass="s3cr3t!"' in content

    def test_unreferenced_baseenv_fields_written_to_env_file(self, tmp_path):
        """All BaseEnv fields are written to .env even when not referenced by any service."""
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        @dataclasses.dataclass
        class Env(BaseEnv):
            db_name: str = env_field()
            db_pass: str = env_field(is_secret=True)

        env_inst = Env(db_name="mydb", db_pass="secret")
        sol = self._make_solution_at(tmp_path, env_inst)

        # Service does not reference any env field
        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol.services = {"db": service}

        generate_compose_file(sol)

        env_file = tmp_path / ".env"
        assert env_file.exists(), ".env must be written even when no service references env fields"
        content = env_file.read_text()
        assert 'db_name="mydb"' in content
        assert 'db_pass="secret"' in content

    def test_special_chars_are_escaped(self, tmp_path):
        """Values with special chars are double-quoted with $, `, \\, and \" escaped."""
        from localbox.builders.compose import _quote_env_value

        # Value containing single quote, double quote, dollar, backtick, backslash
        assert _quote_env_value(r"""$some'var\"abc""") == r'''"\$some'var\\\"abc"'''
        assert _quote_env_value("price $5") == r'"price \$5"'
        assert _quote_env_value("say `hi`") == r'"say \`hi\`"'
        assert _quote_env_value('say "hi"') == r'"say \"hi\""'
        assert _quote_env_value("back\\slash") == r'"back\\slash"'
        assert _quote_env_value("it's fine") == '"it\'s fine"'

    def test_dict_env_vars_written_to_env_file(self, tmp_path):
        """All non-None dict env vars in SolutionConfig are written to .env."""
        from localbox.builders.compose import generate_compose_file
        from localbox.models import ComposeConfig, DockerImage, Service

        sol = self._make_solution_at(tmp_path, {"DB_HOST": "localhost", "DB_PORT": "5432"})

        service = Service(
            name="db",
            image=DockerImage(image="postgres:16"),
            compose=ComposeConfig(),
        )
        service._finalize_image_name()
        sol.services = {"db": service}

        generate_compose_file(sol)

        env_file = tmp_path / ".env"
        assert env_file.exists()
        content = env_file.read_text()
        assert 'DB_HOST="localhost"' in content
        assert 'DB_PORT="5432"' in content
