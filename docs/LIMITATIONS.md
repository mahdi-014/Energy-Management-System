# System Constraints, Boundaries & Limitations
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026  

---

## 1. Sensor Measurement Limitations

### 1.1 PIR Motion Sensor Inherent Characteristics
> [!IMPORTANT]
> **Core Principle**: A PIR sensor detects changes in infrared radiation caused by moving heat sources across optical zones. It **does not** detect human presence, count occupants, or identify living individuals who remain stationary.

* **Stationary Occupant Limitation**: An office worker sitting still at a desk, typing quietly, or reading documentation produces minimal thermal displacement. The PIR sensor output will fall to `LOW` (no motion).
* **Mitigation**: The system must never immediately trigger shutdowns upon motion absence. It utilizes conservative multi-stage grace periods (5 min candidate $\to$ 10 min warning $\to$ 15 min action evaluation) and prominent disclaimers in the user interface.
* **Environmental False Triggers**: Rapid room thermal gradients caused by direct sunlight sweeps, HVAC drafts, or curtain flutter can cause false positive motion pulses.

### 1.2 LDR Light Sensor Characteristics
* **Uncalibrated Analog Voltage**: An LDR (photoresistor) configured in a voltage divider outputs a non-linear resistance change mapped through an analog-to-digital converter (0 to 1023).
* **Relative Indicator Only**: The reading reflects ambient illuminance at the sensor's specific mounting location, angle, and distance from light sources. It **is not** a calibrated illuminance reading in lux ($lx$) or lumens.
* **Calibration Prerequisite**: Daylight-based automation is strictly disabled until the physical sensor is calibrated within the specific room geometry and an explicit calibration confirmation flag is toggled.

### 1.3 DHT11 Environmental Sensor Characteristics
* **Resolution & Accuracy**: The DHT11 has a temperature accuracy of $\pm 2.0^\circ\text{C}$ ($0^\circ\text{C}$ to $50^\circ\text{C}$) and humidity accuracy of $\pm 5\%$ RH ($20\%$ to $90\%$).
* **Sampling Frequency Limit**: The sensor must not be polled faster than once every 1–2 seconds. Polling faster results in stale or self-heated erroneous data.

---

## 2. Power, Energy & Savings Disclaimer

### 2.1 Absence of Power Metering Hardware
* The prototype hardware controls relay contacts but **lacks dedicated electrical power or energy transducers** (such as PZEM-004T, ADE7753, or Current Transformers [CTs]).
* Consequently, the system **cannot**:
  1. Measure instantaneous real power in Watts ($W$) or apparent power in Volt-Amperes ($VA$).
  2. Measure cumulative energy consumption in kilowatt-hours ($kWh$).
  3. Quantify verified monetary utility bill savings in BDT or any currency.
  4. Verify whether a physical load is actively drawing current or if a local appliance switch is manually turned off.

### 2.2 Definition of Operating Duration (Runtime)
* All operational runtime durations presented by the system ($T_{\text{runtime}} = t_{\text{OFF}} - t_{\text{ON}}$) are derived solely from **commanded relay states**.
* **Mandatory Labeling**: Every runtime metric, table, and visualization in documentation and user interfaces is strictly labeled:
  $$\text{"Estimate based on commanded state"}$$
* Under no circumstances shall runtime hours be converted into speculative kilowatt-hours or financial savings.

---

## 3. Appliance Control & Safety Boundaries

### 3.1 Air Conditioner (`ac_01`) Protection
* Mains relays cannot safely modulate or control compressor operation. Abruptly interrupting mains power to a running compressor causes high refrigerant head pressure, motor stall, thermal overload, and permanent compressor damage.
* `ac_01` is strictly restricted to **Alert-Only**. Automated switching is disabled in firmware and policy.

### 3.2 Personal Computer (`pc_01`) Protection
* Abruptly cutting 230V AC mains power to a personal computer or office workstation causes unsaved buffer loss, file system corruption, and database integrity failures.
* `pc_01` is strictly restricted to **Alert-Only**. Forced shutdown via relay is completely prohibited.

---

## 4. Architectural & Deployment Boundaries

* **Single-Room Pilot Scope**: This MVP is engineered for a single representative room (`room1`). It does not include building-level aggregation, hierarchical multi-room scheduling, or microgrid power shedding.
* **Local LAN Boundary**: The MQTT broker and FastAPI service are designed strictly for private office intranet operation. The system must not be exposed to the public internet without an enterprise reverse proxy, TLS encryption, and hardened OAuth2/OIDC single sign-on.
