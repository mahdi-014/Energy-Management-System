# Architecture Decision Records (ADRs)
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026  

---

## ADR-001: Local Safety Gate Authority over Server Proposals
* **Status**: Accepted
* **Context**: The system controls mains-voltage relays connected to lighting, cooling, and computing equipment. Network links, Wi-Fi connections, and server processes are subject to latency, packet drops, bugs, and crashes.
* **Decision**: The ESP8266 embedded controller is the sole and authoritative safety boundary. The server and dashboard may only *propose* or *request* actions. The firmware executes a deterministic 8-point safety gate on every inbound command (`cmd`) and every local rule. The server cannot bypass the safety gate under any circumstance.
* **Consequences**: Protects electrical and computer loads even if the backend is compromised or offline. Requires pure C++ domain logic with 100% host unit test coverage.

---

## ADR-002: Self-Hosted MQTT + FastAPI + SQLite Architecture (Superseding Blynk)
* **Status**: Accepted
* **Context**: Earlier prototypes explored cloud-hosted platforms such as Blynk. However, the DC Office environment requires local data governance, strict network isolation, complete auditability, and zero recurring cloud dependencies.
* **Decision**: Adopt a fully self-hosted stack running inside the DC Office LAN: Eclipse Mosquitto (MQTT broker with username/password authentication), FastAPI (Python 3.11+ backend service), SQLite (single-file relational database with WAL mode), and vanilla HTML/JS dashboard with locally vendored Chart.js.
* **Consequences**: Entire system operates without internet access. Eliminates cloud latency, third-party terms, and rate limits. Requires local backup scripts and host-level service management.

---

## ADR-003: Strict Lockout of AC and PC Power-Off Automation (Test T13)
* **Status**: Accepted
* **Context**: Cutting mains power abruptly to an air conditioning compressor can cause head-pressure stalling, motor burnout, or trip branch circuit breakers. Abruptly disconnecting power to a desktop computer causes filesystem corruption and immediate loss of unsaved operator data.
* **Decision**: Both `ac_01` and `pc_01` are locked to **Alert-Only**. The firmware enforces `autoEligible = false` as a compile-time constant for these devices. Furthermore, per specification Test Case T13, manual power-off commands from the dashboard/API targeting AC and PC are blocked by default.
* **Consequences**: Prevents accidental hardware destruction or data loss. Future AC control will require an IR blaster or smart thermostat interface; future PC control will require OS-level ACPI graceful shutdown.

---

## ADR-004: Bounded RAM Queue with `data_gap` Notification (Flash Endurance Protection)
* **Status**: Accepted
* **Context**: When the network or MQTT broker is disconnected, the ESP8266 must handle unsent state changes and sensor events. Frequent writes to ESP8266 onboard flash (SPIFFS/EEPROM) wear out flash memory sectors rapidly (typically rated for ~10,000–100,000 write cycles).
* **Decision**: Buffer offline events exclusively in a bounded RAM ring buffer (capacity: 50 events). If the buffer fills before network reconnection, the controller drops older uncommitted events and emits a formal `data_gap` event upon reconnecting.
* **Consequences**: Preserves flash memory integrity. The backend database explicitly records the occurrence and duration of data gaps rather than fabricating readings or pretending no data was lost.

---

## ADR-005: Commissioning Default as Alert-Only Across All Loads
* **Status**: Accepted
* **Context**: New sensor deployments frequently suffer from uncalibrated thresholds, incorrect PIR placement, or unpredictable environmental transients. Premature automated switching creates immediate user friction and potential safety hazards.
* **Decision**: All devices default to `auto_action_enabled = false` in `device_policies` at initial database migration. Automatic OFF actions for eligible devices (`light_01`, `fan_01`) can only be enabled by an administrator after passing sensor calibration and observation periods.
* **Consequences**: Guarantees zero unverified automated switching during initial installation and testing phases.

---

## ADR-006: Separation of Commanded State from Physical Feedback (Honest Labeling)
* **Status**: Accepted
* **Context**: The existing hardware prototype has relay control pins but lacks physical current transducers (e.g. ACS712, CT clamps) or auxiliary contact feedback. A GPIO command does not prove that the physical relay closed, the circuit breaker held, or the appliance actually ran.
* **Decision**: All database records and UI components separate `requested_state` from `observed_state`. With no current sensor hardware present, `observed_state` is recorded as `unknown` or `assumed`. All runtime metrics are explicitly labeled: *"estimate based on commanded state"*. Any display of kWh, electrical energy, or monetary savings is strictly forbidden.
* **Consequences**: Maintains engineering honesty, prevents liability from misleading savings claims, and clearly delineates software command from physical reality.

---

## ADR-007: Daylight Automation Gated by Physical Calibration Flag
* **Status**: Accepted
* **Context**: Ambient light varies dramatically depending on window orientation, blinds, artificial light reflection, and resistor tolerances on the LDR voltage divider. Uncalibrated LDR thresholds cause rapid relay oscillation.
* **Decision**: The daylight waste detector and firmware daylight rule remain strictly inactive until an operator performs physical calibration in the target room and explicitly sets `calibration_flag = true` in the system settings. A mandatory 3-minute confirmation window and separate ON/OFF hysteresis thresholds are enforced.
* **Consequences**: Eliminates false daylight shutdowns caused by transient cloud cover or artificial reflections.
