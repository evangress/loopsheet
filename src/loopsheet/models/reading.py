"""A single decoded process value.

`Reading` is the one *runtime* type in an otherwise configuration-only package.
It is what :func:`loopsheet.codec.decode` produces: a raw process-data word
turned into an engineering value that still knows where it came from.

Deliberately **not** here: history, storage, aggregation, alarming. loopsheet
models machines and decodes bytes; keeping a `Reading` a value object is what
stops it from growing into a historian.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import ConfigDict, Field

from loopsheet.models.base import LoopsheetModel
from loopsheet.models.units import Unit


class Quality(StrEnum):
    """Confidence in a decoded value.

    Modelled on the OPC UA / IO-Link split rather than a bare boolean, because
    "the master answered but the device flagged the data invalid" is a genuinely
    different situation from "the wire is dead", and an operator needs to tell
    them apart.
    """

    GOOD = "good"
    """Decoded from valid process data."""

    UNCERTAIN = "uncertain"
    """Decoded, but something upstream is degraded — e.g. an analog channel
    reading inside its over-range band, or a stale cyclic value."""

    BAD = "bad"
    """Not usable. The device reported invalid process data (EtherNet/IP PQI
    bit 2, ifm IoT Core code 530), the port has no device, or the wire is
    broken."""


class Reading(LoopsheetModel):
    """One decoded value, frozen.

    Frozen because a reading is a fact about a moment: mutating one in place
    means some other reference now silently disagrees about what the sensor
    said. Produce a new one instead.

    Attributes:
        name: Channel name as declared on the device, e.g. ``"v_rms"``.
        value: The engineering value. ``None`` when ``quality`` is
            :attr:`Quality.BAD` — an unusable channel has no number, and
            emitting ``0.0`` for "no data" is exactly the silent lie this
            package exists to avoid. ``str`` appears only for ``StringT``
            process-data items, which carry text rather than a measurement.
        unit: Engineering unit; ``None`` if the channel declares none, ``""``
            if it is explicitly dimensionless.
        timestamp: When the value was *observed*, not when it was decoded.
            ``None`` for a decode from a byte string with no known time.
        quality: See :class:`Quality`.
        source: Where the bytes came from — a component tag, a topic, a NodeId.
            Free-form on purpose; it is for humans reading a log.
        raw: The raw integer word before gradient/offset scaling, kept for
            diagnostics. This is what you compare against a vendor tool when a
            decode looks wrong.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
        frozen=True,
    )

    name: str = Field(min_length=1)
    value: bool | int | float | str | None = None
    unit: Unit | None = None
    timestamp: datetime | None = None
    quality: Quality = Quality.GOOD
    source: str | None = None
    raw: int | None = Field(
        default=None,
        description="Raw integer word before scaling, for diagnostics.",
    )

    def __str__(self) -> str:
        if self.value is None:
            return f"{self.name}=<{self.quality.value}>"
        unit = f" {self.unit}" if self.unit else ""
        flag = "" if self.quality is Quality.GOOD else f" [{self.quality.value}]"
        return f"{self.name}={self.value}{unit}{flag}"
