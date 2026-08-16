# loopsheet — TODO

Progress tracker for [PLAN.md](PLAN.md). Phases 1–4 are the meaningful
deliverable; 5–7 build on a frozen core.

**Definition of done for every item:** `ruff check` clean, `mypy --strict`
clean, `pytest` green, and a test added or updated that would fail without the
change.

---

## Phase 0 — Research (in flight)

- [x] Survey local repo conventions (uv · hatchling · ruff · mypy strict · pytest)
- [x] Survey Python prior art — confirmed no existing package fills this seam
- [x] Choose a name, verify `loopsheet` free on PyPI and GitHub
- [x] Write PLAN.md and TODO.md
- [x] **VVB020 device facts** → [`docs/research/ifm-vvb020.md`](docs/research/ifm-vvb020.md)
- [x] **ifm master protocol facts** → [`docs/research/ifm-masters.md`](docs/research/ifm-masters.md)
- [x] Record every unconfirmed value as `UNVERIFIED` rather than guessing

### Blocked — needs an unrestricted network or an account

- [ ] **Obtain the VVB020 IODD.** This is the one hard blocker. IODDfinder now
      requires a login for zip downloads (401) and ifm.com is Akamai-blocked
      (403). Without it there are no bit offsets, no gradients, and no ISDU
      indices. Two routes:
  - [ ] IODDfinder with a free account — vendorId **310**, ioddId **8438**
        (status A) / **10375** (status B)
  - [ ] ifm interface-description PDFs (URLs pattern-derived, both 403 here):
        `ifm-0004E9-20200110-IODD11-en.pdf` / `ifm-000559-20201105-IODD11-en.pdf`
- [ ] Confirm the IoT Core `port[n]/mode` enum values at runtime via
      `getelementinfo` → `format.valuation.valuelist`
- [ ] Resolve the cycle-time unit conflict — AL1350 §9.1.6 says µs (0…132800),
      §9.2.8 says ms, for the *same* parameters. µs is almost certainly right
      (132800 µs = 132.8 ms = the IO-Link maximum). Verify on hardware.
- [ ] AL1590/AL1591 OPC UA specifics — endpoint, port, security policies, auth,
      and whether ifm implements OPC 30120 or a proprietary address space

---

## Phase 1 — Scaffold

- [ ] `uv init --lib`, src layout at `src/loopsheet/`
- [ ] `pyproject.toml` modelled on `../sonome/pyproject.toml`
  - [ ] hatchling build backend, `packages = ["src/loopsheet"]`
  - [ ] `requires-python = ">=3.11"`, Apache-2.0, Kovir Labs / Evan Gress
  - [ ] core deps: `pydantic>=2.9`, `pyyaml` — nothing else
  - [ ] optional extras: `mqtt` `async` `opcua` `enip` `iotcore` `modbus` `units` `aas`
  - [ ] `[dependency-groups] dev`: pytest, pytest-cov, ruff, mypy
  - [ ] ruff line-length 100, `select = [E,W,F,I,UP,B,SIM,C4,RUF]`
  - [ ] mypy `strict = true`, per-module `ignore_missing_imports` overrides
  - [ ] pytest `testpaths=["tests"]`, `addopts = "-ra --strict-markers"`
  - [ ] `[project.scripts] loopsheet = "loopsheet.cli:main"`
- [ ] `LICENSE` (Apache-2.0) and `NOTICE`
- [ ] `CLAUDE.md` in the house template — `## Commands` / `## Architecture` /
      invariants, including the **core-purity hard rule**
- [ ] `README.md`, `ROADMAP.md`, `CHANGELOG.md`, `.gitignore`
- [ ] `uv sync` succeeds; empty `pytest` run is green
- [ ] First commit

---

## Phase 2 — Core models + codec

**No imports beyond `pydantic` and the stdlib in any file in this phase.**

