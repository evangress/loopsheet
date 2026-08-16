# Research — ifm VVB020 vibration sensor

Primary-source notes gathered 2026-08-16, driving
`src/loopsheet/catalog/data/ifm/VVB020.yaml`.

**Rule for this document:** every value is either traced to a source below or
explicitly marked `UNVERIFIED`. A wrong bit offset silently decodes garbage, so
unverified values ship as `null` in the catalog, never as a plausible guess.

## Sources

| # | Source | Notes |
|---|---|---|
| S1 | [ifm device manual "Vibration sensor with IO-Link interface VV", 80298004/01 06/2021 GB](https://portalimages.blob.core.windows.net/products/pdfs/0kdjaxrt_DeviceManualVVB001.pdf) | Family manual: VVB001/010/011/020/021 |
| S2 | [ifm efector VVB datasheet bundle](https://www.instrumart.com/assets/VVB-1-AXIS-DATASHEET.pdf) | Has a dedicated VVB020 section, `EN-US -- VVB020-01 -- 13.04.2023` |
| S3 | [VVB020 datasheet, German edition (Conrad mirror)](https://asset.conrad.com/media10/add/160267/c1/-/de/003321412DS00/datablad-3321412-ifm-electronic-oscillatiesensor-vvb020-18-30-vdc-1-stuks.pdf) | `DE-DE -- VVB020-01`; cleaner column alignment, used to disambiguate S2 |
| S4 | [IODDfinder registry API — VVB020](https://ioddfinder.io-link.com/api/drivers?status=APPROVED&page=0&size=20&productName=VVB020) | Official IO-Link Community registry JSON |
| S5 | [UMH benthos-umh sensorconnect docs](https://docs.umh.app/benthos-umh/input/ifm-io-link-master-sensorconnect) | Decoded PD example — **VVB001, not VVB020** |

Blocked: `www.ifm.com` (403 to every path; 503 via proxy), `manuals.plus`,
`device.report`, `manualzz`, rs-online, `web.archive.org` (429). **IODDfinder
zip download now requires a login (401)** — this is why the bit layout is missing.

---

## 1. The headline finding: VVB020 is two devices

**S1 §3.1:** *"Each product is offered in two software versions (status A and
status B)."* They are distinguished **at the wire level by Device ID**, and
their parameter sets and process data differ.

| | Status A | Status B |
|---|---|---|
| **Device ID** | **1257** (0x04E9) | **1369** (0x0559) |
| Transmission | **COM2, 38.4 kBaud** | **COM3, 230.4 kBaud** |
| Min. process cycle time | **11.6 ms** | **3.6 ms** |
| IODD | `ifm-0004E9-20200110-IODD1.1` (v1.3.63.923543, ioddId 8438) | `ifm-000559-20201105-IODD1.1` (v1.3.66.1043016, ioddId 10375, productName "VVB020 Status B") |
| PDOut | **none** | **yes** |
| Switchable PD values | v-RMS, a-Peak, a-RMS | + crest, temperature; OU1/OU2 can be `OFF` |

S1 §3.1 also warns the PLC port must have "Device identification" enabled or a
status-B unit is rejected.

> **Model consequence.** A part number does **not** map 1:1 to an IO-Link
> identity. `CatalogEntry` needs a **`variants`** list keyed by device ID, each
> carrying its own COM mode, cycle time, IODD reference, and process-data
> layout. The loader must let a machine YAML pin a variant, and the `iotcore`
> adapter can confirm it by reading `.../iolinkdevice/deviceid`.

**Vendor ID: 310** (0x0136), `"ifm electronic gmbh"` — verified via S4, and
independently consistent with the ifm master web-GUI docs.

Other verified IO-Link facts (S2): IO-Link revision **1.1**, SDCI **IEC 61131-9:
2013-07**, **SIO mode: yes**, required master port class **A**, profiles
**BLOB**, **Common – I&D**, **Function (Measurement data, standard resolution)**.

---

## 2. Process data — layout is UNVERIFIED

**I have no verified bit offset, bit length, datatype, gradient, or offset for
any VVB020 process value, in either status.** Both IO-Link interface
descriptions were unreachable.

What *is* known about the structure:

- Datasheet row reads **"Process data analog: 10 / Process data binary: 2"**
  (S2). The PDF's two-column layout is offset by one row in text extraction;
  this mapping was reconstructed from label order and cross-checked against the
  German edition (S3). **The datasheet states no unit for the "10"** — it could
  be a count of analog items or 10 bytes. **PDIn length in bits/bytes:
  UNVERIFIED.**
- **PDOut bit no. 4 = BLOB record trigger, status B only.** S1 §7.2: *"VV units
  with status B can record raw data via a bit (no. 4) in the PdOut data flow.
  Raw data can be recorded via a rising edge of the corresponding bit."*
  Whether "no. 4" is a 0-based offset or a 1-based bit number is not stated.
- **Sibling-part evidence only** (S5, **VVB001** — do not copy into the VVB020
  catalog): decoded PD fields are
  `{"v-Rms", "a-Peak", "a-Rms", "Crest", "Temperature", "Device status", "OUT1", "OUT2"}`
  — 5 analog + 1 status + 2 booleans. The literal sample values `Crest: 41` and
  `Temperature: 394` are *consistent with* a 0.1 gradient on both, but that is
  inference from a sibling part, not a documented gradient. The JSON key order
  is alphabetical and says nothing about bit order.

### ISDU index/subindex — UNVERIFIED

**No Index or Subindex number for any VVB020 parameter was found on any
reachable page.** S1 §7.1 lists parameters by *name only* and explicitly defers:
*"A complete list can be found in the IODD of the unit."*

Indices 16/17/18/19/21/24 (VendorName / VendorText / ProductName / ProductID /
SerialNumber / ApplicationSpecificTag) are **IO-Link spec-defined direct
parameters**, not device-specific, and the "Common – I&D" profile implies they
are implemented — but they were not enumerated on any VVB020 page, so they are
`UNVERIFIED` **for this device**.

### Verified parameter *names* (status B, S1 §7.1)

Useful for matching once the IODD is in hand:

- **Identification** — `Application specific tag`, `Function tag`, `Location tag`
  (free text, **max 32 chars each**), `Date of installation` (**yyyy-mm-dd**,
  not restored after device replacement)
- **Outputs** — `ou1`/`ou2` ∈ **Hno / Hnc / Fno / Fnc / OFF**;
  `SEL1`/`SEL2` ∈ **v-RMS / a-Peak / a-RMS / temperature / crest**;
  `P-n` ∈ **PNP / NPN**
- **Delays** — `dS1`/`dS2` (switch-on), `dr1`/`dr2` (switch-off), **0…50 s**
- **Setpoints** — `SP1`/`SP2`, `rP1`/`rP2` per process value
- **Memory** — `Lo.T`/`Hi.T` (**-30.0…80.0 °C**); max-value memories:
  v-RMS **0.0000…0.0495 m/s**, a-Peak **0.0…490.3 m/s²**,
  a-RMS **0.0…490.3 m/s²**, crest **1.0…50.0**
- **Filters** — `FILT-DC.FCUTOFF`/`.Type`, `FILT-V.…`, `FILT-A.…`
- **Error config** — `FOU1`/`FOU2` ∈ **OFF / ON / OU**
- **Units** — `uni-v-RMS`, `uni-a-Peak, a-RMS`, `uni.T`
- **Diagnostics** — self-test result, `MDC`, `BLOB ID`, `Device status`,
  `Event history`, `Event counter`
- **Machine monitoring** — `mot`, `mrc`, `mrcT`, switch-on operations,
  operating-hours counter, internal temperature, BLOB file transfer

> ⚠️ **Unit conflict to watch.** S1 §7.1 gives the crest setpoint range as
> **SP 20…500 / rP 10…490**, while the VVB020 datasheet (S2/S3) gives
> **SP 2…50 / rP 1…49, step 1**. The factor of 10 suggests S1 prints *raw ISDU
> counts* against a 0.1 gradient. **Inference, not verified** — but it is a
> useful hint for the eventual gradient.

---

## 3. Measured values (S2/S3, VVB020-specific)

| Value | Unit | Range | SP range | rP range | Step | Resolution | Accuracy |
|---|---|---|---|---|---|---|---|
| **v-RMS** | mm/s | **0…45** | 0.2…45 | 0…44.8 | 0.2 | `UNVERIFIED` | `UNVERIFIED` |
| **a-Peak** | m/s² (g) | **0…490.3** (0…50 g) | 2…490.3 | 0…488.3 | 2 | `UNVERIFIED` | `UNVERIFIED` |
| **a-RMS** | m/s² (g) | **0…490.3** (0…50 g) | 2…490.3 | 0…488.3 | 2 | `UNVERIFIED` | `UNVERIFIED` |
| **Crest** | — | **1…50** | 2…50 | 1…49 | 1 | `UNVERIFIED` | `UNVERIFIED` |
| **Temperature** | °C | **-30…80** | -28…80 | -30…78 | 2 | **0.1 °C** | **± 2.5 K + (0.2 × (T_ambient − T_surface))** |

Sensor: **capacitive MEMS**, **1 measurement axis**, frequency range
**2…10 000 Hz**. Frequency-response accuracy **4 kHz ±10 %; 4…10 kHz < 3 dB**.
**Linearity deviation 2 %.**

**No separate ISO-10816 damage-class or condition process value exists.** The
crest factor is the bearing-damage indicator — S1 §6.3.4: *"In condition
monitoring the characteristic value is used for the evaluation of the bearing
condition."* Status B adds an event counter, event history (last 20 events, ring
buffer), operating-hours counter, `mot` (machine operating time) and `mrc`
(threshold-exceed counter) — S1 describes these as **parameters/counters**;
whether any appear in PDIn is `UNVERIFIED`.

### Frequency bands — set by the filter chain, not fixed

Not labelled "ISO 10816" anywhere. **S1 §9.2 gives VVB020 factory filters:**

| Filter | VVB020 factory | Type |
|---|---|---|
| `FILT-DC.FCUTOFF` | **10 Hz** | High-pass |
| `FILT-V.FCUTOFF` | **1000 Hz** | Low-pass |
| `FILT-A.FCUTOFF` | **5000 Hz** | Low-pass |

So **at factory default v-RMS is evaluated over 10…1000 Hz** and **a-Peak /
a-RMS over 10…5000 Hz**. S1 §7.3.5 documents the 10 Hz + 1 kHz combination as
*"evaluation of the signal components between 10…1000 Hz"*. (VVB011/VVB021 use
a 2 Hz DC cutoff; VVB001's a-filter is Bypass.)

Configurable (S1 §7.1): DC high-pass **2 / 10 Hz**; a-filter **bypass /
high-pass / low-pass at 1 / 3 / 5 kHz**; v-filter **low-pass 1 kHz, fixed**.

Selectable units (S1 §7.1): v-RMS ∈ **m/s, mm/s, inch/s**; a-Peak/a-RMS ∈
**m/s², g, mg**; temperature ∈ **°C, °F**. Factory defaults (S1 §9.1):
**m/s, m/s², °C** — note the *datasheet* quotes v-RMS in mm/s while the
*factory default unit* is m/s.

---

## 4. Electrical / mechanical (S2 + S3, VVB020-specific)

**Electrical** — operating voltage **18…30 V DC**, current consumption
**< 50 mA**, insulation resistance **100 MΩ (500 V DC)**, protection class
**III**, reverse-polarity protected.

**Outputs** — **2 digital outputs**. Output signal: **switching signal; IO-Link**.
> **There is no 4-20 mA analog output on the VVB020.** Any analog-output entry
> for this part would be wrong.

PNP/NPN configurable, NO/NC, max voltage drop **2 V**, max load **100 mA/output**,
short-circuit protection **pulsed/clocked**, overload protection yes.

**M12 connector**, A-coded, max cable length 20 m. Wire colours from S1 §5:

| Pin | Function | Colour |
|---|---|---|
| 1 | L+ | BN brown |
| 2 | OUT2 | WH white |
| 3 | L− | BU blue |
| 4 | **OUT1 — switching output or IO-Link** | BK black |

**Environment** — ambient and storage **-30…80 °C** (datasheet notes *"hardware
version BC has a temporarily changed ambient temperature range"* without giving
it — `UNVERIFIED`); **IP 67 / IP 68 / IP 69K**; UL **Ta -30…60 °C**, approval
**L002** (VVB001 is -30…70 °C — 60 °C is VVB020's); EMC 2014/30/EU, DIN EN
61000-6-2/-6-3; shock **50 g/11 ms** and **500 g/1 ms**; vibration **20 g,
10…3000 Hz**; MTTF **299 years**.

**Mechanical** — **116.5 g**, tubular **stainless steel 1.4404 / 316L**,
**⌀ 22 mm × 63.55 mm**, mounted by **set screw**, **tightening torque 8 Nm**.
Supplied adapters: **1/4"-28 UNF / M8** and **1/4"-28 UNF × 5/8" DIN 916**.
Mounting hole: **M8 ≥ 10 mm deep**, or **1/4"-UNF ≥ 13 mm deep**; 3 mm Allen key.

**Mounting affects usable bandwidth** (S1 §4.2) — worth carrying on
`MeasurementPoint`:

| Method | Transferable frequency range |
|---|---|
| Screw | up to ≈ **15 kHz** |
| Direct gluing | up to ≈ **8 kHz** |
| Magnet | up to ≈ **3 kHz** |

**Application class (S2/S3):** *medium-sized machines, power < 300 kW,
rotational speed > 600 rpm*. (S1's family table renders this as "Small
machines" but its rows are visually offset — trust S2/S3.)

---

## 5. BLOB / raw data (S1 §7.2, verified)

- **4 s recording, 25 kHz sampling, 16-bit signed samples, 200 000 bytes total**
- Scale to g: **divide by 2¹⁶/125 = 524.288**
- BLOB IDs: **-4096** (status A + B, on demand) · **-4097** (status B, system
  command) · **-4098** (status B, switching-output-1 event) · **-4099**
  (status B, PDOut bit-4 triggered)
- Transfer time **≥ 7 min**, or **≈ 2 min** over COM3. Importable into
  VES004 ≥ v2.07.00 as `*.bin`.

---

## 6. What is still missing, and how to close it

1. **Complete PDIn bit layout** for status A and status B — bit offset, bit
   length, datatype, gradient, offset, unit per value.
2. **PDIn total length** in bits/bytes.
3. **All ISDU index/subindex numbers**, including the standard 16–24.
4. **Resolution and accuracy** for v-RMS, a-Peak, a-RMS, crest (only setpoint
   *step sizes* are published; only temperature has stated resolution/accuracy).
5. Exact IODD XML filename suffix (`-en.xml` is conventional but unconfirmed).
6. Ambient-temperature range of hardware version **BC**.

**Items 1–3 require the IODD itself.** Two routes from an unrestricted network:

- **ifm interface-description PDFs** — pattern-derived from other ifm devices,
  both returned 403 here, note `IODD11` in the URL vs `IODD1.1` in the name:
  - Status A: `https://www.ifm.com/download/files/ifm-0004E9-20200110-IODD11-en/$file/ifm-0004E9-20200110-IODD11-en.pdf`
  - Status B: `https://www.ifm.com/download/files/ifm-000559-20201105-IODD11-en/$file/ifm-000559-20201105-IODD11-en.pdf`
- **IODDfinder with a free account** — the exact records are vendorId **310**,
  ioddId **8438** (status A) and **10375** (status B).

Until then the `process_data` block in `VVB020.yaml` ships as `null` with
`# UNVERIFIED` markers, and the golden-decode test stays unwritten.
