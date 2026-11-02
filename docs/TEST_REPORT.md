# Test Execution & Verification Report
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026 (Phase 2 State Tracking, Event Logging & Runtime Calculations Completed)  

---

## 1. Executive Summary & Verification Protocol
This living document tracks empirical verification evidence across all functional test cases (**TC-01..TC-12**) and planned operational evaluation tests (**T1..T15**).

* **Inviolable Principle**: Never claim a test has passed without fresh, executed command output observed in the active session.
* **Classification Criteria**:
  - `PASS`: Freshly executed and verified via automated test suite or simulator.
  - `FAIL`: Executed and failed to meet acceptance criteria (blocks phase completion).
  - `NEEDS-HARDWARE`: Requires physical laboratory/bench hardware or real human presence; marked with explicit physical test procedures in `docs/HARDWARE_CHECKLIST.md`.
  - `PENDING`: Scheduled for implementation in an upcoming phase.

---

## 2. Functional Test Cases (TC-01 to TC-12)

| Test ID | Test Scenario | Phase | Target Verification Suite | Status | Execution Evidence / Details |
|---|---|:---:|---|:---:|---|
| **TC-01** | Device changes from OFF to ON | Phase 2 | `server/tests/test_state_logging.py` | **PASS** | State event recorded in SQLite `device_state_events`, open session created in `runtime_sessions` |
| **TC-02** | Device changes from ON to OFF | Phase 2 | `server/tests/test_runtime_calc.py` | **PASS** | Completed runtime session calculated ($T = t_{\text{OFF}} - t_{\text{ON}}$) and stored with `end_known = 1` |
| **TC-03** | Vacancy candidate & alert generation | Phase 3 | `server/tests/test_detector_vacancy.py` | `PENDING` | Multi-stage vacancy logic verified |
| **TC-04** | Daylight-related lighting alert | Phase 3 | `server/tests/test_detector_daylight.py` | `PENDING` | 3m confirmation & hysteresis verified |
| **TC-05** | Maximum runtime exceeded | Phase 3 | `server/tests/test_detector_runtime.py` | `PENDING` | Long-runtime anomaly recorded |
| **TC-06** | Rapid cycling threshold exceeded | Phase 3 | `server/tests/test_detector_cycling.py` | `PENDING` | Diagnostic anomaly generated |
| **TC-07** | Manual override blocks automation | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Action blocked & reason logged |
| **TC-08** | Missing/invalid sensor suppresses action | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Safety gate suppresses auto-OFF |
| **TC-09** | Backend/network loss resilience | Phase 1 & 4 | `firmware/test/test_mqtt_comm.cpp` | **PASS (Simulated)** | Bounded RAM queue and LWT status verified |
| **TC-10** | Expired/duplicate command rejected | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Rejected with reason code |
| **TC-11** | AC/PC alert-only protection | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Forced shutdown blocked |
| **TC-12** | Automatic action allowed & executed | Phase 4 | `simulator/tests/test_e2e_automation.py` | `PENDING` | Full proposal-gate-ack logged |

---

## 3. Evaluation & Acceptance Tests (T1 to T15)

| Test ID | Test Scenario | Phase | Classification | Status | Execution Evidence / Notes |
|---|---|:---:|:---:|:---:|---|
| **T1** | Sensor readings & staleness observation | Phase 1 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | Sensor values update; staleness >60s flags warning (`test_staleness.py`) |
| **T2** | Vacancy stages (5m, 10m, 15m) | Phase 3 | Automated | `PENDING` | Candidate and warning sequence |
| **T3** | Stationary occupant behavior | Phase 3 | **NEEDS-HARDWARE** | `PENDING` | Real human stillness observation |
| **T4** | Daylight threshold confirmation | Phase 3 | Simulated / **NEEDS-HARDWARE** | `PENDING` | Stable threshold & confirmation time |
| **T5** | Daylight hysteresis stability | Phase 3 | Automated | `PENDING` | No relay cycling around threshold |
| **T6** | Manual override priority | Phase 4 | Automated | `PENDING` | Manual hold blocks auto-OFF |
| **T7** | AC/PC automation restriction | Phase 4 | Automated | `PENDING` | Alert-only, no power cut |
| **T8** | Sensor/network fault handling | Phase 1 & 4 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | NULL stored for invalid sensor readings (`test_sensor_ingestion.py`) |
| **T9** | Event & runtime consistency | Phase 2 | Automated | **PASS** | Validated via `test_runtime_calc.py` (exact fixture match $T = t_{\text{OFF}} - t_{\text{ON}}$) |
| **T10** | Restart & safe boot recovery | Phase 1 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | Relays initialized HIGH (inactive) in `setup()` before net init |
| **T11** | Server outage & queue catch-up | Phase 2 | Automated | **PASS** | Bounded 50-item RAM queue, oldest-drop on overflow, `data_gap` event, unclosed sessions marked `end_known = 0` (`test_offline_queue.py`) |
| **T12** | Storage integrity verification | Phase 2 | Automated | **PASS** | Duplicate `event_id` replay ignored without corrupting runtime sessions (`test_dedup.py`) |
| **T13** | Command path & AC/PC off blocked | Phase 4 | Automated | `PENDING` | AC/PC dashboard power-off rejected |
| **T14** | Analysis math accuracy | Phase 2 & 5 | Automated | **PASS** | Hand-calculated fixture validation passed; mandatory honest label verified |
| **T15** | Access control & authentication | Phase 0 | Automated | **PASS** | Validated via `test_auth.py` |

