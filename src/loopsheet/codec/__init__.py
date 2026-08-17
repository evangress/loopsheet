"""Raw bytes ⇄ engineering values. Pure functions, no I/O.

Two paths in:

* :func:`decode` / :func:`decode_hex` — IO-Link cyclic process data, located by
  a :class:`~loopsheet.models.processdata.ProcessDataLayout`.
* :func:`scale` — analog counts from an input card, mapped through two ranges.

Both return :class:`~loopsheet.models.reading.Reading` objects that carry a
quality flag rather than a corrected value. loopsheet reports what the device
said; it never edits a measurement into looking healthier than it is.
"""

from __future__ import annotations

from loopsheet.codec.datatypes import IOLinkDataType, from_bits, to_signed, to_unsigned
from loopsheet.codec.decode import decode, decode_hex, decode_item
from loopsheet.codec.scaling import (
    counts_to_engineering,
    engineering_to_counts,
    quality_for_current,
    scale,
    signal_span,
)
from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout

__all__ = [
    "IOLinkDataType",
    "ProcessDataItem",
    "ProcessDataLayout",
    "counts_to_engineering",
    "decode",
    "decode_hex",
    "decode_item",
    "engineering_to_counts",
    "from_bits",
    "quality_for_current",
    "scale",
    "signal_span",
    "to_signed",
    "to_unsigned",
]
