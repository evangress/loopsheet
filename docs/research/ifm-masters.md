# Research — ifm IO-Link masters: IoT Core / MQTT / OPC UA / EtherNet/IP

Primary-source notes gathered 2026-08-16, driving the catalog entries and the
`bindings/` models. Everything here is either quoted from an ifm operating
instructions PDF or explicitly marked `UNVERIFIED`.

**Working mirror for ifm PDFs** (ifm.com is Akamai-blocked, 403):
`https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-<MODEL>.pdf`

---

## 0. Two corrections to our starting assumptions

### 0.1 AL1342 / AL1343 are Modbus TCP, not EtherNet/IP

The EtherNet/IP DataLine family is **AL1320** (4-port IP67, 80284121/02, FW
3.1.x), **AL1321** (4-port IP69K, 80284122/02), **AL1322** (8-port IP67,
80284132/00, FW 2.3.x), **AL1323** (8-port IP69K, 80284133/00).

### 0.2 AL1350 / AL1352 have NO OPC UA server — confirmed negative

The string "OPC" appears **zero times** in the full AL1350, AL1352, AL1322 and
AL1342 manuals. Their IT-side interfaces are ifm IoT Core (REST/JSON over
HTTP(S)), WebSocket, MQTT, and the proprietary LR AGENT / LR SMARTOBSERVER push.

OPC UA lives on the **SolutionBlock AL1590 / AL1591** (8-port, IP67,
multiprotocol PROFINET + EtherNet/IP, "integrated OPC UA server" plus an IODD
interpreter and Node-RED).

### 0.3 Consequence for the model

**No single ifm master speaks MQTT *and* OPC UA *and* EtherNet/IP.**

| Master family | IoT Core | MQTT | OPC UA | EtherNet/IP | Modbus TCP |
|---|---|---|---|---|---|
| AL1350 / AL1352 (IoT) | ✅ | ✅ | ❌ | ❌ | ❌ |
| AL1320 / AL1321 (EIP 4-port, FW 3.1.x) | ✅ | ✅ | ❌ | ✅ | ❌ |
| AL1322 / AL1323 (EIP 8-port, FW 2.3.x) | ✅ | ❌ | ❌ | ✅ | ❌ |
| AL1342 / AL1343 (Modbus) | ✅ | `UNVERIFIED` | ❌ | ❌ | ✅ |
| AL1590 / AL1591 (SolutionBlock) | ✅ | ✅ | ✅ | ✅ | `UNVERIFIED` |

→ The catalog needs a **`supported_bindings`** field per master part number, and
the loader must reject a binding the part cannot serve. MQTT support is
**firmware-dependent**, so the capability is a function of (part, firmware).

---

## 1. ifm IoT Core REST / JSON API

Applies to AL1350/AL1352 **and** to the separate IoT port of the EtherNet/IP and
Modbus masters — byte-identical JSON examples appear in AL1350, AL1352 and
AL1320. Source: AL1350 80284128/03 §9.2, §14.2.3.

### 1.1 Transports

**GET** (read-only): `http://<ip>/<data_point>/<service>`

```
GET http://192.168.0.250/devicetag/applicationtag/getdata
→ { "cid":-1, "data":{"value":"AL1350"}, "code":200 }
```
`cid` is **-1** on GET (no correlation id supplied).

**POST** to `/` on port 80 (443 when security mode is on):

```json
{ "code":"request", "cid":4711, "adr":"data_point/service",
  "data":{ }, "auth":{"user":"<b64>","passwd":"<b64>"} }
```

| Field | Value | Notes |
|---|---|---|
| `code` | `"request"` \| `"transaction"` \| `"event"` | `"event"` is what the device sends in notifications |
| `cid` | integer, user-assigned | correlation id |
| `adr` | `"<data_point>/<service>"` | leading `/` optional — the manual uses both forms |
| `data` | object | **optional**, only for services that submit data |
| `auth` | `{user, passwd}` | **optional**, only when security mode is active; both Base64 |

Response: `{ "cid":id, "data":{...}, "code":diag }` — `data` omitted on pure writes.

Some ifm sample code uses the numeric alias `"code":10` for `"request"`. The
manual's normative text documents only the string form.

