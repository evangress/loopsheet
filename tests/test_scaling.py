"""Analog scaling and NAMUR NE 43 band classification."""

from __future__ import annotations

import pytest

from loopsheet.codec.scaling import (
    counts_to_engineering,
    engineering_to_counts,
    quality_for_current,
    scale,
    signal_span,
)
from loopsheet.errors import DecodeError
from loopsheet.models.channel import ValueRange
from loopsheet.models.reading import Quality
from loopsheet.models.sensor import SignalType

#: A 16-bit Rockwell analog card's count span for the 4-20 mA nominal range.
CARD = ValueRange(low=3277.0, high=16383.0)
#: A 0-16 bar transmitter.
PRESSURE = ValueRange(low=0.0, high=16.0)


class TestLinearMapping:
    @pytest.mark.parametrize(
        ("counts", "expected"),
        [
            (3277.0, 0.0),  # 4 mA
            (16383.0, 16.0),  # 20 mA
            (9830.0, 8.0),  # midpoint
        ],
    )
    def test_endpoints_and_midpoint(self, counts: float, expected: float) -> None:
        assert counts_to_engineering(counts, CARD, PRESSURE) == pytest.approx(expected, abs=1e-3)

    def test_extrapolates_below_range_rather_than_clamping(self) -> None:
        """A count below the low end is a real under-range, not a zero."""
        assert counts_to_engineering(0.0, CARD, PRESSURE) < 0.0

    def test_round_trip(self) -> None:
        counts = engineering_to_counts(12.5, PRESSURE, CARD)
        assert counts_to_engineering(counts, CARD, PRESSURE) == pytest.approx(12.5)

    def test_zero_width_raw_range_is_a_configuration_bug(self) -> None:
        with pytest.raises(DecodeError, match="zero width"):
            counts_to_engineering(100.0, ValueRange(low=5.0, high=5.0), PRESSURE)

    def test_zero_width_scaled_range_is_a_configuration_bug(self) -> None:
        with pytest.raises(DecodeError, match="zero width"):
            engineering_to_counts(1.0, ValueRange(low=5.0, high=5.0), CARD)

    def test_inverted_range_is_rejected_at_construction(self) -> None:
        with pytest.raises(ValueError, match="must not exceed high"):
            ValueRange(low=10.0, high=1.0)


class TestNamurBands:
    @pytest.mark.parametrize(
        ("ma", "expected"),
        [
            (2.0, Quality.BAD),  # broken wire
            (3.5, Quality.BAD),
            (3.7, Quality.UNCERTAIN),  # under-range
            (4.0, Quality.GOOD),
            (12.0, Quality.GOOD),
            (20.0, Quality.GOOD),
            (20.8, Quality.UNCERTAIN),  # over-range
            (22.0, Quality.BAD),  # fault
        ],
    )
    def test_bands(self, ma: float, expected: Quality) -> None:
        assert quality_for_current(ma) is expected

    def test_band_edges_are_inclusive_of_good(self) -> None:
        assert quality_for_current(3.8) is Quality.GOOD
        assert quality_for_current(20.5) is Quality.GOOD


class TestScale:
    def test_normal_reading(self) -> None:
        reading = scale(
            9830.0,
            CARD,
            PRESSURE,
            name="suction_pressure",
            unit="bar",
            signal_type=SignalType.MA_4_20,
        )
        assert reading.value == pytest.approx(8.0, abs=1e-3)
        assert reading.quality is Quality.GOOD
        assert reading.unit == "bar"

    def test_broken_wire_is_bad_but_keeps_its_value(self) -> None:
        """'The transmitter reads 2 mA' is the diagnostic; quality stops it trending."""
        reading = scale(
            0.0, CARD, PRESSURE, name="suction_pressure", signal_type=SignalType.MA_4_20
        )
        assert reading.quality is Quality.BAD
        assert reading.value is not None
        assert reading.value < 0.0

    def test_zero_current_standard_cannot_detect_a_broken_wire(self) -> None:
        """0-20 mA has no live zero, so 0 mA is ambiguous. Never claim BAD."""
        span = signal_span(SignalType.MA_0_20)
        card = ValueRange(low=0.0, high=16383.0)
        reading = scale(0.0, card, PRESSURE, name="p", signal_type=SignalType.MA_0_20)
        assert reading.quality is Quality.GOOD
        assert span.low == 0.0
        assert not SignalType.MA_0_20.has_live_zero

    def test_without_a_signal_type_out_of_range_is_only_uncertain(self) -> None:
        reading = scale(0.0, CARD, PRESSURE, name="p")
        assert reading.quality is Quality.UNCERTAIN

    def test_voltage_signals_use_the_plain_range_check(self) -> None:
        reading = scale(
            20000.0,
            ValueRange(low=0.0, high=16383.0),
            ValueRange(low=0.0, high=10.0),
            name="level",
            unit="V",
            signal_type=SignalType.V_0_10,
        )
        assert reading.quality is Quality.UNCERTAIN

    def test_live_zero_property(self) -> None:
        assert SignalType.MA_4_20.has_live_zero
        assert SignalType.V_2_10.has_live_zero
        assert not SignalType.V_0_10.has_live_zero
