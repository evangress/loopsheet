"""The part-number catalog.

Data-driven: devices are YAML files plus generic models, not a class per part
number. Adding a sensor is adding a file, and a third party can ship a whole
vendor pack without touching this package.

    >>> from loopsheet import catalog
    >>> catalog.get("ifm:VVB020").ref
    'ifm:VVB020'

Two rules govern what goes in a catalog file:

**Never fabricate precision.** Every numeric value must trace to a datasheet,
manual, or IODD, with the trail recorded in ``sources`` and the reasoning in
``docs/research/``. Anything unconfirmed ships as ``null`` with an
``# UNVERIFIED`` comment. A wrong bit offset silently decodes garbage; a
missing one refuses.

**Capability, not assumption.** Masters declare ``supported_bindings``, and
:meth:`~loopsheet.catalog.schema.CatalogEntry.require_binding` refuses anything
else while naming what the part *does* support.
"""

from __future__ import annotations

from loopsheet.catalog.registry import clear_cache, get, list_parts, vendors
from loopsheet.catalog.schema import (
    CATALOG_SCHEMA_VERSION,
    BindingSupport,
    CatalogEntry,
    Connector,
    DeviceVariant,
    Electrical,
    Environment,
    IOLinkIdentity,
    IsduParameter,
    Mechanical,
    Pin,
)

__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "BindingSupport",
    "CatalogEntry",
    "Connector",
    "DeviceVariant",
    "Electrical",
    "Environment",
    "IOLinkIdentity",
    "IsduParameter",
    "Mechanical",
    "Pin",
    "clear_cache",
    "get",
    "list_parts",
    "vendors",
]