---

## 4. Phase 2 Test Execution Record

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0 -- D:\EMS\.python\python.exe
cachedir: .pytest_cache
rootdir: D:\EMS
plugins: anyio-4.16.0
collecting ... collected 40 items

server/tests/test_api_events.py::test_api_events_filtering PASSED        [  2%]
server/tests/test_api_events.py::test_api_analysis_runtime_endpoint PASSED [  5%]
server/tests/test_api_events.py::test_api_analysis_sessions_endpoint PASSED [  7%]
server/tests/test_api_live.py::test_get_live_telemetry_schema_and_labels PASSED [ 10%]
server/tests/test_api_live.py::test_get_sensor_readings_history PASSED   [ 12%]
server/tests/test_auth.py::test_password_hashing PASSED                  [ 15%]
server/tests/test_auth.py::test_jwt_token_lifecycle PASSED               [ 17%]
server/tests/test_auth.py::test_jwt_tampering_rejected PASSED            [ 20%]
server/tests/test_auth.py::test_jwt_expiration PASSED                    [ 22%]
server/tests/test_auth.py::test_api_login_success_and_role PASSED        [ 25%]
server/tests/test_auth.py::test_api_login_invalid_credentials_t15 PASSED [ 27%]
server/tests/test_auth.py::test_api_protected_profile_t15 PASSED         [ 30%]
server/tests/test_auth.py::test_require_admin_guard_t15 PASSED           [ 32%]
server/tests/test_config.py::test_canonical_device_identifiers PASSED    [ 35%]
server/tests/test_config.py::test_canonical_controller_modes PASSED      [ 37%]
server/tests/test_config.py::test_canonical_device_states PASSED         [ 40%]
server/tests/test_config.py::test_hardcoded_auto_eligibility PASSED      [ 42%]
server/tests/test_config.py::test_settings_defaults PASSED               [ 45%]
server/tests/test_db_migrations.py::test_migration_tables_exist PASSED   [ 47%]
server/tests/test_db_migrations.py::test_device_policies_seeded PASSED   [ 50%]
server/tests/test_db_migrations.py::test_sensor_samples_null_allowed_and_bounds_check PASSED [ 52%]
server/tests/test_db_migrations.py::test_device_state_events_device_constraint PASSED [ 55%]
server/tests/test_db_migrations.py::test_config_table_seeded PASSED      [ 57%]
server/tests/test_dedup.py::test_t12_event_deduplication PASSED          [ 60%]
server/tests/test_lwt_status.py::test_lwt_offline_transition PASSED      [ 62%]
server/tests/test_lwt_status.py::test_heartbeat_online_transition PASSED [ 65%]
server/tests/test_offline_queue.py::test_t11_offline_queue_overflow_and_data_gap_catchup PASSED [ 67%]
server/tests/test_runtime_calc.py::test_t9_t14_hand_calculated_runtime_fixtures PASSED [ 70%]
server/tests/test_runtime_calc.py::test_outage_handling_marks_interrupted_session PASSED [ 72%]
server/tests/test_sensor_ingestion.py::test_sensor_ingestion_valid_payload PASSED [ 75%]
server/tests/test_sensor_ingestion.py::test_sensor_ingestion_null_not_zero_on_invalid PASSED [ 77%]
server/tests/test_sensor_ingestion.py::test_derive_occupancy_state PASSED [ 80%]
server/tests/test_simulator_unit.py::test_simulator_initial_state PASSED [ 82%]
server/tests/test_simulator_unit.py::test_simulator_offline_queue_and_data_gap PASSED [ 85%]
server/tests/test_staleness.py::test_stale_when_no_readings PASSED       [ 87%]
server/tests/test_staleness.py::test_fresh_reading_not_stale PASSED      [ 90%]
server/tests/test_staleness.py::test_stale_after_60_seconds_t1 PASSED    [ 92%]
server/tests/test_state_logging.py::test_tc01_off_to_on_event_logging PASSED [ 95%]
server/tests/test_state_logging.py::test_tc02_on_to_off_event_logging PASSED [ 97%]
server/tests/test_state_logging.py::test_invalid_device_or_state_rejected PASSED [100%]

============================= 40 passed in 4.35s ==============================
```
