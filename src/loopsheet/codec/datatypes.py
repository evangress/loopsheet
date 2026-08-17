"""Turning bit fields into Python values.

The enum itself lives in :mod:`loopsheet.models.datatype` so that the
dependency direction stays one-way; this module owns the *conversions* and
re-exports the enum for convenience.

Everything here operates on an integer that has already been shifted and masked
out of the process-data word — see :mod:`loopsheet.models.processdata` for the
bit-order rules. Keeping extraction and interpretation separate is what makes
sign extension testable in isolation, and sign extension is the single most
common way a hand-rolled IO-Link decoder goes wrong.
"""

from __future__ import annotations

import struct

from loopsheet.models.datatype import IOLinkDataType

__all__ = ["IOLinkDataType", "from_bits", "to_signed", "to_unsigned"]


def to_signed(raw: int, bit_length: int) -> int:
    """Interpret ``raw`` as a two's-complement signed integer of ``bit_length``.

    ``raw`` must already be masked to ``bit_length`` bits.

    The IO-Link temperature case makes the stakes concrete: -30.0 °C at a 0.1
    gradient is raw ``0xFED4`` in 16 bits. Read unsigned, that is 65236, which
    scales to 6523.6 °C — a number no reviewer would miss. Read as a 12-bit
    field by mistake, it becomes 3796 → 379.6 °C, which looks like a plausible
    process temperature. That is why width is explicit everywhere.
    """
    if bit_length < 1 or bit_length > 64:
        raise ValueError(f"bit_length must be 1..64, got {bit_length}")
    limit = 1 << bit_length
    if not 0 <= raw < limit:
        raise ValueError(f"raw value {raw} does not fit in {bit_length} bits")
    sign_bit = 1 << (bit_length - 1)
    return raw - limit if raw & sign_bit else raw


def to_unsigned(raw: int, bit_length: int) -> int:
    """Validate ``raw`` as an unsigned integer of ``bit_length`` bits."""
    if bit_length < 1 or bit_length > 64:
        raise ValueError(f"bit_length must be 1..64, got {bit_length}")
    if not 0 <= raw < (1 << bit_length):
        raise ValueError(f"raw value {raw} does not fit in {bit_length} bits")
    return raw


def _to_float32(raw: int) -> float:
    """Reinterpret a 32-bit pattern as IEEE 754 binary32.

    ``struct`` is used rather than hand-rolled exponent arithmetic because it
    gets subnormals, infinities, and NaN right, and a decoder that silently
    mangles a NaN is a decoder that hides a device fault.
    """
    if not 0 <= raw < (1 << 32):
        raise ValueError(f"raw value {raw} does not fit in 32 bits")
    return float(struct.unpack(">f", struct.pack(">I", raw))[0])


def from_bits(raw: int, datatype: IOLinkDataType, bit_length: int) -> float | int | bool | bytes:
    """Interpret an already-extracted bit field as its declared datatype.

    Args:
        raw: The masked bit field, as an unsigned integer.
        datatype: What the IODD says it is.
        bit_length: Width of the field in bits.

    Returns:
        ``bool`` for ``BooleanT``, ``int`` for the integer types, ``float`` for
        ``Float32T``, ``bytes`` for ``OctetStringT`` and ``StringT``.

    Raises:
        ValueError: If ``raw`` does not fit in ``bit_length``, or the width
            contradicts a fixed-width datatype.
    """
    fixed = datatype.fixed_bit_length
    if fixed is not None and bit_length != fixed:
        raise ValueError(
            f"datatype {datatype.value} is always {fixed} bits, got bit_length={bit_length}"
        )

    match datatype:
        case IOLinkDataType.BOOLEAN:
            return bool(to_unsigned(raw, bit_length))
        case IOLinkDataType.UINTEGER:
            return to_unsigned(raw, bit_length)
        case IOLinkDataType.INTEGER:
            return to_signed(raw, bit_length)
        case IOLinkDataType.FLOAT32:
            return _to_float32(raw)
        case IOLinkDataType.OCTET_STRING | IOLinkDataType.STRING:
            if bit_length % 8:
                raise ValueError(
                    f"datatype {datatype.value} must be a whole number of bytes, "
                    f"got bit_length={bit_length}"
                )
            return to_unsigned(raw, bit_length).to_bytes(bit_length // 8, "big")

    raise AssertionError(f"unhandled datatype {datatype!r}")  # pragma: no cover