### models/
- [ ] `base.py` — `LoopsheetModel` base, `SCHEMA_VERSION`, `semantic_id` field
- [ ] `reading.py` — frozen `Reading(name, value, unit, timestamp, quality, source)`
- [ ] `channel.py` — `ChannelSpec` (unit, range, datatype, provenance metadata), `Signal`
- [ ] `asset.py` — `Motor` · `Pump` · `Gearbox` · `Bearing` · `Fan`, `MeasurementPoint`
- [ ] `site.py` — `Site` → `Area` → `Machine`, with `Machine.find(tag)`
- [ ] `sensor.py` — `IOLinkSensor` · `AnalogSensor` · `DiscreteSensor`
- [ ] `iolink.py` — `IOLinkMaster` · `Port` · `PortMode` · `ValidationMode`
- [ ] `controller.py` — `PLC` · `Chassis` · `IOModule` · `IOChannel` · `Tag`
- [ ] `daq.py` — `DaqDevice` · `EdgeDevice`
- [ ] `component.py` — `Component` union discriminated on `component_type`;
      export `TypeAdapter(Component)` publicly

### codec/
- [ ] `datatypes.py` — IO-Link `IntegerT` / `UIntegerT` / `BooleanT` / `Float32T`
- [ ] `processdata.py` — `ProcessDataItem`, `ProcessDataLayout` with a
      `model_validator` rejecting overlapping bit ranges
- [ ] `decode.py` — `decode(raw: bytes, layout) -> dict[str, Reading]`,
      MSB-first per IO-Link convention, gradient + offset applied
- [ ] `scaling.py` — analog raw counts ⇄ engineering units (4-20 mA, 0-10 V),
      including under/over-range and broken-wire handling

### tests
- [ ] Decoder unit tests **written before** `decode.py` — bit alignment across
      byte boundaries, signed values, booleans, gradient/offset arithmetic
- [ ] Overlapping-bit-range layout raises
- [ ] Truncated / oversized `raw` raises a clear error
- [ ] `TypeAdapter(Component)` round-trips every component subtype
- [ ] JSON Schema generation succeeds for the component union

---

## Phase 3 — Catalog

- [ ] `schema.py` — `CatalogEntry` covering identity, IO-Link block,
      **`variants`**, channels, ISDU parameters, electrical, mechanical
- [ ] **`DeviceVariant`** model — device ID, COM mode, min cycle time, IODD ref,
      `has_pdout`, optional `ProcessDataLayout`. A part number maps to *many*
      (VVB020 status A = 1257 / status B = 1369)
- [ ] **`supported_bindings`** on master entries, and a validator that rejects a
      binding the part cannot serve, naming what it *does* support
- [ ] `registry.py` — `get()` / `list()` via `importlib.resources`;
      never `__file__`-relative paths
- [ ] Entry-point group `loopsheet.catalog` so third parties can ship vendor
      packs; `list()` must not import vendor modules
- [ ] `data/ifm/VVB020.yaml` — verified values only; `process_data: null` with
      `# UNVERIFIED` until the IODD lands
- [ ] `data/ifm/AL1350.yaml`, `AL1352.yaml` — IoT Core + MQTT, **no OPC UA**
- [ ] `data/ifm/AL1320.yaml`, `AL1322.yaml` — EtherNet/IP + IoT Core
      (MQTT on AL1320 FW 3.1.x only, not AL1322 FW 2.3.x)
- [ ] Test: every shipped catalog file validates against `CatalogEntry`
- [ ] Test: `catalog.get("ifm:VVB020")` returns both variants with distinct
      device IDs
- [ ] Test: attaching an OPC UA binding to an AL1350 raises with a message
      naming the supported bindings
- [ ] Test: `catalog.list()` performs no vendor-module imports
- [ ] Test: a variant with `process_data: null` raises a clear
      "layout unavailable, IODD required" error on decode — never a silent
      wrong answer
- [ ] **Golden decode test** — known VVB020 PDIn bytes → expected engineering
      values, hand-computed from the IODD gradient/offset
      *(**blocked** on obtaining the IODD — see Phase 0)*

---

## Phase 4 — Loader + example

- [ ] `io/loader.py` — YAML/JSON → `Machine`, resolving `part:` catalog refs
      and `master`/`port`/`mounted_at` cross-references
- [ ] Clear, located error messages on unresolvable refs and unknown part numbers
- [ ] `io/dump.py` — `Machine` → YAML/JSON
- [ ] `examples/filler_line_3.yaml` — pump + motor + measurement point +
      AL1350 + VVB020 + PLC + MQTT and OPC UA bindings
