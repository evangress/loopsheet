# loopsheet — roadmap

Where this is going, at a coarser grain than [TODO.md](TODO.md) and a longer
horizon than [PLAN.md](PLAN.md).

## 0.1 — the modelling core

The deliverable is "describe a machine in YAML, get a validated object graph
back, and decode process bytes with it." Phases 1–4 of [TODO.md](TODO.md):
scaffold, models + codec, catalog, loader.

Ships when `examples/filler_line_3.yaml` round-trips losslessly and the
component union generates clean JSON Schema.

## 0.2 — bindings and exporters

Protocol *configuration* as data — MQTT, ifm IoT Core, OPC UA, EtherNet/IP,
Modbus stub — plus the emitters that turn a machine into a topic map, a NodeId
map, and a PLC tag map. Still zero network code.

The capability guard rail lands here in full: a binding a part cannot serve
fails validation naming what it does support.

## 0.3 — adapters

Thin optional clients behind extras, in order of value: `iotcore` first (the
shortest path to real bytes off a real sensor), then `mqtt`, `enip`, `opcua`.
Recorded fixtures only in the test suite; no network in CI.

## 0.4 — CLI

`loopsheet validate | show | decode | export | catalog`. Thin by construction:
parse args, call the core, print.

## 1.0 — a frozen contract

1.0 means `SCHEMA_VERSION` is a promise. Prerequisites:

- the VVB020 golden-decode test passes against a real IODD (see below)
- a second vendor's parts in the catalog, proving the schema isn't ifm-shaped
- at least one machine file authored by someone who didn't write the code

## Beyond

- **IODD ingestion** behind an `[iodd]` extra — `xsdata` off the official XSDs;
  [`IOLink.NET`](https://github.com/domdeger/IOLink.NET) is the reference
  implementation to study for process-data interpretation.
- **IODDfinder client** to fetch IODDs on demand into a user cache dir.
- **AAS export** — Digital Nameplate (IDTA 02006) and Technical Data
  (IDTA 02003) submodels, built from provenance metadata already carried on
  every channel.
- **OPC UA nodeset generation** from a `Machine` — expect importer friction;
  treat as v2.
- **Sparkplug B** metric definitions derived from channel metadata.
- **More protocols** — Modbus, Siemens S7.
- **PyPI release.**

## The one open blocker

Everything device-specific downstream of decoding waits on the **VVB020 IODD**.
IODDfinder requires a login for zip downloads; ifm.com is Akamai-blocked.
Vendor ID, device IDs, COM modes, cycle times, ranges, units, filter bands,
pinout, and electricals are all verified — bit offsets and gradients are not.

Until it lands, `process_data` is `null`, decode raises rather than guesses, and
the golden-decode test stays unwritten. See Phase 0 in [TODO.md](TODO.md) and
[`docs/research/ifm-vvb020.md`](docs/research/ifm-vvb020.md).

## Non-goals

Historian or time-series storage · an OPC UA *server* · a protocol stack of our
own · a GUI configurator · class-per-part-number device drivers · guessing a
device value we cannot trace to a primary source.