### 1.2 Diagnostic codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 230 | OK but needs reboot |
| 231 | OK but block request not finished |
| 232 | Data accepted but internally modified (e.g. cycle time adjusted) |
| 233 | IP settings updated; reload device, wait ≥1 s |
| 400 / 401 / 403 | Bad request / Unauthorized / Forbidden |
| 500 / 503 | Internal error / Service unavailable (port in wrong mode, no device) |
| **530** | **Requested data is invalid — "invalid process data"** |
| 531 | IO-Link error (master or device) |
| 532 | PLC connected error (write blocked, master still bound to fieldbus PLC) |

### 1.3 Paths that matter

**Process input data** — the value is an **uppercase hex string**, no `0x`
prefix, length implied by the device's PD length:

```json
{ "code":"request", "cid":4711, "adr":"/iolinkmaster/port[2]/iolinkdevice/pdin/getdata" }
→ { "cid":4711, "data":{"value":"03C9"}, "code":200 }
```
In DI mode PDIn is one byte: `"00"` = OFF, `"01"` = ON.

**Process output data:**
```json
{ "code":"request", "cid":10, "adr":"iolinkmaster/port[2]/iolinkdevice/pdout/setdata",
  "data":{"newvalue":"01000000004D"} }
```

**Device identity** — `iolinkmaster/port[n]/iolinkdevice/` + `status` `vendorid`
`deviceid` `productname` `serial` (all r), `applicationspecifictag` (rw).

**Master-level:** `/deviceinfo/{vendor,productcode,serialnumber,swrevision,hwrevision,bootloaderrevision,devicefamily}/getdata`,
`/processdatamaster/{temperature,voltage,current,supervisionstatus}/getdata`,
`/iotsetup/network/{ipaddress,macaddress}/getdata`, `/iolinkmaster/port[n]/pin2in/getdata`.

**Port config** — `iolinkmaster/port[n]/` + `mode` (rw*), `mastercycletime_preset`
(rw*), `mastercycletime_actual` (r), `comspeed` (r). \* only when the fieldbus
PLC is not RUNNING.

**Validation / data storage** — `validation_datastorage_mode`,
`validation_vendorid`, `validation_deviceid` (rw), service
`validation_useconnecteddevice`; `datastorage/{maxsize,chunksize,size}` (r),
services `getblobdata`, `start_stream_set`, `stream_set`.

**ISDU by index/subindex** — `index` and `subindex` are NUMBERs, `value` is a
hex STRING:
```json
{ "code":"request", "cid":4711, "adr":"/iolinkmaster/port[2]/iolinkdevice/iolreadacyclic",
  "data":{"index":21,"subindex":0} }
→ { "cid":4711, "data":{"value":"4730323134323830373130"}, "code":200 }   // "G0214280710"

{ "code":"request", "cid":4711, "adr":"/iolinkmaster/port[2]/iolinkdevice/iolwriteacyclic",
  "data":{"index":580,"subindex":0,"value":"34"} }
```

**Discovery** — `gettree` (optional `{adr, level}`, level 0–20), `getelementinfo`,
`getidentity`, `querytree`, `getsubscriberlist`.

**Multi-read** — note the response shape differs from `getdata`:
```json
{ "code":"request", "cid":4711, "adr":"/getdatamulti",
  "data":{"datatosend":["/processdatamaster/temperature","/deviceinfo/serialnumber"]} }
→ { "cid":4711, "data":{
      "processdatamaster/temperature":{"code":200,"data":44},
      "deviceinfo/serialnumber":{"code":200,"data":"000174210147"} }, "code":200 }
```
⚠️ Per-item value key is **`data`, not `value`**, and returned keys have **no
leading slash** even when the request paths did.

### 1.4 Authentication

Off by default. Enabling `iotsetup/security/securitymode` forces **HTTPS only**
and requires `auth` on every POST (Base64 user + password; default user
`administrator`). Password is write-only. `/getidentity`,
`/deviceinfo/vendor/getdata` and `/deviceinfo/productcode/getdata` stay
readable unauthenticated.

---

## 2. MQTT

AL1350 / AL1352 (FW 3.1.x) and AL1320 / AL1321 (FW 3.1.x). **Not** AL1322 /
AL1323 (FW 2.3.x — no MQTT chapter). Source: AL1350 §9.2.23, §14.2.1.

### 2.1 Configuration — `connections/mqttConnection`

