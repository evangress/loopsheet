"""Pure data models: the machine, what is bolted to it, and what it measures.

**Core purity.** Nothing in this package imports anything but ``pydantic`` and
the stdlib — not ``paho``, not ``asyncua``, not ``httpx``, not even guarded by a
``try``. ``tests/test_core_purity.py`` enforces it. See CLAUDE.md §2.
"""

from __future__ import annotations

from loopsheet.models.asset import (
    Asset,
    AssetBase,
    Axis,
    Bearing,
    Fan,
    Gearbox,
    Location,
    MeasurementPoint,
    Motor,
    Mounting,
    Pump,
)
from loopsheet.models.base import (
    SCHEMA_VERSION,
    Identifier,
    LoopsheetModel,
    PartRef,
    PortNumber,
    SemanticModel,
)
from loopsheet.models.channel import ChannelSpec, FrequencyBand, Signal, ValueRange
from loopsheet.models.component import COMPONENT_ADAPTER, COMPONENT_TYPES, Component
from loopsheet.models.component_base import ComponentBase
from loopsheet.models.controller import (
    PLC,
    Chassis,
    IOChannel,
    IODirection,
    IOModule,
    IOSignal,
    Tag,
)
from loopsheet.models.daq import DaqDevice, EdgeDevice
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.iolink import CycleTime, IOLinkMaster, Port, PortMode, ValidationMode
from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout
from loopsheet.models.reading import Quality, Reading
from loopsheet.models.sensor import (
    AnalogSensor,
    ComMode,
    DiscreteSensor,
    IOLinkSensor,
    SensorBase,
    SignalType,
)
from loopsheet.models.site import Area, Machine, Site
from loopsheet.models.units import KNOWN_UNITS, Unit, normalize_unit

__all__ = [
    "COMPONENT_ADAPTER",
    "COMPONENT_TYPES",
    "KNOWN_UNITS",
    "PLC",
    "SCHEMA_VERSION",
    "AnalogSensor",
    "Area",
    "Asset",
    "AssetBase",
    "Axis",
    "Bearing",
    "ChannelSpec",
    "Chassis",
    "ComMode",
    "Component",
    "ComponentBase",
    "CycleTime",
    "DaqDevice",
    "DiscreteSensor",
    "EdgeDevice",
    "Fan",
    "FrequencyBand",
    "Gearbox",
    "IOChannel",
    "IODirection",
    "IOLinkDataType",
    "IOLinkMaster",
    "IOLinkSensor",
    "IOModule",
    "IOSignal",
    "Identifier",
    "Location",
    "LoopsheetModel",
    "Machine",
    "MeasurementPoint",
    "Motor",
    "Mounting",
    "PartRef",
    "Port",
    "PortMode",
    "PortNumber",
    "ProcessDataItem",
    "ProcessDataLayout",
    "Pump",
    "Quality",
    "Reading",
    "SemanticModel",
    "SensorBase",
    "Signal",
    "SignalType",
    "Site",
    "Tag",
    "Unit",
    "ValidationMode",
    "ValueRange",
    "normalize_unit",
]
