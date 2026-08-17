"""Analog raw counts ⇄ engineering units.

The other half of the decoder. IO-Link devices hand over a scaled integer;
4-20 mA transmitters hand over a count from an analog input card, and turning
that into pressure or flow needs two ranges and a decision about what to do at
the edges.

Under- and over-range handling is the part that matters. A live-zero signal
(4-20 mA, 2-10 V) can distinguish "the process is at zero" from "the wire is
cut", and throwing that distinction away by clamping is how a broken
transmitter reads as a healthy minimum for six months.

NAMUR NE 43 sets the conventional bands for 4-20 mA:

===============  ===================  =========================
Current          Band                 Quality
===============  ===================  =========================
< 3.6 mA         fault / broken wire  :attr:`Quality.BAD`
3.6 to 3.8 mA    under-range          :attr:`Quality.UNCERTAIN`
3.8 to 20.5 mA   measuring range      :attr:`Quality.GOOD`
20.5 to 21.0 mA  over-range           :attr:`Quality.UNCERTAIN`
> 21.0 mA        fault                :attr:`Quality.BAD`
===============  ===================  =========================

loopsheet reports these bands. It never clamps, never substitutes a value, and
never silently returns the range limit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from loopsheet.errors import DecodeError
from loopsheet.models.channel import ValueRange
from loopsheet.models.reading import Quality, Reading
from loopsheet.models.sensor import SignalType

__all__ = [
    "NAMUR_FAULT_HIGH_MA",
    "NAMUR_FAULT_LOW_MA",
    "NAMUR_OVER_RANGE_MA",
    "NAMUR_UNDER_RANGE_MA",
    "counts_to_engineering",
    "engineering_to_counts",
    "quality_for_current",
    "scale",
    "signal_span",
]

# NAMUR NE 43 band edges, in milliamps.
NAMUR_FAULT_LOW_MA: Final[float] = 3.6
NAMUR_UNDER_RANGE_MA: Final[float] = 3.8
NAMUR_OVER_RANGE_MA: Final[float] = 20.5
NAMUR_FAULT_HIGH_MA: Final[float] = 21.0

#: Nominal signal span per standard, used when a caller gives an engineering
#: range and a signal type but no explicit electrical range.
_SIGNAL_SPANS: Final[dict[SignalType, tuple[float, float]]] = {
    SignalType.MA_4_20: (4.0, 20.0),
    SignalType.MA_0_20: (0.0, 20.0),
    SignalType.V_0_10: (0.0, 10.0),
    SignalType.V_2_10: (2.0, 10.0),
    SignalType.V_PM_10: (-10.0, 10.0),
}


def signal_span(signal_type: SignalType) -> ValueRange:
    """The nominal electrical span of a signal standard."""
    low, high = _SIGNAL_SPANS[signal_type]
    return ValueRange(low=low, high=high)


def counts_to_engineering(counts: float, raw_range: ValueRange, scaled_range: ValueRange) -> float:
    """Linearly map a raw count onto an engineering value.

    Extrapolates outside ``raw_range`` on purpose: a count below the low end is
    a real, reportable under-range condition, and returning the low limit
    instead would erase it. Use :func:`scale` to get the quality flag alongside.

    Raises:
        DecodeError: If ``raw_range`` is degenerate. A zero-width input span
            makes the mapping undefined, and that is a configuration bug worth
            surfacing rather than a division to be guarded away.
    """
    span = raw_range.high - raw_range.low
    if span == 0:
        raise DecodeError(
            f"raw range {raw_range} has zero width — a raw count cannot be mapped "
            "onto an engineering value through it"
        )
    fraction = (counts - raw_range.low) / span
    return scaled_range.low + fraction * (scaled_range.high - scaled_range.low)


def engineering_to_counts(value: float, scaled_range: ValueRange, raw_range: ValueRange) -> float:
    """The inverse of :func:`counts_to_engineering`.

    Needed for writing setpoints to an analog output, and for building test
    fixtures that are honest about what a given engineering value looks like on
    the wire.
    """
    span = scaled_range.high - scaled_range.low
    if span == 0:
        raise DecodeError(
            f"scaled range {scaled_range} has zero width — an engineering value "
            "cannot be mapped back onto counts through it"
        )
    fraction = (value - scaled_range.low) / span
    return raw_range.low + fraction * (raw_range.high - raw_range.low)


def quality_for_current(ma: float) -> Quality:
    """Classify a 4-20 mA signal against the NAMUR NE 43 bands."""
    if ma < NAMUR_FAULT_LOW_MA or ma > NAMUR_FAULT_HIGH_MA:
        return Quality.BAD
    if ma < NAMUR_UNDER_RANGE_MA or ma > NAMUR_OVER_RANGE_MA:
        return Quality.UNCERTAIN
    return Quality.GOOD


def scale(
    counts: float,
    raw_range: ValueRange,
    scaled_range: ValueRange,
    *,
    name: str,
    unit: str | None = None,
    signal_type: SignalType | None = None,
    source: str | None = None,
    timestamp: datetime | None = None,
) -> Reading:
    """Turn a raw analog count into a :class:`Reading` with an honest quality.

    Args:
        counts: The raw value from the input card.
        raw_range: The card's count span for the *nominal* signal range — e.g.
            3277…16383 for 4-20 mA on a 16-bit Rockwell analog card.
        scaled_range: The engineering span that maps onto it.
        name: Channel name for the reading.
        unit: Engineering unit of the scaled value.
        signal_type: Enables NAMUR band classification. Without it, an
            out-of-range count is reported as
            :attr:`~loopsheet.models.reading.Quality.UNCERTAIN` — the fault
            bands are only meaningful once the standard is known.
        source: Provenance stamped onto the reading.
        timestamp: When the value was observed.

    Returns:
        A reading whose ``value`` is always the extrapolated engineering number
        and whose ``quality`` says whether to trust it. A
        :attr:`~loopsheet.models.reading.Quality.BAD` reading keeps its value
        rather than nulling it, because "the transmitter is reading 2.1 mA" is
        the diagnostic; the quality flag is what stops it being trended.
    """
    value = counts_to_engineering(counts, raw_range, scaled_range)

    if signal_type is not None and signal_type in {SignalType.MA_4_20, SignalType.MA_0_20}:
        span = signal_span(signal_type)
        ma = counts_to_engineering(counts, raw_range, span)
        quality = (
            quality_for_current(ma)
            if signal_type.has_live_zero
            # 0-20 mA has no live zero: a dead wire is indistinguishable from a
            # legitimate zero, so the most that can be said is over-range.
            else (Quality.UNCERTAIN if ma > NAMUR_OVER_RANGE_MA or ma < 0.0 else Quality.GOOD)
        )
    elif counts < raw_range.low or counts > raw_range.high:
        quality = Quality.UNCERTAIN
    else:
        quality = Quality.GOOD

    return Reading(
        name=name,
        value=value,
        unit=unit,
        timestamp=timestamp,
        quality=quality,
        source=source,
        raw=int(counts) if float(counts).is_integer() else None,
    )
