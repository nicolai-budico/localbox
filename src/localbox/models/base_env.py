"""BaseEnv — typed environment base class for solution.py."""

import dataclasses

_MISSING = object()  # local sentinel for "no default given"


@dataclasses.dataclass(frozen=True)
class EnvField:
    """Sentinel stored as class-level default on BaseEnv subclasses."""

    is_secret: bool = False


def env_field(is_secret: bool = False) -> "EnvField":
    """Declare an Env field. Use is_secret=True to mask value in logs/output."""
    return EnvField(is_secret=is_secret)


def is_env_secret(field: "EnvField") -> bool:
    return field.is_secret


@dataclasses.dataclass
class BaseEnv:
    """Base class for solution environment definitions.

    Subclasses must be decorated with @dataclass. All fields must use env_field().

    Usage:
        @dataclasses.dataclass
        class Env(BaseEnv):
            DB_NAME: str = env_field()
            DB_PASS: str = env_field(is_secret=True)
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        # Validate all annotated fields use env_field().
        # Runs before @dataclass is applied, so inspect raw class namespace.
        for name in cls.__annotations__:
            default = cls.__dict__.get(name, _MISSING)
            if default is _MISSING or not isinstance(default, EnvField):
                raise TypeError(f"{cls.__name__}.{name}: must use env_field(), got {default!r}")
