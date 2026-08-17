"""The containment tree: Site → Area → Machine.

A :class:`Machine` is the unit that gets authored, validated, and shipped as
one YAML file. :class:`Area` and :class:`Site` exist above it to give a machine
a place in the plant — which is what an MQTT topic prefix, an OPC UA namespace,
and an ISA-95 equipment hierarchy are all built from.

Cross-reference integrity is enforced here rather than in the loader, so that a
`Machine` assembled in Python is held to the same standard as one parsed from a
file. A dangling ``mounted_at`` is a broken loop sheet whichever way it was
built.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from loopsheet.models.asset import Asset, MeasurementPoint
from loopsheet.models.base import SCHEMA_VERSION, Identifier, SemanticModel
from loopsheet.models.channel import Signal
from loopsheet.models.component import Component
from loopsheet.models.component_base import ComponentBase
from loopsheet.models.iolink import IOLinkMaster
from loopsheet.models.sensor import IOLinkSensor


class Machine(SemanticModel):
    """One machine and everything bolted to it.

    Attributes:
        schema_version: Version of the serialized contract this file was
            written against. Carried on the machine, not just the file, so a
            `Machine` that has been passed around in memory still knows.
        assets: The mechanical world — motors, pumps, bearings.
        measurement_points: Where sensors mount on those assets.
        components: The electrical world — sensors, masters, controllers.
        signals: Explicit loop-sheet rows. Optional: most signals are implied
            by a component's channels, and ``signals`` is for the ones that
            need naming or re-tagging by hand.

    Protocol bindings are deliberately absent: they are their own discriminated
    union that references components by tag, and they arrive in TODO.md Phase 5.
    Adding the field then is an additive schema change.
    """

    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    name: Identifier
    description: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None

    assets: list[Asset] = Field(default_factory=list)
    measurement_points: list[MeasurementPoint] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)

    # ----------------------------------------------------------------- #
    # Lookup                                                            #
    # ----------------------------------------------------------------- #

    def find(self, tag_or_id: str) -> ComponentBase | None:
        """Return the component with this tag, falling back to its id.

        Tag first, because the tag is the name the rest of the plant uses; a
        component with no explicit tag answers to its id, which
        :attr:`~loopsheet.models.component_base.ComponentBase.effective_tag`
        already handles.
        """
        for component in self.components:
            if component.effective_tag == tag_or_id:
                return component
        return next((c for c in self.components if c.id == tag_or_id), None)

    def asset(self, asset_id: str) -> Asset | None:
        """Return the mechanical asset with this id, or ``None``."""
        return next((a for a in self.assets if a.id == asset_id), None)

    def measurement_point(self, point_id: str) -> MeasurementPoint | None:
        """Return the measurement point with this id, or ``None``."""
        return next((p for p in self.measurement_points if p.id == point_id), None)

    def sensors(self) -> list[IOLinkSensor]:
        """Every IO-Link sensor on this machine."""
        return [c for c in self.components if isinstance(c, IOLinkSensor)]

    def masters(self) -> list[IOLinkMaster]:
        """Every IO-Link master on this machine."""
        return [c for c in self.components if isinstance(c, IOLinkMaster)]

    # ----------------------------------------------------------------- #
    # Integrity                                                         #
    # ----------------------------------------------------------------- #

    @model_validator(mode="after")
    def _ids_are_unique(self) -> Machine:
        for label, ids in (
            ("asset", [a.id for a in self.assets]),
            ("measurement point", [p.id for p in self.measurement_points]),
            ("component", [c.id for c in self.components]),
        ):
            seen: set[str] = set()
            for value in ids:
                if value in seen:
                    raise ValueError(f"machine {self.name!r}: duplicate {label} id {value!r}")
                seen.add(value)

        tags = [c.effective_tag for c in self.components]
        seen_tags: set[str] = set()
        for tag in tags:
            if tag in seen_tags:
                raise ValueError(
                    f"machine {self.name!r}: duplicate component tag {tag!r}. Tags become "
                    "topic segments and PLC tag names, so they must be unique"
                )
            seen_tags.add(tag)
        return self

    @model_validator(mode="after")
    def _references_resolve(self) -> Machine:
        """Every id referenced somewhere must exist somewhere.

        The error names the referring object, the field, and the missing id —
        a machine file has hundreds of ids and "KeyError: 'P101'" would cost
        the author ten minutes each time.
        """
        asset_ids = {a.id for a in self.assets}
        point_ids = {p.id for p in self.measurement_points}
        component_ids = {c.id for c in self.components}
        master_ids = {m.id for m in self.masters()}

        def require(value: str | None, valid: set[str], what: str, where: str) -> None:
            if value is not None and value not in valid:
                known = ", ".join(sorted(valid)) or "none declared"
                raise ValueError(
                    f"machine {self.name!r}: {where} references unknown {what} "
                    f"{value!r}. Known {what}s: {known}"
                )

        for point in self.measurement_points:
            require(point.asset, asset_ids, "asset", f"measurement point {point.id!r}")

        for component in self.components:
            where = f"component {component.id!r}"
            mounted_at = getattr(component, "mounted_at", None)
            require(mounted_at, point_ids, "measurement point", where)
            if isinstance(component, IOLinkSensor):
                require(component.master, master_ids, "IO-Link master", where)

        for master in self.masters():
            for port in master.ports:
                require(
                    port.device,
                    component_ids,
                    "component",
                    f"master {master.id!r} port {port.number}",
                )

        for signal in self.signals:
            require(signal.component, component_ids, "component", f"signal {signal.tag!r}")
            require(
                signal.measurement_point,
                point_ids,
                "measurement point",
                f"signal {signal.tag!r}",
            )

        return self

    @model_validator(mode="after")
    def _iolink_wiring_is_consistent(self) -> Machine:
        """A sensor's ``port`` must exist on its master and not be double-booked.

        Two sensors claiming port 1 of the same master is a wiring error that
        no amount of downstream cleverness can recover from, and it is trivially
        detectable here.
        """
        occupied: dict[tuple[str, int], str] = {}
        by_id = {m.id: m for m in self.masters()}

        for sensor in self.sensors():
            if sensor.master is None or sensor.port is None:
                continue
            master = by_id.get(sensor.master)
            if master is None:  # already reported by _references_resolve
                continue
            if master.port_count is not None and sensor.port > master.port_count:
                raise ValueError(
                    f"sensor {sensor.id!r} is wired to port {sensor.port} of master "
                    f"{master.id!r}, which has only {master.port_count} ports"
                )
            key = (master.id, sensor.port)
            if key in occupied:
                raise ValueError(
                    f"sensors {occupied[key]!r} and {sensor.id!r} are both wired to "
                    f"port {sensor.port} of master {master.id!r}"
                )
            occupied[key] = sensor.id
        return self


class Area(SemanticModel):
    """A production area within a site — a line, a cell, a department."""

    name: Identifier
    description: str | None = None
    machines: list[Machine] = Field(default_factory=list)

    def machine(self, name: str) -> Machine | None:
        """Return the machine with this name, or ``None``."""
        return next((m for m in self.machines if m.name == name), None)


class Site(SemanticModel):
    """A plant. The root of the containment tree.

    ``path`` segments from here down are what topic prefixes and namespace
    URIs get built from, which is why every level's ``name`` is a constrained
    :data:`~loopsheet.models.base.Identifier` rather than free text.
    """

    name: Identifier
    description: str | None = None
    location: str | None = None
    areas: list[Area] = Field(default_factory=list)

    def area(self, name: str) -> Area | None:
        """Return the area with this name, or ``None``."""
        return next((a for a in self.areas if a.name == name), None)

    def machines(self) -> list[Machine]:
        """Every machine in the site, flattened."""
        return [m for a in self.areas for m in a.machines]
