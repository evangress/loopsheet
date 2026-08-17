"""Exception types.

One shallow hierarchy under :class:`LoopsheetError`, so a caller can catch
everything this package raises with one clause while still being able to tell
"the file is wrong" from "the device data is wrong".

Pydantic's own ``ValidationError`` is deliberately *not* wrapped. Its error
list is far more useful than anything a re-raise would produce, and hiding it
behind a generic message would be a downgrade.
"""

from __future__ import annotations


class LoopsheetError(Exception):
    """Base for every error raised by loopsheet."""


class DecodeError(LoopsheetError):
    """Raw process data could not be decoded against a layout."""


class LayoutUnavailableError(DecodeError):
    """The device's process-data layout is not known.

    Raised instead of returning a plausible-looking wrong answer. The usual
    cause is a catalog entry whose ``process_data`` is ``null`` because the
    vendor's IODD could not be obtained — see ``docs/research/`` for which
    devices are in that state and why.
    """


class CatalogError(LoopsheetError):
    """A part number could not be resolved, or a catalog file is malformed."""


class ReferenceError_(LoopsheetError):
    """A machine file references an id that does not exist.

    Named with a trailing underscore to avoid shadowing the builtin
    ``ReferenceError``, which means something entirely different.
    """


class CapabilityError(LoopsheetError):
    """A binding was attached to hardware that cannot serve it.

    The message always names the part *and* what it does support: no single
    ifm master speaks MQTT and OPC UA and EtherNet/IP, and telling someone
    only that their config is wrong wastes the most useful half of the answer.
    """