| Path | Access | Notes |
|---|---|---|
| `../type`, `../status` | r | status ∈ `init`/`running`/`stopped`/`error` |
| `../status/preset` | r | basic setting **`running`** |
| `../MQTTSetup/QoS` | rw | 0 / 1 / 2 |
| `../MQTTSetup/version` | r | |
| `../mqttCmdChannel/status/preset` | r | basic setting **`stopped`** |
| `../mqttCmdChannel/mqttCmdChannelSetup/brokerIP` | rw | STRING |
| `../mqttCmdChannel/mqttCmdChannelSetup/brokerPort` | rw | **STRING**, e.g. `"1883"` |
| `../mqttCmdChannel/mqttCmdChannelSetup/cmdTopic` | rw | |
| `../mqttCmdChannel/mqttCmdChannelSetup/defaultReplyTopic` | rw | |

Services: `../status/{start,stop,reset}`, `../mqttCmdChannel/status/{start,stop,reset}`.

**No username, password, client-ID, CA certificate, or TLS/`mqtts` parameter
exists anywhere in the MQTT profile in FW 3.1.x.** Only `mqtt://` is documented.
Treat as **plaintext MQTT, no auth**. Newer firmware `UNVERIFIED`.

Constraints: max **10** simultaneous MQTT connections; wildcards `+` and `#` are
**not supported** in topics.

### 2.2 Publishing is a subscription with an `mqtt://` callback

There is **no separate publisher config**. The topic is the **path component of
the callback URL** — `mqtt://<brokerIP>:<brokerPort>/<topic>`. **ifm defines no
topic hierarchy; you choose it.**

```json
{ "code":"request", "cid":-1, "adr":"/timer[1]/counter/datachanged/subscribe",
  "data":{ "callback":"mqtt://192.168.82.100:1883/abc",
           "datatosend":["processdatamaster/temperature"] } }
```

**Triggers:**
- **Interval** — subscribe on `/timer[x]/counter/datachanged/subscribe`
  (`x ∈ [1,2]`), then `/timer[x]/interval/setdata` `{"newvalue":500}`.
  Valid range **500 … 2147483647 ms**.
- **On-event** — `iolinkmaster/port[n]/portevent/datachanged/subscribe`
  (device plugged/pulled/mode changed) or
  `iolinkmaster/port[n]/iolinkdevice/iolinkevent/datachanged/subscribe`.

`duration` may be `"lifetime"` (default) or `"uptime"`.

### 2.3 Published payload

```json
{ "code":"event", "cid":4711, "adr":"",
  "data":{
    "eventno":"6317",
    "srcurl":"/timer[1]/counter/datachanged",
    "payload":{
      "/timer[1]/counter":{"code":200,"data":1},
      "/processdatamaster/temperature":{"code":200,"data":39},
      "/iolinkmaster/port[2]/iolinkdevice/pdin":{"code":200,"data":"03B0"} } } }
```

- `adr` is the **empty string**; `eventno` is a **STRING**.
- Per-item value key is **`data`, not `value`** (as in `getdatamulti`).
- `datatosend` URLs are **bare data points** (`.../pdin`), not `.../pdin/getdata`.
- Payload keys keep whatever leading-slash form was subscribed with.
- PDIn arrives as the same uppercase hex string.

CSV codec (`"codec":"csv0"`) exists but is **TCP-only — not available over MQTT**.

WebSocket: `ws://<ip>:80/websocket`, callback `"ws:///myTopic"`, max 8
connections. **`wss://` is explicitly not supported.**

---

## 3. OPC UA

- **AL1350 / AL1352 / AL1322 / AL1342: no OPC UA.** Confirmed by grep, zero hits.
- **AL1590 / AL1591 (SolutionBlock)** have an integrated OPC UA server.
- **All AL159x OPC UA specifics are `UNVERIFIED`** — endpoint URL and port,
  security policies/modes, authentication, address-space layout. ifm.com is
  Akamai-blocked and the 241-page AL1590 manual was not reachable as a PDF.
  `opc.tcp://<ip>:4840` is only the IEC 62541-6 default, **not confirmed for ifm**.
  ifm marketing says "certificate-based encryption" — implies a server
  certificate, says nothing about user token types.

