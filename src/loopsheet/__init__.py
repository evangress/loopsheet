"""loopsheet — digital-twin data models for industrial machines.

Describe a machine and everything bolted to it once, as typed data, and reuse
that description for validation, protocol configuration, and decoding raw
process data into engineering units.

An ISA-5.4 *loop sheet* is the drawing that follows one instrument end to end —
sensor, tag, wiring, I/O channel, controller, engineering-unit scaling. That
join is what this package models.

    >>> from loopsheet import Machine, Motor
    >>> m = Machine(name="filler_line_3", assets=[Motor(id="M101", rated_rpm=1780)])
    >>> m.asset("M101").rated_rpm
    1780.0

Core installs ``pydantic`` and ``pyyaml`` and nothing else. Every wire protocol
lives behind an optional extra and is imported only from
:mod:`loopsheet.adapters`.
"""

from __future__ import annotations

from loopsheet.codec import decode, decode_hex, scale
from loopsheet.errors import (
    CapabilityError,
    CatalogError,
    DecodeError,
    LayoutUnavailableError,
    LoopsheetError,
)
from loopsheet.models import (
    COMPONENT_ADAPTER,
    PLC,
    SCHEMA_VERSION,
    AnalogSensor,
    Area,
    Bearing,
    ChannelSpec,
    Component,
    DaqDevice,
    DiscreteSensor,
    EdgeDevice,
    Fan,
    Gearbox,
    IOLinkMaster,
    IOLinkSensor,
    Machine,
    MeasurementPoint,
    Motor,
    ProcessDataItem,
    ProcessDataLayout,
    Pump,
    Quality,
    Reading,
    Signal,
    Site,
)

__version__ = "0.1.0a0"

# TODO(loopsheet): `load_machine` arrives with io/loader.py in TODO.md Phase 4;
# `catalog` with the registry in Phase 3. Both belong in this namespace.

__all__ = [
    "COMPONENT_ADAPTER",
    "PLC",
    "SCHEMA_VERSION",
    "AnalogSensor",
    "Area",
    "Bearing",
    "CapabilityError",
    "CatalogError",
    "ChannelSpec",
    "Component",
    "DaqDevice",
    "DecodeError",
    "DiscreteSensor",
    "EdgeDevice",
    "Fan",
    "Gearbox",
    "IOLinkMaster",
    "IOLinkSensor",
    "LayoutUnavailableError",
    "LoopsheetError",
    "Machine",
    "MeasurementPoint",
    "Motor",
    "ProcessDataItem",
    "ProcessDataLayout",
    "Pump",
    "Quality",
    "Reading",
    "Signal",
    "Site",
    "__version__",
    "decode",
    "decode_hex",
    "scale",
]
