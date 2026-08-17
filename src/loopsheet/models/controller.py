"""Controllers and the I/O tree beneath them.

A `PLC` owns chassis, a chassis owns modules, a module owns channels, and a
channel is where a physical wire lands. This is the half of the loop sheet
that a controls engineer draws from the right-hand side.

The vocabulary leans Rockwell (chassis / slot / module / tag) because that is
the proof-case controller, but nothing here is vendor-specific: a Siemens rack
and slot map onto the same three levels, and ``address`` is free text precisely
so ``%IW64`` and ``Local:2:I.Ch0Data`` can both be written down honestly.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier, SemanticModel
from loopsheet.models.channel import ValueRange
from loopsheet.models.component_base import ComponentBase
from loopsheet.models.units import Unit


class IODirection(StrEnum):
    """Which way the signal flows, from the controller's point of view."""

    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"


class IOSignal(StrEnum):
    """The electrical nature of an I/O channel."""

    DISCRETE = "discrete"
    ANALOG_CURRENT = "analog_current"
    ANALOG_VOLTAGE = "analog_voltage"
    RTD = "rtd"
    THERMOCOUPLE = "thermocouple"
    HIGH_SPEED_COUNTER = "high_speed_counter"


class IOChannel(SemanticModel):
    """One physical terminal on an I/O module.

    ``raw_range`` is the module's count span — 4-20 mA on a 16-bit Rockwell
    analog card is typically 3277…16383 counts, and that is a property of the
    *card*, not of the transmitter. Keeping it here, separate from the
    sensor's engineering span, is what makes
    :mod:`loopsheet.codec.scaling` a pure function of two ranges instead of a
    pile of vendor special-cases.
    """

    id: Identifier
    number: int = Field(ge=0, description="Channel number on the module, usually 0-based.")
    direction: IODirection = IODirection.INPUT
    signal: IOSignal = IOSignal.DISCRETE

    address: str | None = Field(
        default=None,
        description="Controller-native address, verbatim — '%IW64', "
        "'Local:2:I.Ch0Data'. Free text because every vendor spells it differently.",
    )
    raw_range: ValueRange | None = Field(
        default=None, description="The module's raw count span for this channel."
    )
    unit: Unit | None = None
    description: str | None = None


class IOModule(SemanticModel):
    """A card in a chassis."""

    id: Identifier
    slot: int = Field(ge=0)
    part: str | None = Field(default=None, description="Catalog part, e.g. '5069-IF8'.")
    channels: list[IOChannel] = Field(default_factory=list)
    description: str | None = None

    @model_validator(mode="after")
    def _channel_numbers_unique(self) -> IOModule:
        seen: set[int] = set()
        for ch in self.channels:
            if ch.number in seen:
                raise ValueError(f"module {self.id!r}: channel {ch.number} declared twice")
            seen.add(ch.number)
        return self


class Chassis(SemanticModel):
    """A rack or backplane holding modules."""

    id: Identifier
    part: str | None = None
    modules: list[IOModule] = Field(default_factory=list)
    description: str | None = None

    @model_validator(mode="after")
    def _slots_unique(self) -> Chassis:
        seen: set[int] = set()
        for module in self.modules:
            if module.slot in seen:
                raise ValueError(
                    f"chassis {self.id!r}: slot {module.slot} occupied twice (module {module.id!r})"
                )
            seen.add(module.slot)
        return self


class Tag(SemanticModel):
    """A named variable in the controller's program.

    The bridge between the electrical world and the software one. ``address``
    points at the I/O channel it is wired from, where there is one; a computed
    tag has none, and that is a legitimate row of a loop sheet too.
    """

    name: Identifier
    datatype: str | None = Field(default=None, description="Controller datatype, e.g. 'REAL'.")
    address: str | None = None
    io_channel: Identifier | None = None
    unit: Unit | None = None
    description: str | None = None


class PLC(ComponentBase):
    """A programmable controller."""

    component_type: Literal["plc"] = "plc"

    ip: str | None = None
    slot: int | None = Field(default=None, ge=0, description="CPU slot, for backplane routing.")
    firmware: str | None = None
    chassis: list[Chassis] = Field(default_factory=list)
    tags: list[Tag] = Field(default_factory=list)

    def io_channels(self) -> list[IOChannel]:
        """Every I/O channel under this controller, flattened."""
        return [ch for c in self.chassis for m in c.modules for ch in m.channels]
