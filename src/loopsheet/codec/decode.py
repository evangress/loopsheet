"""Raw process data → :class:`~loopsheet.models.reading.Reading` objects.

Pure. No I/O, no clock reads unless a timestamp is handed in, no network. Given
the same bytes and the same layout this returns the same values forever, which
is what makes a golden-decode test meaningful.

The bit-order contract is documented in :mod:`loopsheet.models.processdata`,
and the short version is: assemble the octets big-endian, then locate each item
by shifting right by its ``bit_offset``.
"""

from __future__ import annotations

from datetime import datetime

from loopsheet.codec.datatypes import from_bits
from loopsheet.errors import DecodeError, LayoutUnavailableError
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout
from loopsheet.models.reading import Quality, Reading

__all__ = ["decode", "decode_hex", "decode_item"]


def decode(
    raw: bytes,
    layout: ProcessDataLayout | None,
    *,
    source: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Reading]:
    """Decode a process-data word into readings, keyed by channel name.

    Args:
        raw: The cyclic process data exactly as it came off the wire, most
            significant octet first.
        layout: What the IODD says is inside it. ``None`` is not an error in
            the model — plenty of real devices have no obtainable IODD — but it
            *is* an error to try to decode against it.
        source: Free-form provenance stamped onto every reading: a component
            tag, a topic, a NodeId. It is what makes a log line answerable.
        timestamp: When the data was observed. Passed in rather than read from
            the clock so the function stays pure and the caller keeps control
            of what "now" means.

    Returns:
        One :class:`~loopsheet.models.reading.Reading` per layout item.

    Raises:
        LayoutUnavailableError: If ``layout`` is ``None``.
        DecodeError: If ``raw`` is the wrong length for the layout.
    """
    if layout is None:
        raise LayoutUnavailableError(
            "process-data layout unavailable — the device's IODD is required to "
            "know where each value sits in the word. Refusing to guess: a wrong "
            "bit offset decodes silently plausible garbage"
        )

    expected = layout.byte_length
    if len(raw) != expected:
        raise DecodeError(
            f"process data is {len(raw)} bytes, layout declares {layout.bit_length} bits "
            f"({expected} bytes). "
            + (
                "Truncated data usually means the read was cut short."
                if len(raw) < expected
                else "Extra bytes usually mean the wrong port or the wrong variant."
            )
        )

    word = int.from_bytes(raw, "big")
    return {
        item.name: decode_item(word, item, source=source, timestamp=timestamp)
        for item in layout.items
    }


def decode_hex(
    raw_hex: str,
    layout: ProcessDataLayout | None,
    *,
    source: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Reading]:
    """Decode process data delivered as a hex string.

    ifm's IoT Core returns PDIn as an **uppercase hex string** rather than
    binary, and it is the shortest path to real bytes off a real sensor, so
    parsing it belongs in core rather than in the adapter. Case and surrounding
    whitespace are accepted; anything else is an error.
    """
    cleaned = raw_hex.strip()
    if len(cleaned) % 2:
        raise DecodeError(
            f"hex process data has an odd number of digits ({len(cleaned)}); "
            "a partial octet cannot be placed in the word"
        )
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise DecodeError(f"process data {raw_hex!r} is not valid hex: {exc}") from exc
    return decode(raw, layout, source=source, timestamp=timestamp)


def decode_item(
    word: int,
    item: ProcessDataItem,
    *,
    source: str | None = None,
    timestamp: datetime | None = None,
) -> Reading:
    """Extract and scale one item out of an assembled process-data word.

    Exposed separately because it is the piece worth testing exhaustively:
    byte-boundary spanning, sign extension, and gradient arithmetic all live
    here, and each is a way to be confidently wrong.
    """
    field = (word >> item.bit_offset) & ((1 << item.bit_length) - 1)
    interpreted = from_bits(field, item.datatype, item.bit_length)

    value: bool | int | float | str | None
    if isinstance(interpreted, bytes):
        # StringT carries text. OctetStringT is opaque binary with no sensible
        # Reading representation, so the value is None and `raw` keeps the bits.
        value = None if item.datatype is IOLinkDataType.OCTET_STRING else _as_text(interpreted)
    elif item.datatype.is_numeric and (item.gradient != 1.0 or item.offset != 0.0):
        # Only build a float when scaling actually does something. A counter
        # decoded as 42 should stay 42, not become 42.0.
        value = interpreted * item.gradient + item.offset
    else:
        value = interpreted

    quality = Quality.GOOD
    if (
        item.range is not None
        and isinstance(value, int | float)
        and not isinstance(value, bool)
        # Out of range is reported, never corrected. Clamping a measurement is
        # how a genuine fault becomes an invisible one.
        and not item.range.contains(float(value))
    ):
        quality = Quality.UNCERTAIN

    return Reading(
        name=item.name,
        value=value,
        unit=item.unit,
        timestamp=timestamp,
        quality=quality,
        source=source,
        raw=field,
    )


def _as_text(data: bytes) -> str:
    """Decode a StringT payload, trimming the NUL padding IO-Link pads with."""
    return data.rstrip(b"\x00").decode("ascii", errors="replace")