- [ ] Test: lossless round-trip of the example
- [ ] Test: `m.find("pump_de_bearing").mounted_at.asset.id == "P101"`
- [ ] **Core-purity test** — `models` / `codec` / `bindings` / `io` import with
      every optional dependency sabotaged out of `sys.modules`

---

## Phase 5 — Bindings + exporters

- [ ] `bindings/base.py` — `Binding` union discriminated on `protocol`,
      referencing components by tag rather than containment
- [ ] `bindings/mqtt.py` — broker, port, topic, QoS, payload format.
      **Model ifm reality:** the topic is the path of an `mqtt://host:port/topic`
      subscribe callback; there is no ifm-defined hierarchy; FW 3.1.x has
      **no credentials, no TLS, no client-id**; wildcards unsupported; max 10
      connections; trigger is either `timer[1..2]` interval (**500 ms min**) or
      a port/device event
- [ ] `bindings/iotcore.py` — the ifm IoT Core binding is its own protocol:
      base URL, `{code, cid, adr, data, auth}` envelope, optional Base64 auth
- [ ] `bindings/opcua.py` — endpoint, security policy + mode, auth, namespace
      URI, NodeId template. Mark AL159x specifics `UNVERIFIED`; do **not**
      default the port to 4840 as though it were confirmed for ifm
- [ ] `bindings/enip.py` — assembly instances (**100/101/102 in, 150/151 out,
      199 config**), connection sizes derived from process-data length `n`,
      per-port byte offsets (8-port PD from byte 190 at instance 100, stride
      `n`), PQI **bit 2 = invalid data**, ISDU via **class 0x80, instance 0x01,
      attribute = port**, services **0x4B read / 0x4C write**, RPI min 1 ms
- [ ] `bindings/modbus.py` — stub (AL1342/AL1343)
- [ ] `export/topicmap.py` · `nodemap.py` · `tagmap.py`
- [ ] `model_validator` cross-checks — e.g. Sparkplug payload requires
      `group_id` + `edge_node_id`; EtherNet/IP binding requires assembly instance
- [ ] Tests for each emitter against the example machine

---

## Phase 6 — Adapters (optional extras)

- [ ] Shared lazy-import helper raising `ImportError("install loopsheet[x]")`
- [ ] `adapters/iotcore.py` — ifm IoT Core client *(first: shortest path to real
      bytes)*. PDIn arrives as an **uppercase hex string**; `getdatamulti` and
      event payloads key the value under **`data`**, plain `getdata` under
      **`value`** — the shapes genuinely differ, cover both. Handle code **530**
      (invalid process data) and **503** (wrong port mode / no device) as typed
      errors, not exceptions-with-strings
- [ ] `adapters/iotcore.py` — variant confirmation: read
      `.../iolinkdevice/deviceid` and check it against the pinned catalog variant
- [ ] `adapters/mqtt.py` — publish decoded readings per the binding config
- [ ] `adapters/enip.py` — `pycomm3` `CIPDriver.generic_message()` explicit messaging
- [ ] `adapters/opcua.py` — `asyncua` client reading mapped NodeIds
- [ ] Tests use recorded fixtures / fakes — no network in the test suite

---

## Phase 7 — CLI

- [ ] `loopsheet validate <file>` — exit 0/1 with located errors
- [ ] `loopsheet show <file>` — render the machine tree
- [ ] `loopsheet decode <part> <hex-bytes>` — decode PDIn from the catalog
- [ ] `loopsheet export --format topics|nodes|tags <file>`
- [ ] `loopsheet catalog list|show <part>`
- [ ] CLI stays thin — parse args, call the core, print

---

## Later / stretch

- [ ] IODD XML ingestion behind an `[iodd]` extra (`xsdata` from the official
      XSDs; study `IOLink.NET` for the PD-interpretation logic)
- [ ] IODDfinder REST client to fetch IODDs on demand into a user cache dir
- [ ] AAS export — Digital Nameplate (IDTA 02006) + Technical Data (IDTA 02003)
- [ ] OPC UA nodeset generation / server instantiation from a `Machine`
      *(expect asyncua importer friction — treat as v2)*
- [ ] Sparkplug B metric definitions derived from channel metadata
- [ ] Modbus and Siemens S7 adapters
- [ ] Publish to PyPI
