# Changelog

All notable changes to loopsheet are recorded here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`SCHEMA_VERSION` — the version of the *serialized machine-file contract* — is
tracked separately from the package version. Additive schema changes bump its
minor; any rename or removal bumps its major and gets a migration note here.

## [Unreleased]

### Added

- Project scaffold: `pyproject.toml` (hatchling + uv, Python `>=3.11`,
  Apache-2.0), `LICENSE`, `NOTICE`, `CLAUDE.md`, `README.md`, `ROADMAP.md`.
- `loopsheet.models` — `LoopsheetModel` base with `SCHEMA_VERSION = 1`, frozen
  `Reading`, `ChannelSpec` / `Signal`, mechanical assets and `MeasurementPoint`,
  `Site` → `Area` → `Machine`, sensors, IO-Link master and ports, PLC and I/O
  tree, DAQ and edge devices, and the `Component` discriminated union.
- `loopsheet.codec` — IO-Link datatypes, `ProcessDataItem` /
  `ProcessDataLayout` with overlap rejection, MSB-first `decode()`, and analog
  raw-count scaling with under/over-range and broken-wire handling.

### Notes

- Schema contract starts at `SCHEMA_VERSION = 1`; nothing is released yet, so
  no migrations exist.
- The ifm VVB020 process-data bit layout remains **unverified** — IODDfinder
  requires a login and ifm.com blocks automated access. Catalog entries ship
  `process_data: null` and the golden-decode test stays unwritten. Tracked as
  Phase 0 in [TODO.md](TODO.md).
