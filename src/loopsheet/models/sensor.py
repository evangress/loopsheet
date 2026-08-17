"""Sensors — IO-Link, analog, and discrete.

Three sensor kinds cover essentially every field device that lands on a machine
today. What distinguishes them is not what they measure but *how a value gets
off them*, which is what determines how loopsheet turns raw data into a
:class:`~loopsheet.models.reading.Reading`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier, PortNumber
from loopsheet.models.channel import ValueRange
from loopsheet.models.component_base import ComponentBase
from loopsheet.models.processdata import ProcessDataLayout
from loopsheet.models.units import Unit


class ComMode(StrEnum):
    """IO-Link physical transmission rate.

    Not cosmetic: COM mode sets the achievable cycle time, and the two software
    statuses of the same ifm VVB020 part number differ by it — status A is COM2
    at 11.6 ms minimum, status B is COM3 at 3.6 ms
    (``docs/research/ifm-vvb020.md`` §1).
    """

    COM1 = "COM1"
    """4.8 kBaud."""

    COM2 = "COM2"
    """38.4 kBaud."""

    COM3 = "COM3"
    """230.4 kBaud."""


class SensorBase(ComponentBase):
    """Fields shared by every sensor."""

    mounted_at: Identifier | None = Field(
        default=None,
        description="Id of the MeasurementPoint this sensor is mounted at. "
        "Without it a reading is a number with no subject.",
    )
    measures: str | None = Field(
        default=None,
        description="What is being measured, e.g. 'vibration', 'temperature'.",
    )


class IOLinkSensor(SensorBase):
    """A sensor speaking IO-Link into a master port.

    ``process_data`` is the layout its cyclic PDIn arrives in. It is
    **optional and frequently ``None``** — the layout comes from the device's
    IODD, and an IODD is not always obtainable. The proof-case VVB020 is
    exactly that situation today. Decoding against ``None`` raises a clear
    "layout unavailable, IODD required" error rather than returning a
    plausible wrong number.

    ``device_id`` pins the wire-level identity. A part number is not one
    IO-Link identity, so where a part has variants the machine file pins one
    (``variant: status_b``) and an adapter can confirm the pin at runtime
    against ``.../iolinkdevice/deviceid``.
    """

    component_type: Literal["iolink_sensor"] = "iolink_sensor"

    master: Identifier | None = Field(
        default=None, description="Id of the IOLinkMaster this sensor is wired to."
    )
    port: PortNumber | None = None

    vendor_id: int | None = Field(default=None, ge=0, le=65535)
    device_id: int | None = Field(default=None, ge=0, le=0xFFFFFF)
    com_mode: ComMode | None = None
    min_cycle_time_ms: float | None = Field(default=None, gt=0.0)
    iolink_revision: str | None = Field(default=None, description="e.g. '1.1'.")
    sio_supported: bool | None = None

    process_data: ProcessDataLayout | None = Field(
        default=None,
        description="PDIn layout. None means 'not known' — decode must refuse, not guess.",
    )
    process_data_out: ProcessDataLayout | None = Field(
        default=None, description="PDOut layout, where the device has one."
    )

    @model_validator(mode="after")
    def _master_and_port_travel_together(self) -> IOLinkSensor:
        if (self.master is None) != (self.port is None):
            raise ValueError(
                f"sensor {self.id!r}: master and port must be given together — "
                "a port number without a master does not identify a physical socket"
            )
        return self


class SignalType(StrEnum):
    """The analog current or voltage standard on the wire.

    Live-zero standards (``4-20 mA``, ``2-10 V``) are the ones worth having: a
    reading of 0 mA is unambiguously a broken wire rather than a legitimate
    zero, which is what makes :class:`~loopsheet.models.reading.Quality.BAD`
    detectable at all.
    """

    MA_4_20 = "4-20mA"
    MA_0_20 = "0-20mA"
    V_0_10 = "0-10V"
    V_2_10 = "2-10V"
    V_PM_10 = "±10V"

    @property
    def has_live_zero(self) -> bool:
        """True if a below-range signal is distinguishable from a real zero."""
        return self in {SignalType.MA_4_20, SignalType.V_2_10}


class AnalogSensor(SensorBase):
    """A 4-20 mA or 0-10 V transmitter on an analog input channel.

    ``scaled_range`` is the engineering span the full signal maps to: a
    4-20 mA transmitter with ``scaled_range: {low: 0, high: 16}`` and
    ``unit: bar`` reads 0 bar at 4 mA and 16 bar at 20 mA. The conversion
    itself lives in :mod:`loopsheet.codec.scaling`.
    """

    component_type: Literal["analog_sensor"] = "analog_sensor"

    signal_type: SignalType = SignalType.MA_4_20
    scaled_range: ValueRange | None = Field(
        default=None, description="Engineering span the full signal maps to."
    )
    unit: Unit | None = None

    controller: Identifier | None = Field(
        default=None, description="Id of the PLC or DAQ device this lands on."
    )
    io_channel: Identifier | None = Field(
        default=None, description="Id of the IOChannel it is wired to."
    )

    @model_validator(mode="after")
    def _scaled_range_needs_a_unit(self) -> AnalogSensor:
        if self.scaled_range is not None and self.unit is None:
            raise ValueError(
                f"analog sensor {self.id!r}: scaled_range is given without a unit. "
                "An engineering span with no unit cannot be interpreted"
            )
        return self


class DiscreteSensor(SensorBase):
    """A switch, proximity sensor, or any other on/off input.

    ``normally_closed`` and ``active_low`` are separate on purpose: the first
    is a property of the device, the second of the input circuit, and a
    correctly-wired NC sensor on a sinking input is not the same thing as
    either one alone.
    """

    component_type: Literal["discrete_sensor"] = "discrete_sensor"

    normally_closed: bool = Field(
        default=False, description="Device contact is closed in the un-actuated state."
    )
    active_low: bool = Field(
        default=False, description="Input circuit reads TRUE when the signal is pulled low."
    )
    on_state_text: str | None = Field(default=None, description="e.g. 'part present'.")
    off_state_text: str | None = None

    controller: Identifier | None = None
    io_channel: Identifier | None = None
