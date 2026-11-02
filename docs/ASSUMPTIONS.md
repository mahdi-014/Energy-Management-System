# Operational and Hardware Assumptions Baseline
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026  

---

## 1. Architectural & Deployment Defaults

1. **Server Host**:
   - Primary target: Standard office PC running Windows or Linux with Docker & Docker Compose.
   - Secondary compatibility: Debian / Raspberry Pi OS on Raspberry Pi 3B/4/5.
   - All code is platform-agnostic (POSIX paths, UTC timestamps, portable SQLite).

2. **Server Runtime Environment**:
   - Containerized deployment via `deploy/docker-compose.yml` orchestrating `eclipse-mosquitto` and `fastapi`.
   - Native Python 3.11+ fallback supported directly via standard virtual environment and native Mosquitto installation.

3. **Network Architecture**:
   - Strictly isolated to the local office LAN (no public cloud or internet ingress).
   - MQTT broker runs on port 1883 with username and password authentication.
   - ESP8266 controller connects via 2.4 GHz WPA2-PSK Wi-Fi.
   - Time synchronization uses standard NTP (`pool.ntp.org` / `time.google.com`). If NTP is unreachable, the firmware marks telemetry as `time_unsynced` and rejects commands with expiry deadlines.

4. **Security & User Access**:
   - Authentication required for control actions (`POST /api/cmd`) and settings updates (`PUT /api/settings`).
   - Two default role tiers:
     - `admin`: Full access to manual control, policy reconfiguration, anomaly resolution, and system audit logs.
     - `viewer`: Read-only access to live status cards, telemetry history, and analysis charts.
   - Rate limiting enforced on login endpoints to prevent brute-force credential attacks.

---

## 2. Hardware Assumptions & `TODO_CONFIRM` Baseline

The hardware configuration is grounded in the existing prototype sketch discovered in the project archive (`Smart_Classroom_ESP8266_Blynk.ino`). Because physical access is not available to the software agent, every pin and electrical property remains marked `TODO_CONFIRM` until confirmed against the physical bench setup.

| Item | Assumed Prototype Value | `TODO_CONFIRM` Status | Rationale / Safety Note |
|---|---|:---:|---|
| **Controller** | NodeMCU ESP-12E (ESP8266) | Confirmed via sketch | 3.3V logic level, single analog ADC input (`A0`). |
| **PIR Sensor Pin** | `D5` (GPIO14) | `TODO_CONFIRM` | Standard active-HIGH digital motion pulse. Must confirm 3.3V logic level. |
| **LDR Sensor Pin** | `A0` (ADC0) | `TODO_CONFIRM` | Analog voltage divider (0 to 1023). Range 0–1.0V internal or 0–3.3V NodeMCU on-board divider. |
| **DHT11 Data Pin** | `D3` (GPIO0) | `TODO_CONFIRM` | Boot-strap pin! Requires external pull-up for boot. Recommend moving to `D6` (GPIO12) if boot hangs. |
| **Relay Light (`light_01`)** | `D0` (GPIO16) | `TODO_CONFIRM` | Active-LOW. Note: GPIO16 has no internal pull-up and has different wake-up circuitry. |
| **Relay Fan (`fan_01`)** | `D6` (GPIO12) | `TODO_CONFIRM` | Active-LOW. Safe standard GPIO pin. |
| **Relay PC (`pc_01`)** | `D7` (GPIO13) | `TODO_CONFIRM` | Active-LOW. Safe standard GPIO pin. |
| **Relay AC (`ac_01`)** | `D8` (GPIO15) | `TODO_CONFIRM` | Boot-strap pin! Must be pulled LOW during boot. Driving an active-LOW relay may invert boot level. |
| **I2C LCD Display** | SDA=`D2` (GPIO4), SCL=`D1` (GPIO5) | `TODO_CONFIRM` | Standard PCF8574 I2C bus at address `0x27`. Diagnostic display only. |
| **Relay Active Logic** | Active-LOW (`LOW = ON`, `HIGH = OFF`) | `TODO_CONFIRM` | Standard for optocoupled 4-channel relay boards. |
| **Relay Boot State** | All relays de-energized (OFF) | `TODO_CONFIRM` | Firmware drives all relay GPIOs `HIGH` immediately in `setup()` prior to peripheral/network initialization. |
| **Relay Load Limits** | Resistive loads only | `TODO_CONFIRM` | Direct switching of high-power AC compressor or PC PSU prohibited without interposing contactor. |

---

## 3. Operational Policy & Threshold Defaults

1. **Appliance Scope & Protection Matrix**:
   - `light_01`: Automation eligible (`autoEligible = true`). Permitted auto-OFF on vacancy (15 min) or confirmed daylight.
   - `fan_01`: Automation eligible (`autoEligible = true`). Permitted auto-OFF on confirmed vacancy (15 min).
   - `ac_01`: Strictly alert-only (`autoEligible = false`). Auto-switching prohibited. Dashboard manual power-OFF blocked by default (Test T13) to prevent compressor damage.
   - `pc_01`: Strictly alert-only (`autoEligible = false`). Auto-switching prohibited. Dashboard manual power-OFF blocked by default (Test T13) to prevent data corruption.
   - Default commissioning state: `auto_action_enabled = false` across **all** devices. System begins in 100% alert-only mode.

2. **Vacancy Detection Timing**:
   - Stage 1: No motion for 5 minutes (300 s) $\to$ Inferred state: `vacancy_candidate`.
   - Stage 2: No motion for 10 minutes (600 s) $\to$ Inferred state: `vacancy_candidate`, warning alert issued if device is ON.
   - Stage 3: No motion for 15 minutes (900 s) $\to$ Inferred state: `vacant_confirmed`. Re-evaluates safety gate; if eligible and enabled, proposes auto-OFF.

3. **Daylight Lighting Rule**:
   - Hysteresis required: Separate ON and OFF brightness thresholds (`LIGHT_ON_THRESHOLD`, `LIGHT_OFF_THRESHOLD`).
   - Confirmation window: Must remain continuously above threshold for 3 minutes (180 s) before proposing action.
   - Safety lock: Daylight automation is **strictly disabled** until in-room physical LDR calibration is marked complete (`calibration_flag = true`).

4. **Safety & Switching Constraints**:
   - Minimum ON time: 2 minutes (120 s) for fans, 5 minutes for AC (alert diagnostic).
   - Minimum OFF time: 1 minute (60 s).
   - Manual Override Hold: 10 minutes (600 s) following any manual command. During this hold, all automated commands for the device are rejected.
   - Rapid Cycling Diagnostic: >4 state changes in 10 minutes. Diagnostic warning only; never triggers a relay.

5. **Data Handling & Zero/Null Invariants**:
   - Missing or corrupted sensor readings are stored as `NULL`, never converted to `0`.
   - Stale sensor reading threshold: >60 seconds without fresh update flags data as invalid.
   - Interrupted device sessions (controller reboot, network outage) are recorded with `end_known = false` and reported separately.
