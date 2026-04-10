"""BaseEnv — typed environment base class for solution.py."""

import dataclasses
from typing import Any

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


class EnvRef(str):
    """A `str` subclass whose value is ``${<name>}``.

    Instance access on a :class:`BaseEnv` subclass returns an ``EnvRef``, so
    f-strings and concatenation naturally produce compose-style variable
    references. The original raw value is preserved on ``EnvRef.raw``.
    """

    name: str
    raw: str

    def __new__(cls, name: str, raw: str) -> "EnvRef":
        inst = super().__new__(cls, f"${{{name}}}")
        inst.name = name
        inst.raw = raw
        return inst

    def __repr__(self) -> str:
        return f"EnvRef(name={self.name!r}, raw={self.raw!r})"


@dataclasses.dataclass
class BaseEnv:
    """Base class for solution environment definitions.

    Subclasses must be decorated with @dataclass. All fields must use env_field().

    Usage:
        @dataclasses.dataclass
        class Env(BaseEnv):
            DB_NAME: str = env_field()
            DB_PASS: str = env_field(is_secret=True)

    After construction, instance-level access to each field returns an
    :class:`EnvRef` (a ``str`` equal to ``"${FIELD}"``). Raw values are
    available via :meth:`raw_value` and :meth:`raw_values`.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        # Validate all annotated fields use env_field().
        # Runs before @dataclass is applied, so inspect raw class namespace.
        for name in cls.__annotations__:
            default = cls.__dict__.get(name, _MISSING)
            if default is _MISSING or not isinstance(default, EnvField):
                raise TypeError(f"{cls.__name__}.{name}: must use env_field(), got {default!r}")

    def __post_init__(self) -> None:
        # Collect raw values and replace instance attrs with EnvRef references.
        #
        # Every declared field becomes an EnvRef, even when the user did not
        # supply a value. Unset fields produce an EnvRef whose ``raw`` is an
        # empty string and that is absent from ``_raw_values``; the compose
        # walker raises ``ValueError`` if such a field is actually referenced
        # at generate time. This lets users build ``ComposeConfig.environment``
        # dicts at import time with ``config.env.db_pass`` even when
        # ``db_pass`` is set later by ``solution-override.py``.
        raw: dict[str, str] = {}
        object.__setattr__(self, "_raw_values", raw)
        for f in dataclasses.fields(self):
            value = object.__getattribute__(self, f.name)
            if isinstance(value, EnvField):
                # Leave the raw mapping empty for this field but rewrite the
                # instance attribute so f-strings still produce ``${name}``.
                object.__setattr__(self, f.name, EnvRef(f.name, ""))
                continue
            raw[f.name] = value
            object.__setattr__(self, f.name, EnvRef(f.name, value))

    def __setattr__(self, name: str, value: Any) -> None:
        # Route assignments to declared fields through _raw_values so that
        # late overrides (e.g. in solution-override.py:
        #     solution.config.env.db_pass = "x"
        # ) update the raw mapping and the instance attr stays an EnvRef.
        #
        # During dataclass-generated __init__ (which runs before
        # __post_init__), `_raw_values` does not exist yet. In that window we
        # fall through to plain attribute assignment and let __post_init__
        # convert every field to an EnvRef at the end of construction.
        try:
            raw_map: dict[str, str] = object.__getattribute__(self, "_raw_values")
        except AttributeError:
            object.__setattr__(self, name, value)
            return

        field_names = {f.name for f in dataclasses.fields(self)}
        if name not in field_names:
            object.__setattr__(self, name, value)
            return

        # Accept raw strings, EnvRef (unwrap to its .raw), and the EnvField
        # sentinel (which means "unset this field").
        if isinstance(value, EnvField):
            raw_map.pop(name, None)
            object.__setattr__(self, name, value)
            return

        raw_value: str = value.raw if isinstance(value, EnvRef) else value
        raw_map[name] = raw_value
        object.__setattr__(self, name, EnvRef(name, raw_value))

    def raw_value(self, name: str) -> str:
        """Return the raw value for ``name``.

        Raises ``KeyError`` if the field does not exist or was never set.
        """
        raw: dict[str, str] = object.__getattribute__(self, "_raw_values")
        return raw[name]

    def raw_values(self) -> dict[str, str]:
        """Return a copy of the mapping of field name → raw value.

        Only fields that were actually set on the instance appear here.
        """
        raw: dict[str, str] = object.__getattribute__(self, "_raw_values")
        return dict(raw)
