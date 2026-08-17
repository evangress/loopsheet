"""DAQ and edge devices.

The devices that sit beside a machine rather than inside its control system: a
data-acquisition chassis logging analog channels, or an edge gateway that reads
a fieldbus and publishes upward. They are modelled separately from
:class:`~loopsheet.models.controller.PLC` because they do not run the process —
they observe it — and because their defining property is a **sample rate**,
which a PLC's cyclic scan is not.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier
from loopsheet.models.component_base import ComponentBase
from loopsheet.models.controller import IOChannel


class DaqDevice(ComponentBase):
    """A data-acquisition device: analog channels sampled at a known rate.

    ``sample_rate_hz`` and ``resolution_bits`` are the two numbers that decide
    what the data can support. A 25 kHz sampler resolves content up to 12.5 kHz
    and no further, so recording an "8 kHz vibration band" from a 10 kHz device
    is not a configuration choice — it is a mistake, and the model should carry
    enough to notice it.
    """

    component_type: Literal["daq_device"] = "daq_device"

    ip: str | None = None
    sample_rate_hz: float | None = Field(default=None, gt=0.0)
    resolution_bits: int | None = Field(default=None, ge=1, le=64)
    simultaneous_sampling: bool | None = Field(
        default=None,
        description="True if channels are sampled together rather than multiplexed. "
        "Multiplexing introduces inter-channel phase skew, which matters for "
        "anything phase-sensitive.",
    )
    io_channels: list[IOChannel] = Field(default_factory=list)

    @property
    def nyquist_hz(self) -> float | None:
        """Highest frequency the sample rate can represent, or ``None``."""
        return self.sample_rate_hz / 2.0 if self.sample_rate_hz else None

    @model_validator(mode="after")
    def _channel_ids_unique(self) -> DaqDevice:
        seen: set[str] = set()
        for ch in self.io_channels:
            if ch.id in seen:
                raise ValueError(f"DAQ device {self.id!r}: channel id {ch.id!r} declared twice")
            seen.add(ch.id)
        return self


class EdgeDevice(ComponentBase):
    """A gateway between the machine network and everything above it.

    An IPC, an ifm IoT Core master acting as a gateway, or any box whose job is
    to read one protocol and publish another. ``upstream_of`` names the
    components whose data it carries, which is what lets an export walk from a
    sensor to the broker its values actually reach.
    """

    component_type: Literal["edge_device"] = "edge_device"

    ip: str | None = None
    hostname: str | None = None
    firmware: str | None = None
    upstream_of: list[Identifier] = Field(
        default_factory=list,
        description="Ids of components whose data this device forwards.",
    )