**Companion spec** (exists, ifm conformance `UNVERIFIED`): **OPC 30120 "IO-Link
Devices and IO-Link Masters", Release 1.0, 2018-12-01**, IO-Link Community +
OPC Foundation. Defines `IOLinkMasterType` (`Restart`,
`ResetStatisticsOnAllPorts`), `IOLinkPortType` (`ResetStatistics`,
`UpdateConfiguration`), `IOLinkDeviceType`, `IOLinkIODDDeviceType` for
IODD-derived dynamic types, `ProcessDataVariableType` for PDIn, and
`ReadISDU` / `WriteISDU` methods. Mandatory identity: `VendorName`,
`ProductName`, `ProductID`, `SerialNumber`.

---

## 4. EtherNet/IP (AL1320 / AL1321 / AL1322 / AL1323)

### 4.1 Assembly instances — identical on 4-port and 8-port

| Connection | Config | Input | Output |
|---|---|---|---|
| Exclusive Owner IO-Acyc-Diag | 199 | **100** | **150** |
| Exclusive Owner IO-Acyc | 199 | **101** | **150** |
| Exclusive Owner IO | 199 | **102** | **151** |
| Input only | 199 | **100** | 193 (empty) |
| Listen only | 199 | **100** | 192 (empty) |

### 4.2 Sizes — set by config byte 1 (`Process Data Length`)

`n` = per-port PD size in bytes. Sizes shown for input 100 / output 150.

| Value | n | 8-port in / out | 4-port in / out |
|---|---|---|---|
| 0x00 | 2 | **206 / 62** | **126 / 54** |
| 0x01 | 4 | 222 / 78 | 134 / 62 |
| 0x02 | 8 | 254 / 110 | 150 / 78 |
| 0x03 | 16 | 318 / 174 | 182 / 110 |
| 0x04 | 32 | 446 / 302 | 246 / 174 |

Derived for the other instances — 8-port: 101 = 62+8n, 102 = 20+8n, 151 = 2+8n;
4-port: 101 = 54+4n, 102 = 12+4n, 151 = 2+4n.

### 4.3 Input assembly 100 byte map

**8-port:** 0–1 DI (pin2/pin4) · 2–3 status · 4–45 acyclic **response** channel
(42 B) · then per port **18 B stride from byte 46** (2 B PQI + 16 B
diag/VID/DID/events) · **IO-Link input data starts at byte 190**, stride `n`.

**4-port:** same head · per-port 18 B stride from 46 · **IO-Link input data
starts at byte 118**.

**Instance 101:** head + 2 B PQI per port from 46 · 8-port IO-Link data from
**62**, 4-port from **54**.

**Instance 102:** 0–1 DI · 2–3 status · 2 B PQI per port from 4 · 8-port
IO-Link data from **20**, 4-port from **12**.

### 4.4 Output assemblies

**150:** byte 0 = DO bits (one per port) · 1–3 reserved · 4–45 acyclic
**request** channel · **IO-Link output from byte 46**, stride `n`.
**151:** byte 0 = DO bits · 1 reserved · **IO-Link output from byte 2**.

### 4.5 PQI byte — where "PDIn invalid" lives

Byte 0 of the 2-byte PQI (byte 1 reserved):

| Bit | Name | 1 means |
|---|---|---|
| 7 | Diagnosis present | new event present |
| 6 | Wrong PD Output Length | projected length too small |
| 5 | Wrong PD Input Length | projected length too small |
| 4 | Wrong Cycle Time | wrong cycle time |
| 3 | Wrong VID / DID | mismatch |
| **2** | **Invalid Data** | **PDIn invalid** |
| 1 | Dev Not Conn | not connected |
| 0 | IOL Mode | is IO-Link |

### 4.6 Config assembly 199

Byte 0 = Access Rights (0x00 EIP+IoT · 0x01 EIP+IoT read-only · 0x02 EIP only ·
**0x03 keep setting, default**). Byte 1 = Process Data Length. Then **12 bytes
per port** — 4-port total 50 B, 8-port total 98 B.

Per-port block, offset `n` within the block:

