# CLAUDE.md — loopsheet

> Guidance for Claude Code (and any human) working in this repository.
> Read this first. It encodes *how* we build here, not just *what* we build.

loopsheet models industrial machines as typed data: the mechanical asset, the
sensors bolted to it, the IO-Link master or PLC they land on, and the MQTT /
OPC UA / EtherNet-IP configuration that carries their values off the machine.
Describe it once, reuse it for validation, protocol config, decoding raw
process data into engineering units, and later AAS / OPC UA export.

An ISA-5.4 **loop sheet** is the drawing that follows one instrument end to end
— sensor, tag, wiring, I/O channel, controller, engineering-unit scaling. That
join is the product.

Planning docs: [PLAN.md](PLAN.md) · progress: [TODO.md](TODO.md) · primary
sources: [`docs/research/`](docs/research/).

---

## 1. What loopsheet is (and is not)

- **Is:** a pydantic model layer plus a pure decoder and a part-number catalog.
  YAML in → a validated `Machine` out; raw process bytes in → `Reading`s out.
- **Is not:** a SCADA system, a historian, a protocol stack, or an OPC UA
  server. There is no storage and no history. Live protocol clients exist only
  as thin optional adapters over other people's libraries.
- **Hard rule:** if a device value is not traceable to an IODD, datasheet, or
  manual, it ships as `null` with an `# UNVERIFIED` comment. A wrong bit offset
  silently decodes garbage, which is worse than a missing one.

---

## 2. Architecture

Layered; **dependency direction points inward**. Pure functions everywhere
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

### The core-purity hard rule

**`models/`, `codec/`, `bindings/`, and `catalog/` import nothing but
`pydantic`, `pyyaml`, and the stdlib.** Not `paho`, not `asyncua`, not `httpx`,
not `pint` — not even guarded by a `try`. If a core module wants a protocol
library, the abstraction is in the wrong place: stop and reconsider.

`pyyaml` is in that list because it is a *core* dependency, not an extra: the
catalog is YAML files, and `catalog/registry.py` has to read them. `models/`
and `codec/` still import neither — they take parsed data. The rule that
matters is that **nothing behind an optional extra is ever imported from
core**, and that is what the test enforces.

Two reasons this is load-bearing:

1. `asyncua` is **LGPL-3.0**. Never importing it from core keeps loopsheet's
   Apache-2.0 grant clean.
2. The whole value proposition is that you can model a machine on a laptop with
   no drivers installed.

`tests/test_core_purity.py` enforces it by sabotaging every optional dependency
out of `sys.modules` and importing the core. Keep that test passing.

---

## 3. Coding principles

Each has a concrete meaning *in this codebase*.

**Components and bindings are separate.** An `IOLinkSensor` does not know that
MQTT exists. `Binding` is its own discriminated union, linked to components by
`tag` reference, never by containment. This separation is exactly what lets
every protocol library stay optional.

**Discriminated unions are the spine.** `Field(discriminator=...)` on
`component_type` and on `protocol`. O(1) dispatch, readable validation errors,
clean `oneOf` + `discriminator` JSON Schema. `TypeAdapter(Component)` is public
so callers can validate raw dicts and generate schema.

**Capability, not assumption.** Every master part declares
`supported_bindings`. A `Machine` that attaches an OPC UA binding to an AL1350
must fail validation with a message naming the part *and what it does support*.
No single ifm master speaks MQTT and OPC UA and EtherNet/IP — see
[`docs/research/ifm-masters.md`](docs/research/ifm-masters.md). This guard rail
is the single most useful thing the package does for someone specifying
hardware.

**Variants are first-class.** A part number is not one IO-Link identity. The
VVB020 ships as status A (device ID 1257, COM2, 11.6 ms) and status B (1369,
COM3, 3.6 ms), with different parameter sets and process data. Machine YAML
pins a variant; the `iotcore` adapter can confirm the pin against
`.../iolinkdevice/deviceid`. Silently guessing a variant decodes wrong.

**`MeasurementPoint` is the sensor ↔ asset link.** A vibration reading has to be
*about* something — "pump P-101, drive-end bearing, radial-horizontal". Without
it the model is a wiring list, not a twin.

**Never fabricate precision.** Every numeric value in a catalog file comes from
the IODD, datasheet, or manual, and `docs/research/` records where. Unconfirmed
values are `null` + `# UNVERIFIED`. Decoding against a missing layout raises
"layout unavailable, IODD required" — never a silent wrong answer.

