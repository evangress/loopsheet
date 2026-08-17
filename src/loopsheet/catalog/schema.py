"""What a catalog file contains.

A catalog entry is everything loopsheet knows about a *part number*, as opposed
to a particular unit bolted to a particular machine. The machine file says
"``ifm:VVB020`` at port 1 of ``master_1``"; the catalog says what a VVB020 is.

Two shapes here are consequences of research rather than of taste, and both are
documented in ``docs/research/``:

**Variants.** A part number is not one IO-Link identity. The ifm VVB020 ships
in two software statuses distinguished at the wire level by device ID — 1257
(status A, COM2, 11.6 ms) and 1369 (status B, COM3, 3.6 ms) — with different
parameter sets, different process data, and PDOut only on status B. An entry
therefore holds a *list* of :class:`DeviceVariant`, and a machine pins one.

**Capabilities.** No single ifm master speaks MQTT and OPC UA and EtherNet/IP.
:attr:`CatalogEntry.supported_bindings` says what a part can actually serve,
and :meth:`CatalogEntry.require_binding` refuses anything else with a message
naming what it *does* support. This is the single most useful thing the package
does for someone specifying hardware.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from loopsheet.errors import CapabilityError, LayoutUnavailableError
from loopsheet.models.base import Identifier, SemanticModel
from loopsheet.models.channel import ChannelSpec, ValueRange
from loopsheet.models.component import COMPONENT_TYPES
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.processdata import ProcessDataLayout
from loopsheet.models.protocol import BindingProtocol
from loopsheet.models.sensor import ComMode
from loopsheet.models.units import Unit

#: Catalog files carry their own contract version, separate from the machine
#: file's ``schema_version``. They are shipped inside the wheel, so the two can
#: drift and a third-party vendor pack pinned to an older catalog schema should
#: still be readable.
CATALOG_SCHEMA_VERSION = 1


class BindingSupport(SemanticModel):
    """One protocol a part can serve, with the caveats that come with it.

    Capability is a function of *(part, firmware)*, not of part alone: MQTT is
    present on ifm AL1320/AL1321 at FW 3.1.x and absent from AL1322/AL1323 at
    FW 2.3.x, for masters in the same EtherNet/IP family. Rather than implement
    version-range arithmetic against vendor strings like ``"3.1.x"`` — which is
    guesswork dressed as logic — an entry declares what its *documented*
    firmware supports and records which firmware that was.

    ``verified`` exists because "the manual has no OPC UA chapter" and "the
    manual says there is no OPC UA" are different strengths of evidence, and
    the catalog should not flatten them.
    """

    protocol: BindingProtocol
    firmware: str | None = Field(
        default=None,
        description="Firmware this capability was documented against, e.g. '3.1.x'.",
    )
    verified: bool = Field(
        default=True,
        description="False when support is inferred rather than documented.",
    )
    notes: str | None = None


class IOLinkIdentity(SemanticModel):
    """The IO-Link facts that are true of the part regardless of variant."""

    vendor_id: int = Field(ge=0, le=65535, description="IO-Link vendor ID. ifm is 310.")
    revision: str | None = Field(default=None, description="IO-Link revision, e.g. '1.1'.")
    sio_supported: bool | None = None
    port_class: str | None = Field(default=None, description="Required master port class, A or B.")
    profiles: list[str] = Field(
        default_factory=list,
        description="Declared IO-Link profiles, e.g. blob, common_id, function_measurement.",
    )


class DeviceVariant(SemanticModel):
    """One wire-level identity of a part number.

    Attributes:
        id: Short name a machine file pins, e.g. ``status_b``.
        device_id: The IO-Link device ID. This is what actually distinguishes
            variants on the wire, and what an adapter reads back from
            ``.../iolinkdevice/deviceid`` to confirm a pin.
        com_mode: Transmission rate, which sets the achievable cycle time.
        min_cycle_time_ms: The device's own floor. A master configured faster
            than this will not achieve it however it is set.
        iodd: IODD reference name, for tracing a layout back to its source.
        has_pdout: Whether the variant has process-data output at all.
        pdin_length_bits: Total PDIn width. ``None`` means unknown — which is
            different from zero.
        process_data: The PDIn layout. **Frequently ``None``**, and that is not
            a modelling failure: the layout comes from the IODD, and an IODD is
            not always obtainable. Decoding against ``None`` raises rather than
            guessing.
    """

    id: Identifier
    device_id: int | None = Field(default=None, ge=0, le=0xFFFFFF)
    com_mode: ComMode | None = None
    min_cycle_time_ms: float | None = Field(default=None, gt=0.0)
    iodd: str | None = None
    has_pdout: bool | None = None

    pdin_length_bits: int | None = Field(default=None, ge=1, le=256)
    pdout_length_bits: int | None = Field(default=None, ge=1, le=256)
    process_data: ProcessDataLayout | None = None
    process_data_out: ProcessDataLayout | None = None

    description: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _declared_lengths_agree_with_layouts(self) -> DeviceVariant:
        """A layout that contradicts the declared PD length is a transcription bug.

        Both come from the same IODD, so disagreement means one of them was
        typed wrong — and either way the decoder would read the wrong number of
        bytes off the wire.
        """
        for label, length, layout in (
            ("pdin", self.pdin_length_bits, self.process_data),
            ("pdout", self.pdout_length_bits, self.process_data_out),
        ):
            if length is not None and layout is not None and layout.bit_length != length:
                raise ValueError(
                    f"variant {self.id!r}: {label}_length_bits is {length} but its "
                    f"layout declares {layout.bit_length} bits"
                )
        if self.has_pdout is False and self.process_data_out is not None:
            raise ValueError(
                f"variant {self.id!r}: has_pdout is false but a PDOut layout is declared"
            )
        return self

    @property
    def layout_known(self) -> bool:
        """True if this variant's PDIn can be decoded."""
        return self.process_data is not None

    def require_process_data(self, part_ref: str | None = None) -> ProcessDataLayout:
        """Return the PDIn layout, or raise a located, actionable error.

        Use this rather than reaching for ``variant.process_data`` directly
        anywhere a decode is about to happen: the raised message names the part
        and variant, which is the difference between "something is None" and
        "go and fetch the VVB020 status-B IODD".
        """
        if self.process_data is None:
            where = f"{part_ref} variant {self.id!r}" if part_ref else f"variant {self.id!r}"
            raise LayoutUnavailableError(
                f"process-data layout unavailable for {where} — the device's IODD "
                f"({self.iodd or 'reference unknown'}) is required to know where each "
                "value sits in the word. Refusing to guess: a wrong bit offset decodes "
                "silently plausible garbage"
            )
        return self.process_data


