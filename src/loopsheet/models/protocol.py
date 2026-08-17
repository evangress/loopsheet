"""The protocols a device can speak.

Lives in ``models`` because two packages need it and neither should depend on
the other: :mod:`loopsheet.catalog` uses it to declare what a part number
*can* serve, and :mod:`loopsheet.bindings` will use it as the discriminator on
the binding union in TODO.md Phase 5.

These are IT-side protocols — how values leave the machine — not fieldbuses in
general. A part's protocol list is a hardware fact, and it is a narrower one
than most people expect: no single ifm IO-Link master speaks MQTT *and* OPC UA
*and* EtherNet/IP (``docs/research/ifm-masters.md`` §0.3).
"""

from __future__ import annotations

from enum import StrEnum


class BindingProtocol(StrEnum):
    """A protocol a component's values can be published or read over."""

    MQTT = "mqtt"
    """Plain MQTT to a broker. On ifm FW 3.1.x this means *plaintext, no auth*:
    no username, password, client-id, CA certificate, or TLS parameter exists
    anywhere in the profile."""

    OPCUA = "opcua"
    """OPC UA server on the device. Rare on IO-Link masters — on ifm it appears
    only on the AL1590/AL1591 SolutionBlock, and all of its specifics are
    unverified."""

    ETHERNET_IP = "ethernet_ip"
    """EtherNet/IP implicit (cyclic assemblies) plus explicit messaging."""

    MODBUS_TCP = "modbus_tcp"
    """Modbus TCP server."""

    IOTCORE = "iotcore"
    """ifm's IoT Core REST / JSON-RPC API. Vendor-specific rather than a
    standard, but it is a genuine binding: it is the shortest path to real
    process data off an ifm master, and modelling it as "HTTP" would lose the
    ``{code, cid, adr, data, auth}`` envelope that makes it usable."""

    PROFINET = "profinet"
    """PROFINET IO device."""
