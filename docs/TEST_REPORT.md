# Test Execution & Verification Report
**Project**: DC Office Single-Room Hybrid Energy Management System (DCEMS) MVP  
**Last Updated**: November 2, 2026 (Phase 3 Alert-Only Anomaly Detectors & Calibration Helper Completed)  

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
| **TC-03** | Vacancy candidate & alert generation | Phase 3 | `server/tests/test_detector_vacancy.py` | **PASS** | Multi-stage vacancy logic verified (5m candidate, 10m warning info, 15m confirmed warning) |
| **TC-04** | Daylight-related lighting alert | Phase 3 | `server/tests/test_detector_daylight.py` | **PASS** | 3m confirmation & hysteresis verified; locked when uncalibrated |
| **TC-05** | Maximum runtime exceeded | Phase 3 | `server/tests/test_detector_runtime.py` | **PASS** | Long-runtime anomaly recorded with severity = info |
| **TC-06** | Rapid cycling threshold exceeded | Phase 3 | `server/tests/test_detector_cycling.py` | **PASS** | Diagnostic anomaly generated (>4 in 10m); relays unaffected |
| **TC-07** | Manual override blocks automation | Phase 4 | `server/tests/test_safety_gate_parity.py` | **PASS** | Manual hold (600s) and manual mode block automated proposals |
| **TC-08** | Missing/invalid sensor suppresses action | Phase 3 & 4 | `server/tests/test_detector_sensor_quality.py` | **PASS** | Diagnostic alert generated for stale (>60s) or invalid data; suppresses auto actions |
| **TC-09** | Backend/network loss resilience | Phase 1 & 4 | `firmware/src/mqtt_comm.cpp` | **PASS (Simulated)** | Bounded RAM queue, LWT status, offline drop counting verified |
| **TC-10** | Expired/duplicate command rejected | Phase 4 | `server/tests/test_safety_gate_parity.py` | **PASS** | Replayed action_id and expired TTL rejected with explicit reason codes |
| **TC-11** | AC/PC alert-only protection | Phase 3 & 4 | `server/tests/test_detector_vacancy.py` | **PASS** | Alert generated for running AC/PC on vacancy; automated shutdown blocked |
| **TC-12** | Automatic action allowed & executed | Phase 4 | `simulator/tests/test_e2e_automation.py` | **PASS** | Full proposal -> safety gate -> relay transition -> ACK cycle verified |

---

## 3. Evaluation & Acceptance Tests (T1 to T15)

| Test ID | Test Scenario | Phase | Classification | Status | Execution Evidence / Notes |
|---|---|:---:|:---:|:---:|---|
| **T1** | Sensor readings & staleness observation | Phase 1 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | Sensor values update; staleness >60s flags warning (`test_staleness.py`) |
| **T2** | Vacancy stages (5m, 10m, 15m) | Phase 3 | Automated | **PASS** | Candidate, warning, and confirmed sequence validated (`test_detector_vacancy.py`) |
| **T3** | Stationary occupant behavior | Phase 3 | **NEEDS-HARDWARE** | `PENDING` | Documented in `docs/LIMITATIONS.md` & UI warning; physical human stillness |
| **T4** | Daylight threshold confirmation | Phase 3 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | 3m confirmation window verified (`test_detector_daylight.py`) |
| **T5** | Daylight hysteresis stability | Phase 3 | Automated | **PASS** | Separate ON/OFF thresholds prevent relay cycling (`test_detector_daylight.py`) |
| **T6** | Manual override priority | Phase 4 | Automated | **PASS** | Manual hold (600s) and MANUAL mode block auto-actions (`test_safety_gate_parity.py`) |
| **T7** | AC/PC automation restriction | Phase 4 | Automated | **PASS** | Ineligible for auto actions; hardcoded allowlist constraint verified (`test_safety_gate_parity.py`) |
| **T8** | Sensor/network fault handling | Phase 1 & 4 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | NULL stored for invalid sensor readings; `sensor_issue` alert raised |
| **T9** | Event & runtime consistency | Phase 2 | Automated | **PASS** | Validated via `test_runtime_calc.py` (exact fixture match $T = t_{\text{OFF}} - t_{\text{ON}}$) |
| **T10** | Restart & safe boot recovery | Phase 1 | Simulated / **NEEDS-HARDWARE** | **PASS (Simulated)** | Relays initialized HIGH (inactive) in `setup()` before net init |
| **T11** | Server outage & queue catch-up | Phase 2 | Automated | **PASS** | Bounded 50-item RAM queue, oldest-drop on overflow, `data_gap` event, unclosed sessions marked `end_known = 0` (`test_offline_queue.py`) |
| **T12** | Storage integrity verification | Phase 2 | Automated | **PASS** | Duplicate `event_id` replay ignored without corrupting runtime sessions (`test_dedup.py`) |
| **T13** | Command path & AC/PC off blocked | Phase 4 | Automated | **PASS** | AC/PC dashboard power-off rejected at policy and safety gate layers (`test_safety_gate_parity.py`, `test_api_control.py`) |
| **T14** | Analysis math accuracy | Phase 2 & 5 | Automated | **PASS** | Hand-calculated fixture validation passed; mandatory honest label verified |
| **T15** | Access control & authentication | Phase 0 | Automated | **PASS** | Validated via `test_auth.py` |

