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
        """Env.FIELD reference in compose environment should resolve to actual value."""
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

        svc_def = generate_service_definition(solution, service)
        assert svc_def["environment"]["POSTGRES_DB"] == "mydb"

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
        """Regular string values in compose environment should pass through unchanged."""
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

        svc_def = generate_service_definition(solution, service)
        assert svc_def["environment"]["REDIS_MAXMEMORY"] == "256mb"
