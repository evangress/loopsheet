"""Base model, schema contract, and the shared vocabulary of the model layer.

Core purity: this module imports ``pydantic`` and the stdlib. Nothing else.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Serialized contract                                                         #
# --------------------------------------------------------------------------- #

#: Version of the *serialized machine-file contract*, not of the package.
#: Machine YAML files are real user data. Additive changes bump the minor part;
#: any rename or removal bumps the major and needs a migration note in
#: CHANGELOG.md. Never silently change a field's meaning or units.
SCHEMA_VERSION: Final[int] = 1


class LoopsheetModel(BaseModel):
    """Base for every model in the package.

    The config is deliberately strict:

    ``extra="forbid"``
        A typo in a hand-authored YAML file is an error, not a silently ignored
        key. This is the single highest-value validation setting for a package
        whose input is hand-written config.
    ``validate_assignment=True``
        Mutating a loaded model re-validates, so a `Machine` cannot be edited
        into an invalid state in memory.
    ``populate_by_name=True``
        Fields may carry YAML-friendly aliases without breaking Python access.
    ``str_strip_whitespace=True``
        Trailing spaces in a YAML tag are never meaningful.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        use_enum_values=False,
        frozen=False,
    )


class SemanticModel(LoopsheetModel):
    """A model that can carry an external semantic identifier.

    ``semantic_id`` is an IRI/IRDI naming *what this thing means* in some
    external dictionary — ECLASS, IEC CDD, an IDTA submodel template, or an
    OPC UA type node. loopsheet never interprets it; it carries it so that AAS
    export, OPC UA NodeId generation, and Sparkplug metric naming are nearly
    free later (PLAN.md §3.5).
    """

    semantic_id: str | None = Field(
        default=None,
        description="External semantic reference (ECLASS / IEC CDD IRDI, or an IRI).",
    )


# --------------------------------------------------------------------------- #
# Shared constrained field types                                              #
# --------------------------------------------------------------------------- #

#: An identifier used to cross-reference objects inside one machine file:
#: asset ids, component ids, measurement-point ids, binding targets.
#: Constrained so that ids stay usable as MQTT topic segments, OPC UA browse
#: names, and PLC tag fragments without escaping.
Identifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_.\-]*$"),
]

#: A catalog reference in ``vendor:PART`` form, e.g. ``ifm:VVB020``.
PartRef = Annotated[
    str,
    Field(min_length=3, max_length=128, pattern=r"^[a-z0-9_\-]+:[A-Za-z0-9_.\-]+$"),
]

#: IO-Link master port number. IO-Link ports are 1-based on every master and
#: in every vendor manual; 0-based indexing here would be a footgun at the
#: wiring diagram.
PortNumber = Annotated[int, Field(ge=1, le=32)]
