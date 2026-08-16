# loopsheet — implementation plan

> Digital-twin data models for industrial machines: sensors, IO-Link masters,
> PLCs, and DAQ devices, with their MQTT / OPC UA / EtherNet-IP configuration.
>
> Status: pre-scaffold. Progress tracked in [TODO.md](TODO.md).

---

## 1. Context

Describe a machine and everything bolted to it *once*, as typed data, and reuse
that description everywhere — validation, protocol configuration, decoding raw
process data into engineering units, and eventually AAS / OPC UA export.

The proof case is an **ifm VVB020** vibration sensor on an ifm IO-Link master,
with its MQTT, OPC UA, and EtherNet/IP communication configuration captured
alongside the device itself.

### Why this package should exist

A survey of PyPI and GitHub (2026-08) found no Python package that does this.
The closest neighbours each cover one slice and none covers the join:

| Project | Covers | Gap |
|---|---|---|
| `iodd-parser` (2★, Feb 2026) | IODD XML → dataclasses | Parse-only; no process-data decoding, no protocol config |
| `basyx-python-sdk` | AAS serialization | Verbose metamodel, poor authoring ergonomics |
| `pycomm3` / `asyncua` / `paho-mqtt` | Wire protocols | Zero device semantics |
| `pymeasure` / `qcodes` | Catalog + descriptor patterns | Wrong domain (lab instruments) |

