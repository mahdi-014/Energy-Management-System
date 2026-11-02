# Specification Analysis & Requirements Baseline
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Status**: Step 1 Analysis Baseline  
**Date**: November 2, 2026  

---

## 1. Merged Requirements Summary
Both source documents (`Project_Details.pdf` [Doc 1] and `DC_office_EMS_peoject.pdf` [Doc 2]) align on the core vision, domain constraints, and fundamental safety architecture:

1. **Scope & Deployment**:
   - Single representative DC office room deployment.
   - 4 discrete appliance categories: `light_01`, `fan_01`, `ac_01`, `pc_01`.
   - Core sensor suite: PIR motion sensor, LDR ambient light sensor, DHT11 temperature and humidity sensor.
   - Strictly out of scope: Direct electrical power/kWh metering, verified monetary savings claims, accurate headcount estimation via PIR, on-device ML/AI, automatic AC temperature control, light dimming, graceful PC OS shutdown, multi-room networking, and internet-exposed control.

2. **Core Architectural Principle (Safety-First Hybrid Control)**:
   - Local rule-based control runs on the ESP8266 for reliability and fail-safety.
   - Backend service performs storage, descriptive analytics, and anomaly detection.
   - Detection $\neq$ Authorization: Detecting an anomaly never directly flips a relay.
   - Authority boundary: The ESP8266 owns safety. The backend may only propose actions. Every action must pass the firmware safety gate, which evaluates local rules, sensor freshness, mode, manual holds, and device allowlists. The server cannot bypass this gate.
   - Fail-Safe & Autonomous Offline Operation: Local rules continue running during server or network outages. Events are held in a bounded RAM queue; on overflow, a `data_gap` event is logged rather than losing data silently.

3. **Occupancy & Sensor Reality**:
   - PIR detects motion, not presence or headcount. Stationary occupants can result in no motion. Vacancy rules must incorporate multi-stage grace periods (e.g., 5 min candidate, 10 min warning, 15 min action evaluation).
   - Daylight evaluation requires LDR calibration in the physical room, hysteresis, confirmation intervals (e.g. 3 min), and must remain disabled until calibrated.
   - Missing or invalid sensor data must be stored as `NULL` (never as `0`) with a validity flag, and must immediately suppress dependent automatic actions while generating a `sensor_quality` event.

4. **Auditability & Honest Labeling**:
   - Operating durations are calculated from commanded relay transitions ($T_{\text{runtime}} = t_{\text{OFF}} - t_{\text{ON}}$) and must always be labeled: *"estimate based on commanded state"*.
   - Unclosed sessions caused by reboots or outages must be explicitly flagged with `end_known = false` and reported separately.
   - Every state change, proposed action, allowed action, and blocked action must record a unique ID, timestamp, and machine-readable `reason_code`.

---

## 2. Conflicts & Discrepancies Resolution Matrix
Where the two documents differ, we adhere to the governing rule: **choose the more conservative, safer option**, record the rationale in `docs/DECISIONS.md`, and notify the user.

