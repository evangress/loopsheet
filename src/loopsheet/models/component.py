"""The component union.

Every device on a machine is one of these, discriminated on ``component_type``.

A discriminated union rather than a base-class-and-``isinstance`` hierarchy
buys three concrete things (PLAN.md §3.2):

* **O(1) validation dispatch** — pydantic reads ``component_type`` and goes
  straight to the right model instead of trying each in turn.
* **Readable errors** — a bad field on a sensor reports as a sensor error, not
  as five parallel "did not match" reports.
* **Clean JSON Schema** — ``oneOf`` plus a ``discriminator``, which is what
  editors need to offer completion on a machine YAML file.

:data:`COMPONENT_ADAPTER` is public so callers can validate raw dicts and
generate schema without importing every subtype.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field, TypeAdapter

from loopsheet.models.controller import PLC
from loopsheet.models.daq import DaqDevice, EdgeDevice
from loopsheet.models.iolink import IOLinkMaster, Port
from loopsheet.models.sensor import AnalogSensor, DiscreteSensor, IOLinkSensor

#: Any device that can appear in a machine's ``components`` list.
Component = Annotated[
    IOLinkSensor
    | AnalogSensor
    | DiscreteSensor
    | IOLinkMaster
    | Port
    | PLC
    | DaqDevice
    | EdgeDevice,
    Field(discriminator="component_type"),
]

#: Validate a raw dict into the right component subtype, or generate the
#: union's JSON Schema::
#:
#:     COMPONENT_ADAPTER.validate_python({"component_type": "plc", "id": "plc1"})
#:     COMPONENT_ADAPTER.json_schema()
COMPONENT_ADAPTER: TypeAdapter[Component] = TypeAdapter(Component)

#: ``component_type`` discriminator value → model class. Useful for tooling
#: that needs to enumerate the union without re-deriving it from the annotation.
COMPONENT_TYPES: dict[str, type] = {
    "iolink_sensor": IOLinkSensor,
    "analog_sensor": AnalogSensor,
    "discrete_sensor": DiscreteSensor,
    "iolink_master": IOLinkMaster,
    "iolink_port": Port,
    "plc": PLC,
    "daq_device": DaqDevice,
    "edge_device": EdgeDevice,
}


def dump_component(component: Component, *, exclude_defaults: bool = True) -> dict[str, Any]:
    """Serialize a component to a plain dict that can be validated straight back.

    Use this rather than :meth:`~pydantic.BaseModel.model_dump` anywhere the
    result will be re-read. ``component_type`` carries a per-subtype default, so
    a bare ``model_dump(exclude_defaults=True)`` **drops the discriminator** and
    produces a dict the union can no longer resolve. That is a quiet way to
    write an unloadable machine file, and the fix belongs here rather than in
    every caller.

    ``exclude_defaults`` is on by default because a machine file should read
    like what its author wrote, not like a dump of every field in the model.
    """
    data: dict[str, Any] = component.model_dump(
        mode="json", exclude_defaults=exclude_defaults, exclude_none=True
    )
    data["component_type"] = component.component_type
    return data


__all__ = [
    "COMPONENT_ADAPTER",
    "COMPONENT_TYPES",
    "PLC",
    "AnalogSensor",
    "Component",
    "DaqDevice",
    "DiscreteSensor",
    "EdgeDevice",
    "IOLinkMaster",
    "IOLinkSensor",
    "Port",
    "dump_component",
]