| Off | Field | Values |
|---|---|---|
| n+0 | Port Mode | 0x00 Disabled · 0x01 DI (pin 4) · 0x02 DO (pin 4) · 0x03 IO-Link |
| n+1 | Cycle Time | 0x00 fastest · 0x01 2 ms · 0x02 4 · 0x03 8 · 0x04 16 · 0x05 32 · 0x06 64 · 0x07 128 ms |
| n+2 | Swap | 0x00 disabled · 0x01 enabled (EIP little-endian vs IO-Link big-endian) |
| n+3 | Validation / Data Storage | 0x00 no check and clear · 0x01 type compat V1.0 · 0x02 type compat V1.1 · 0x03 V1.1 + Backup + Restore · 0x04 V1.1 + Backup |
| n+4, n+5 | Vendor ID | **byte order `UNVERIFIED`** — AL1320 prints LSB/MSB, AL1322 prints MSB/LSB |
| n+6…n+8 | Device ID | 3 bytes MSB→LSB |
| n+9 | reserved | |
| n+10 | Fail-safe, IO-Link | 0x00 none · 0x01 Reset Value · 0x02 Old Value · 0x03 Pattern |
| n+11 | Fail-safe, DO | 0x00 Reset Value · 0x01 Old Value · 0x02 Set Value |

Surfaces in RSLogix / Omron Network Configurator as parameter IDs `0030` Port
Mode, `0031` Cycle Time, `0032` Swap, `0033` Validation/DS, `0036` Fail-safe —
**+0x100 per port** (`0130`, `0230`, … `0730`).

### 4.7 Explicit messaging — ISDU

**Class `0x80` "IO-Link Requests", Instance `0x01`, Attribute = port number
`0x01…0x08`** (`0x01…0x04` on 4-port).

| Service | Code |
|---|---|
| Read_ISDU | **0x4B** |
| Write_ISDU | **0x4C** |
| Write Failsafe Pattern | **0x4D** |

Read request data: `UINT index` + `USINT subindex`. Response data = raw
parameter bytes **in IO-Link big-endian order** (ifm warns you may need to
re-order for CIP). Write request: `UINT index`, `USINT subindex`, then data
bytes MSB first.

Worked examples: read index 90 sub 3 from port 2 → Class 0x80, Inst 0x01, Attr
0x02, Svc 0x4B, data `0x005A, 0x03`. Write index 91 sub 5 = 0xABCD on port 3 →
Attr 0x03, Svc 0x4C, data `0x005B, 0x05, 0xAB, 0xCD`.

CIP errors: 0x02 resource unavailable (port busy) · 0x05 invalid class/instance
· 0x08 wrong service · 0x09 wrong attribute (bad port) · 0x0F insufficient
access rights · 0x20 invalid parameter · **0x1E embedded service error** →
user data byte 0 = IO-Link Error Code, byte 1 = Additional Code.

### 4.8 EDS, RPI, identity

- **EDS (AL1322, confirmed): `ifm_IOL_Master_AL1322.eds`** with icon
  `EIP_DL_8P_IP67.ico`, both in the same folder. AL1320/1321/1323 filenames
  `UNVERIFIED`.
- **RPI minimum 1 ms.** ifm publishes **no recommended or typical default** —
  do not invent one.
- Identity object 0x01 (AL1322): Vendor ID **322**, Device type **12**, Product
  code **1322**, Revision **1.1**, Product Name `"IO-Link Master DL EIP 8P IP67"`.
- CIP classes: 0x01 Identity, 0x02 Message Router, 0x04 Assembly, 0x06
  Connection Manager, 0x47 DLR, 0x48 QoS, **0x80 IO-Link Requests**, 0xF5
  TCP/IP, 0xF6 Ethernet Link.
- Default IPs: EtherNet/IP port `192.168.1.250`; separate IoT port `169.254.x.x`.

---

## 5. Port configuration — cross-protocol view

| Concept | IoT Core | EtherNet/IP config assy 199 |
|---|---|---|
| Port mode | `port[n]/mode` (enum values `UNVERIFIED`) | byte n+0: 0x00 Disabled / 0x01 DI / 0x02 DO / 0x03 IO-Link |
| Cycle time | `mastercycletime_preset` / `_actual` | byte n+1: enum 0x00 fastest … 0x07 128 ms |
| Validation / DS | `validation_datastorage_mode`, `validation_vendorid`, `validation_deviceid` | byte n+3 |
| Fail-safe | not exposed in FW 3.1.x | bytes n+10 / n+11, plus CIP service 0x4D |
| PDIn invalid | response code **530** (or 503 wrong mode / no device) | **PQI bit 2** |
| Byte swap | not exposed | byte n+2 |

**ifm's own IO-Link Vendor ID is 310** (from the web GUI `[Vendor ID]` field
documentation, range 0…65535, default 0; Device ID range 0…16777215).

