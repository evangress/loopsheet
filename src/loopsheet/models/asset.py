"""Mechanical assets and the points at which they are measured.

This is the half of the model that has nothing to do with wiring. A vibration
reading has to be *about* something — "pump P-101, drive-end bearing,
radial-horizontal" — and without that link the package models a wiring list
rather than a machine (PLAN.md §3.3).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier, SemanticModel

# --------------------------------------------------------------------------- #
# Mechanical assets                                                           #
# --------------------------------------------------------------------------- #


class AssetBase(SemanticModel):
    """Common fields for anything that rotates, pumps, or drives."""

    id: Identifier
    name: str | None = Field(default=None, description="Human label; defaults to the id.")
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    description: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.id


class Motor(AssetBase):
    """An electric motor.

    ``rated_rpm`` matters beyond documentation: running speed sets the 1x order,
    which is what makes a vibration spectrum interpretable at all.
    """

    kind: Literal["motor"] = "motor"
    rated_rpm: float | None = Field(default=None, gt=0.0)
    rated_kw: float | None = Field(default=None, gt=0.0)
    rated_voltage_v: float | None = Field(default=None, gt=0.0)
    poles: int | None = Field(default=None, ge=2, description="Pole count, always even.")
    frame_size: str | None = None
    driven_by_vfd: bool = Field(
        default=False,
        description="A VFD makes running speed variable, so a fixed rated_rpm "
        "is no longer the 1x order at runtime.",
    )

    @model_validator(mode="after")
    def _poles_even(self) -> Motor:
        if self.poles is not None and self.poles % 2:
            raise ValueError(f"motor {self.id!r}: pole count must be even, got {self.poles}")
        return self


class Pump(AssetBase):
    """A pump. ``driver`` names the asset that turns it."""

    kind: Literal["pump"] = "pump"
    driver: Identifier | None = Field(
        default=None, description="Id of the driving asset, usually a motor."
    )
    pump_type: str | None = Field(default=None, description="e.g. 'centrifugal', 'gear'.")
    vane_count: int | None = Field(
        default=None,
        ge=1,
        description="Impeller vanes — sets the vane-pass order in a spectrum.",
    )
    rated_flow_m3h: float | None = Field(default=None, gt=0.0)
    rated_head_m: float | None = Field(default=None, gt=0.0)


class Fan(AssetBase):
    """A fan or blower."""

    kind: Literal["fan"] = "fan"
    driver: Identifier | None = None
    blade_count: int | None = Field(
        default=None, ge=1, description="Sets the blade-pass order in a spectrum."
    )
    rated_flow_m3h: float | None = Field(default=None, gt=0.0)


class Gearbox(AssetBase):
    """A gearbox. ``ratio`` is input:output, so 4.5 means 4.5 turns in per turn out."""

    kind: Literal["gearbox"] = "gearbox"
    driver: Identifier | None = None
    ratio: float | None = Field(default=None, gt=0.0)
    stages: int | None = Field(default=None, ge=1)
    tooth_counts: list[int] | None = Field(
        default=None,
        description="Teeth per gear, in mesh order — sets gear-mesh orders.",
    )


class Bearing(AssetBase):
    """A bearing, usually a child of the asset it supports.

    ``designation`` is the thing worth capturing: given "6205" a downstream
    tool can look up the fault frequencies. loopsheet does not ship a bearing
    database — that is a different package's job.
    """

    kind: Literal["bearing"] = "bearing"
    host: Identifier | None = Field(
        default=None, description="Id of the asset this bearing supports."
    )
    designation: str | None = Field(default=None, description="e.g. '6205', 'NU312'.")
    rolling_elements: int | None = Field(default=None, ge=1)


#: Every mechanical asset, discriminated on ``kind``.
Asset = Annotated[
    Motor | Pump | Fan | Gearbox | Bearing,
    Field(discriminator="kind"),
]


# --------------------------------------------------------------------------- #
# Measurement points                                                          #
# --------------------------------------------------------------------------- #


class Location(StrEnum):
    """Where on the asset the point sits.

    Drive end / non-drive end is the vocabulary every vibration analyst and
    every ISO 10816 report already uses; inventing a different one would make
    loopsheet data harder to read, not easier.
    """

    DRIVE_END = "drive_end"
    NON_DRIVE_END = "non_drive_end"
    INBOARD = "inboard"
    OUTBOARD = "outboard"
    INPUT = "input"
    OUTPUT = "output"
    CASING = "casing"
    FOUNDATION = "foundation"
    OTHER = "other"


class Axis(StrEnum):
    """Measurement direction relative to the shaft."""

    RADIAL_HORIZONTAL = "radial_horizontal"
    RADIAL_VERTICAL = "radial_vertical"
    AXIAL = "axial"
    TRIAXIAL = "triaxial"
    UNSPECIFIED = "unspecified"


class Mounting(StrEnum):
    """How the sensor is attached — this caps usable bandwidth.

    ifm's own figures (``docs/research/ifm-vvb020.md`` §4): screw ≈15 kHz,
    glue ≈8 kHz, magnet ≈3 kHz. A 5 kHz a-RMS channel on a magnet-mounted
    sensor is not measuring what its datasheet says it measures, and that is
    worth being able to check.
    """

    SCREW = "screw"
    GLUE = "glue"
    MAGNET = "magnet"
    STUD = "stud"
    HANDHELD = "handheld"
    UNSPECIFIED = "unspecified"

    @property
    def max_transferable_hz(self) -> float | None:
        """Approximate upper frequency the mounting transfers, or ``None``.

        Vendor guidance figures, not a specification — use them to flag a
        suspicious configuration, never to correct a measured value.
        """
        return {
            Mounting.SCREW: 15_000.0,
            Mounting.STUD: 15_000.0,
            Mounting.GLUE: 8_000.0,
            Mounting.MAGNET: 3_000.0,
        }.get(self)


class MeasurementPoint(SemanticModel):
    """A physical place on an asset where a sensor is mounted.

    The sensor ↔ asset link. A component references a point by id via
    ``mounted_at``; the point references the asset it belongs to. Keeping the
    point separate from both means a sensor can be replaced without rewriting
    the asset, and an asset can carry points that have no sensor yet.
    """

    id: Identifier
    asset: Identifier = Field(description="Id of the asset this point is on.")
    location: Location = Location.OTHER
    axis: Axis = Axis.UNSPECIFIED
    mounting: Mounting = Mounting.UNSPECIFIED
    description: str | None = None
