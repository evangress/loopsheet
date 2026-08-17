"""Process-data layout — where each value lives inside a cyclic word.

This is *description*, not behaviour: :mod:`loopsheet.codec.decode` reads a
layout and produces :class:`~loopsheet.models.reading.Reading` objects. Keeping
the layout in ``models`` keeps the dependency direction one-way (``codec``
imports ``models``, never the reverse) and lets a catalog entry carry a layout
without pulling in the decoder.

Bit order — read this before touching anything
==============================================

Two different "orders" are in play and conflating them is the classic way to
decode garbage:

**Octet order on the wire is MSB-first (big-endian).** A 32-bit process-data
word arrives as four bytes, most significant first. Assemble it with
``int.from_bytes(raw, "big")``.

**Item offsets are counted from the LSB of the whole word.** This is the IODD
``RecordItem/@bitOffset`` convention: the offset locates an item's *least*
significant bit relative to the least significant bit of the entire process
data. So extraction is::

    value = (word >> bit_offset) & ((1 << bit_length) - 1)

Worked example — a 16-bit word with a 12-bit measurement in the high bits and
a 1-bit alarm flag just below it::

    bit index:  15                    4  3  2  1  0
                [------ measurement ----][ ][ ][ ][alarm]
    measurement: bit_offset=4,  bit_length=12
    alarm:       bit_offset=0,  bit_length=1

An item at ``bit_offset=0`` is therefore at the *end* of the transmitted bytes,
not the beginning. If a decode comes out looking bit-shifted, this is almost
always why.

Scaling
=======

A raw integer becomes an engineering value by ``value = raw * gradient +
offset``, exactly as the IODD states it. Both default to the identity
(``1.0`` / ``0.0``), so a layout with no scaling declared returns raw counts —
which is correct, not a silent guess.
"""

from __future__ import annotations

import builtins
from itertools import pairwise

from pydantic import Field, model_validator

from loopsheet.models.base import Identifier, SemanticModel
from loopsheet.models.channel import ValueRange
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.units import Unit


class ProcessDataItem(SemanticModel):
    """One value inside a process-data word.

    Attributes:
        name: Matches the :class:`~loopsheet.models.channel.ChannelSpec` name on
            the owning component, which is how a decoded value gets its range
            and description back.
        datatype: See :class:`~loopsheet.models.datatype.IOLinkDataType`.
        bit_offset: Offset of this item's LSB from the LSB of the whole word.
        bit_length: Width in bits. Must match the datatype's fixed width where
            it has one (``BooleanT`` is 1, ``Float32T`` is 32).
        gradient: Multiplier applied to the raw integer. IODD calls this
            ``gradient``; a 0.1 gradient turning 394 into 39.4 °C is the usual
            shape.
        offset: Added after the gradient.
        unit: Unit of the *scaled* value.
        range: Valid range of the scaled value, used to flag out-of-range
            decodes as :attr:`~loopsheet.models.reading.Quality.UNCERTAIN`
            rather than to clamp them. loopsheet never edits a measured number.
    """

    name: Identifier
    datatype: IOLinkDataType
    bit_offset: int = Field(ge=0, le=2047)
    bit_length: int = Field(ge=1, le=64)

    gradient: float = Field(default=1.0, description="Scale factor: value = raw*gradient+offset.")
    offset: float = Field(default=0.0)

    unit: Unit | None = None
    range: ValueRange | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _width_matches_datatype(self) -> ProcessDataItem:
        fixed = self.datatype.fixed_bit_length
        if fixed is not None and self.bit_length != fixed:
            raise ValueError(
                f"process-data item {self.name!r}: datatype {self.datatype.value} is "
                f"always {fixed} bits, got bit_length={self.bit_length}"
            )
        if not self.datatype.is_numeric and (self.gradient != 1.0 or self.offset != 0.0):
            raise ValueError(
                f"process-data item {self.name!r}: gradient/offset scaling is meaningless "
                f"for datatype {self.datatype.value}"
            )
        return self

    @property
    def bit_span(self) -> builtins.range:
        """The bit indices this item occupies, LSB-relative.

        Spelled ``builtins.range`` because the ``range`` *field* above shadows
        the builtin inside the class body. The field name is worth keeping —
        ``range: [0, 45]`` is what a catalog author writes — so the annotation
        is what gives way.
        """
        return builtins.range(self.bit_offset, self.bit_offset + self.bit_length)


class ProcessDataLayout(SemanticModel):
    """The full cyclic word for one direction on one device variant.

    Attributes:
        bit_length: Total width of the process data. IO-Link PDIn is at most
            32 bytes (256 bits); PDOut likewise. The value is *not* rounded to
            a byte boundary in the IODD, and loopsheet does not round it
            either — a 12-bit PDIn is legal and occupies two transmitted bytes
            with the top four ignored.
        items: The values inside it. Order is irrelevant; ``bit_offset`` is
            authoritative.
    """

    bit_length: int = Field(ge=1, le=256, description="Total process-data width in bits.")
    items: list[ProcessDataItem] = Field(min_length=1)
    description: str | None = None

    @property
    def byte_length(self) -> int:
        """Transmitted length in bytes, rounding a partial byte up."""
        return (self.bit_length + 7) // 8

    @model_validator(mode="after")
    def _items_are_unique_bounded_and_disjoint(self) -> ProcessDataLayout:
        """Reject duplicate names, out-of-bounds items, and overlapping ranges.

        Overlap is the failure this validator exists for. Two items sharing a
        bit is never a legitimate IODD layout, and the symptom downstream is
        one plausible-looking value and one silently wrong one — which is
        exactly the class of bug this package refuses to ship.
        """
        seen_names: set[str] = set()
        for item in self.items:
            if item.name in seen_names:
                raise ValueError(f"process-data item {item.name!r} declared twice")
            seen_names.add(item.name)

            end = item.bit_offset + item.bit_length
            if end > self.bit_length:
                raise ValueError(
                    f"process-data item {item.name!r} occupies bits "
                    f"{item.bit_offset}..{end - 1}, past the declared "
                    f"{self.bit_length}-bit word"
                )

        # Sort by offset so the overlap check is a linear scan and the error
        # message names the two items in the order a reader will find them.
        ordered = sorted(self.items, key=lambda i: i.bit_offset)
        for earlier, later in pairwise(ordered):
            earlier_end = earlier.bit_offset + earlier.bit_length
            if later.bit_offset < earlier_end:
                raise ValueError(
                    f"process-data items {earlier.name!r} (bits {earlier.bit_offset}.."
                    f"{earlier_end - 1}) and {later.name!r} (bits {later.bit_offset}.."
                    f"{later.bit_offset + later.bit_length - 1}) overlap"
                )
        return self

    def item(self, name: str) -> ProcessDataItem | None:
        """Return the named item, or ``None``."""
        return next((i for i in self.items if i.name == name), None)
