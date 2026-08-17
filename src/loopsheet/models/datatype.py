"""IO-Link process-data datatypes.

The enum lives in ``models`` rather than ``codec`` so the dependency direction
stays one-way: ``codec`` imports ``models``, never the reverse. The conversion
functions that turn bits into Python values live in
:mod:`loopsheet.codec.datatypes`, which re-exports this enum for convenience.

Names follow IEC 61131-9 (SDCI) as they appear in an IODD's
``SimpleDatatype``/``DatatypeRef`` elements, so a value copied out of an IODD
lands in a catalog file unchanged.
"""

from __future__ import annotations

from enum import StrEnum


class IOLinkDataType(StrEnum):
    """A datatype an IO-Link process-data item can carry.

    ``BooleanT`` is one bit. ``IntegerT`` and ``UIntegerT`` are variable-width
    (2..64 bits in the spec; any width the IODD declares), which is why bit
    length is a property of the *item*, not of the type. ``Float32T`` is IEEE
    754 single precision and is always 32 bits.

    ``OctetStringT`` and ``StringT`` appear in process data rarely, and only in
    fixed-length form. They are carried so an IODD can round-trip; the decoder
    returns them as ``bytes`` / ``str`` with no scaling.
    """

    BOOLEAN = "BooleanT"
    INTEGER = "IntegerT"
    """Two's-complement signed integer, MSB first."""

    UINTEGER = "UIntegerT"
    """Unsigned integer, MSB first."""

    FLOAT32 = "Float32T"
    """IEEE 754 binary32, big-endian. Always 32 bits."""

    OCTET_STRING = "OctetStringT"
    STRING = "StringT"

    @property
    def is_numeric(self) -> bool:
        """True if a gradient/offset scaling may be applied to this type."""
        return self in {
            IOLinkDataType.INTEGER,
            IOLinkDataType.UINTEGER,
            IOLinkDataType.FLOAT32,
        }

    @property
    def fixed_bit_length(self) -> int | None:
        """The type's mandatory bit length, or ``None`` if it is variable."""
        if self is IOLinkDataType.BOOLEAN:
            return 1
        if self is IOLinkDataType.FLOAT32:
            return 32
        return None
