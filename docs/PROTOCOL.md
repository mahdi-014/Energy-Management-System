# MQTT Communication & Message Protocol Specification
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Version**: 1.0  
**Transport**: MQTT v3.1.1 over TCP (Port 1883) with Username/Password Authentication  
**Topic Root**: `dcems/room1/`  

---

## 1. Topic Hierarchy Overview

| Topic Name | Direction | QoS | Retained | Purpose & Delivery Trigger |
|---|:---:|:---:|:---:|---|
| `dcems/room1/sensors` | ESP $\to$ Server | 0 | No | Periodic telemetry snapshot (every 30 s). |
| `dcems/room1/state` | ESP $\to$ Server | 1 | **Yes** | Commanded relay states & controller mode. Published strictly on change and on boot. |
| `dcems/room1/events` | ESP $\to$ Server | 1 | No | Rule triggers, override events, faults, and `data_gap` notices. |
| `dcems/room1/cmd` | Server $\to$ ESP | 1 | No | Action proposal / manual command sent to the firmware safety gate. |
| `dcems/room1/ack` | ESP $\to$ Server | 1 | No | Authoritative gate response (`accepted`, `blocked`, `expired`, `duplicate`). |
| `dcems/room1/status` | ESP $\to$ Server | 1 | **Yes** | LWT (`offline`) set on connect; periodic heartbeat (`online`) every 30 s. |

---

## 2. Topic Schemas & Message Formats

### 2.1 `dcems/room1/sensors` (Telemetry Snapshot)
Published periodically every 30 seconds by the ESP8266 or simulator.

