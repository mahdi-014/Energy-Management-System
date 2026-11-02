# Operational and Hardware Assumptions Baseline
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026 (Updated with Verified Prototype Code)  

---

## 1. Grounding in the Hardware Prototype
The hardware design, pin mapping, sensor signal processing, and display interfaces are directly grounded in the physical prototype sketch provided by the project team (`firmware/legacy/Smart_Classroom_ESP8266_Blynk.ino`):

### 1.1 Verified Physical Pin Mapping
| Appliance / Sensor | NodeMCU Pin | ESP8266 GPIO | Verification Status | Operational & Boot Characteristics |
|---|:---:|:---:|:---:|---|
| **PIR Motion Sensor** | `D5` | GPIO14 | **VERIFIED** | Active-HIGH digital motion pulse. Safe standard GPIO. |
| **LDR Light Sensor** | `A0` | ADC0 | **VERIFIED** | Analog input (0–1023). Moving-average filter over 10 samples (polled every 200 ms). |
| **DHT11 Data** | `D3` | GPIO0 | **VERIFIED** | Active data bus. **Boot-strap pin**: requires external pull-up for boot. |
| **Relay Light (`light_01`)** | `D0` | GPIO16 | **VERIFIED** | Active-LOW relay driver. Initialized to `HIGH` (OFF) at power-on. |
| **Relay Fan (`fan_01`)** | `D6` | GPIO12 | **VERIFIED** | Active-LOW relay driver. Initialized to `HIGH` (OFF) at power-on. |
| **Relay PC (`pc_01`)** | `D7` | GPIO13 | **VERIFIED** | Active-LOW relay driver. Initialized to `HIGH` (OFF) at power-on. |
| **Relay AC (`ac_01`)** | `D8` | GPIO15 | **VERIFIED** | Active-LOW relay driver. **Boot-strap pin**: must be pulled LOW during boot. |
| **I2C LCD SDA** | `D2` | GPIO4 | **VERIFIED** | LiquidCrystal_I2C (address `0x27`, 16x2 characters). |
| **I2C LCD SCL** | `D1` | GPIO5 | **VERIFIED** | LiquidCrystal_I2C clock line. |

### 1.2 Verified Relay Control Logic
- Optocoupled 4-channel module operates on **active-LOW** logic:
  $$\text{RELAY\_ON} = \text{LOW} \ (0\text{V}), \quad \text{RELAY\_OFF} = \text{HIGH} \ (3.3\text{V})$$
- In `setup()`, all 4 relay GPIO pins are driven `HIGH` (de-energized) before network or peripheral initialization to eliminate startup chatter.

---

## 2. Replacing Blynk with Self-Hosted Stack

The legacy prototype relied on Blynk cloud services and virtual pins. DCEMS completely replaces the Blynk stack with self-hosted LAN components:

| Legacy Blynk Component | DCEMS Self-Hosted Replacement | Key Improvement & Safety Enhancement |
|---|---|---|
| **Blynk Cloud Broker** | **Eclipse Mosquitto (LAN)** | Zero external internet dependency, full local data ownership, LAN-only isolation. |
| **V0: Temperature** | `dcems/room1/sensors` $\to$ `temperature_c` | Stored in SQLite with UTC epoch timestamps. Missing readings stored as `NULL`. |
| **V1: Humidity** | `dcems/room1/sensors` $\to$ `humidity_pct` | Plausible bounds check ($20\% \le \text{hum} \le 90\%$). |
| **V2: Room Light** | `dcems/room1/sensors` $\to$ `ldr_raw` & `ambient_light_level` | Moving-average filtered ADC + calibrated percentage. |
| **V3: Motion State** | `dcems/room1/sensors` $\to$ `pir_motion` & `last_motion_at` | Explains motion detection vs human presence. Inferred occupancy states. |
| **V4..V7: Device Statuses** | `dcems/room1/state` (Retained MQTT) | Commanded vs observed state separation (`assumed`/`confirmed`). |
| **V8: Manual Mode Switch** | Dashboard Control Toggle $\to$ `dcems/room1/cmd` | Authoritative firmware safety gate validates transitions. |
| **V9..V12: Relay Controls** | Dashboard Manual Controls $\to$ `dcems/room1/cmd` | Passes firmware 8-point safety gate. **AC and PC power-off blocked by default (T13)**. |
| **V13..V14: Sliders** | Settings API $\to$ `config` Table | Audit-logged settings changes with versioning and validation. |
| **Speculative kWh/Cost Calculation** | **Descriptive Runtime Only ($T = t_{\text{OFF}} - t_{\text{ON}}$)** | Eliminates misleading energy/tariff claims; strictly labeled *"estimate based on commanded state"*. |

---

## 3. Operational Policy & Threshold Defaults

1. **Appliance Protection Matrix**:
   - `light_01`: Automation eligible (`autoEligible = true`). Permitted auto-OFF on vacancy (15 min) or confirmed daylight.
   - `fan_01`: Automation eligible (`autoEligible = true`). Permitted auto-OFF on confirmed vacancy (15 min).
   - `ac_01`: Strictly alert-only (`autoEligible = false`). Auto-switching prohibited. Dashboard manual power-OFF blocked by default (Test T13) to prevent compressor damage.
   - `pc_01`: Strictly alert-only (`autoEligible = false`). Auto-switching prohibited. Dashboard manual power-OFF blocked by default (Test T13) to prevent filesystem corruption.
   - Default commissioning state: `auto_action_enabled = false` across **all** devices. System begins in 100% alert-only mode.

2. **Vacancy Detection Timing**:
   - Stage 1: No motion for 5 minutes (300 s) $\to$ `vacancy_candidate`.
   - Stage 2: No motion for 10 minutes (600 s) $\to$ `vacancy_candidate`, warning alert issued if device is ON.
   - Stage 3: No motion for 15 minutes (900 s) $\to$ `vacant_confirmed`. Re-evaluates safety gate; if eligible and enabled, proposes auto-OFF.

3. **Daylight Lighting Rule**:
   - Hysteresis required: Separate ON and OFF brightness thresholds (`LIGHT_ON_THRESHOLD`, `LIGHT_OFF_THRESHOLD`).
   - Confirmation window: Must remain continuously above threshold for 3 minutes (180 s) before proposing action.
   - Safety lock: Daylight automation is **strictly disabled** until in-room physical LDR calibration is marked complete (`calibration_flag = true`).

4. **Safety & Switching Constraints**:
   - Minimum ON time: 2 minutes (120 s) for fans.
   - Minimum OFF time: 1 minute (60 s).
   - Manual Override Hold: 10 minutes (600 s) following any manual command. During this hold, all automated commands for the device are rejected.
   - Rapid Cycling Diagnostic: >4 state changes in 10 minutes. Diagnostic warning only; never triggers a relay.

5. **Data Handling & Zero/Null Invariants**:
   - Missing or corrupted sensor readings are stored as `NULL`, never converted to `0`.
   - Stale sensor reading threshold: >60 seconds without fresh update flags data as invalid.
   - Interrupted device sessions (controller reboot, network outage) are recorded with `end_known = false` and reported separately.
