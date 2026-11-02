# DC Office Single-Room Hybrid Energy Management System (DCEMS)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PlatformIO](https://img.shields.io/badge/PlatformIO-ESP8266-orange.svg)](https://platformio.org/)
[![Safety Gate](https://img.shields.io/badge/Safety_Gate-8--Point_Authoritative-red.svg)](#firmware-safety-gate-reference)
[![Tests Passing](https://img.shields.io/badge/Tests-73%20passed-brightgreen.svg)](#testing--verification)

A safety-critical, explainable, hybrid IoT energy management system designed for a single representative DC Office room. DCEMS combines embedded local rule execution on an ESP8266 (NodeMCU), an authoritative 8-point firmware safety gate, and a fully self-hosted local server stack (Mosquitto MQTT, FastAPI, SQLite, and an offline web dashboard) that completely replaces third-party cloud platforms (e.g., Blynk).

---

## Core Design Principles

> [!IMPORTANT]
> **1. The ESP8266 Embedded Controller Owns Physical Load Safety**  
> The backend server and web dashboard may only *propose* or *request* actions. Every state transition command must pass through the firmware's deterministic 8-point safety gate before a relay pin can be toggled. The server can never bypass this gate.

> [!WARNING]
> **2. AC and PC Loads are Strictly Alert-Only**  
> Abrupt mains power cutoff damages compressor motors (`ac_01`) and corrupts filesystems (`pc_01`). Both devices are locked to `autoEligible = false` at compile-time in firmware. Furthermore, manual power-off commands from the dashboard targeting AC or PC are blocked by default (Test T13 safeguard).

> [!NOTE]
> **3. Honest Engineering Labeling (No False AI or Energy Claims)**  
> - **Motion $\neq$ Presence**: *"PIR detects motion, not people."* Stationary occupants can result in zero motion pulses. Multi-stage grace periods are enforced.
> - **Commanded State $\neq$ Physical Current**: In the absence of physical CT current meters, all runtime durations ($T_{\text{runtime}} = t_{\text{OFF}} - t_{\text{ON}}$) are explicitly labeled:  
>   $$\text{"Estimate based on commanded state"}$$
> - **Zero Speculative Savings**: No speculative kWh, monetary savings, or machine-learning performance claims are generated.
> - **Detection $\neq$ Authorization**: Detecting an anomaly never automatically switches relays. All alerts are alert-only unless policy and gate explicitly allow.

---

## Hardware Prototype Grounding & Blynk Replacement

DCEMS directly preserves and enhances the physical circuit configuration verified in the team's prototype sketch (`firmware/legacy/Smart_Classroom_ESP8266_Blynk.ino`).

### Verified Physical Pin Mapping (NodeMCU ESP-12E)
| Appliance / Sensor | NodeMCU Pin | ESP8266 GPIO | Electrical Logic | Description |
|---|:---:|:---:|:---:|---|
| **PIR Motion Sensor** | `D5` | GPIO14 | Active-HIGH | Digital motion pulse detection. |
| **LDR Light Sensor** | `A0` | ADC0 | Analog (0–1023) | Moving-average filter (10 samples, 200ms interval). |
| **DHT11 Data** | `D3` | GPIO0 | Bi-directional | Room temperature and humidity. Boot-strap pullup. |
| **Relay Light (`light_01`)** | `D0` | GPIO16 | Active-LOW | Relay channel 1. Switched OFF at boot (Pin HIGH). |
| **Relay Fan (`fan_01`)** | `D6` | GPIO12 | Active-LOW | Relay channel 2. Switched OFF at boot (Pin HIGH). |
| **Relay PC (`pc_01`)** | `D7` | GPIO13 | Active-LOW | Relay channel 3. **Alert-Only**; power cut blocked. |
| **Relay AC (`ac_01`)** | `D8` | GPIO15 | Active-LOW | Relay channel 4. **Alert-Only**; power cut blocked. |
| **I2C LCD SDA** | `D2` | GPIO4 | I2C Data | 16x2 diagnostic character LCD (address `0x27`). |
| **I2C LCD SCL** | `D1` | GPIO5 | I2C Clock | 16x2 diagnostic character LCD clock. |

### How DCEMS Replaces Blynk
* **Cloud Broker $\to$ Local Mosquitto**: Replaces cloud reliance with private, authenticated LAN MQTT on port 1883.
* **Virtual Datastreams (V0..V7) $\to$ Structured MQTT JSON**: Telemetry published to `dcems/room1/sensors` and retained states to `dcems/room1/state`.
* **Unrestricted Controls (V8..V14) $\to$ Policy-Validated Actions**: Replaces raw manual sliders with an authenticated web dashboard backed by the firmware safety gate.
* **Fake Energy Formulas $\to$ Descriptive Runtime Tracking**: Replaces hardcoded watt/tariff multipliers with transparent operational interval tracking.

---

## System Architecture

```mermaid
flowchart TD
    subgraph Room ["Room 1 (DC Office Environment)"]
        Sensors["Sensors<br/>(PIR, LDR, DHT11)"]
        ESP["ESP8266 Controller<br/>(Sensors, Rules, State Machine)"]
        Gate["Pure C++ Safety Gate<br/>(8-Point Authoritative Validator)"]
        Relays["Active-LOW Mains Relays<br/>(light_01, fan_01, ac_01, pc_01)"]
        LCD["16x2 I2C Diagnostic LCD"]
    end

    subgraph ServerHost ["Self-Hosted Server (Local LAN)"]
        Broker["Eclipse Mosquitto MQTT<br/>(Port 1883, User/Pass Auth)"]
        API["FastAPI Backend Service<br/>(Ingestion, Policy, Analysis, Auth)"]
        Detectors["Explainable Detectors<br/>(Vacancy, Daylight, Runtime, Cycling, Quality)"]
        DB[("SQLite WAL Database<br/>(Timestamps in UTC, Foreign Keys)")]
    end

    subgraph Client ["Operator Terminal"]
        Dashboard["Web Dashboard (Vanilla JS + Local Chart.js)<br/>(Live, Events, Alerts, Control, Settings, Analysis)"]
    end

    Sensors -->|Raw Pulses & ADC| ESP
    ESP --> Gate
    Gate -->|Validated State Only| Relays
    ESP --> LCD

    ESP <-->|MQTT pub/sub (JSON)| Broker
    Broker <-->|paho-mqtt| API
    API <--> DB
    API --> Detectors
    Detectors --> DB
    Dashboard <-->|REST API + Polling| API
```

---

## Repository Structure

```
Energy-Management-System/
├── dashboard/                # Static Single-Page Web Dashboard (Zero CDN)
│   ├── css/style.css         # Responsive dark-theme interface styling
│   ├── js/
│   │   ├── chart.min.js      # Vendored offline Chart.js engine
│   │   ├── live.js           # Live telemetry, staleness banners, mode display
│   │   ├── events.js         # State transition logs, runtime cards, sessions
│   │   ├── anomalies.js      # Deterministic alert feed & acknowledge actions
│   │   ├── control.js        # System mode toggle, appliance buttons, ACK audit
│   │   └── analysis.js       # 24h usage histogram & adaptive baseline monitor
│   └── index.html            # Complete unified multi-tab dashboard layout
├── deploy/                   # Production Deployment Orchestration
│   ├── docker-compose.yml    # Mosquitto broker + FastAPI service definition
│   ├── mosquitto.conf        # Authenticated LAN MQTT broker configuration
│   ├── .env.example          # Environment variables template
│   └── secrets.example.h     # Wi-Fi and MQTT credentials template
├── docs/                     # Engineering Documentation Baseline
│   ├── ASSUMPTIONS.md        # Hardware pins, timing intervals, and defaults
│   ├── DECISIONS.md          # Architecture Decision Records (ADR-001..007)
│   ├── HARDWARE_CHECKLIST.md # Physical bench and mains safety checklist
│   ├── LIMITATIONS.md        # Measurement boundaries and PIR disclaimers
│   ├── PROTOCOL.md           # MQTT topics, JSON schemas, reason codes
│   ├── SPEC_ANALYSIS.md      # Specification analysis and traceability matrix
│   ├── TEST_REPORT.md        # Empirical test execution evidence (73/73 passed)
│   └── source/               # Original proposal PDFs and assets
├── firmware/                 # Embedded C++ Firmware (NodeMCU ESP8266)
│   ├── include/config.h      # Compile-time device table, pins, thresholds
│   ├── include/secrets.example.h
│   ├── src/
│   │   ├── main.cpp          # Setup, safe boot, non-blocking cooperative loop
│   │   ├── sensors.h/.cpp    # Non-blocking acquisition (PIR, LDR MA, DHT11)
│   │   ├── state.h/.cpp      # Relay GPIO control, manual hold tracking
│   │   ├── rules.h/.cpp      # Autonomous local vacancy & daylight rules
│   │   ├── safety_gate.h/.cpp# Pure C++ 8-point authoritative safety gate
│   │   └── mqtt_comm.h/.cpp  # Bounded 50-event RAM queue, LWT, ACK publisher
│   ├── legacy/               # Original prototype sketch preserved for audit
│   └── platformio.ini        # PlatformIO build configuration
├── server/                   # Self-Hosted Backend Service (Python 3.11+, FastAPI)
│   ├── app/
│   │   ├── auth.py           # PBKDF2 password hashing & JWT authentication
│   │   ├── config.py         # App settings & canonical device definitions
│   │   ├── db.py             # SQLite WAL connection manager & migrations
│   │   ├── mqtt_client.py    # Background MQTT subscriber & telemetry cache
│   │   ├── policy.py         # Server proposal validation & signed command issuer
│   │   ├── analysis.py       # Runtime math, hourly histogram, Median + MAD
│   │   ├── detectors/        # Deterministic explainable anomaly detectors
│   │   │   ├── vacancy.py    # 5m candidate, 10m warning, 15m confirmed
│   │   │   ├── daylight.py   # LDR threshold + 3m confirmation + hysteresis
│   │   │   ├── runtime.py    # Max continuous runtime threshold
│   │   │   ├── cycling.py    # >4 switches in 10m diagnostic monitor
│   │   │   └── sensor_quality.py # Missing/stale/out-of-range detection
│   │   └── main.py           # REST API routes & static dashboard mount
│   ├── migrations/           # Plain SQL schema migrations (001, 002)
│   └── tests/                # Automated pytest suite (68 tests)
├── simulator/                # Host-Side Hardware Emulator & Verification
│   ├── mock_esp.py           # Python ESP8266 mock with 1:1 safety gate parity
│   ├── run_e2e_demo.py       # Complete end-to-end verification demo script
│   └── tests/                # Simulator automation tests (5 tests)
└── README.md
```

---

## Getting Started

### 1. Prerequisites
- **Docker & Docker Compose** (Recommended for production deployment) OR
- **Python 3.11+** and **Eclipse Mosquitto** (For native development)
- **Git**

### 2. Environment Configuration
```bash
# Clone the repository
git clone https://github.com/mahdi-014/Energy-Management-System.git
cd Energy-Management-System

# Set up local environment files
cp deploy/.env.example deploy/.env
cp firmware/include/secrets.example.h firmware/include/secrets.h
```

### 3. Option A: Running via Docker Compose
```bash
cd deploy
docker compose up -d
```
The FastAPI backend will automatically execute schema migrations, seed default operator accounts (`admin` / `admin123`), and serve the dashboard at:
👉 **`http://localhost:8000`**

### 4. Option B: Native Host Execution
```bash
# Set Python path and run backend
export PYTHONPATH="server:."
python server/app/main.py
```

### 5. Running the Turnkey E2E Demonstration Script
To verify the complete system lifecycle without physical hardware:
```bash
python simulator/run_e2e_demo.py
```
This script exercises:
- Sensor ingestion and occupancy inference.
- Multi-stage vacancy detection (5m, 10m, 15m).
- Server proposal generation and policy checks.
- ESP8266 8-point hardware safety gate validation.
- Relay actuation and asynchronous ACK ingestion.
- Test T13 AC & PC power-off blocking.
- 24-hour hourly usage distribution in Asia/Dhaka local time.
- Data-driven adaptive baseline calculations (Median + MAD).

---

## Testing & Verification

The test suite validates the entire system against all acceptance criteria:
```bash
# Run the complete test suite across server and simulator
pytest server/tests simulator/tests -v
```

### Verified Test Summary (73 / 73 Passed)
| Test ID | Category | Scenario Verified | Outcome |
|---|---|---|:---:|
| **TC-01** | State Tracking | OFF $\to$ ON state transition and open session creation | **PASS** |
| **TC-02** | State Tracking | ON $\to$ OFF transition and session duration calculation | **PASS** |
| **TC-03** | Anomaly Detection | Vacancy candidate, warning, and alert progression (5m, 10m, 15m) | **PASS** |
| **TC-04** | Anomaly Detection | Daylight waste alert with 3-minute confirmation window | **PASS** |
| **TC-05** | Anomaly Detection | Continuous maximum runtime threshold alert | **PASS** |
| **TC-06** | Anomaly Detection | Rapid cycling diagnostic alert (>4 transitions in 10m) | **PASS** |
| **TC-07** | Safety Gate | Active manual hold (600s) and MANUAL mode block auto-actions | **PASS** |
| **TC-08** | Anomaly Detection | Missing/stale ($>60\text{s}$) sensor data suppresses auto-actions | **PASS** |
| **TC-09** | MQTT Resilience | Bounded 50-event RAM ring buffer and `data_gap` on overflow | **PASS (Simulated)** |
| **TC-10** | Safety Gate | Expired TTL and duplicate `action_id` rejected | **PASS** |
| **TC-11** | Load Safeguard | AC and PC vacancy alerts raised; automated shutdown blocked | **PASS** |
| **TC-12** | End-to-End Cycle | Complete Proposal $\to$ Gate $\to$ Relay Transition $\to$ ACK Cycle | **PASS** |
| **T1..T15** | Evaluation Suite | Staleness, hysteresis, safe boot, math accuracy, and T13 lockout | **PASS** |

*See [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md) for full execution traces.*

---

## Firmware Safety Gate Reference

The ESP8266 firmware safety gate (`firmware/src/safety_gate.cpp`) enforces 8 mandatory checks before any relay transition is authorized:

```text
                        Inbound Proposed Action
                                  │
                   ┌──────────────▼──────────────┐
                   │ 1. Device in allowlist?     ├─ NO ──► Blocked (device_not_auto_eligible)
                   │    (light_01, fan_01 only)  │
                   └──────────────┬──────────────┘
                                 YES
                   ┌──────────────▼──────────────┐
                   │ 2. Mode == AUTO?            ├─ NO ──► Blocked (controller_in_manual_mode)
                   └──────────────┬──────────────┘
                                 YES
                   ┌──────────────▼──────────────┐
                   │ 3. Active manual hold?      ├─ YES ─► Blocked (manual_override_active)
                   │    (Within 600s of manual)  │
                   └──────────────┬──────────────┘
                                  NO
                   ┌──────────────▼──────────────┐
                   │ 4. Sensor fresh & valid?    ├─ NO ──► Blocked (sensor_data_stale_or_invalid)
                   │    (Age <= 60s, bounds ok)  │
                   └──────────────┬──────────────┘
                                 YES
                   ┌──────────────▼──────────────┐
                   │ 5. Min ON/OFF satisfied?    ├─ NO ──► Blocked (min_interval_violated)
                   │    (Contact protection)     │
                   └──────────────┬──────────────┘
                                 YES
                   ┌──────────────▼──────────────┐
                   │ 6. Duplicate or expired?    ├─ YES ─► Expired / Duplicate (reason_code)
                   │    (Ring buffer + NTP sync) │
                   └──────────────┬──────────────┘
                                  NO
                   ┌──────────────▼──────────────┐
                   │ 7. Redundant transition?    ├─ YES ─► Blocked (redundant_transition)
                   │    (e.g. OFF -> OFF)        │
                   └──────────────┬──────────────┘
                                  NO
                   ┌──────────────▼──────────────┐
                   │ 8. Device safeguards (T13)? ├─ NO ──► Blocked (ac_pc_power_off_blocked)
                   │    (AC compressor, PC data) │
                   └──────────────┬──────────────┘
                                 YES
                                  │
                    Relay Actuated + ACK Accepted
```

---

## Web Dashboard Features

The web dashboard is fully responsive, accessible over the local network, and operates completely offline with zero CDN dependencies:

1. **Live Telemetry Tab**: Real-time environmental readings (Temperature, Humidity, Light level, Motion), inferred room occupancy state, commanded appliance badges, and prominent staleness/offline alert banners.
2. **Events & History Tab**: Filterable device transition log (Manual, Local Rule, Server Proposal), daily runtime breakdown cards, and runtime session audit table.
3. **Anomalies & Alerts Tab**: Feed of active and acknowledged deterministic alerts with evidence payloads and operator acknowledge buttons.
4. **Control Tab**: Operating mode switcher (AUTO / MANUAL), manual appliance switches with AC/PC power-off safeguards, and live command ACK audit log.
5. **Settings & Calibration Tab**: Interactive LDR daylight sensor calibration wizard and threshold configuration.
6. **Analysis & Profiles Tab**: 24-hour hourly usage histogram (rendered via vendored Chart.js in Asia/Dhaka local time) and data-driven adaptive baseline monitor (Median + MAD).

---

## Physical Hardware Commissioning

For physical deployment on bench or office hardware, follow the step-by-step procedures in [`docs/HARDWARE_CHECKLIST.md`](docs/HARDWARE_CHECKLIST.md):
- Active-LOW relay coil polarity verification.
- Optocoupler isolation and flyback diode checks.
- Bootstrap pin precautions (`D3`/GPIO0 pullup, `D8`/GPIO15 pulldown).
- LDR physical calibration procedure.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
