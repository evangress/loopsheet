"""Decoding process data.

Byte-boundary spanning, sign extension, and gradient arithmetic are each a way
to be confidently wrong, so each gets a hand-computed expectation rather than a
round-trip through the code under test.

The VVB020 golden-decode test is deliberately absent: its IODD is not
obtainable, so there are no verified bit offsets to test against. Writing one
against invented offsets would prove nothing. See TODO.md Phase 0.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from loopsheet.codec.decode import decode, decode_hex, decode_item
from loopsheet.errors import DecodeError, LayoutUnavailableError
from loopsheet.models.channel import ValueRange
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout
from loopsheet.models.reading import Quality


class TestBitPlacement:
    def test_item_at_offset_zero_is_the_last_transmitted_bits(self) -> None:
        """bit_offset counts from the LSB of the whole word, IODD-style.

        0x00FF as two bytes: an 8-bit item at offset 0 sees 0xFF, and one at
        offset 8 sees 0x00. Getting this backwards is the classic IO-Link
        decoder bug, so it is asserted directly rather than inferred.
        """
        layout = ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="low", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=8
                ),
                ProcessDataItem(
                    name="high", datatype=IOLinkDataType.UINTEGER, bit_offset=8, bit_length=8
                ),
            ],
        )
        readings = decode(b"\x00\xff", layout)
        assert readings["low"].value == 0xFF
        assert readings["high"].value == 0x00

    def test_field_spanning_a_byte_boundary(self) -> None:
        """A 12-bit value at offset 4 of a 16-bit word straddles both bytes.

        Word 0xABCD = 1010 1011 1100 1101. Shifting right 4 leaves
        1010 1011 1100 = 0xABC.
        """
        layout = ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="measurement",
                    datatype=IOLinkDataType.UINTEGER,
                    bit_offset=4,
                    bit_length=12,
                ),
                ProcessDataItem(
                    name="status", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=4
                ),
            ],
        )
        readings = decode(b"\xab\xcd", layout)
        assert readings["measurement"].value == 0xABC
        assert readings["status"].value == 0xD

    def test_field_spanning_three_bytes(self) -> None:
        # 0x123456 >> 6 = 0x48D1, masked to 17 bits = 0x048D1.
        layout = ProcessDataLayout(
            bit_length=24,
            items=[
                ProcessDataItem(
                    name="wide", datatype=IOLinkDataType.UINTEGER, bit_offset=6, bit_length=17
                )
            ],
        )
        assert decode(b"\x12\x34\x56", layout)["wide"].value == (0x123456 >> 6) & 0x1FFFF

    def test_bits_outside_every_item_are_ignored(self) -> None:
        layout = ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="a", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=4
                )
            ],
        )
        assert decode(b"\xff\xf5", layout)["a"].value == 5


class TestSignAndScaling:
    def test_signed_value_is_sign_extended(self) -> None:
        layout = ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="temperature",
                    datatype=IOLinkDataType.INTEGER,
                    bit_offset=0,
                    bit_length=16,
                    gradient=0.1,
                    unit="°C",
                )
            ],
        )
        reading = decode(b"\xfe\xd4", layout)["temperature"]
        assert reading.value == pytest.approx(-30.0)
        assert reading.unit == "°C"
        assert reading.raw == 0xFED4

    def test_gradient_and_offset_are_applied_in_that_order(self) -> None:
        layout = ProcessDataLayout(
            bit_length=8,
            items=[
                ProcessDataItem(
                    name="v",
                    datatype=IOLinkDataType.UINTEGER,
                    bit_offset=0,
                    bit_length=8,
                    gradient=0.5,
                    offset=-10.0,
                )
            ],
        )
        # 100 * 0.5 - 10 = 40.0, not (100 - 10) * 0.5 = 45.0.
        assert decode(b"\x64", layout)["v"].value == pytest.approx(40.0)

    def test_identity_scaling_keeps_the_value_an_int(self) -> None:
        """A counter that reads 42 should stay 42, not become 42.0."""
        layout = ProcessDataLayout(
            bit_length=8,
            items=[
                ProcessDataItem(
                    name="count", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=8
                )
            ],
        )
        value = decode(b"\x2a", layout)["count"].value
        assert value == 42
        assert isinstance(value, int)

    def test_booleans_decode_as_bool(self) -> None:
        layout = ProcessDataLayout(
            bit_length=8,
            items=[
                ProcessDataItem(
                    name="out1", datatype=IOLinkDataType.BOOLEAN, bit_offset=0, bit_length=1
                ),
                ProcessDataItem(
                    name="out2", datatype=IOLinkDataType.BOOLEAN, bit_offset=1, bit_length=1
                ),
            ],
        )
        readings = decode(b"\x01", layout)
        assert readings["out1"].value is True
        assert readings["out2"].value is False


class TestQuality:
    def _layout(self) -> ProcessDataLayout:
        return ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="v_rms",
                    datatype=IOLinkDataType.UINTEGER,
                    bit_offset=0,
                    bit_length=16,
                    gradient=0.1,
                    unit="mm/s",
                    range=ValueRange(low=0.0, high=45.0),
                )
            ],
        )

    def test_in_range_is_good(self) -> None:
        assert decode(b"\x00\xf0", self._layout())["v_rms"].quality is Quality.GOOD

    def test_out_of_range_is_uncertain_but_keeps_its_value(self) -> None:
        """Out of range is reported, never corrected -- clamping hides faults."""
        reading = decode(b"\x0f\xff", self._layout())["v_rms"]
        assert reading.quality is Quality.UNCERTAIN
        assert reading.value == pytest.approx(409.5)

    def test_metadata_is_carried_through(self) -> None:
        when = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        reading = decode(b"\x00\xf0", self._layout(), source="vib_1", timestamp=when)["v_rms"]
        assert reading.source == "vib_1"
        assert reading.timestamp == when


class TestErrors:
    def _layout(self) -> ProcessDataLayout:
        return ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="a", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=16
                )
            ],
        )

    def test_missing_layout_refuses_rather_than_guessing(self) -> None:
        with pytest.raises(LayoutUnavailableError, match="IODD is required"):
            decode(b"\x00\x00", None)

    def test_missing_layout_is_catchable_as_a_decode_error(self) -> None:
        with pytest.raises(DecodeError):
            decode(b"\x00\x00", None)

    def test_truncated_data_raises_and_says_so(self) -> None:
        with pytest.raises(DecodeError, match="Truncated"):
            decode(b"\x00", self._layout())

    def test_oversized_data_points_at_the_likely_cause(self) -> None:
        with pytest.raises(DecodeError, match="wrong port or the wrong variant"):
            decode(b"\x00\x00\x00", self._layout())


class TestDecodeHex:
    """ifm's IoT Core returns PDIn as an uppercase hex string."""

    def _layout(self) -> ProcessDataLayout:
        return ProcessDataLayout(
            bit_length=16,
            items=[
                ProcessDataItem(
                    name="a", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=16
                )
            ],
        )

    @pytest.mark.parametrize("raw", ["ABCD", "abcd", " ABCD "])
    def test_case_and_whitespace_are_accepted(self, raw: str) -> None:
        assert decode_hex(raw, self._layout())["a"].value == 0xABCD

    def test_odd_digit_count_raises(self) -> None:
        with pytest.raises(DecodeError, match="odd number of digits"):
            decode_hex("ABC", self._layout())

    def test_non_hex_raises(self) -> None:
        with pytest.raises(DecodeError, match="not valid hex"):
            decode_hex("ZZZZ", self._layout())


def test_decode_item_is_usable_standalone() -> None:
    reading = decode_item(
        0xABCD,
        ProcessDataItem(name="x", datatype=IOLinkDataType.UINTEGER, bit_offset=4, bit_length=12),
    )
    assert reading.value == 0xABC
