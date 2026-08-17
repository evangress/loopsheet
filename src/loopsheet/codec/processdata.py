"""Process-data layout — re-exported from :mod:`loopsheet.models.processdata`.

The layout models are *description*, so they live in ``models`` and the
dependency direction stays one-way. They are re-exported here because
"process data" is a codec concept to anyone reading the package from the
outside, and ``from loopsheet.codec.processdata import ProcessDataLayout``
should not be a dead end.

Read the module docstring of :mod:`loopsheet.models.processdata` before writing
any layout: it is where the bit-order convention is spelled out.
"""

from __future__ import annotations

from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout

__all__ = ["ProcessDataItem", "ProcessDataLayout"]