Non-Python prior art worth reading rather than depending on:
[`IOLink.NET`](https://github.com/domdeger/IOLink.NET) (C#, MIT) is the most
complete open implementation of IODD parsing **plus** process-data
interpretation, and is safe to study for the decoder design.

**The differentiator is the seam**: a pydantic model that carries IO-Link
device semantics *and* the protocol binding config *and* a part-number catalog.

### The name

An ISA-5.4 **loop sheet** is the drawing that follows one instrument end to
end — sensor, tag, wiring, I/O channel, controller, engineering-unit scaling.
That is precisely the join this package models.

### Decisions locked

| Question | Answer |
|---|---|
| Runtime scope | Pure models in core; live protocol clients behind extras |
| Device definitions | Data-driven YAML catalog + generic classes; no class-per-part-number |
| Standards posture | Own clean schema, standards-informed; AAS / OPC UA as later exporters |
| Authoring format | YAML files, loaded and validated |
| Device kinds in v1 | IO-Link devices + masters, discrete & analog I/O, PLC + I/O tree, DAQ / edge devices, rotating assets |
| Live values | Config plus a lightweight decoded `Reading` type — no history, no storage |
| Python floor | `>=3.11` (not the `>=3.14` house default — this package has an external audience, and most industrial Python in the field is 3.11/3.12) |
| License | Apache-2.0, Kovir Labs, Evan Gress |

### Research findings that shaped the design

Primary-source notes live in [`docs/research/`](docs/research/) — read them
before writing any catalog file.

- [`ifm-masters.md`](docs/research/ifm-masters.md) — IoT Core JSON API, MQTT,
  OPC UA, EtherNet/IP, port configuration
- [`ifm-vvb020.md`](docs/research/ifm-vvb020.md) — the sensor itself

Three findings changed the model:

**1. No single ifm master speaks MQTT *and* OPC UA *and* EtherNet/IP.**
AL1350/AL1352 (IoT) do MQTT + IoT Core but have **no OPC UA** — confirmed by
grep, zero hits across the full manuals. EtherNet/IP is AL1320/AL1321/AL1322/
AL1323. AL1342/AL1343 are **Modbus TCP**, not EtherNet/IP. OPC UA appears on
the SolutionBlock **AL1590/AL1591**. MQTT is also firmware-dependent — present
on AL1320/AL1321 at FW 3.1.x, absent on AL1322/AL1323 at FW 2.3.x.
→ the catalog needs **`supported_bindings`** per part, and the loader must
reject a binding the hardware cannot serve.

**2. A part number is not one IO-Link identity.** The VVB020 ships in two
software statuses distinguished at the wire level by Device ID — **1257 (status
A, COM2, 11.6 ms)** and **1369 (status B, COM3, 3.6 ms)** — with different
parameter sets, different process data, and PDOut only on status B.
→ `CatalogEntry` needs a **`variants`** list keyed by device ID.

**3. The VVB020 process-data bit layout could not be obtained.** IODDfinder now
requires a login for zip downloads and ifm.com is Akamai-blocked. Vendor ID
(310), device IDs, COM modes, cycle times, ranges, units, filter bands, pinout
and electricals are all verified — **the bit offsets and gradients are not**.
→ `process_data` ships as `null` with `# UNVERIFIED` markers until the IODD is
in hand, and the golden-decode test stays unwritten. See
[Phase 0 in TODO.md](TODO.md).

`C:\Users\gress\Github\machine-base` was the seed for this idea. It is empty
with no commits; `loopsheet` supersedes it.

---

## 2. Architecture

Layered, dependency direction points **inward**. Pure functions everywhere
except `adapters/` and `io/`.

```
                     YAML machine file
                            │
                     io/loader.py          I/O  parse + validate + resolve refs
                            │
   ┌────────────────────────┼────────────────────────┐
   ▼                        ▼                        ▼
models/                 catalog/                bindings/
  asset tree              part-number data        MQTT / OPC UA /
  components              + registry              EtherNet-IP config
  channels                                        (pure config, no clients)
   │                        │                        │
   └────────────┬───────────┴────────────┬───────────┘
                ▼                        ▼
            codec/                   export/
              raw bytes ⇄ Reading      emit topic maps, node maps,
              (pure, no I/O)           tag maps, AAS (later)
                                          │
                                          ▼
                                     adapters/          ← the ONLY socket I/O
                                       mqtt · opcua · enip · iotcore
                                       (optional extras, lazy-imported)
```

**Hard rule.** `models/`, `catalog/`, `codec/`, and `bindings/` import nothing
but `pydantic` and the stdlib. If a core module wants `paho` or `asyncua`, the
abstraction is in the wrong place — stop and reconsider.

### Repository layout

```
loopsheet/
  pyproject.toml            hatchling + uv; mirrors ../sonome/pyproject.toml
  PLAN.md  TODO.md  CLAUDE.md  README.md  ROADMAP.md  CHANGELOG.md
  LICENSE  NOTICE
  src/loopsheet/
    __init__.py             public API: load_machine, Machine, Reading, catalog
    models/
      base.py               LoopsheetModel base, SCHEMA_VERSION, semantic_id
      site.py               Site → Area → Machine
      asset.py              Motor · Pump · Gearbox · Bearing · Fan, MeasurementPoint
      component.py          Component union, discriminated on `component_type`
      sensor.py             IOLinkSensor · AnalogSensor · DiscreteSensor
      iolink.py             IOLinkMaster · Port · PortMode · ValidationMode
      controller.py         PLC · Chassis · IOModule · IOChannel · Tag
      daq.py                DaqDevice · EdgeDevice
      channel.py            ChannelSpec · Signal (the loop-sheet row)
      reading.py            Reading (frozen)
    codec/
      datatypes.py          IO-Link IntegerT / UIntegerT / BooleanT / Float32T
      processdata.py        ProcessDataItem · ProcessDataLayout
      decode.py             decode(raw: bytes, layout) → dict[str, Reading]
      scaling.py            analog raw counts ⇄ engineering units
    bindings/
      base.py               Binding union, discriminated on `protocol`
      mqtt.py               broker, TLS, topic template, QoS, payload format
      opcua.py              endpoint, security policy/mode, ns URI, NodeId template
      enip.py               assemblies, sizes, RPI, per-port byte offsets
      modbus.py             stub for later
    catalog/
      registry.py           get() · list() · entry-point discovery
      schema.py             CatalogEntry pydantic model
      data/ifm/VVB020.yaml  ← the proof case
      data/ifm/AL1350.yaml  AL1352.yaml  AL1322.yaml
    io/
      loader.py             YAML/JSON → Machine, catalog reference resolution
      dump.py               Machine → YAML/JSON, round-trips losslessly
    export/
      topicmap.py           → MQTT topic ↔ channel map
      nodemap.py            → OPC UA NodeId map
      tagmap.py             → PLC tag / EtherNet-IP offset map
    adapters/               optional, lazy-imported, clear ImportError on miss
      mqtt.py  opcua.py  enip.py  iotcore.py
    cli.py                  thin: validate · show · decode · export
  examples/filler_line_3.yaml
  tests/
```

---

## 3. Key model decisions

**1. Components and bindings are separate.** An `IOLinkSensor` does not know
that MQTT exists. `Binding` is its own discriminated union, linked to
components by `tag` reference. This separation is what lets every protocol
library stay genuinely optional.

**2. Discriminated unions are the spine.** `Field(discriminator=...)` on
`component_type` and `protocol`. O(1) dispatch, readable validation errors, and
a clean `oneOf` + `discriminator` JSON Schema. `TypeAdapter(Component)` is
public so callers can validate raw dicts and generate schema.

**3. `MeasurementPoint` is the sensor ↔ asset link.** A vibration reading has
to be *about* something — "pump P-101, drive-end bearing, radial-horizontal".
The sensor mounts at a measurement point; the point belongs to a mechanical
asset. Without this the model is a wiring list, not a twin.

**4. Units are strings in core.** `unit: "mm/s"`, validated against a known
set. `pint` raises the Python floor and drags in flexcache / flexparser /
platformdirs, so it lives behind a `[units]` extra that offers
`Annotated[Quantity, PydanticPintQuantity(...)]` fields.

**5. Carry provenance now, cash it in later.** Every channel gets `index`,
`subindex`, `bit_offset`, `bit_length`, `semantic_id`. That metadata is what
makes AAS export, OPC UA NodeId generation, and Sparkplug metric naming nearly
free later.

**6. `SCHEMA_VERSION` on the serialized contract.** Machine YAML files are real
user data. Additive changes bump minor; any rename or removal bumps major and
needs a migration note.

**7. Capability, not assumption.** Every master part declares
`supported_bindings`; a `Machine` that attaches an OPC UA binding to an AL1350
must fail validation with a message naming the part and what it does support.
This is the finding from §1 above turned into a guard rail — it is the single
most useful thing this package can do for someone specifying hardware.

**8. Variants are first-class.** `catalog.get("ifm:VVB020")` returns an entry
with two variants; the machine YAML pins one (`variant: status_b`), and the
`iotcore` adapter can confirm the pin at runtime by reading
`.../iolinkdevice/deviceid`. Silently guessing a variant would decode wrong.

### Catalog entry shape

Reflecting findings 2 and 3 — verified values populated, unverified explicitly
`null`. Full provenance in [`docs/research/ifm-vvb020.md`](docs/research/ifm-vvb020.md).

```yaml
# src/loopsheet/catalog/data/ifm/VVB020.yaml
schema_version: 1
part_number: VVB020
vendor: ifm
component_type: iolink_sensor
description: Single-axis MEMS vibration sensor for condition monitoring

iolink:
  vendor_id: 310                  # verified — IODDfinder
  revision: "1.1"
  sio_supported: true
  port_class: A
  profiles: [blob, common_id, function_measurement]

variants:                         # a part number is not one identity
  - id: status_a
    device_id: 1257               # 0x04E9, verified
    com_mode: COM2
    min_cycle_time_ms: 11.6
    iodd: ifm-0004E9-20200110-IODD1.1
    has_pdout: false
    pdin_length_bits: null        # UNVERIFIED
    process_data: null            # UNVERIFIED — needs the IODD
  - id: status_b
    device_id: 1369               # 0x0559, verified
    com_mode: COM3
    min_cycle_time_ms: 3.6
    iodd: ifm-000559-20201105-IODD1.1
    has_pdout: true
    pdin_length_bits: null        # UNVERIFIED
    process_data: null            # UNVERIFIED — needs the IODD

channels:                         # semantics are known even where bits are not
  - {name: v_rms,       unit: mm/s, range: [0, 45],      band_hz: [10, 1000]}
  - {name: a_peak,      unit: m/s², range: [0, 490.3],   band_hz: [10, 5000]}
  - {name: a_rms,       unit: m/s², range: [0, 490.3],   band_hz: [10, 5000]}
  - {name: crest,       unit: null, range: [1, 50]}
  - {name: temperature, unit: °C,   range: [-30, 80], resolution: 0.1}

parameters: []                    # UNVERIFIED — no ISDU index found for this part

electrical:
  supply_voltage_v: {min: 18, max: 30}
  current_consumption_ma_max: 50
  digital_outputs: 2
  analog_output: null             # VVB020 has NO 4-20 mA output
  connector: {type: M12, coding: A}
  pinout:
    1: {function: L+,   colour: BN}
    2: {function: OUT2, colour: WH}
    3: {function: L-,   colour: BU}
    4: {function: OUT1_OR_IOLINK, colour: BK}
```

> **Never fabricate precision.** Every numeric value in a catalog file must
> come from the IODD or the datasheet. Anything unconfirmed ships as `null`
> with an explicit `# UNVERIFIED` marker — a wrong bit offset silently decodes
> garbage, which is worse than a missing one. This is the `sonome` rule applied
> to a device catalog.

### Authoring target

```yaml
# examples/filler_line_3.yaml
schema_version: 1
site: {name: Plant 2, area: Filling}
machine:
  name: filler_line_3
  assets:
    - {id: P101, kind: pump, driver: M101}
    - {id: M101, kind: motor, rated_rpm: 1780, rated_kw: 15}
  measurement_points:
    - {id: P101_DE_H, asset: P101, location: drive_end, axis: radial_horizontal}
  controllers:
    - {part: 5069-L320ER, vendor: rockwell, ip: 10.0.1.10}
  components:
    - {part: ifm:AL1350, id: master_1, ip: 10.0.1.21}
    - {part: ifm:VVB020, id: vib_1, tag: pump_de_bearing,
       master: master_1, port: 1, mounted_at: P101_DE_H}
  bindings:
    - {protocol: mqtt, target: vib_1, broker: 10.0.1.5,
       topic: "plant2/filling/line3/{tag}/{channel}", qos: 1}
    - {protocol: opcua, target: vib_1, endpoint: "opc.tcp://10.0.1.21:4840"}
```

```python
from loopsheet import load_machine
from loopsheet.codec import decode

m = load_machine("examples/filler_line_3.yaml")
s = m.find("pump_de_bearing")

s.part_number                  # 'VVB020'
s.channels["v_rms"].unit       # 'mm/s'
s.mounted_at.asset.id          # 'P101'
m.topic_map()["pump_de_bearing/v_rms"]

decode(raw_pdin_bytes, s.process_data)   # {'v_rms': Reading(2.4, 'mm/s', ...)}
```

---

## 4. Dependencies

Core: **`pydantic>=2.9`** and **`pyyaml`**. Nothing else.

```toml
[project.optional-dependencies]
mqtt    = ["paho-mqtt>=2.1"]     # EPL-2.0 OR BSD-3-Clause
async   = ["aiomqtt>=2.4"]       # async wrapper over paho
opcua   = ["asyncua>=1.1"]       # LGPL-3.0 — optional on purpose
enip    = ["pycomm3>=1.2"]       # MIT; generic CIP explicit messaging
iotcore = ["httpx>=0.27"]        # ifm IoT Core REST / JSON-RPC
modbus  = ["pymodbus>=3.7"]      # BSD-3-Clause
units   = ["pint>=0.24", "pydantic-pint>=0.5"]
aas     = ["basyx-python-sdk>=2.0"]
```

**Rejected deliberately:** `cpppo` (GPLv3 plus a licensing-enforcement hard
dependency), `python-opcua`/`opcua` (deprecated by its own maintainers),
`iolink` (dead, Windows-only, single USB master), `ioddcombase` (proprietary),
`pyi40aas` (superseded by basyx), `tahu` on PyPI (abandoned 2022).

`asyncua` being LGPL-3.0 is the sharpest reason the extras split matters:
keeping it out of core and never importing it from core keeps the Apache-2.0
grant clean.

---

## 5. Build order

Phases are tracked as checkboxes in [TODO.md](TODO.md).

1. **Scaffold** — `uv init --lib`, src layout, tooling config, license, docs.
2. **Core models + codec** — pydantic only. Tests first for the bit-slicing
   decoder; it is the piece most likely to be subtly wrong.
3. **Catalog** — schema, `importlib.resources` loader, entry-point group,
   VVB020 + AL1350 entries.
4. **Loader + example** — YAML → `Machine`, ref resolution, round-trip test.
5. **Bindings + exporters** — three protocol config models, three map emitters.
   Still zero network code.
6. **Adapters behind extras** — `iotcore` first (the shortest path to real
   VVB020 bytes), then `mqtt`, `enip`, `opcua`.
7. **CLI** — `loopsheet validate | show | decode | export`.

Phases 1–4 are the meaningful deliverable; 5–7 build on a frozen core.

---

## 6. Verification

**Definition of done for any change** (the `sonome` §4 standard):
`ruff check` clean, `mypy --strict` clean, tests green, and a test added or
updated that would fail without the change.

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src/loopsheet
uv run pytest -q
```

Tests that specifically matter:

- **Golden decode** — a known VVB020 PDIn byte string decodes to expected
  engineering values, hand-computed from the IODD gradient/offset. This is the
  test that proves the whole idea works.
- **Overlap validation** — a `ProcessDataLayout` with colliding bit ranges must
  raise.
- **Round-trip** — `examples/filler_line_3.yaml` → `Machine` → YAML is
  equivalent modulo key order.
- **Catalog integrity** — every shipped catalog file validates against
  `CatalogEntry`; `catalog.list()` returns part numbers without importing
  vendor modules.
- **Core purity** — `models` / `codec` / `bindings` import cleanly with every
  optional dependency sabotaged out of `sys.modules`.

End-to-end, once hardware is available: point the `iotcore` adapter at a real
AL1350, read port 1 PDIn, decode it, and compare against the value ifm moneo
or LR Device shows for the same sensor.
