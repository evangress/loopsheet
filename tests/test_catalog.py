"""The part-number catalog: registry behaviour, shipped-data integrity, capabilities.

The most important assertions here are the *negative* ones. Every shipped
catalog file must validate, but the tests that earn their keep are the ones
proving loopsheet refuses to guess: no OPC UA on an AL1350, no unpinned variant
on the VVB020, no decode against a missing layout.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from loopsheet import catalog
from loopsheet.catalog.registry import _load
from loopsheet.catalog.schema import (
    BindingSupport,
    CatalogEntry,
    DeviceVariant,
    Electrical,
)
from loopsheet.errors import CapabilityError, CatalogError, LayoutUnavailableError
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.processdata import ProcessDataItem, ProcessDataLayout
from loopsheet.models.protocol import BindingProtocol
from loopsheet.models.sensor import ComMode


def entry(**kw: Any) -> CatalogEntry:
    """A minimal valid entry, overridable field by field."""
    return CatalogEntry.model_validate(
        {
            "part_number": "TEST01",
            "vendor": "acme",
            "component_type": "iolink_sensor",
            **kw,
        }
    )


# --------------------------------------------------------------------------- #
# Registry                                                                    #
# --------------------------------------------------------------------------- #


class TestRegistry:
    def test_ifm_is_discovered(self) -> None:
        assert "ifm" in catalog.vendors()

    def test_every_shipped_part_is_listed(self) -> None:
        parts = catalog.list_parts()
        assert "ifm:VVB020" in parts
        assert "ifm:AL1350" in parts
        assert "ifm:AL1352" in parts
        assert "ifm:AL1320" in parts
        assert "ifm:AL1322" in parts

    def test_listing_is_sorted(self) -> None:
        parts = catalog.list_parts()
        assert parts == sorted(parts)

    def test_listing_can_be_scoped_to_one_vendor(self) -> None:
        assert catalog.list_parts("ifm") == catalog.list_parts()

    def test_listing_parses_no_yaml(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The file name IS the part number, so listing must never open a file.

        Listing 400 parts should not cost 400 YAML parses. Sabotage the parser
        and confirm the listing still works.
        """
        catalog.clear_cache()

        def explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("list_parts must not parse YAML")

        monkeypatch.setattr(yaml, "safe_load", explode)
        assert "ifm:VVB020" in catalog.list_parts()

    def test_listing_runs_no_vendor_code(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Discovery must never call EntryPoint.load(), which executes vendor code."""
        from importlib.metadata import EntryPoint

        catalog.clear_cache()

        def explode(self: EntryPoint) -> None:
            raise AssertionError("discovery must not call EntryPoint.load()")

        monkeypatch.setattr(EntryPoint, "load", explode)
        assert catalog.list_parts()

    def test_get_returns_a_validated_entry(self) -> None:
        assert catalog.get("ifm:VVB020").ref == "ifm:VVB020"

    def test_get_returns_a_copy_so_callers_cannot_poison_the_cache(self) -> None:
        first = catalog.get("ifm:VVB020")
        first.channels.clear()
        assert catalog.get("ifm:VVB020").channels, "cached entry was mutated by a caller"

    def test_unknown_part_lists_what_the_vendor_does_ship(self) -> None:
        with pytest.raises(CatalogError, match=r"ifm ships:.*VVB020"):
            catalog.get("ifm:NOPE")

    def test_unknown_vendor_lists_known_vendors(self) -> None:
        with pytest.raises(CatalogError, match=r"Known vendors: ifm"):
            catalog.get("acme:WIDGET")

    @pytest.mark.parametrize("ref", ["VVB020", "ifm:", ":VVB020", ""])
    def test_malformed_reference_is_rejected(self, ref: str) -> None:
        with pytest.raises(CatalogError, match=r"malformed catalog reference|unknown catalog"):
            catalog.get(ref)

    def test_cache_can_be_cleared(self) -> None:
        catalog.get("ifm:VVB020")
        catalog.clear_cache()
        assert catalog.get("ifm:VVB020").ref == "ifm:VVB020"


# --------------------------------------------------------------------------- #
# Shipped data integrity                                                      #
# --------------------------------------------------------------------------- #


class TestShippedData:
    @pytest.mark.parametrize("ref", catalog.list_parts())
    def test_every_shipped_file_validates(self, ref: str) -> None:
        assert catalog.get(ref).ref == ref

    @pytest.mark.parametrize("ref", catalog.list_parts())
    def test_every_shipped_file_cites_its_sources(self, ref: str) -> None:
        """An entry with populated values and no provenance should not exist."""
        assert catalog.get(ref).sources, f"{ref} declares no sources"

    @pytest.mark.parametrize("ref", catalog.list_parts())
    def test_declared_identity_matches_the_file_path(self, ref: str) -> None:
        vendor, part = ref.split(":")
        loaded = catalog.get(ref)
        assert (loaded.vendor, loaded.part_number) == (vendor, part)

    def test_vvb020_has_both_variants_with_distinct_device_ids(self) -> None:
        """A part number is not one IO-Link identity."""
        vvb = catalog.get("ifm:VVB020")
        assert {v.id for v in vvb.variants} == {"status_a", "status_b"}

        status_a = vvb.variant("status_a")
        status_b = vvb.variant("status_b")
        assert status_a is not None and status_b is not None
        assert status_a.device_id == 1257
        assert status_b.device_id == 1369
        assert status_a.com_mode is ComMode.COM2
        assert status_b.com_mode is ComMode.COM3
        assert status_a.min_cycle_time_ms == 11.6
        assert status_b.min_cycle_time_ms == 3.6
        assert status_a.has_pdout is False
        assert status_b.has_pdout is True

    def test_vvb020_process_data_is_honestly_absent(self) -> None:
        """The IODD is unobtainable, so there are no bit offsets to ship."""
        vvb = catalog.get("ifm:VVB020")
        for variant in vvb.variants:
            assert variant.process_data is None
            assert not variant.layout_known

    def test_vvb020_channels_are_semantically_complete(self) -> None:
        """Names, units, ranges and bands are known even though the bits are not."""
        vvb = catalog.get("ifm:VVB020")
        assert [c.name for c in vvb.channels] == [
            "v_rms",
            "a_peak",
            "a_rms",
            "crest",
            "temperature",
        ]
        v_rms = vvb.channel("v_rms")
        assert v_rms is not None
        assert v_rms.unit == "mm/s"
        assert v_rms.range is not None
        assert (v_rms.range.low, v_rms.range.high) == (0.0, 45.0)
        assert v_rms.band_hz is not None
        assert (v_rms.band_hz.low_hz, v_rms.band_hz.high_hz) == (10.0, 1000.0)

    def test_vvb020_crest_is_dimensionless_not_unknown(self) -> None:
        """`""` means explicitly dimensionless; `None` would mean 'not established'."""
        crest = catalog.get("ifm:VVB020").channel("crest")
        assert crest is not None
        assert crest.unit == ""

    def test_vvb020_has_no_analog_output(self) -> None:
        """A confirmed negative. An analog-output entry for this part would be wrong."""
        electrical = catalog.get("ifm:VVB020").electrical
        assert electrical is not None
        assert electrical.analog_output is None
        assert electrical.digital_outputs == 2

    def test_vvb020_pinout_is_complete(self) -> None:
        electrical = catalog.get("ifm:VVB020").electrical
        assert electrical is not None
        assert set(electrical.pinout) == {1, 2, 3, 4}
        assert electrical.pinout[4].function == "OUT1_OR_IOLINK"
        assert electrical.pinout[4].colour == "BK"

    def test_vvb020_isdu_parameters_are_not_invented(self) -> None:
        """No index or subindex was found for any VVB020 parameter. Ship none."""
        assert catalog.get("ifm:VVB020").parameters == []

    def test_vvb020_vendor_id(self) -> None:
        iolink = catalog.get("ifm:VVB020").iolink
        assert iolink is not None
        assert iolink.vendor_id == 310
        assert iolink.revision == "1.1"
        assert iolink.port_class == "A"


# --------------------------------------------------------------------------- #
# Capabilities -- the guard rail                                              #
# --------------------------------------------------------------------------- #


class TestCapabilities:
    def test_al1350_serves_iotcore_and_mqtt(self) -> None:
        al1350 = catalog.get("ifm:AL1350")
        assert al1350.supports(BindingProtocol.IOTCORE)
        assert al1350.supports(BindingProtocol.MQTT)

    def test_opcua_on_an_al1350_raises_naming_what_it_does_support(self) -> None:
        """The confirmed negative that motivates the whole capability model."""
        al1350 = catalog.get("ifm:AL1350")
        assert not al1350.supports(BindingProtocol.OPCUA)
        with pytest.raises(CapabilityError) as exc:
            al1350.require_binding(BindingProtocol.OPCUA)
        message = str(exc.value)
        assert "ifm:AL1350" in message
        assert "does not support opcua" in message
        assert "iotcore" in message and "mqtt" in message

    def test_ethernet_ip_on_an_al1350_raises(self) -> None:
        with pytest.raises(CapabilityError, match="does not support ethernet_ip"):
            catalog.get("ifm:AL1350").require_binding(BindingProtocol.ETHERNET_IP)

    def test_mqtt_is_firmware_dependent_across_one_protocol_family(self) -> None:
        """AL1320 at FW 3.1.x has MQTT; AL1322 at FW 2.3.x does not.

        Same EtherNet/IP family, different capability -- which is exactly why
        supported_bindings is declared per part and not per family.
        """
        al1320 = catalog.get("ifm:AL1320")
        al1322 = catalog.get("ifm:AL1322")

        assert al1320.supports(BindingProtocol.MQTT)
        assert not al1322.supports(BindingProtocol.MQTT)
        assert al1320.supports(BindingProtocol.ETHERNET_IP)
        assert al1322.supports(BindingProtocol.ETHERNET_IP)

        assert al1320.require_binding(BindingProtocol.MQTT).firmware == "3.1.x"
        assert al1322.firmware == "2.3.x"

    def test_no_shipped_ifm_master_serves_all_three_protocols(self) -> None:
        """No single ifm master speaks MQTT and OPC UA and EtherNet/IP."""
        wanted = {BindingProtocol.MQTT, BindingProtocol.OPCUA, BindingProtocol.ETHERNET_IP}
        for ref in catalog.list_parts():
            loaded = catalog.get(ref)
            if loaded.component_type == "iolink_master":
                assert not wanted.issubset(set(loaded.protocols)), ref

    def test_a_master_entry_must_declare_its_capabilities(self) -> None:
        """Without supported_bindings every binding validates and the guard does nothing."""
        with pytest.raises(ValidationError, match="must declare supported_bindings"):
            entry(component_type="iolink_master", supported_bindings=[])

    def test_duplicate_protocol_declarations_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="declared twice"):
            entry(
                component_type="iolink_master",
                supported_bindings=[
                    BindingSupport(protocol=BindingProtocol.MQTT),
                    BindingSupport(protocol=BindingProtocol.MQTT),
                ],
            )

    def test_a_part_with_no_bindings_says_so_plainly(self) -> None:
        with pytest.raises(CapabilityError, match="no bindings at all"):
            entry().require_binding(BindingProtocol.MQTT)


# --------------------------------------------------------------------------- #
# Variants                                                                    #
# --------------------------------------------------------------------------- #


class TestVariantResolution:
    def test_an_ambiguous_part_must_be_pinned(self) -> None:
        """Silently taking the first variant would decode the wrong values."""
        with pytest.raises(CapabilityError) as exc:
            catalog.get("ifm:VVB020").require_variant(None)
        message = str(exc.value)
        assert "2 variants" in message
        assert "status_a" in message and "status_b" in message
        assert "guessing one decodes the wrong values" in message

    def test_a_pinned_variant_resolves(self) -> None:
        assert catalog.get("ifm:VVB020").require_variant("status_b").device_id == 1369

    def test_an_unknown_pin_lists_the_real_ones(self) -> None:
        with pytest.raises(CapabilityError, match="Known variants: status_a, status_b"):
            catalog.get("ifm:VVB020").require_variant("status_c")

    def test_a_single_variant_part_needs_no_pin(self) -> None:
        single = entry(variants=[DeviceVariant(id="only", device_id=1)])
        assert single.require_variant(None).id == "only"

    def test_a_part_with_no_variants_says_so(self) -> None:
        with pytest.raises(CapabilityError, match="declares no variants"):
            entry().require_variant(None)

    def test_variants_sharing_a_device_id_are_rejected(self) -> None:
        """Indistinguishable on the wire defeats the entire point of variants."""
        with pytest.raises(ValidationError, match="cannot be told apart on the wire"):
            entry(
                variants=[
                    DeviceVariant(id="a", device_id=1257),
                    DeviceVariant(id="b", device_id=1257),
                ]
            )

    def test_duplicate_variant_ids_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate variant id"):
            entry(variants=[DeviceVariant(id="a"), DeviceVariant(id="a")])

    def test_variants_without_device_ids_do_not_collide(self) -> None:
        assert len(entry(variants=[DeviceVariant(id="a"), DeviceVariant(id="b")]).variants) == 2


class TestVariantLayout:
    def _layout(self, bits: int = 16) -> ProcessDataLayout:
        return ProcessDataLayout(
            bit_length=bits,
            items=[
                ProcessDataItem(
                    name="v", datatype=IOLinkDataType.UINTEGER, bit_offset=0, bit_length=bits
                )
            ],
        )

    def test_a_missing_layout_refuses_and_names_the_part(self) -> None:
        """Never a silent wrong answer -- the error has to be actionable."""
        vvb = catalog.get("ifm:VVB020")
        variant = vvb.require_variant("status_b")
        with pytest.raises(LayoutUnavailableError) as exc:
            variant.require_process_data(vvb.ref)
        message = str(exc.value)
        assert "ifm:VVB020" in message
        assert "status_b" in message
        assert "ifm-000559-20201105-IODD1.1" in message
        assert "IODD" in message

    def test_a_missing_layout_still_reports_without_a_part_ref(self) -> None:
        with pytest.raises(LayoutUnavailableError, match="variant 'status_a'"):
            catalog.get("ifm:VVB020").require_variant("status_a").require_process_data()

    def test_a_present_layout_is_returned(self) -> None:
        variant = DeviceVariant(id="v", process_data=self._layout())
        assert variant.require_process_data().bit_length == 16
        assert variant.layout_known

    def test_a_layout_contradicting_the_declared_length_is_rejected(self) -> None:
        """Both come from the same IODD, so disagreement means a transcription bug."""
        with pytest.raises(ValidationError, match="pdin_length_bits is 32 but its layout"):
            DeviceVariant(id="v", pdin_length_bits=32, process_data=self._layout(16))

    def test_pdout_layout_on_a_variant_without_pdout_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="has_pdout is false but a PDOut layout"):
            DeviceVariant(id="v", has_pdout=False, process_data_out=self._layout())


# --------------------------------------------------------------------------- #
# Schema guards                                                               #
# --------------------------------------------------------------------------- #


class TestSchemaGuards:
    def test_unknown_component_type_lists_the_known_ones(self) -> None:
        with pytest.raises(ValidationError, match="unknown component_type 'toaster'"):
            entry(component_type="toaster")

    def test_duplicate_channels_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate channel 'v_rms'"):
            entry(channels=[{"name": "v_rms"}, {"name": "v_rms"}])

    def test_vendor_must_be_a_lowercase_slug(self) -> None:
        """The vendor is a directory name and half of a catalog reference."""
        with pytest.raises(ValidationError):
            entry(vendor="IFM Electronic")

    def test_a_typo_in_a_catalog_field_is_an_error(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            entry(chanels=[])

    def test_pinout_beyond_the_connector_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="connector has 4 pins"):
            Electrical.model_validate(
                {
                    "connector": {"type": "M12", "coding": "A", "pins": 4},
                    "pinout": {1: {"function": "L+"}, 5: {"function": "?"}},
                }
            )

    def test_isdu_parameters_default_to_subindex_zero(self) -> None:
        """Subindex 0 addresses the whole record. That is IO-Link's convention."""
        loaded = entry(parameters=[{"index": 90, "name": "thing"}])
        assert loaded.parameter(90) is not None
        assert loaded.parameters[0].subindex == 0


def test_loader_rejects_a_file_whose_identity_disagrees_with_its_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The file path is the index, so the two must agree or the part is unreachable."""
    catalog.clear_cache()
    real = yaml.safe_load

    def swapped(stream: Any) -> Any:
        data = real(stream)
        if isinstance(data, dict):
            data["part_number"] = "SOMETHINGELSE"
        return data

    monkeypatch.setattr(yaml, "safe_load", swapped)
    with pytest.raises(CatalogError, match="The file path is the index"):
        _load("ifm:VVB020")
    catalog.clear_cache()
