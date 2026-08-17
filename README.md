# loopsheet

**Digital-twin data models for industrial machines** — sensors, IO-Link masters,
PLCs, and DAQ devices, together with their MQTT / OPC UA / EtherNet-IP
configuration.

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)](TODO.md)

> An ISA-5.4 *loop sheet* is the drawing that follows one instrument end to end:
> sensor, tag, wiring, I/O channel, controller, engineering-unit scaling.
> That join is what this package models.

---

## Why

Describe a machine and everything bolted to it **once**, as typed data, and
reuse that description everywhere:

- **validation** — reject an OPC UA binding on a master that has no OPC UA
- **protocol configuration** — emit topic maps, NodeId maps, PLC tag maps
- **decoding** — turn raw IO-Link process bytes into engineering units
- **export** — AAS and OPC UA nodesets, later, nearly free from the provenance
  metadata already carried on every channel

No existing Python package covers the join. `iodd-parser` parses IODD XML but
decodes nothing; `basyx-python-sdk` serializes AAS with punishing authoring
ergonomics; `pycomm3` / `asyncua` / `paho-mqtt` speak wire protocols with zero
device semantics. loopsheet is the seam between them.

## Status

**Pre-alpha, not on PyPI yet.** Progress is tracked phase by phase in
[TODO.md](TODO.md); the design rationale is in [PLAN.md](PLAN.md).

One honest caveat up front: the proof-case sensor's **process-data bit layout is
not yet verified**. IODDfinder now requires a login and ifm.com blocks
automated access, so `process_data` ships as `null` marked `# UNVERIFIED`
rather than as a plausible guess. Decoding against a missing layout raises a
clear error. See [`docs/research/ifm-vvb020.md`](docs/research/ifm-vvb020.md).

## Install

```bash
pip install loopsheet                       # core: pydantic + pyyaml, nothing else
pip install "loopsheet[mqtt]"               # + paho-mqtt
pip install "loopsheet[iotcore]"            # + httpx, for ifm IoT Core
pip install "loopsheet[opcua]"              # + asyncua (LGPL-3.0)
```

Core installs two dependencies. Every wire protocol is an optional extra,
lazy-imported from `loopsheet.adapters` and never from the model layer.

## Use

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
  components:
    - {part: ifm:AL1350, id: master_1, ip: 10.0.1.21}
    - {part: ifm:VVB020, id: vib_1, tag: pump_de_bearing,
       master: master_1, port: 1, mounted_at: P101_DE_H}
  bindings:
    - {protocol: mqtt, target: vib_1, broker: 10.0.1.5,
       topic: "plant2/filling/line3/{tag}/{channel}", qos: 1}
```

```python
from loopsheet import load_machine
from loopsheet.codec import decode

m = load_machine("examples/filler_line_3.yaml")
s = m.find("pump_de_bearing")

s.part_number  # 'VVB020'
s.channels["v_rms"].unit  # 'mm/s'
s.mounted_at.asset.id  # 'P101'
m.topic_map()["pump_de_bearing/v_rms"]

decode(raw_pdin_bytes, s.process_data)  # {'v_rms': Reading(2.4, 'mm/s', ...)}
```

## Design rules

Three rules explain most of the code:

1. **Core purity.** `models` / `codec` / `bindings` / `catalog` import nothing
   but `pydantic` and the stdlib. This keeps modelling driver-free and keeps
   LGPL `asyncua` out of the Apache-2.0 grant.
2. **Capability, not assumption.** Parts declare `supported_bindings`. Attaching
   a protocol the hardware cannot serve fails validation, with a message naming
   what it *does* support.
3. **Never fabricate precision.** Unverified device values are `null` with an
   `# UNVERIFIED` marker and a source note in `docs/research/`. A wrong bit
   offset silently decodes garbage; a missing one just refuses.

Full guidance in [CLAUDE.md](CLAUDE.md).

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy src/loopsheet
```

Definition of done: `ruff` clean, `mypy --strict` clean, tests green, plus a
test that would fail without the change.

## License

Apache-2.0 · Kovir Labs · Evan Gress. See [LICENSE](LICENSE) and
[NOTICE](NOTICE). Part numbers and trademarks belong to their owners and are
used for identification only; no vendor IODD, EDS, or GSD file is vendored here.
