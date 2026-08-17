"""Channels and signals — the loop-sheet row.

A :class:`ChannelSpec` is *what a device can tell you*: one named measurable
value with its unit, range, and enough provenance to find it on the wire again.

A :class:`Signal` is *one row of the loop sheet*: this channel, on this
component, measuring this point, known downstream by this tag. It is the join
that makes the rest of the package worth having.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier, SemanticModel
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.units import Unit


class ValueRange(SemanticModel):
    """A closed measuring range in engineering units."""

    low: float
    high: float

    @model_validator(mode="after")
    def _ordered(self) -> ValueRange:
        if self.low > self.high:
            raise ValueError(f"range low ({self.low}) must not exceed high ({self.high})")
        return self

    def contains(self, value: float) -> bool:
        """True if ``value`` falls inside the range, inclusive."""
        return self.low <= value <= self.high

    def __str__(self) -> str:
        return f"{self.low}…{self.high}"


class FrequencyBand(SemanticModel):
    """The frequency band a value is evaluated over, in Hz.

    Vibration values are meaningless without one: the ifm VVB020's v-RMS is
    evaluated over 10…1000 Hz at factory defaults and a-RMS over 10…5000 Hz,
    set by the configurable filter chain rather than fixed in hardware
    (``docs/research/ifm-vvb020.md`` §3). Two v-RMS numbers from different
    filter settings are not comparable, so the band travels with the channel.
    """

    low_hz: float = Field(ge=0.0)
    high_hz: float = Field(gt=0.0)

    @model_validator(mode="after")
    def _ordered(self) -> FrequencyBand:
        if self.low_hz >= self.high_hz:
            raise ValueError(f"band low_hz ({self.low_hz}) must be below high_hz ({self.high_hz})")
        return self

    def __str__(self) -> str:
        return f"{self.low_hz}…{self.high_hz} Hz"


class ChannelSpec(SemanticModel):
    """One named measurable value a device produces.

    Everything except ``name`` is optional, because a channel is often known
    semantically long before its wire layout is. The VVB020 ships today with
    five fully described channels and no bit offsets at all — its IODD is not
    obtainable without a login. Modelling those as "known name, unknown
    location" is honest; inventing a plausible ``bit_offset`` would not be.

    The provenance block (``index``/``subindex``/``bit_offset``/``bit_length``)
    is what makes AAS export, OPC UA NodeId generation, and Sparkplug metric
    naming nearly free later (PLAN.md §3.5). Carry it even when nothing reads
    it yet.
    """

    name: Identifier
    description: str | None = None

    unit: Unit | None = None
    range: ValueRange | None = None
    resolution: float | None = Field(
        default=None,
        gt=0.0,
        description="Smallest resolvable step in engineering units.",
    )
    accuracy: str | None = Field(
        default=None,
        description="Datasheet accuracy, verbatim — e.g. '± 2.5 K + (0.2 x delta-T)'. "
        "Free text because vendors state it as a formula, not a number.",
    )
    band_hz: FrequencyBand | None = None

    # --- provenance: where this value lives on the wire ---------------------
    datatype: IOLinkDataType | None = None
    bit_offset: int | None = Field(
        default=None,
        ge=0,
        description="Offset of this item's LSB from the LSB of the whole process-data "
        "word, per the IODD RecordItem convention. See "
        "loopsheet.models.processdata for the full bit-order note.",
    )
    bit_length: int | None = Field(default=None, ge=1, le=64)
    index: int | None = Field(
        default=None, ge=0, le=65535, description="ISDU index, for acyclic parameters."
    )
    subindex: int | None = Field(default=None, ge=0, le=255)

    @model_validator(mode="after")
    def _bit_layout_is_complete_or_absent(self) -> ChannelSpec:
        """A half-specified bit location is worse than none at all.

        ``bit_offset`` without ``bit_length`` decodes an arbitrary number of
        bits; ``bit_length`` without ``bit_offset`` decodes from an arbitrary
        place. Either the layout is known or it is not.
        """
        if (self.bit_offset is None) != (self.bit_length is None):
            raise ValueError(
                f"channel {self.name!r}: bit_offset and bit_length must be given "
                "together or not at all — a partial bit layout decodes garbage"
            )
        fixed = self.datatype.fixed_bit_length if self.datatype else None
        if fixed is not None and self.bit_length is not None and self.bit_length != fixed:
            raise ValueError(
                f"channel {self.name!r}: datatype {self.datatype} is always {fixed} bits, "
                f"got bit_length={self.bit_length}"
            )
        return self

    @property
    def layout_known(self) -> bool:
        """True if this channel can be located in a process-data word."""
        return self.bit_offset is not None and self.bit_length is not None


class Signal(SemanticModel):
    """One row of the loop sheet.

    Follows a single measurable value end to end: which component produces it,
    which of that component's channels it is, what physical point it describes,
    and what the rest of the plant calls it.

    ``tag`` is the name that travels: it is what an MQTT topic, an OPC UA
    BrowseName, or a PLC tag is built from. ``component`` / ``channel`` /
    ``measurement_point`` are references resolved by the loader against the
    machine they belong to — a `Signal` deliberately holds ids rather than
    objects so that a machine file stays a flat, diffable document.
    """

    tag: Identifier
    component: Identifier
    channel: Identifier
    measurement_point: Identifier | None = None
    description: str | None = None