class IsduParameter(SemanticModel):
    """An acyclic parameter, addressed by ISDU index and subindex.

    Subindex 0 addresses a whole record; 1..n address items within it. That
    convention is IO-Link's, not ours, which is why the default is 0 rather
    than ``None``.
    """

    index: int = Field(ge=0, le=65535)
    subindex: int = Field(default=0, ge=0, le=255)
    name: str
    datatype: IOLinkDataType | None = None
    access: str | None = Field(default=None, description="ro, rw, or wo.")
    unit: Unit | None = None
    range: ValueRange | None = None
    default: str | None = Field(default=None, description="Factory default, verbatim.")
    description: str | None = None


class Connector(SemanticModel):
    """The physical connector on the device."""

    type: str = Field(description="e.g. 'M12'.")
    coding: str | None = Field(default=None, description="e.g. 'A'.")
    pins: int | None = Field(default=None, ge=2)


class Pin(SemanticModel):
    """One pin of the connector."""

    function: str = Field(description="e.g. 'L+', 'OUT2', 'OUT1_OR_IOLINK'.")
    colour: str | None = Field(default=None, description="Standard wire colour code, e.g. 'BN'.")


class Electrical(SemanticModel):
    """Supply, outputs, and wiring.

    ``analog_output`` is explicitly nullable and worth setting to ``null`` on
    purpose: the VVB020 has *no* 4-20 mA output, and an entry that simply
    omitted the field would read as "unknown" rather than "confirmed absent".
    """

    supply_voltage_v: ValueRange | None = None
    current_consumption_ma_max: float | None = Field(default=None, gt=0.0)
    digital_outputs: int | None = Field(default=None, ge=0)
    analog_output: str | None = None
    protection_class: str | None = None
    connector: Connector | None = None
    pinout: dict[int, Pin] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _pinout_matches_connector(self) -> Electrical:
        if self.connector is not None and self.connector.pins is not None and self.pinout:
            stray = [p for p in self.pinout if p < 1 or p > self.connector.pins]
            if stray:
                raise ValueError(
                    f"pinout declares pin(s) {stray} but the connector has "
                    f"{self.connector.pins} pins"
                )
        return self


