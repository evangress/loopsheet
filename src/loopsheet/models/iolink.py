"""IO-Link masters and their ports.

Enum values are sourced from the EtherNet/IP configuration assembly documented
in ``docs/research/ifm-masters.md`` §4.6, where ifm prints them as concrete
byte values. The equivalent ifm IoT Core JSON enum (``port[n]/mode``) is
**UNVERIFIED** — plausibly the same numbers, but the manual does not say, and
it is resolvable at runtime via ``getelementinfo`` →
``format.valuation.valuelist``. loopsheet therefore models modes by *name*, and
leaves the numeric mapping to whichever adapter is talking.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier, PortNumber
from loopsheet.models.component_base import ComponentBase


class PortMode(StrEnum):
    """What a master port is doing.

    Byte ``n+0`` of ifm's config assembly 199: ``0x00`` Disabled, ``0x01`` DI
    (pin 4), ``0x02`` DO (pin 4), ``0x03`` IO-Link.
    """

    DISABLED = "disabled"
    DI = "di"
    """Digital input on pin 4 — the port is in SIO mode, reading a switch."""

    DO = "do"
    """Digital output on pin 4."""

    IOLINK = "iolink"
    """IO-Link communication. The only mode in which process data is decoded."""


class ValidationMode(StrEnum):
    """How strictly the master checks the device plugged into a port.

    Byte ``n+3`` of ifm's config assembly 199. The mode matters for more than
    safety: the VVB020 status-B variant is **rejected** unless device
    identification is enabled, because status A and status B differ only by
    device ID at the wire level (``docs/research/ifm-vvb020.md`` §1).

    The Backup/Restore options carry an operational hazard worth knowing:
    changing them can push stored parameters back onto a replaced device,
    overwriting a field technician's settings.
    """

    NONE = "none"
    """No check, and clear any stored data (``0x00``)."""

    TYPE_COMPATIBLE_V10 = "type_compatible_v10"
    """Vendor ID + device ID checked, IO-Link 1.0 device (``0x01``)."""

    TYPE_COMPATIBLE_V11 = "type_compatible_v11"
    """Vendor ID + device ID checked, IO-Link 1.1 device (``0x02``)."""

    V11_BACKUP_RESTORE = "v11_backup_restore"
    """1.1 + data storage backup *and* restore (``0x03``)."""

    V11_BACKUP = "v11_backup"
    """1.1 + data storage backup only (``0x04``)."""

    @property
    def checks_device_id(self) -> bool:
        """True if this mode verifies the device ID, and so pins the variant."""
        return self is not ValidationMode.NONE


class CycleTime(IntEnum):
    """Master cycle-time setting, as the fixed enum ifm exposes.

    Byte ``n+1`` of config assembly 199. Values are milliseconds, except
    :attr:`FASTEST`, which asks the master to negotiate the quickest cycle the
    device supports. A device's own floor still applies — the VVB020 needs
    11.6 ms in status A (COM2) and 3.6 ms in status B (COM3), so pinning 2 ms
    on a status-A unit is not achievable however it is configured.
    """

    FASTEST = 0
    MS_2 = 2
    MS_4 = 4
    MS_8 = 8
    MS_16 = 16
    MS_32 = 32
    MS_64 = 64
    MS_128 = 128


class Port(ComponentBase):
    """One port on an IO-Link master.

    A port is modelled as a component in its own right rather than a bare int
    so that it can carry its own validation policy, cycle time, and — once a
    device is attached — that device's identity. ``device`` is the id of the
    component plugged in, resolved by the loader.
    """

    component_type: Literal["iolink_port"] = "iolink_port"

    number: PortNumber
    mode: PortMode = PortMode.IOLINK
    validation: ValidationMode = ValidationMode.NONE
    cycle_time: CycleTime = CycleTime.FASTEST

    device: Identifier | None = Field(
        default=None, description="Id of the component plugged into this port."
    )
    expected_vendor_id: int | None = Field(default=None, ge=0, le=65535)
    expected_device_id: int | None = Field(default=None, ge=0, le=0xFFFFFF)

    @model_validator(mode="after")
    def _device_requires_iolink_mode(self) -> Port:
        if self.device is not None and self.mode is not PortMode.IOLINK:
            raise ValueError(
                f"port {self.number}: an IO-Link device ({self.device!r}) is attached "
                f"but the port mode is {self.mode.value!r}. A device in "
                f"{self.mode.value!r} mode produces no process data to decode — "
                "set mode: iolink, or attach the device as a discrete signal instead"
            )
        return self


class IOLinkMaster(ComponentBase):
    """An IO-Link master: the gateway between IO-Link devices and a fieldbus.

    ``ip`` is the address of whichever interface loopsheet talks to. ifm's
    EtherNet/IP masters expose *two* — the fieldbus port (default
    ``192.168.1.250``) and a separate IoT port (link-local ``169.254.x.x``) —
    so ``iot_ip`` exists to describe them both without pretending they are one
    device.

    Which protocols a master can actually serve is a property of the *part*,
    not of this model: see ``supported_bindings`` on the catalog entry. No
    single ifm master speaks MQTT and OPC UA and EtherNet/IP
    (``docs/research/ifm-masters.md`` §0.3), and attaching a binding the
    hardware cannot serve must fail validation.
    """

    component_type: Literal["iolink_master"] = "iolink_master"

    ip: str | None = Field(default=None, description="Fieldbus / primary interface address.")
    iot_ip: str | None = Field(
        default=None,
        description="Separate IoT-port address, where the master has one.",
    )
    port_count: int | None = Field(default=None, ge=1, le=32)
    ports: list[Port] = Field(default_factory=list)
    firmware: str | None = Field(
        default=None,
        description="Firmware version. Load-bearing, not cosmetic: MQTT is "
        "present on ifm AL1320/AL1321 at FW 3.1.x and absent on AL1322/AL1323 "
        "at FW 2.3.x for the same protocol family.",
    )

    @model_validator(mode="after")
    def _ports_are_unique_and_in_range(self) -> IOLinkMaster:
        seen: set[int] = set()
        for port in self.ports:
            if port.number in seen:
                raise ValueError(f"master {self.id!r}: port {port.number} declared twice")
            seen.add(port.number)
            if self.port_count is not None and port.number > self.port_count:
                raise ValueError(
                    f"master {self.id!r}: port {port.number} declared, but the master "
                    f"has only {self.port_count} ports"
                )
        return self

    def port(self, number: int) -> Port | None:
        """Return the port with this number, or ``None``."""
        return next((p for p in self.ports if p.number == number), None)