| # | Topic | Document 1 (`Project_Details.pdf`) | Document 2 (`DC_office_EMS_peoject.pdf`) & Task Spec | Chosen Option | Rationale / Decision Record Reference |
|---|---|---|---|---|---|
| 1 | **Backend & Cloud Platform** | Suggests retaining Blynk IoT platform for monitoring/dashboard alongside external backend. | Mandates a fully self-hosted stack: Eclipse Mosquitto (MQTT), FastAPI, SQLite, and vanilla HTML/JS dashboard. | **Self-Hosted Stack (Mosquitto + FastAPI + SQLite)** | Eliminates external cloud dependencies, prevents data leakage outside the DC Office LAN, avoids third-party API rate limits, and guarantees local-only command paths. |
| 2 | **Messaging Transport** | Suggests MQTT or HTTP REST for controller-to-backend communication. | Locks MQTT + JSON over Eclipse Mosquitto on LAN with username/password auth. | **MQTT + JSON (Mosquitto)** | Provides lightweight, bi-directional, event-driven pub/sub, Last Will and Testament (LWT) for instant offline detection, and decoupled buffering. |
| 3 | **Branding & "AI" Terminology** | Uses "Single-Room Hybrid AI Energy Management System". | Focuses on explainable, transparent rule-based detection and descriptive statistics; explicitly forbids "AI-powered" claims. | **Deterministic, Explainable Rule & Statistical Engine** | Safety-critical systems require deterministic auditability. No black-box ML claims. The UI and docs will label logic transparently as rules, thresholds, and statistical baselines (median + MAD). |
| 4 | **AC & PC Control Authority** | Notes AC and PC as alert-only for vacancy; leaves dashboard manual override ambiguous. | Strictly enforces AC/PC as monitor/alert-only. Test T13 explicitly requires dashboard power-off commands for AC and PC to be **blocked**. | **Strict Alert-Only & Power-Off Blocked for AC/PC** | Abruptly cutting mains power to an AC compressor can destroy the compressor or void warranties; cutting PC power causes operating system corruption and data loss. Both are compile-time blocked in firmware safety gate (`autoEligible = false`) and rejected by policy on the dashboard/server. |
| 5 | **Daylight Automation Activation** | Notes daylight detection as an initial feature. | Mandates daylight automation is strictly **disabled** until physical in-room LDR calibration is completed and confirmed via setting flag. | **Disabled by Default Until Calibrated** | Uncalibrated photoresistors vary widely by ADC voltage divider, ambient window angle, and indoor lighting reflections. Running automation uncalibrated causes severe false cycling. |
| 6 | **Event Buffering & Storage** | Suggests optional persistent buffering on controller flash memory. | Cautions against frequent flash writes due to ESP8266 flash endurance limits; specifies a bounded RAM ring buffer with explicit `data_gap` events on overflow. | **Bounded RAM Buffer with `data_gap` Notification** | Prevents flash wear-out on the ESP8266 EEPROM/SPIFFS while maintaining full auditability of lost data during extended network outages. |
| 7 | **Initial Automation State** | Example policy lists `auto_action_enabled = true` for fan. | Mandates `auto_action_enabled = false` (alert-only) across **all** devices at initial deployment. | **Alert-Only Default (`auto_action_enabled = false`)** | Safe commissioning protocol. Automation is enabled per device by administrators only after observation and test passage. |

---

## 3. Requirements Traceability Matrix
This matrix maps every Functional Requirement (FR-01 to FR-18), Test Case (TC-01 to TC-12), and Planned Evaluation Test (T1 to T15) to its implementation phase, target files, and verification method.

