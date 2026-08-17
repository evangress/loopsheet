"""Model validation: the component union, schema generation, and machine integrity."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from loopsheet.models import (
    PLC,
    SCHEMA_VERSION,
    AnalogSensor,
    DaqDevice,
    DiscreteSensor,
    EdgeDevice,
    IOLinkMaster,
    IOLinkSensor,
    Machine,
    MeasurementPoint,
    Motor,
    Port,
    Pump,
    Quality,
    Reading,
)
from loopsheet.models.asset import Axis, Location, Mounting
from loopsheet.models.channel import ChannelSpec, FrequencyBand, ValueRange
from loopsheet.models.component import COMPONENT_ADAPTER, COMPONENT_TYPES, dump_component
from loopsheet.models.datatype import IOLinkDataType
from loopsheet.models.iolink import PortMode, ValidationMode


class TestComponentUnion:
    @pytest.mark.parametrize("component_type", sorted(COMPONENT_TYPES))
    def test_every_subtype_round_trips_through_the_adapter(self, component_type: str) -> None:
        """A dict in, the right class out, and the same dict back."""
        payload: dict[str, object] = {"component_type": component_type, "id": "thing_1"}
        if component_type == "iolink_port":
            payload["number"] = 1
        component = COMPONENT_ADAPTER.validate_python(payload)
        assert isinstance(component, COMPONENT_TYPES[component_type])
        dumped = dump_component(component)
        assert dumped["component_type"] == component_type
        assert COMPONENT_ADAPTER.validate_python(dumped) == component

    @pytest.mark.parametrize("component_type", sorted(COMPONENT_TYPES))
    def test_a_bare_model_dump_drops_the_discriminator(self, component_type: str) -> None:
        """The footgun `dump_component` exists to close.

        `component_type` carries a per-subtype default, so excluding defaults
        silently removes it and the result no longer resolves. Pinned here so a
        future dumper cannot regress into writing unloadable machine files.
        """
        payload: dict[str, object] = {"component_type": component_type, "id": "thing_1"}
        if component_type == "iolink_port":
            payload["number"] = 1
        component = COMPONENT_ADAPTER.validate_python(payload)
        naive = component.model_dump(exclude_defaults=True)
        assert "component_type" not in naive
        with pytest.raises(ValidationError):
            COMPONENT_ADAPTER.validate_python(naive)

    def test_json_schema_generates_with_a_discriminator(self) -> None:
        schema = COMPONENT_ADAPTER.json_schema()
        assert "oneOf" in schema
        assert schema["discriminator"]["propertyName"] == "component_type"
        assert len(schema["oneOf"]) == len(COMPONENT_TYPES)

    def test_unknown_component_type_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            COMPONENT_ADAPTER.validate_python({"component_type": "toaster", "id": "t1"})

    def test_a_typo_in_a_field_name_is_an_error_not_a_shrug(self) -> None:
        """extra='forbid' is the highest-value setting for hand-authored config."""
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            IOLinkSensor(id="vib_1", portt=1)  # type: ignore[call-arg]

    def test_ids_must_be_reference_safe(self) -> None:
        """Ids become topic segments and tag names, so spaces cannot be allowed."""
        with pytest.raises(ValidationError):
            IOLinkSensor(id="vib 1")

    def test_effective_tag_falls_back_to_id(self) -> None:
        assert IOLinkSensor(id="vib_1").effective_tag == "vib_1"
        assert IOLinkSensor(id="vib_1", tag="pump_de_bearing").effective_tag == "pump_de_bearing"

    def test_part_reference_is_split(self) -> None:
        sensor = IOLinkSensor(id="vib_1", part="ifm:VVB020")
        assert sensor.vendor == "ifm"
        assert sensor.part_number == "VVB020"

    def test_malformed_part_reference_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IOLinkSensor(id="vib_1", part="VVB020")


class TestChannelSpec:
    def test_a_channel_may_be_semantically_known_and_electrically_unknown(self) -> None:
        """The VVB020's situation today: names and ranges yes, bit offsets no."""
        channel = ChannelSpec(
            name="v_rms",
            unit="mm/s",
            range=ValueRange(low=0.0, high=45.0),
            band_hz=FrequencyBand(low_hz=10.0, high_hz=1000.0),
        )
        assert not channel.layout_known

    def test_half_a_bit_layout_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be given together"):
            ChannelSpec(name="v_rms", bit_offset=4)

    def test_a_complete_bit_layout_is_accepted(self) -> None:
        assert ChannelSpec(name="v_rms", bit_offset=4, bit_length=12).layout_known

    def test_datatype_width_is_cross_checked(self) -> None:
        with pytest.raises(ValidationError, match="always 1 bits"):
            ChannelSpec(name="out1", datatype=IOLinkDataType.BOOLEAN, bit_offset=0, bit_length=8)

    def test_inverted_frequency_band_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be below high_hz"):
            FrequencyBand(low_hz=1000.0, high_hz=10.0)