### Data Storage behaviour

| Option | Validates | Stores | Restores |
|---|---|---|---|
| No check and clear | no | no | no |
| Type compatible V1.0 | V1.0 compat | no | no |
| Type compatible V1.1 | V1.1 compat | no | no |
| V1.1 with Backup + Restore | V1.1 + VID/DID | **yes, automatic** | **yes** |
| V1.1 with Restore | V1.1 + VID/DID | no | **yes** |

Applies **only in IO-Link mode**. For the Backup/Restore options, changing
vendor ID or device ID online **deletes the data memory** and re-backs-up from
the connected device.

---

## 6. Open questions — carry as `UNVERIFIED`, never guess

1. IoT Core `iolinkmaster/port[n]/mode` numeric enum values. **Resolve at
   runtime** via `getelementinfo`, which returns `format.valuation.valuelist`.
   (The EtherNet/IP config assembly uses 0x00/0x01/0x02/0x03 — plausible but
   not proof for the IoT enum.)
2. QoS literal for `MQTTSetup/QoS/setdata` — manual prints `"QoS2"` while
   typing the field as Number.
3. Correct prefix for the MQTT command-channel `status/start` service — the
   manual is self-inconsistent. `querytree` on hardware is authoritative.
4. MQTT credentials / TLS on firmware newer than 3.1.x.
5. All AL1590 / AL1591 OPC UA specifics.
6. Whether ifm implements OPC 30120 or a proprietary address space.
7. Vendor-ID byte order in the config-assembly per-port block.
8. EDS filenames for AL1320 / AL1321 / AL1323.
9. Whether the ISDU response echoes service 0x4B or 0x4C.
10. **Cycle-time unit conflict** — within the *same* AL1350 manual, §9.1.6 (web
    GUI) says **microseconds**, range 0…132800; §9.2.8 (IoT Core) says the same
    parameters are in **ms**. 132800 µs = 132.8 ms matches the IO-Link maximum,
    so µs is almost certainly right and the IoT table is the error. Verify on
    hardware before committing.
11. AUX PWR status-bit polarity — the AL1322 legend is self-contradictory.

⚠️ The manual's own MQTT configuration example is **printed malformed** (missing
comma, `"data":{"192.168.82.100"}` instead of `{"newvalue":"192.168.82.100"}`).
Use the `{"newvalue": …}` form, consistent with every other `setdata`.

---

## Sources

- [AL1350 (80284128/03, FW 3.1.x)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1350.pdf)
- [AL1352 (80284138/03, FW 3.1.x)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1352.pdf)
- [AL1320 EtherNet/IP 4-port (80284121/02)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1320.pdf)
- [AL1321 EtherNet/IP 4-port IP69K (80284122/02)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1321.pdf)
- [AL1322 EtherNet/IP 8-port (80284132/00)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1322.pdf)
- [AL1323 EtherNet/IP 8-port IP69K (80284133/00)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1323.pdf)
- [AL1342 Modbus TCP (80284136/00)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1342.pdf)
- [AL1343 Modbus TCP IP69K (80284137/01)](https://www.quicktimeonline.com/assets/images/pdf/IFM%20Electronic/operating-instruction-AL1343.pdf)
- [Omron NJ/NX ↔ ifm AL1322 EtherNet/IP Connection Guide P700](https://assets.omron.eu/downloads/latest/connection_guide/en/p700_nj_nx-series_-%5Bethernet_ip%5D-_ifm_io-link_master_(al1322)_cg_en.pdf)
- [ifm/python-opd100-example](https://github.com/ifm/python-opd100-example/blob/master/opd100_loader.py)
- [corlina/BF-001-IFM-PYTHON daemon3.py](https://github.com/corlina/BF-001-IFM-PYTHON/blob/master/daemon3.py)
- [OPC 30120 IO-Link companion spec §5](https://reference.opcfoundation.org/IOLink/v100/docs/5)
- [OPC-UA for IO-Link v1.0 PDF](https://io-link.com/fileadmin/user_upload/Downloads/IO-Link_Integration/OPC-UA_for_IO-Link_10212_V10_Dec18.pdf)
- [ifm AL1590 product page](https://www.ifm.com/us/en/product/AL1590) · [product news: OPC UA server](https://www.ifm.com/gb/en/shared/productnews/2025/hmi/field-compatible-io-link-master-with-opc-ua-server)