### 3.1 Functional Requirements (FR-01 to FR-18)
| Req ID | Requirement Description | Phase | Implementing Files | Test / Verification Files | Notes & Constraints |
|---|---|:---:|---|---|---|
| **FR-01** | Unique device identification (`light_01`, `fan_01`, `ac_01`, `pc_01`) | Phase 0 | `firmware/include/config.h`, `server/app/config.py` | `server/tests/test_config.py` | Standardized canonical strings across C++ and Python. |
| **FR-02** | Record available sensor readings with UTC timestamps | Phase 1 | `firmware/src/sensors.cpp`, `firmware/src/mqtt_comm.cpp`, `server/app/mqtt_client.py`, `server/app/db.py` | `server/tests/test_sensor_ingestion.py` | Device time via NTP + server receipt time; UTC epoch seconds. |
| **FR-03** | Record requested device state changes and sources (`manual`, `local_rule`, `server_proposal`) | Phase 2 | `firmware/src/state.cpp`, `server/app/db.py`, `server/app/main.py` | `server/tests/test_state_logging.py`, `firmware/test/test_state.cpp` | Logged to `device_state_events` table. |
| **FR-04** | Calculate operating duration from recorded ON and OFF events | Phase 2 | `server/app/analysis.py`, `server/app/db.py` | `server/tests/test_runtime_calc.py` | Hand-calculated fixture validation; $T = t_{\text{OFF}} - t_{\text{ON}}$; open sessions flagged. |
| **FR-05** | Identify potential waste during confirmed/suspected vacancy | Phase 3 | `server/app/detectors/vacancy.py`, `firmware/src/rules.cpp` | `server/tests/test_detector_vacancy.py`, `firmware/test/test_rules.cpp` | Multi-stage: 5m candidate, 10m warning, 15m action re-eval. |
| **FR-06** | Identify potential daylight-related lighting waste after calibration | Phase 3 | `server/app/detectors/daylight.py`, `firmware/src/rules.cpp` | `server/tests/test_detector_daylight.py`, `firmware/test/test_rules.cpp` | Requires calibration flag = true, 3m confirmation, hysteresis. |
| **FR-07** | Identify configured maximum-runtime violations | Phase 3 | `server/app/detectors/runtime.py` | `server/tests/test_detector_runtime.py` | Configurable per device; info severity (does not prove waste). |
| **FR-08** | Identify unusually frequent ON/OFF transitions (>4 in 10m) | Phase 3 | `server/app/detectors/cycling.py` | `server/tests/test_detector_cycling.py` | Diagnostic only. Never triggers relay switching. |
| **FR-09** | Store anomaly type, severity, evidence (JSON), detection method | Phase 3 | `server/app/db.py`, `server/app/detectors/base.py` | `server/tests/test_anomaly_storage.py` | Persisted in `anomaly_events` table. |
| **FR-10** | Generate alerts for configured anomaly conditions with dedup/cooldown | Phase 3 | `server/app/detectors/base.py`, `server/app/main.py` | `server/tests/test_alert_cooldown.py` | One open alert per device+type; suppress spam during active condition. |
| **FR-11** | Support device-specific automatic control permissions and versions | Phase 4 | `firmware/src/safety_gate.cpp`, `server/app/policy.py`, `server/app/db.py` | `firmware/test/test_safety_gate.cpp`, `server/tests/test_policy.py` | Independent policies in `device_policies` table; `autoEligible` in firmware. |
| **FR-12** | Support manual override and manual hold period | Phase 4 | `firmware/src/safety_gate.cpp`, `firmware/src/state.cpp`, `server/app/policy.py` | `firmware/test/test_safety_gate.cpp`, `server/tests/test_override.py` | Manual command resets manual hold timer (e.g. 10m hold). |
| **FR-13** | Reject automatic actions that violate local policy | Phase 4 | `firmware/src/safety_gate.cpp` | `firmware/test/test_safety_gate.cpp` | 8-point firmware safety gate executes on ESP8266; server cannot bypass. |
| **FR-14** | Log reason for every automatic action or rejected proposal | Phase 4 | `firmware/src/safety_gate.cpp`, `server/app/db.py` | `firmware/test/test_safety_gate.cpp`, `server/tests/test_control_actions.py` | Logged in `control_actions` and firmware serial/events. |
| **FR-15** | Maintain local rule-based operation during backend/network failure | Phase 1 & 4 | `firmware/src/rules.cpp`, `firmware/src/mqtt_comm.cpp` | `simulator/tests/test_e2e_offline.py` | Autonomous loop continues; RAM queue buffers events; `data_gap` on overflow. |
| **FR-16** | Identify missing/invalid sensor data and suppress unsafe actions | Phase 1 & 3 | `firmware/src/sensors.cpp`, `server/app/detectors/sensor_quality.py`, `firmware/src/safety_gate.cpp` | `firmware/test/test_safety_gate.cpp`, `server/tests/test_sensor_quality.py` | Sensor staleness/bounds check triggers `sensor_issue` and blocks auto OFF. |
| **FR-17** | Support historical data analysis when sufficient records exist | Phase 5 (Ph 6 opt) | `server/app/analysis.py` | `server/tests/test_analysis.py` | Runtime aggregates, waste time overlap, optional median+MAD baseline. |
| **FR-18** | Distinguish estimated runtime indicators from measured energy | Phase 1..5 | `dashboard/`, `server/app/analysis.py`, `docs/` | `server/tests/test_labels.py` | Explicit labeling: "estimate based on commanded state", no kWh/cost claims. |

---