class TestIOLink:
    def test_a_device_on_a_non_iolink_port_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="produces no process data"):
            Port(id="p1", number=1, mode=PortMode.DI, device="vib_1")

    def test_duplicate_port_numbers_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="port 1 declared twice"):
            IOLinkMaster(
                id="master_1",
                ports=[Port(id="p1", number=1), Port(id="p1b", number=1)],
            )

    def test_a_port_beyond_the_master_s_capacity_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="has only 4 ports"):
            IOLinkMaster(id="master_1", port_count=4, ports=[Port(id="p8", number=8)])

    def test_validation_mode_knows_whether_it_pins_a_variant(self) -> None:
        """Status B of the VVB020 is rejected unless device ID is checked."""
        assert not ValidationMode.NONE.checks_device_id
        assert ValidationMode.TYPE_COMPATIBLE_V11.checks_device_id

    def test_sensor_master_and_port_travel_together(self) -> None:
        with pytest.raises(ValidationError, match="must be given together"):
            IOLinkSensor(id="vib_1", port=1)


class TestAssets:
    def test_motor_pole_count_must_be_even(self) -> None:
        with pytest.raises(ValidationError, match="must be even"):
            Motor(id="M101", poles=3)

    def test_mounting_caps_usable_bandwidth(self) -> None:
        """ifm's own figures -- a magnet-mounted sensor cannot see 5 kHz."""
        assert Mounting.MAGNET.max_transferable_hz == 3000.0
        assert Mounting.SCREW.max_transferable_hz == 15000.0
        assert Mounting.UNSPECIFIED.max_transferable_hz is None

    def test_assets_are_discriminated_on_kind(self) -> None:
        machine = Machine(name="m", assets=[Motor(id="M101"), Pump(id="P101", driver="M101")])
        assert machine.asset("P101").kind == "pump"  # type: ignore[union-attr]