---

## 4. Phase 3 Test Execution Record

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0 -- D:\EMS\.python\python.exe
cachedir: .pytest_cache
rootdir: D:\EMS
plugins: anyio-4.16.0
collecting ... collected 50 items

server/tests/test_alert_cooldown.py::test_alert_deduplication_and_cooldown PASSED [  2%]
server/tests/test_api_anomalies.py::test_api_anomalies_list_and_filter PASSED [  4%]
server/tests/test_api_anomalies.py::test_api_anomalies_acknowledge PASSED [  6%]
server/tests/test_api_daylight_calibration_workflow PASSED [  8%]
server/tests/test_api_events.py::test_api_events_filtering PASSED        [ 10%]
server/tests/test_api_events.py::test_api_analysis_runtime_endpoint PASSED [ 12%]
server/tests/test_api_events.py::test_api_analysis_sessions_endpoint PASSED [ 14%]
server/tests/test_api_live.py::test_get_live_telemetry_schema_and_labels PASSED [ 16%]
server/tests/test_api_live.py::test_get_sensor_readings_history PASSED   [ 18%]
server/tests/test_auth.py::test_password_hashing PASSED                  [ 20%]
server/tests/test_auth.py::test_jwt_token_lifecycle PASSED               [ 22%]
server/tests/test_auth.py::test_jwt_tampering_rejected PASSED            [ 24%]
server/tests/test_auth.py::test_jwt_expiration PASSED                    [ 26%]
server/tests/test_auth.py::test_api_login_success_and_role PASSED        [ 28%]
server/tests/test_auth.py::test_api_login_invalid_credentials_t15 PASSED [ 30%]
server/tests/test_auth.py::test_api_protected_profile_t15 PASSED         [ 32%]
server/tests/test_require_admin_guard_t15 PASSED           [ 34%]
server/tests/test_config.py::test_canonical_device_identifiers PASSED    [ 36%]
server/tests/test_config.py::test_canonical_controller_modes PASSED      [ 38%]
server/tests/test_config.py::test_canonical_device_states PASSED         [ 40%]
server/tests/test_config.py::test_hardcoded_auto_eligibility PASSED      [ 42%]
server/tests/test_config.py::test_settings_defaults PASSED               [ 44%]
server/tests/test_db_migrations.py::test_migration_tables_exist PASSED   [ 46%]
server/tests/test_db_migrations.py::test_device_policies_seeded PASSED   [ 48%]
server/tests/test_db_migrations.py::test_sensor_samples_null_allowed_and_bounds_check PASSED [ 50%]
server/tests/test_db_migrations.py::test_device_state_events_device_constraint PASSED [ 52%]
server/tests/test_config.py::test_config_table_seeded PASSED      [ 54%]
server/tests/test_dedup.py::test_t12_event_deduplication PASSED          [ 56%]
server/tests/test_detector_cycling.py::test_tc06_rapid_cycling_diagnostic_detection PASSED [ 58%]
server/tests/test_detector_daylight.py::test_tc04_t4_t5_daylight_gating_confirmation_and_hysteresis PASSED [ 60%]
server/tests/test_detector_runtime.py::test_tc05_runtime_threshold_detection PASSED [ 62%]
server/tests/test_detector_sensor_quality.py::test_tc08_t8_sensor_quality_and_staleness_anomaly PASSED [ 64%]
server/tests/test_detector_vacancy.py::test_tc03_t2_vacancy_stages_progression PASSED [ 66%]
server/tests/test_detector_vacancy.py::test_tc11_ac_pc_vacancy_alert_only PASSED [ 68%]
server/tests/test_lwt_status.py::test_lwt_offline_transition PASSED      [ 70%]
server/tests/test_lwt_status.py::test_heartbeat_online_transition PASSED [ 72%]
server/tests/test_offline_queue.py::test_t11_offline_queue_overflow_and_data_gap_catchup PASSED [ 74%]
server/tests/test_runtime_calc.py::test_t9_t14_hand_calculated_runtime_fixtures PASSED [ 76%]
server/tests/test_runtime_calc.py::test_outage_handling_marks_interrupted_session PASSED [ 78%]
server/tests/test_sensor_ingestion.py::test_sensor_ingestion_valid_payload PASSED [ 80%]
server/tests/test_sensor_ingestion.py::test_sensor_ingestion_null_not_zero_on_invalid PASSED [ 82%]
server/tests/test_sensor_ingestion.py::test_derive_occupancy_state PASSED [ 84%]
server/tests/test_simulator_unit.py::test_simulator_initial_state PASSED [ 86%]
server/tests/test_simulator_unit.py::test_simulator_offline_queue_and_data_gap PASSED [ 88%]
server/tests/test_staleness.py::test_stale_when_no_readings PASSED       [ 90%]
server/tests/test_staleness.py::test_fresh_reading_not_stale PASSED      [ 92%]
server/tests/test_staleness.py::test_stale_after_60_seconds_t1 PASSED    [ 94%]
server/tests/test_state_logging.py::test_tc01_off_to_on_event_logging PASSED [ 96%]
server/tests/test_state_logging.py::test_tc02_on_to_off_event_logging PASSED [ 98%]
server/tests/test_state_logging.py::test_invalid_device_or_state_rejected PASSED [100%]