### 3.2 Test Cases (TC-01 to TC-12)
| Test ID | Test Scenario | Expected Result | Phase | Test Implementation File | Verification Type |
|---|---|---|:---:|---|---|
| **TC-01** | Device changes OFF $\to$ ON | Timestamped state event recorded in DB | Phase 2 | `server/tests/test_state_logging.py` | Automated Pytest / Simulator |
| **TC-02** | Device changes ON $\to$ OFF | Completed runtime session calculated and stored | Phase 2 | `server/tests/test_runtime_calc.py` | Automated Pytest / Fixtures |
| **TC-03** | No PIR motion for vacancy period with eligible device ON | Vacancy anomaly + alert generated according to policy | Phase 3 | `server/tests/test_detector_vacancy.py` | Automated Pytest / Simulator |
| **TC-04** | Ambient daylight above calibrated threshold while light ON | Daylight alert generated after confirmation interval | Phase 3 | `server/tests/test_detector_daylight.py` | Automated Pytest / Simulator |
| **TC-05** | Device exceeds configured maximum runtime | Long-runtime anomaly recorded (info severity) | Phase 3 | `server/tests/test_detector_runtime.py` | Automated Pytest |
| **TC-06** | Device exceeds rapid-cycling threshold (>4 in 10 min) | Diagnostic anomaly generated | Phase 3 | `server/tests/test_detector_cycling.py` | Automated Pytest |
| **TC-07** | Manual override active when auto action proposed | Action blocked by safety gate; reason logged | Phase 4 | `firmware/test/test_safety_gate.cpp` | Native C++ Host Test & Pytest |
| **TC-08** | Required sensor data missing or invalid | Unsafe actions suppressed; `sensor_issue` logged | Phase 4 | `firmware/test/test_safety_gate.cpp` | Native C++ Host Test & Pytest |
| **TC-09** | Backend or internet connection lost | Local supported rules continue; events buffered | Phase 1 & 4 | `firmware/test/test_mqtt_comm.cpp` | Simulator & Native Test |
| **TC-10** | Expired or duplicate control command received | Controller rejects command with reason code | Phase 4 | `firmware/test/test_safety_gate.cpp` | Native C++ Host Test & Pytest |
| **TC-11** | AC or PC vacancy anomaly detected | Alert generated; unauthorized shutdown prevented | Phase 3 & 4 | `server/tests/test_policy.py`, `firmware/test/test_safety_gate.cpp` | Native C++ Host Test & Pytest |
| **TC-12** | Automatic action allowed and executed | Proposed state, policy decision, result, and reason logged | Phase 4 | `simulator/tests/test_e2e_automation.py` | End-to-End Simulator Test |

---

### 3.3 Planned Evaluation Tests (T1 to T15)
| Test ID | Test Scenario | Phase | Verification Method & File | Classification |
|---|---|:---:|---|---|
| **T1** | Sensor readings (PIR, LDR, DHT11 normal updates) | Phase 1 | `server/tests/test_sensor_ingestion.py` & Live Page | PASS (Simulated) / **NEEDS-HARDWARE** (Bench) |
| **T2** | Vacancy stages (5m candidate, 10m warning, 15m action) | Phase 3 | `server/tests/test_detector_vacancy.py` | PASS (Simulated & Unit) |
| **T3** | Stationary occupant behavior (PIR stillness) | Phase 3 | Documented in `docs/LIMITATIONS.md` & UI warning | **NEEDS-HARDWARE** (Physical human stillness) |
| **T4** | Daylight threshold (dim vs bright after calibration) | Phase 3 | `server/tests/test_detector_daylight.py` | PASS (Simulated) / **NEEDS-HARDWARE** (Lux meter) |
| **T5** | Hysteresis (light cycling around threshold) | Phase 3 | `firmware/test/test_rules.cpp` & `server/tests/test_hysteresis.py` | PASS (Unit & Simulated) |
| **T6** | Manual override priority over automation | Phase 4 | `firmware/test/test_safety_gate.cpp` | PASS (Unit & Simulated) |
| **T7** | AC/PC restriction (no power cut on vacancy) | Phase 4 | `firmware/test/test_safety_gate.cpp` | PASS (Unit & Simulated) |
| **T8** | Sensor/network fault (disconnect sensor/link) | Phase 1 & 4 | `server/tests/test_sensor_quality.py`, `firmware/test/test_safety_gate.cpp` | PASS (Simulated) / **NEEDS-HARDWARE** (Wire pull) |
| **T9** | Event & runtime log consistency | Phase 2 | `server/tests/test_runtime_calc.py` | PASS (Automated Fixture) |
| **T10** | Controller restart & safe boot recovery | Phase 1 | Firmware boot test / Simulator reboot | PASS (Simulated) / **NEEDS-HARDWARE** (Mains bounce) |
| **T11** | Server outage resilience & event queue catch-up | Phase 2 | `simulator/tests/test_e2e_offline.py` | PASS (Automated E2E) |
| **T12** | Storage integrity (DB rows vs emitted messages) | Phase 2 | `server/tests/test_storage_integrity.py` | PASS (Automated E2E) |
| **T13** | Command path validation (AC/PC power-off blocked) | Phase 4 | `server/tests/test_api_control.py` & `firmware/test/test_safety_gate.cpp` | PASS (Unit & Integration) |
| **T14** | Analysis accuracy (hand-calculated verification) | Phase 5 | `server/tests/test_analysis_accuracy.py` | PASS (Automated Fixture Math) |
| **T15** | Access control & auth enforcement | Phase 0 & 4 | `server/tests/test_auth.py` | PASS (Automated API Test) |