class TestMachineIntegrity:
    def _machine(self) -> Machine:
        return Machine(
            name="filler_line_3",
            assets=[Motor(id="M101", rated_rpm=1780.0), Pump(id="P101", driver="M101")],
            measurement_points=[
                MeasurementPoint(
                    id="P101_DE_H",
                    asset="P101",
                    location=Location.DRIVE_END,
                    axis=Axis.RADIAL_HORIZONTAL,
                    mounting=Mounting.SCREW,
                )
            ],
            components=[
                IOLinkMaster(id="master_1", part="ifm:AL1350", port_count=8),
                IOLinkSensor(
                    id="vib_1",
                    part="ifm:VVB020",
                    tag="pump_de_bearing",
                    master="master_1",
                    port=1,
                    mounted_at="P101_DE_H",
                ),
            ],
        )

    def test_a_valid_machine_builds(self) -> None:
        machine = self._machine()
        assert machine.schema_version == SCHEMA_VERSION
        assert machine.find("pump_de_bearing") is not None
        assert machine.find("vib_1") is not None  # id fallback
        assert machine.find("nope") is None

    def test_the_sensor_to_asset_link_resolves(self) -> None:
        """The join the whole package exists for."""
        machine = self._machine()
        sensor = machine.find("pump_de_bearing")
        assert isinstance(sensor, IOLinkSensor)
        point = machine.measurement_point(sensor.mounted_at or "")
        assert point is not None
        assert point.asset == "P101"

    def test_dangling_measurement_point_reference_names_the_culprit(self) -> None:
        with pytest.raises(ValidationError, match="unknown measurement point 'ghost'"):
            Machine(
                name="m",
                components=[IOLinkSensor(id="vib_1", mounted_at="ghost")],
            )

    def test_dangling_asset_reference_lists_what_is_known(self) -> None:
        with pytest.raises(ValidationError, match="Known assets: M101"):
            Machine(
                name="m",
                assets=[Motor(id="M101")],
                measurement_points=[MeasurementPoint(id="pt1", asset="P999")],
            )

    def test_duplicate_component_ids_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate component id"):
            Machine(name="m", components=[PLC(id="a"), PLC(id="a")])

    def test_duplicate_tags_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate component tag"):
            Machine(
                name="m",
                components=[PLC(id="a", tag="shared"), PLC(id="b", tag="shared")],
            )

    def test_two_sensors_on_one_port_is_a_wiring_error(self) -> None:
        with pytest.raises(ValidationError, match="both wired to port 1"):
            Machine(
                name="m",
                components=[
                    IOLinkMaster(id="master_1", port_count=8),
                    IOLinkSensor(id="vib_1", master="master_1", port=1),
                    IOLinkSensor(id="vib_2", master="master_1", port=1),
                ],
            )

    def test_a_port_beyond_the_master_s_capacity_is_caught_at_machine_level(self) -> None:
        with pytest.raises(ValidationError, match="which has only 4 ports"):
            Machine(
                name="m",
                components=[
                    IOLinkMaster(id="master_1", port_count=4),
                    IOLinkSensor(id="vib_1", master="master_1", port=5),
                ],
            )

    def test_sensors_and_masters_are_filterable(self) -> None:
        machine = self._machine()
        assert [s.id for s in machine.sensors()] == ["vib_1"]
        assert [m.id for m in machine.masters()] == ["master_1"]


class TestOtherComponents:
    def test_analog_sensor_span_needs_a_unit(self) -> None:
        with pytest.raises(ValidationError, match="without a unit"):
            AnalogSensor(id="pt1", scaled_range=ValueRange(low=0.0, high=16.0))

    def test_discrete_sensor_separates_device_and_circuit_polarity(self) -> None:
        sensor = DiscreteSensor(id="ps1", normally_closed=True, active_low=True)
        assert sensor.normally_closed and sensor.active_low

    def test_daq_nyquist(self) -> None:
        assert DaqDevice(id="daq1", sample_rate_hz=25000.0).nyquist_hz == 12500.0
        assert DaqDevice(id="daq1").nyquist_hz is None

    def test_edge_device_carries_what_it_forwards(self) -> None:
        assert EdgeDevice(id="edge1", upstream_of=["master_1"]).upstream_of == ["master_1"]

    def test_plc_io_channels_flatten(self) -> None:
        plc = PLC(id="plc1")
        assert plc.io_channels() == []


class TestReading:
    def test_readings_are_frozen(self) -> None:
        reading = Reading(name="v_rms", value=2.4, unit="mm/s")
        with pytest.raises(ValidationError):
            reading.value = 3.0  # type: ignore[misc]

    def test_bad_quality_reads_without_a_number(self) -> None:
        assert str(Reading(name="v_rms", quality=Quality.BAD)) == "v_rms=<bad>"

    def test_str_shows_unit_and_flags_non_good_quality(self) -> None:
        assert str(Reading(name="v_rms", value=2.4, unit="mm/s")) == "v_rms=2.4 mm/s"
        assert (
            str(Reading(name="v_rms", value=2.4, unit="mm/s", quality=Quality.UNCERTAIN))
            == "v_rms=2.4 mm/s [uncertain]"
        )
