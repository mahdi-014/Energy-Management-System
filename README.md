# DC Office Single-Room Hybrid Energy Management System (DCEMS)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PlatformIO](https://img.shields.io/badge/PlatformIO-ESP8266-orange.svg)](https://platformio.org/)
[![Safety Gate](https://img.shields.io/badge/Safety_Gate-Authoritative-red.svg)](#core-safety-principles)

A safety-critical, explainable, hybrid IoT energy management system designed for a single representative DC Office room. DCEMS combines embedded local rule execution on an ESP8266 (NodeMCU), an authoritative 8-point firmware safety gate, and a fully self-hosted local server stack (Mosquitto MQTT, FastAPI, SQLite, and a web dashboard) that completely replaces third-party cloud platforms (e.g., Blynk).

---

## Core Safety Principles

> [!IMPORTANT]
> **1. The ESP8266 Embedded Controller Owns Physical Load Safety**  
> The backend server and web dashboard may only *propose* or *request* actions. Every state transition command must pass through the firmware's deterministic 8-point safety gate before a relay pin can be toggled. The server can never bypass this gate.

> [!WARNING]
> **2. AC and PC Loads are Strictly Alert-Only**  
> Abrupt mains power cutoff damages compressor motors (`ac_01`) and corrupts filesystems (`pc_01`). Both devices are locked to `autoEligible = false` at compile-time in firmware. Furthermore, manual power-off commands from the dashboard targeting AC or PC are blocked by default.

> [!NOTE]
> **3. Honest Engineering Labeling (No False AI or Energy Claims)**  
> - **Motion $\neq$ Presence**: *"PIR detects motion, not people."* Stationary occupants can result in zero motion pulses. Multi-stage grace periods are enforced.
> - **Commanded State $\neq$ Physical Current**: In the absence of physical CT current meters, all runtime durations ($T_{\text{runtime}} = t_{\text{OFF}} - t_{\text{ON}}$) are explicitly labeled:  
>   $$\text{"Estimate based on commanded state"}$$
> - **Zero Speculative Savings**: No speculative kWh, monetary savings, or machine-learning performance claims are generated.

---

## Hardware Prototype Grounding & Blynk Replacement

DCEMS directly preserves and enhances the physical circuit configuration verified in the team's prototype sketch (`firmware/legacy/Smart_Classroom_ESP8266_Blynk.ino`).

### Verified Physical Pin Mapping (NodeMCU ESP-12E)
| Appliance / Sensor | NodeMCU Pin | ESP8266 GPIO | Electrical Logic | Description |
|---|:---:|:---:|:---:|---|
| **PIR Motion Sensor** | `D5` | GPIO14 | Active-HIGH | Digital motion pulse detection. |
| **LDR Light Sensor** | `A0` | ADC0 | Analog (0–1023) | Moving-average filter (10 samples, 200ms interval). |
| **DHT11 Data** | `D3` | GPIO0 | Bi-directional | Room temperature and humidity. Requires pull-up. |
| **Relay Light (`light_01`)** | `D0` | GPIO16 | Active-LOW | Relay channel 1. Switched OFF at boot. |
| **Relay Fan (`fan_01`)** | `D6` | GPIO12 | Active-LOW | Relay channel 2. Switched OFF at boot. |
| **Relay PC (`pc_01`)** | `D7` | GPIO13 | Active-LOW | Relay channel 3. **Alert-Only**; power cut blocked. |
| **Relay AC (`ac_01`)** | `D8` | GPIO15 | Active-LOW | Relay channel 4. **Alert-Only**; power cut blocked. |
| **I2C LCD SDA** | `D2` | GPIO4 | I2C Data | 16x2 diagnostic character LCD (address `0x27`). |
| **I2C LCD SCL** | `D1` | GPIO5 | I2C Clock | 16x2 diagnostic character LCD clock. |

### How DCEMS Replaces Blynk
* **Cloud Broker $\to$ Local Mosquitto**: Replaces cloud reliance with private, authenticated LAN MQTT on port 1883.
* **Virtual Datastreams (V0..V7) $\to$ Structured MQTT JSON**: Telemetry published to `dcems/room1/sensors` and retained states to `dcems/room1/state`.
* **Unrestricted Controls (V8..V14) $\to$ Policy-Validated Actions**: Replaces raw manual sliders with a web dashboard backed by JWT authentication and the firmware safety gate.
* **Fake Energy Formulas $\to$ Descriptive Runtime Tracking**: Replaces hardcoded watt/tariff multipliers with transparent operational interval tracking.

---

## Repository Structure

```
Energy-Management-System/
├── deploy/                   # Production deployment orchestration
│   ├── docker-compose.yml    # Mosquitto broker + FastAPI service
│   ├── mosquitto.conf        # Authenticated LAN MQTT broker configuration
│   └── .env.example          # Environment configuration template
├── docs/                     # Engineering documentation and specifications
│   ├── ASSUMPTIONS.md        # Hardware pins, intervals, and defaults
│   ├── DECISIONS.md          # Architecture Decision Records (ADR-001..007)
│   ├── HARDWARE_CHECKLIST.md # Physical bench and mains safety checklist
│   ├── LIMITATIONS.md        # Measurement boundaries and PIR disclaimers
│   ├── PROTOCOL.md           # MQTT topics, JSON schemas, and reason codes
│   ├── SPEC_ANALYSIS.md      # Specification analysis and traceability matrix
│   ├── TEST_REPORT.md        # Living automated and manual test execution log
│   └── source/               # Original project proposal and specification PDFs
├── firmware/                 # Embedded C++ firmware (NodeMCU ESP8266)
│   ├── include/config.h      # Compile-time device table and pin constants
│   ├── include/secrets.example.h # Wi-Fi and MQTT credentials template
│   └── legacy/               # Original prototype sketch for reference
├── server/                   # Self-hosted backend service (Python 3.11+, FastAPI)
│   ├── app/
│   │   ├── auth.py           # PBKDF2 password hashing & JWT token validation
│   │   ├── config.py         # App settings & canonical device eligibility
│   │   ├── db.py             # SQLite WAL connection manager & migrations
│   │   └── main.py           # FastAPI routes and lifespan hooks
│   ├── migrations/           # Plain SQL schema and seed migrations (001, 002)
│   └── tests/                # Automated pytest suite (Unit, DB, Auth, Simulator)
├── simulator/                # Host-side hardware emulator
│   └── mock_esp.py           # Python ESP8266 mock with bounded queue & LWT
└── README.md                 # System overview and operational guide
```

---

## Getting Started

### 1. Prerequisites
- **Docker & Docker Compose** (Recommended for deployment) OR
- **Python 3.11+** and **Eclipse Mosquitto** (For native development)
- **Git**

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/mahdi-014/Energy-Management-System.git
cd Energy-Management-System

# Configure secrets
cp deploy/.env.example deploy/.env
cp firmware/include/secrets.example.h firmware/include/secrets.h
```

### 3. Running via Docker Compose
```bash
cd deploy
docker compose up -d
```
The FastAPI backend will automatically run migrations, seed initial users (`admin`, `viewer`), and expose the API and dashboard at `http://localhost:8000`.

### 4. Running the Test Suite (Native)
```bash
# Execute unit and integration tests
pytest server/tests -v
```

### 5. Running the Hardware Simulator
```bash
python simulator/mock_esp.py
```
The simulator connects to the Mosquitto broker, sets up Last Will and Testament, publishes online status and device state, and simulates sensor snapshots on `dcems/room1/sensors`.

---

## Implementation Roadmap

- [x] **Phase 0: Project Scaffold, Protocol, Database & Docker Setup** *(Completed)*
  - Reconciled specs, documented architecture, generated migrations (10 tables), built auth system, verified simulator bounded queue (20/20 tests passing).
- [ ] **Phase 1: Monitor-Only Telemetry Pipeline** *(Next)*
  - Non-blocking firmware sensors (PIR, LDR MA filter, DHT11), MQTT client, Live dashboard page, LWT offline banner.
- [ ] **Phase 2: State Tracking, Event Logging & Runtime Calculations**
  - Retained state tracking, bounded RAM queue with `data_gap`, hand-calculated runtime session fixtures ($T = t_{\text{OFF}} - t_{\text{ON}}$).
- [ ] **Phase 3: Alert-Only Anomaly Detectors & Calibration Helper**
  - 5 explainable detectors (Vacancy stages, Daylight waste, Long runtime, Rapid cycling, Sensor quality), Alerts page, calibration profile.
- [ ] **Phase 4: Controlled Automation & Authoritative Firmware Safety Gate**
  - 8-point pure C++ safety gate, manual override holds, AC/PC power-off lockout (Test T13), command/ack path.
- [ ] **Phase 5: Descriptive Analysis, Evaluation, Backup & Final Verification**
  - Daily runtime breakdown, potential waste overlap, SQLite backup/restore scripts, complete test report.

