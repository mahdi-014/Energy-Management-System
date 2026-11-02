# Test Execution & Verification Report
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026 (Phase 0 Scaffold Completed)  

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
| **TC-01** | Device changes from OFF to ON | Phase 2 | `server/tests/test_state_logging.py` | `PENDING` | State event recorded in SQLite |
| **TC-02** | Device changes from ON to OFF | Phase 2 | `server/tests/test_runtime_calc.py` | `PENDING` | Completed runtime session calculated |
| **TC-03** | Vacancy candidate & alert generation | Phase 3 | `server/tests/test_detector_vacancy.py` | `PENDING` | Multi-stage vacancy logic verified |
| **TC-04** | Daylight-related lighting alert | Phase 3 | `server/tests/test_detector_daylight.py` | `PENDING` | 3m confirmation & hysteresis verified |
| **TC-05** | Maximum runtime exceeded | Phase 3 | `server/tests/test_detector_runtime.py` | `PENDING` | Long-runtime anomaly recorded |
| **TC-06** | Rapid cycling threshold exceeded | Phase 3 | `server/tests/test_detector_cycling.py` | `PENDING` | Diagnostic anomaly generated |
| **TC-07** | Manual override blocks automation | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Action blocked & reason logged |
| **TC-08** | Missing/invalid sensor suppresses action | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Safety gate suppresses auto-OFF |
| **TC-09** | Backend/network loss resilience | Phase 1 & 4 | `firmware/test/test_mqtt_comm.cpp` | `PENDING` | Local rules continue, queue buffers |
| **TC-10** | Expired/duplicate command rejected | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Rejected with reason code |
| **TC-11** | AC/PC alert-only protection | Phase 4 | `firmware/test/test_safety_gate.cpp` | `PENDING` | Forced shutdown blocked |
| **TC-12** | Automatic action allowed & executed | Phase 4 | `simulator/tests/test_e2e_automation.py` | `PENDING` | Full proposal-gate-ack logged |

---

## 3. Evaluation & Acceptance Tests (T1 to T15)

| Test ID | Test Scenario | Phase | Classification | Status | Execution Evidence / Notes |
|---|---|:---:|:---:|:---:|---|
| **T1** | Sensor readings observation | Phase 1 | Simulated / **NEEDS-HARDWARE** | `PENDING` | Sensor values update; faults indicated |
| **T2** | Vacancy stages (5m, 10m, 15m) | Phase 3 | Automated | `PENDING` | Candidate and warning sequence |
| **T3** | Stationary occupant behavior | Phase 3 | **NEEDS-HARDWARE** | `PENDING` | Real human stillness observation |
| **T4** | Daylight threshold confirmation | Phase 3 | Simulated / **NEEDS-HARDWARE** | `PENDING` | Stable threshold & confirmation time |
| **T5** | Daylight hysteresis stability | Phase 3 | Automated | `PENDING` | No relay cycling around threshold |
| **T6** | Manual override priority | Phase 4 | Automated | `PENDING` | Manual hold blocks auto-OFF |
| **T7** | AC/PC automation restriction | Phase 4 | Automated | `PENDING` | Alert-only, no power cut |
| **T8** | Sensor/network fault handling | Phase 1 & 4 | Simulated / **NEEDS-HARDWARE** | `PENDING` | Unsafe actions suppressed |
| **T9** | Event & runtime consistency | Phase 2 | Automated | `PENDING` | Timestamps & durations match estimates |
| **T10** | Restart & safe boot recovery | Phase 1 | Simulated / **NEEDS-HARDWARE** | `PENDING` | Relays boot OFF, state recovers |
| **T11** | Server outage & queue catch-up | Phase 2 | Automated | `PENDING` | Bounded queue & `data_gap` logged |
| **T12** | Storage integrity verification | Phase 2 | Automated | `PENDING` | Emitted events match DB rows |
| **T13** | Command path & AC/PC off blocked | Phase 4 | Automated | `PENDING` | AC/PC dashboard power-off rejected |
| **T14** | Analysis math accuracy | Phase 5 | Automated | `PENDING` | Hand-calculated fixtures match engine |
| **T15** | Access control & authentication | Phase 0 | Automated | **PASS** | Validated via `test_auth.py` (2026-11-02 14:21:32 UTC+6) |

---

## 4. Phase 0 Test Execution Record

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0
rootdir: D:\EMS
collected 20 items

server/tests/test_auth.py::test_password_hashing PASSED                  [  5%]
server/tests/test_auth.py::test_jwt_token_lifecycle PASSED               [ 10%]
server/tests/test_auth.py::test_jwt_tampering_rejected PASSED            [ 15%]
server/tests/test_auth.py::test_jwt_expiration PASSED                    [ 20%]
server/tests/test_auth.py::test_api_login_success_and_role PASSED        [ 25%]
server/tests/test_auth.py::test_api_login_invalid_credentials_t15 PASSED [ 30%]
server/tests/test_auth.py::test_api_protected_profile_t15 PASSED         [ 35%]
server/tests/test_auth.py::test_require_admin_guard_t15 PASSED           [ 40%]
server/tests/test_config.py::test_canonical_device_identifiers PASSED    [ 45%]
server/tests/test_config.py::test_canonical_controller_modes PASSED      [ 50%]
server/tests/test_config.py::test_canonical_device_states PASSED         [ 55%]
server/tests/test_config.py::test_hardcoded_auto_eligibility PASSED      [ 60%]
server/tests/test_config.py::test_settings_defaults PASSED               [ 65%]
server/tests/test_db_migrations.py::test_migration_tables_exist PASSED   [ 70%]
server/tests/test_db_migrations.py::test_device_policies_seeded PASSED   [ 75%]
server/tests/test_db_migrations.py::test_sensor_samples_null_allowed_and_bounds_check PASSED [ 80%]
server/tests/test_db_migrations.py::test_device_state_events_device_constraint PASSED [ 85%]
server/tests/test_db_migrations.py::test_config_table_seeded PASSED      [ 90%]
server/tests/test_simulator_unit.py::test_simulator_initial_state PASSED [ 95%]
server/tests/test_simulator_unit.py::test_simulator_offline_queue_and_data_gap PASSED [100%]

============================= 20 passed in 2.65s ==============================
```