class Mechanical(SemanticModel):
    """Size, material, and how it mounts."""

    weight_g: float | None = Field(default=None, gt=0.0)
    material: str | None = None
    diameter_mm: float | None = Field(default=None, gt=0.0)
    length_mm: float | None = Field(default=None, gt=0.0)
    width_mm: float | None = Field(default=None, gt=0.0)
    height_mm: float | None = Field(default=None, gt=0.0)
    mounting: str | None = None
    tightening_torque_nm: float | None = Field(default=None, gt=0.0)


class Environment(SemanticModel):
    """Where the part is rated to live."""

    ambient_temperature_c: ValueRange | None = None
    storage_temperature_c: ValueRange | None = None
    ip_ratings: list[str] = Field(default_factory=list)
    shock: str | None = None
    vibration: str | None = None
    mtbf_years: float | None = Field(default=None, gt=0.0)


class CatalogEntry(SemanticModel):
    """Everything loopsheet knows about one part number.

    ``sources`` is not decoration. Every numeric value in a catalog file has to
    be traceable to a datasheet, manual, or IODD, and this is where the trail
    starts. An entry with populated values and no sources should not pass
    review.
    """

    schema_version: int = Field(default=CATALOG_SCHEMA_VERSION, ge=1)

    part_number: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.\-]+$")
    vendor: str = Field(min_length=1, pattern=r"^[a-z0-9_\-]+$")
    component_type: str
    product_name: str | None = None
    family: str | None = None
    description: str | None = None

    sources: list[str] = Field(
        default_factory=list,
        description="Where the values came from — document numbers, URLs, IODD names.",
    )
    firmware: str | None = Field(
        default=None, description="Firmware the entry was transcribed against."
    )

    iolink: IOLinkIdentity | None = None
    variants: list[DeviceVariant] = Field(default_factory=list)
    channels: list[ChannelSpec] = Field(default_factory=list)
    parameters: list[IsduParameter] = Field(default_factory=list)

    supported_bindings: list[BindingSupport] = Field(default_factory=list)
    port_count: int | None = Field(default=None, ge=1, le=32)
    default_ip: str | None = None

    electrical: Electrical | None = None
    mechanical: Mechanical | None = None
    environment: Environment | None = None

    notes: str | None = None

    # ----------------------------------------------------------------- #
    # Identity                                                          #
    # ----------------------------------------------------------------- #

    @property
    def ref(self) -> str:
        """The catalog reference a machine file writes, e.g. ``ifm:VVB020``."""
        return f"{self.vendor}:{self.part_number}"

    def variant(self, variant_id: str) -> DeviceVariant | None:
        """Return the named variant, or ``None``."""
        return next((v for v in self.variants if v.id == variant_id), None)

    def channel(self, name: str) -> ChannelSpec | None:
        """Return the named channel, or ``None``."""
        return next((c for c in self.channels if c.name == name), None)

    def parameter(self, index: int, subindex: int = 0) -> IsduParameter | None:
        """Return the ISDU parameter at this address, or ``None``."""
        return next(
            (p for p in self.parameters if p.index == index and p.subindex == subindex),
            None,
        )

    def require_variant(self, variant_id: str | None) -> DeviceVariant:
        """Resolve a pinned variant, refusing to pick one on the caller's behalf.

        A part with exactly one variant needs no pin. A part with several does:
        silently taking the first would decode a status-A VVB020 against a
        status-B layout, and the numbers would look entirely reasonable.
        """
        if variant_id is not None:
            found = self.variant(variant_id)
            if found is None:
                known = ", ".join(v.id for v in self.variants) or "none declared"
                raise CapabilityError(
                    f"{self.ref} has no variant {variant_id!r}. Known variants: {known}"
                )
            return found

        if len(self.variants) == 1:
            return self.variants[0]
        if not self.variants:
            raise CapabilityError(f"{self.ref} declares no variants")
        known = ", ".join(v.id for v in self.variants)
        raise CapabilityError(
            f"{self.ref} has {len(self.variants)} variants ({known}) and none is pinned. "
            "Set `variant:` on the component — these differ at the wire level and "
            "guessing one decodes the wrong values"
        )

    # ----------------------------------------------------------------- #
    # Capability                                                        #
    # ----------------------------------------------------------------- #

    @property
    def protocols(self) -> list[BindingProtocol]:
        """The protocols this part can serve."""
        return [b.protocol for b in self.supported_bindings]

    def supports(self, protocol: BindingProtocol) -> bool:
        """True if this part can serve ``protocol``."""
        return protocol in self.protocols

    def require_binding(self, protocol: BindingProtocol) -> BindingSupport:
        """Return the support record for ``protocol``, or raise naming the alternatives.

        The message always lists what the part *does* support. Telling someone
        only that their configuration is wrong throws away the more useful half
        of the answer, and this is the exact case people hit: an AL1350 is an
        ifm IO-Link master with an Ethernet port, so OPC UA looks like a
        reasonable assumption right up until it silently never connects.
        """
        for support in self.supported_bindings:
            if support.protocol is protocol:
                return support
        supported = ", ".join(sorted(p.value for p in self.protocols)) or "no bindings at all"
        raise CapabilityError(
            f"{self.ref} does not support {protocol.value}. It supports: {supported}"
        )

    # ----------------------------------------------------------------- #
    # Integrity                                                         #
    # ----------------------------------------------------------------- #

    @model_validator(mode="after")
    def _component_type_is_known(self) -> CatalogEntry:
        if self.component_type not in COMPONENT_TYPES:
            known = ", ".join(sorted(COMPONENT_TYPES))
            raise ValueError(
                f"{self.ref}: unknown component_type {self.component_type!r}. Known types: {known}"
            )
        return self

    @model_validator(mode="after")
    def _variants_are_distinguishable(self) -> CatalogEntry:
        """Variants must differ by id *and* by device ID.

        Two variants sharing a device ID cannot be told apart on the wire, so
        an adapter could never confirm which one is plugged in — which defeats
        the entire reason variants exist.
        """
        seen_ids: set[str] = set()
        seen_device_ids: dict[int, str] = {}
        for variant in self.variants:
            if variant.id in seen_ids:
                raise ValueError(f"{self.ref}: duplicate variant id {variant.id!r}")
            seen_ids.add(variant.id)

            if variant.device_id is None:
                continue
            if variant.device_id in seen_device_ids:
                raise ValueError(
                    f"{self.ref}: variants {seen_device_ids[variant.device_id]!r} and "
                    f"{variant.id!r} share device ID {variant.device_id}, so they cannot "
                    "be told apart on the wire"
                )
            seen_device_ids[variant.device_id] = variant.id
        return self

    @model_validator(mode="after")
    def _channels_are_unique(self) -> CatalogEntry:
        seen: set[str] = set()
        for channel in self.channels:
            if channel.name in seen:
                raise ValueError(f"{self.ref}: duplicate channel {channel.name!r}")
            seen.add(channel.name)
        return self

    @model_validator(mode="after")
    def _bindings_are_unique(self) -> CatalogEntry:
        seen: set[BindingProtocol] = set()
        for support in self.supported_bindings:
            if support.protocol in seen:
                raise ValueError(f"{self.ref}: protocol {support.protocol.value!r} declared twice")
            seen.add(support.protocol)
        return self

    @model_validator(mode="after")
    def _masters_declare_their_capabilities(self) -> CatalogEntry:
        """A master with no declared bindings cannot guard anything.

        The capability check is the point of cataloguing a master at all. An
        entry that omits ``supported_bindings`` would silently accept every
        protocol, which is worse than not shipping the entry.
        """
        if self.component_type == "iolink_master" and not self.supported_bindings:
            raise ValueError(
                f"{self.ref}: an IO-Link master entry must declare supported_bindings. "
                "Without it, every binding validates and the guard rail does nothing"
            )
        return self