**Units are strings in core.** `unit: "mm/s"`, validated against a known set.
`pint` drags in flexcache / flexparser / platformdirs, so it lives behind the
`[units]` extra.

**Carry provenance now, cash it in later.** Every channel keeps `index`,
`subindex`, `bit_offset`, `bit_length`, `semantic_id`. That metadata is what
makes AAS export, OPC UA NodeId generation, and Sparkplug metric naming nearly
free later.

**Stable data contracts.** Machine YAML files are real user data. Carry
`SCHEMA_VERSION`. Additive changes bump minor; any rename or removal bumps major
and needs a migration note in CHANGELOG.md. Never silently change a field's
meaning or units.

**Fail loud in the small, resilient in the large.** Loading one machine file
raises on bad input with a *located* message (which file, which component,
which field). A batch validate reports every file's errors rather than dying on
the first.

**Explicit over implicit.** Full type hints on every public function. Real units
in field names or descriptions (`_ms`, `_hz`, `_v`). No magic numbers — bit
widths, assembly instances, and default cycle times are named constants with a
comment citing the source.

**YAGNI.** No class-per-part-number: devices are data-driven YAML plus generic
classes. No plugin framework beyond the one entry-point group. Prefer a boring
function to a clever class.

---

## 4. Commands

```bash
uv sync                              # create env, install core + dev group
uv run pytest -q                     # tests
uv run ruff format .                 # format
uv run ruff check . --fix            # lint
uv run mypy src/loopsheet            # types must pass clean

uv run loopsheet validate examples/filler_line_3.yaml
uv run loopsheet show examples/filler_line_3.yaml
uv run loopsheet decode ifm:VVB020 0A1B2C3D --variant status_b
uv run loopsheet export --format topics examples/filler_line_3.yaml
```

**Definition of done for any change:** `ruff check` clean, `mypy --strict`
clean, `pytest` green, and a test added or updated that would fail without the
change.

---

## 5. Working agreements for Claude Code

- **Read the seam before you cut.** Identify which layer (§2) the change belongs
  to and keep it there. Don't smear logic across layers to save a few lines.
- **Never add an import to core.** If you think core needs a third-party
  package, that is a design bug — say so instead of adding it.
- **Never invent a device value.** Check `docs/research/` first. If it isn't
  there and you can't reach a primary source, ship `null` + `# UNVERIFIED` and
  add a line to TODO.md Phase 0.
- **Bit-slicing gets tests first.** The decoder is the piece most likely to be
  subtly wrong: byte-boundary spanning, sign extension, gradient/offset
  arithmetic. Write the assertion before the implementation.
- **Do not break `SCHEMA_VERSION`** without bumping it and saying so in the
  summary.
- **Show your test.** Behavior change ⇒ a `pytest` case in the same change.
- **No network in the test suite.** Adapter tests use recorded fixtures/fakes.
- **When unsure, leave `# TODO(loopsheet):` with a one-line rationale** rather
  than guessing at intent.

---

## 6. Licensing & attribution

Apache-2.0, Kovir Labs · Evan Gress. Preserve headers and `NOTICE`. Live traps:

- **`asyncua` is LGPL-3.0.** Optional, adapter-only, never imported from core.
- **Rejected deliberately:** `cpppo` (GPLv3 + a licensing-enforcement hard
  dependency), `python-opcua`/`opcua` (deprecated by its own maintainers),
  `ioddcombase` (proprietary), `pyi40aas` (superseded), `tahu` on PyPI
  (abandoned 2022).
- **Never vendor a vendor file.** IODD / EDS / GSD files are not redistributable
  here. Transcribe values with a source citation; fetch IODDs at runtime into a
  user cache dir if we ever automate it.
- Part numbers and trademarks are used for identification only.

---

## 7. Project facts

- **Name:** loopsheet (`loopsheet` on PyPI, free as of 2026-08).
- **Org:** Kovir Labs · `kovirlabs.dev`
- **Status:** pre-alpha. Phases 1–4 in [TODO.md](TODO.md) are the meaningful
  deliverable; 5–7 build on a frozen core.
- **Python floor `>=3.11`**, not the house 3.14 default — this package has an
  external audience and most industrial Python in the field is 3.11/3.12.
- **The proof case** is an ifm VVB020 on an ifm IO-Link master. Its process-data
  bit layout is **still unknown** (IODDfinder needs a login, ifm.com is
  Akamai-blocked) — that is the one open blocker, tracked as Phase 0.
- **Audience:** controls engineers and integrators who want their hardware
  described once, honestly, in a file they can diff. Build like they'll read
  every line, because they will.