---

## 4. Unknown Hardware Facts (`TODO_CONFIRM`)
Because we cannot touch the physical hardware, the following hardware details are marked `TODO_CONFIRM` in `firmware/include/config.h` and documented in `docs/HARDWARE_CHECKLIST.md` and `docs/ASSUMPTIONS.md`. Sensible software defaults are assumed for simulation and compilation:

1. **Microcontroller Board Pin Mapping**:
   - `PIR_PIN`: Assumed `D5` (GPIO14). Must confirm actual board header.
   - `DHT_PIN`: Assumed `D6` (GPIO12). Must confirm DHT model (DHT11 vs DHT22) and pin.
   - `LDR_PIN`: Assumed `A0` (ADC0, 0-1.0V internal or 0-3.3V NodeMCU divider).
   - `RELAY_LIGHT_PIN`: Assumed `D1` (GPIO5).
   - `RELAY_FAN_PIN`: Assumed `D2` (GPIO4).
   - `RELAY_AC_PIN`: Assumed `D7` (GPIO13).
   - `RELAY_PC_PIN`: Assumed `D8` (GPIO15 - note: GPIO15 requires external pull-down to boot).
   - *Boot-Strap Warning*: Pins GPIO0 (D3), GPIO2 (D4), and GPIO15 (D8) alter ESP8266 boot modes. Avoid using GPIO0/GPIO2 for relays to prevent relay chatter during reboot.
2. **Relay Trigger Logic**:
   - Active-LOW (`LOW = Relay ON`, `HIGH = Relay OFF`) is standard on most 4-channel optocoupled relay modules. Assumed active-LOW with `RELAY_ACTIVE_LEVEL = LOW`. Must confirm against physical module.
3. **Relay Initial Boot State**:
   - NodeMCU GPIOs default to input/floating during power-on reset. Relays must be held in the de-energized (OFF) state during boot prior to WiFi connection.
4. **LDR Calibration Curve & Voltage Divider**:
   - Raw ADC reading range is 0 to 1023. Daylight threshold and dark threshold are marked `TODO_CONFIRM` (default placeholders: Day > 700, Dark < 300). Daylight rule remains disabled until calibration.
5. **Sensor Voltage Compatibility & Pull-Ups**:
   - DHT11 data line requires a 4.7kΩ–10kΩ pull-up resistor to 3.3V. PIR sensor output must be 3.3V logic (some 5V PIR modules output 3.3V on OUT, others output 5V which requires a voltage divider before ESP8266 GPIO).
6. **Relay Contact Ratings & Load Isolation**:
   - 10A 250VAC relays cannot directly switch inductive loads like 1.5–2 ton AC compressors or high-power room heaters without an intermediate industrial contactor.