#### JSON Schema
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["event_id", "ts", "room_id", "pir", "ldr", "valid", "quality"],
  "properties": {
    "event_id": { "type": "string", "description": "Unique UUID or monotonic sequence ID" },
    "ts": { "type": "integer", "description": "Device UTC timestamp in epoch seconds" },
    "room_id": { "type": "string", "enum": ["room1"] },
    "pir": { "type": ["integer", "null"], "enum": [0, 1, null], "description": "1 = motion detected, 0 = no motion, null = fault" },
    "ldr": { "type": ["integer", "null"], "minimum": 0, "maximum": 1023, "description": "Raw ADC light level (0-1023)" },
    "temp": { "type": ["number", "null"], "minimum": 0.0, "maximum": 50.0, "description": "Room temperature in Celsius" },
    "hum": { "type": ["number", "null"], "minimum": 20.0, "maximum": 90.0, "description": "Relative humidity percentage" },
    "last_motion_at": { "type": ["integer", "null"], "description": "UTC timestamp of latest detected motion pulse" },
    "valid": { "type": "boolean", "description": "True if all readings are within nominal bounds and fresh" },
    "quality": { "type": "string", "enum": ["ok", "degraded", "fault"] }
  }
}
```

#### Example Payload
```json
{
  "event_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "ts": 1793606400,
  "room_id": "room1",
  "pir": 0,
  "ldr": 542,
  "temp": 28.5,
  "hum": 64.0,
  "last_motion_at": 1793606100,
  "valid": true,
  "quality": "ok"
}
```

---

### 2.2 `dcems/room1/state` (Device & Controller State)
Published on any state transition or upon boot. Retained flag is `true`.

#### JSON Schema
```json
{
  "type": "object",
  "required": ["ts", "mode", "devices"],
  "properties": {
    "ts": { "type": "integer", "description": "Device UTC epoch timestamp" },
    "mode": { "type": "string", "enum": ["AUTO", "MANUAL"] },
    "devices": {
      "type": "object",
      "required": ["light_01", "fan_01", "ac_01", "pc_01"],
      "properties": {
        "light_01": { "type": "string", "enum": ["ON", "OFF"] },
        "fan_01": { "type": "string", "enum": ["ON", "OFF"] },
        "ac_01": { "type": "string", "enum": ["ON", "OFF"] },
        "pc_01": { "type": "string", "enum": ["ON", "OFF"] }
      }
    },
    "observed_state": { "type": "string", "enum": ["assumed", "unknown"] }
  }
}
```

#### Example Payload
```json
{
  "ts": 1793606400,
  "mode": "AUTO",
  "devices": {
    "light_01": "ON",
    "fan_01": "ON",
    "ac_01": "OFF",
    "pc_01": "ON"
  },
  "observed_state": "assumed"
}
```

---

### 2.3 `dcems/room1/events` (Firmware Operational & Audit Events)
Published whenever a local rule triggers, an override begins/expires, or buffer overflows.

#### Example Payloads
**Vacancy Warning Event:**
```json
{
  "event_id": "e45a2781-8b89-42b1-8409-cf8a08d29b12",
  "ts": 1793606700,
  "type": "vacancy_candidate",
  "device_id": "fan_01",
  "rule_id": "V1",
  "decision": "warning",
  "reason": "no_motion_10_min",
  "context": { "last_motion_sec_ago": 600 }
}
```

**Data Gap Event (After Reconnection):**
```json
{
  "event_id": "f882ba11-3049-43c2-bf72-138374249a01",
  "ts": 1793607000,
  "type": "data_gap",
  "gap_start_ts": 1793606400,
  "gap_end_ts": 1793606990,
  "dropped_events_count": 14,
  "reason": "ram_queue_overflow_during_disconnect"
}
```

---

### 2.4 `dcems/room1/cmd` (Command & Action Proposal)
Published by the backend service to request a mode switch or appliance state change.

#### JSON Schema
```json
{
  "type": "object",
  "required": ["action_id", "issued_at", "expires_at", "source"],
  "properties": {
    "action_id": { "type": "string", "format": "uuid" },
    "issued_at": { "type": "integer" },
    "expires_at": { "type": "integer" },
    "source": { "type": "string", "enum": ["server_proposal", "dashboard_manual"] },
    "command_type": { "type": "string", "enum": ["DEVICE_SWITCH", "MODE_CHANGE"] },
    "device_id": { "type": "string", "enum": ["light_01", "fan_01", "ac_01", "pc_01"] },
    "requested_state": { "type": "string", "enum": ["ON", "OFF"] },
    "target_mode": { "type": "string", "enum": ["AUTO", "MANUAL"] },
    "policy_version": { "type": "integer" },
    "reason": { "type": "string" }
  }
}
```

#### Example Payload
```json
{
  "action_id": "7a35118d-69be-4f51-b8ba-0a4a58ebcc47",
  "issued_at": 1793607000,
  "expires_at": 1793607030,
  "source": "server_proposal",
  "command_type": "DEVICE_SWITCH",
  "device_id": "fan_01",
  "requested_state": "OFF",
  "policy_version": 1,
  "reason": "vacancy_confirmed_15_min"
}
```

---

### 2.5 `dcems/room1/ack` (Safety Gate Command Acknowledgement)
Published strictly by the ESP8266 or simulator in response to every `cmd`.

#### JSON Schema
```json
{
  "type": "object",
  "required": ["action_id", "ts", "result"],
  "properties": {
    "action_id": { "type": "string" },
    "ts": { "type": "integer" },
    "result": { "type": "string", "enum": ["accepted", "blocked", "expired", "duplicate"] },
    "reason_code": { "type": "string" },
    "device_id": { "type": "string" },
    "commanded_state": { "type": "string" }
  }
}
```

#### Reason Code Taxonomy
| `result` | `reason_code` | Explanation |
|---|---|---|
| `accepted` | `ok_manual_command` | Manual override processed successfully. |
| `accepted` | `ok_policy_validated` | Automated action passed all 8 safety checks. |
| `blocked` | `device_not_auto_eligible` | Attempted automation on non-eligible device (`ac_01`, `pc_01`). |
| `blocked` | `controller_in_manual_mode` | Automated action proposed while mode is `MANUAL`. |
| `blocked` | `manual_override_active` | Device is under active manual hold timer. |
| `blocked` | `sensor_data_stale_or_invalid` | Required sensor reading is stale (>60s) or out of bounds. |
| `blocked` | `min_interval_violation` | Minimum ON or OFF switching interval not satisfied. |
| `blocked` | `redundant_transition` | Proposed state matches current state (e.g. `OFF -> OFF`). |
| `blocked` | `dashboard_ac_pc_power_off_blocked` | Safety policy forbids manual mains cutoff for AC/PC (T13). |
| `expired` | `command_expired` | $t_{\text{current}} > t_{\text{expires\_at}}$. |
| `duplicate` | `duplicate_action_id` | `action_id` present in recent ring buffer. |

---

### 2.6 `dcems/room1/status` (LWT & Heartbeat)
* **LWT (Last Will and Testament)**:
  Configured by the ESP8266 client on initial connection:
  - Topic: `dcems/room1/status`
  - Payload: `{"status":"offline","ts":1793607000,"reason":"unexpected_disconnect"}`
  - Retain: `true`, QoS: 1
* **Online Heartbeat**:
  Published immediately upon connection and every 30 seconds:
  - Payload: `{"status":"online","ts":1793607030,"firmware_version":"1.0.0","uptime_sec":1240}`
  - Retain: `true`, QoS: 1

