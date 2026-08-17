"""Shared base for everything that hangs off a machine.

Split from :mod:`loopsheet.models.component` purely to break an import cycle:
the subtypes need the base, and the union in ``component.py`` needs the
subtypes. Nothing else lives here.
"""

from __future__ import annotations

from pydantic import Field

from loopsheet.models.base import Identifier, PartRef, SemanticModel
from loopsheet.models.channel import ChannelSpec


class ComponentBase(SemanticModel):
    """Common identity for any device on a machine.

    A component knows what it *is* and where it is mounted. It emphatically
    does not know how its values leave the plant: an ``IOLinkSensor`` has no
    idea that MQTT exists. Protocol configuration is a separate
    :class:`~loopsheet.bindings.base.Binding` union that references components
    by ``tag`` (PLAN.md §3.1). That separation is exactly what lets every
    protocol library stay optional.

    Attributes:
        id: Unique within a machine file. Used by ``master``, ``mounted_at``,
            and binding ``target`` references.
        part: Catalog reference in ``vendor:PART`` form, e.g. ``ifm:VVB020``.
            The loader resolves it and merges catalog-supplied channels,
            electricals, and capabilities onto this component.
        variant: Which catalog variant to pin, e.g. ``status_b``. A part number
            is not one IO-Link identity — the VVB020 ships as device ID 1257
            (status A) and 1369 (status B) with *different process data*.
            Guessing decodes wrong, so an ambiguous part must be pinned
            (PLAN.md §3.8).
        tag: The name that travels downstream into topics, BrowseNames, and PLC
            tags. Defaults to ``id`` when unset.
        channels: What this component measures. Usually populated from the
            catalog; an override here wins, which is how a site-specific
            configuration (a rescaled 4-20 mA loop, a renamed channel) is
            expressed without forking a catalog file.
    """

    id: Identifier
    part: PartRef | None = None
    variant: Identifier | None = None
    tag: Identifier | None = None
    name: str | None = None
    description: str | None = None
    serial_number: str | None = None

    channels: list[ChannelSpec] = Field(default_factory=list)

    @property
    def effective_tag(self) -> str:
        """The name this component is known by downstream."""
        return self.tag or self.id

    @property
    def part_number(self) -> str | None:
        """The bare part number, without the vendor prefix."""
        return self.part.split(":", 1)[1] if self.part else None

    @property
    def vendor(self) -> str | None:
        """The vendor prefix of :attr:`part`."""
        return self.part.split(":", 1)[0] if self.part else None

    def channel(self, name: str) -> ChannelSpec | None:
        """Return the named channel, or ``None``."""
        return next((c for c in self.channels if c.name == name), None)
