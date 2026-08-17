"""Datatype interpretation — sign extension is the thing being guarded here.

Written before `codec/datatypes.py` per CLAUDE.md §5: the decoder is the piece
most likely to be subtly wrong, and "subtly wrong" here means a number that
looks like a plausible process value.
"""

from __future__ import annotations

import math

import pytest

from loopsheet.codec.datatypes import from_bits, to_signed, to_unsigned
from loopsheet.models.datatype import IOLinkDataType


class TestToSigned:
    @pytest.mark.parametrize(
        ("raw", "bits", "expected"),
        [
            (0b0000, 4, 0),
            (0b0111, 4, 7),
            (0b1000, 4, -8),  # most negative
            (0b1111, 4, -1),
            (0x7FFF, 16, 32767),
            (0x8000, 16, -32768),
            (0xFFFF, 16, -1),
            (0x01, 1, -1),  # a 1-bit signed field is 0 or -1
            (0x00, 1, 0),
        ],
    )
    def test_two_s_complement(self, raw: int, bits: int, expected: int) -> None:
        assert to_signed(raw, bits) == expected

    def test_temperature_case_from_research(self) -> None:
        """-30.0 degC at a 0.1 gradient is 0xFED4 in 16 bits.

        The lower bound of the VVB020's temperature range
        (docs/research/ifm-vvb020.md section 3). Read unsigned it is 65236,
        which scales to 6523.6 degC -- obviously wrong. The point of the test
        is that the obviously-wrong reading is the one we do NOT produce.
        """
        assert to_signed(0xFED4, 16) == -300
        assert to_unsigned(0xFED4, 16) == 65236

    def test_rejects_value_wider_than_field(self) -> None:
        with pytest.raises(ValueError, match="does not fit in 4 bits"):
            to_signed(0b1_0000, 4)

    @pytest.mark.parametrize("bits", [0, -1, 65])
    def test_rejects_impossible_width(self, bits: int) -> None:
        with pytest.raises(ValueError, match=r"bit_length must be 1\.\.64"):
            to_signed(0, bits)


class TestFromBits:
    def test_boolean(self) -> None:
        assert from_bits(1, IOLinkDataType.BOOLEAN, 1) is True
        assert from_bits(0, IOLinkDataType.BOOLEAN, 1) is False

    def test_boolean_must_be_one_bit(self) -> None:
        with pytest.raises(ValueError, match="always 1 bits"):
            from_bits(1, IOLinkDataType.BOOLEAN, 8)

    def test_uinteger_stays_int(self) -> None:
        value = from_bits(0xFFFF, IOLinkDataType.UINTEGER, 16)
        assert value == 65535
        assert isinstance(value, int)

    def test_integer_is_signed(self) -> None:
        assert from_bits(0xFFFF, IOLinkDataType.INTEGER, 16) == -1

    def test_float32(self) -> None:
        # 0x40490FDB is pi in IEEE 754 binary32.
        value = from_bits(0x40490FDB, IOLinkDataType.FLOAT32, 32)
        assert isinstance(value, float)
        assert value == pytest.approx(math.pi, rel=1e-7)

    def test_float32_preserves_nan(self) -> None:
        """A NaN is a device telling you something. Do not launder it into a number."""
        value = from_bits(0x7FC00000, IOLinkDataType.FLOAT32, 32)
        assert isinstance(value, float)
        assert math.isnan(value)

    def test_float32_must_be_32_bits(self) -> None:
        with pytest.raises(ValueError, match="always 32 bits"):
            from_bits(0, IOLinkDataType.FLOAT32, 16)

    def test_string_returns_bytes(self) -> None:
        assert from_bits(0x4142, IOLinkDataType.STRING, 16) == b"AB"

    def test_string_must_be_whole_bytes(self) -> None:
        with pytest.raises(ValueError, match="whole number of bytes"):
            from_bits(0, IOLinkDataType.STRING, 12)


class TestDataTypeProperties:
    def test_fixed_widths(self) -> None:
        assert IOLinkDataType.BOOLEAN.fixed_bit_length == 1
        assert IOLinkDataType.FLOAT32.fixed_bit_length == 32
        assert IOLinkDataType.INTEGER.fixed_bit_length is None

    def test_only_numeric_types_scale(self) -> None:
        assert IOLinkDataType.INTEGER.is_numeric
        assert IOLinkDataType.UINTEGER.is_numeric
        assert IOLinkDataType.FLOAT32.is_numeric
        assert not IOLinkDataType.BOOLEAN.is_numeric
        assert not IOLinkDataType.STRING.is_numeric