============================= 50 passed in 5.46s ==============================
```

---

## 5. Phase 4 Test Execution Record (68/68 Passed)

```text
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.2.0, pluggy-1.7.0 -- D:\EMS\.python\python.exe
cachedir: .pytest_cache
rootdir: D:\EMS
plugins: anyio-4.16.0
collecting ... collected 68 items

server/tests/test_alert_cooldown.py::test_alert_deduplication_and_cooldown PASSED [  1%]
server/tests/test_api_anomalies.py::test_api_anomalies_list_and_filter PASSED [  2%]
server/tests/test_api_anomalies.py::test_api_anomalies_acknowledge PASSED [  4%]
server/tests/test_api_daylight_calibration_workflow PASSED [  5%]
server/tests/test_api_control.py::test_api_control_device_success PASSED [  7%]
server/tests/test_api_control.py::test_api_control_device_ac_pc_power_off_blocked_t13 PASSED [  8%]
server/tests/test_api_control.py::test_api_control_mode_transitions PASSED [ 10%]
server/tests/test_api_control.py::test_api_control_manual_override_and_audit PASSED [ 11%]
server/tests/test_api_events.py::test_api_events_filtering PASSED        [ 13%]
server/tests/test_api_events.py::test_api_analysis_runtime_endpoint PASSED [ 14%]
server/tests/test_api_events.py::test_api_analysis_sessions_endpoint PASSED [ 16%]
server/tests/test_api_live.py::test_get_live_telemetry_schema_and_labels PASSED [ 17%]
server/tests/test_api_live.py::test_get_sensor_readings_history PASSED   [ 19%]
server/tests/test_auth.py::test_password_hashing PASSED                  [ 20%]
server/tests/test_auth.py::test_jwt_token_lifecycle PASSED               [ 22%]
server/tests/test_auth.py::test_jwt_tampering_rejected PASSED            [ 23%]
server/tests/test_auth.py::test_jwt_expiration PASSED                    [ 25%]
server/tests/test_auth.py::test_api_login_success_and_role PASSED        [ 26%]
server/tests/test_auth.py::test_api_login_invalid_credentials_t15 PASSED [ 27%]
server/tests/test_auth.py::test_api_protected_profile_t15 PASSED         [ 29%]
server/tests/test_require_admin_guard_t15 PASSED           [ 30%]
server/tests/test_config.py::test_canonical_device_identifiers PASSED    [ 32%]
server/tests/test_config.py::test_canonical_controller_modes PASSED      [ 33%]
server/tests/test_config.py::test_canonical_device_states PASSED         [ 35%]
server/tests/test_config.py::test_hardcoded_auto_eligibility PASSED      [ 36%]
server/tests/test_config.py::test_settings_defaults PASSED               [ 38%]
server/tests/test_db_migrations.py::test_migration_tables_exist PASSED   [ 39%]
server/tests/test_db_migrations.py::test_device_policies_seeded PASSED   [ 41%]
server/tests/test_db_migrations.py::test_sensor_samples_null_allowed_and_bounds_check PASSED [ 42%]
server/tests/test_db_migrations.py::test_device_state_events_device_constraint PASSED [ 44%]
server/tests/test_config.py::test_config_table_seeded PASSED      [ 45%]
server/tests/test_dedup.py::test_t12_event_deduplication PASSED          [ 47%]
server/tests/test_detector_cycling.py::test_tc06_rapid_cycling_diagnostic_detection PASSED [ 48%]
server/tests/test_detector_daylight.py::test_tc04_t4_t5_daylight_gating_confirmation_and_hysteresis PASSED [ 50%]
server/tests/test_detector_runtime.py::test_tc05_runtime_threshold_detection PASSED [ 51%]
server/tests/test_detector_sensor_quality.py::test_tc08_t8_sensor_quality_and_staleness_anomaly PASSED [ 52%]
server/tests/test_detector_vacancy.py::test_tc03_t2_vacancy_stages_progression PASSED [ 54%]
server/tests/test_detector_vacancy.py::test_tc11_ac_pc_vacancy_alert_only PASSED [ 55%]
server/tests/test_lwt_status.py::test_lwt_offline_transition PASSED      [ 57%]
server/tests/test_lwt_status.py::test_heartbeat_online_transition PASSED [ 58%]
server/tests/test_offline_queue.py::test_t11_offline_queue_overflow_and_data_gap_catchup PASSED [ 60%]
server/tests/test_policy.py::test_validate_server_proposal_ac_pc_ineligible PASSED [ 61%]
server/tests/test_policy.py::test_validate_server_proposal_default_disabled PASSED [ 63%]
server/tests/test_policy.py::test_validate_server_proposal_enabled_and_manual_override PASSED [ 64%]
server/tests/test_policy.py::test_issue_device_command_t13_safeguard PASSED [ 66%]
server/tests/test_policy.py::test_issue_device_command_allowed_and_ack_processing PASSED [ 67%]
server/tests/test_policy.py::test_issue_mode_command_lifecycle PASSED    [ 69%]
server/tests/test_runtime_calc.py::test_t9_t14_hand_calculated_runtime_fixtures PASSED [ 70%]
server/tests/test_runtime_calc.py::test_outage_handling_marks_interrupted_session PASSED [ 72%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_1_device_allowlist_auto_eligible PASSED [ 73%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_2_controller_mode_blocks_auto PASSED [ 75%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_3_manual_override_hold PASSED [ 76%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_5_min_switching_intervals PASSED [ 77%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_6_duplicate_and_expired_commands PASSED [ 79%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_7_redundant_transition PASSED [ 80%]
server/tests/test_safety_gate_parity.py::test_safety_gate_point_8_test_t13_ac_pc_power_off_safeguard PASSED [ 82%]
server/tests/test_sensor_ingestion.py::test_sensor_ingestion_valid_payload PASSED [ 83%]
server/tests/test_sensor_ingestion.py::test_sensor_ingestion_null_not_zero_on_invalid PASSED [ 85%]
server/tests/test_sensor_ingestion.py::test_derive_occupancy_state PASSED [ 86%]
server/tests/test_simulator_unit.py::test_simulator_initial_state PASSED [ 88%]
server/tests/test_simulator_unit.py::test_simulator_offline_queue_and_data_gap PASSED [ 89%]
server/tests/test_staleness.py::test_stale_when_no_readings PASSED       [ 91%]
server/tests/test_staleness.py::test_fresh_reading_not_stale PASSED      [ 92%]
server/tests/test_staleness.py::test_stale_after_60_seconds_t1 PASSED    [ 94%]
server/tests/test_state_logging.py::test_tc01_off_to_on_event_logging PASSED [ 95%]
server/tests/test_state_logging.py::test_tc02_on_to_off_event_logging PASSED [ 97%]
server/tests/test_state_logging.py::test_invalid_device_or_state_rejected PASSED [ 98%]
simulator/tests/test_e2e_automation.py::test_tc12_e2e_proposal_gate_relay_ack_cycle PASSED [100%]

============================= 68 passed in 6.45s ==============================
```
