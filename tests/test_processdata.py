"""Process-data layout validation.

Overlapping bit ranges are the failure this file exists for. Two items sharing
a bit yields one plausible value and one silently wrong one, which is exactly
the class of bug loopsheet refuses to ship.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout


def item(name: str, offset: int, length: int, **kw: object) -> ProcessDataItem:
    return ProcessDataItem(
        name=name,
        datatype=kw.pop("datatype", IOLinkDataType.UINTEGER),  # type: ignore[arg-type]
        bit_offset=offset,
        bit_length=length,
        **kw,  # type: ignore[arg-type]
    )


class TestOverlap:
    def test_adjacent_items_are_fine(self) -> None:
        layout = ProcessDataLayout(
            bit_length=16,
            items=[item("low", 0, 8), item("high", 8, 8)],
        )
        assert layout.byte_length == 2

    def test_overlapping_items_raise(self) -> None:
        with pytest.raises(ValidationError, match="overlap"):
            ProcessDataLayout(bit_length=16, items=[item("a", 0, 12), item("b", 8, 8)])

    def test_error_names_both_items_and_their_bits(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ProcessDataLayout(bit_length=16, items=[item("a", 0, 12), item("b", 8, 8)])
        message = str(exc.value)
        assert "'a'" in message
        assert "'b'" in message
        assert "0..11" in message

    def test_single_shared_bit_is_still_an_overlap(self) -> None:
        with pytest.raises(ValidationError, match="overlap"):
            ProcessDataLayout(bit_length=16, items=[item("a", 0, 9), item("b", 8, 1)])

    def test_declaration_order_does_not_matter(self) -> None:
        """The scan sorts by offset, so a layout written high-to-low still catches."""
        with pytest.raises(ValidationError, match="overlap"):
            ProcessDataLayout(bit_length=16, items=[item("b", 8, 8), item("a", 0, 12)])

    def test_gaps_are_allowed(self) -> None:
        """Reserved bits are normal in a real IODD; a gap is not an error."""
        layout = ProcessDataLayout(bit_length=32, items=[item("a", 0, 8), item("b", 24, 8)])
        assert len(layout.items) == 2


class TestBounds:
    def test_item_past_the_end_raises(self) -> None:
        with pytest.raises(ValidationError, match="past the declared 16-bit word"):
            ProcessDataLayout(bit_length=16, items=[item("a", 8, 16)])

    def test_item_exactly_filling_the_word_is_fine(self) -> None:
        ProcessDataLayout(bit_length=16, items=[item("a", 0, 16)])

    def test_duplicate_names_raise(self) -> None:
        with pytest.raises(ValidationError, match="declared twice"):
            ProcessDataLayout(bit_length=16, items=[item("a", 0, 8), item("a", 8, 8)])

    def test_byte_length_rounds_a_partial_byte_up(self) -> None:
        """A 12-bit PDIn is legal and occupies two transmitted bytes."""
        layout = ProcessDataLayout(bit_length=12, items=[item("a", 0, 12)])
        assert layout.byte_length == 2


class TestItemValidation:
    def test_boolean_must_be_one_bit(self) -> None:
        with pytest.raises(ValidationError, match="always 1 bits"):
            item("flag", 0, 8, datatype=IOLinkDataType.BOOLEAN)

    def test_scaling_a_boolean_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="scaling is meaningless"):
            item("flag", 0, 1, datatype=IOLinkDataType.BOOLEAN, gradient=0.1)

    def test_unknown_unit_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="unknown unit"):
            item("temp", 0, 16, unit="degrees")

    def test_ascii_unit_alias_is_normalised(self) -> None:
        assert item("accel", 0, 16, unit="m/s2").unit == "m/s²"

    def test_bit_span(self) -> None:
        assert list(item("a", 4, 3).bit_span) == [4, 5, 6]

    def test_layout_lookup(self) -> None:
        layout = ProcessDataLayout(bit_length=16, items=[item("a", 0, 8), item("b", 8, 8)])
        assert layout.item("b") is not None
        assert layout.item("missing") is None
