import pytest
import sqlite3
from datetime import datetime, timezone
from app.db import get_db_connection, run_migrations
from app.analysis import process_device_state_event, handle_outage_or_data_gap, get_daily_runtime_breakdown

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_t9_t14_hand_calculated_runtime_fixtures():
    """
    T9 & T14: Hand-calculated verification of operating duration:
    Formula: T = t_OFF - t_ON

    Hand-calculated Fixtures:
    - Target Date: 2026-11-02 (Day start: 1762041600 UTC)
    - Device 'fan_01':
        Session 1: ON at 1762042000, OFF at 1762042600 -> Duration = 600s (10 min)
        Session 2: ON at 1762045000, OFF at 1762046200 -> Duration = 1200s (20 min)
        Expected Total Runtime = 1800s (30 min = 0.50 hrs)
        Completed sessions = 2, Interrupted sessions = 0

    - Device 'light_01':
        Session 1: ON at 1762043000, OFF at 1762043900 -> Duration = 900s (15 min = 0.25 hrs)
        Completed sessions = 1, Interrupted sessions = 0

    - Device 'ac_01':
        Zero sessions -> Total Runtime = 0s, 0.00 hrs

    - Device 'pc_01':
        Zero sessions -> Total Runtime = 0s, 0.00 hrs
    """
    conn = get_db_connection()
    try:
        # Day 2026-11-02 starts at epoch 1793577600
        # 1. Ingest fan_01 session 1: 1793578000 to 1793578600 (600s)
        process_device_state_event({
            "event_id": "ev_f1_on",
            "timestamp_utc": 1793578000,
            "device_id": "fan_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "switch_on"
        }, custom_conn=conn)
        process_device_state_event({
            "event_id": "ev_f1_off",
            "timestamp_utc": 1793578600,
            "device_id": "fan_01",
            "requested_state": "OFF",
            "state_source": "local_rule",
            "reason_code": "vacancy_auto_off"
        }, custom_conn=conn)

        # 2. Ingest fan_01 session 2: 1793581000 to 1793582200 (1200s)
        process_device_state_event({
            "event_id": "ev_f2_on",
            "timestamp_utc": 1793581000,
            "device_id": "fan_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "switch_on"
        }, custom_conn=conn)
        process_device_state_event({
            "event_id": "ev_f2_off",
            "timestamp_utc": 1793582200,
            "device_id": "fan_01",
            "requested_state": "OFF",
            "state_source": "manual",
            "reason_code": "switch_off"
        }, custom_conn=conn)

        # 3. Ingest light_01 session: 1793579000 to 1793579900 (900s)
        process_device_state_event({
            "event_id": "ev_l1_on",
            "timestamp_utc": 1793579000,
            "device_id": "light_01",
            "requested_state": "ON",
            "state_source": "local_rule",
            "reason_code": "motion_detect"
        }, custom_conn=conn)
        process_device_state_event({
            "event_id": "ev_l1_off",
            "timestamp_utc": 1793579900,
            "device_id": "light_01",
            "requested_state": "OFF",
            "state_source": "local_rule",
            "reason_code": "daylight_auto_off"
        }, custom_conn=conn)

        # Query daily breakdown for 2026-11-02
        breakdown = get_daily_runtime_breakdown("2026-11-02", custom_conn=conn)

        # Verify fan_01 hand calculation
        fan_data = breakdown["devices"]["fan_01"]
        assert fan_data["total_runtime_sec"] == 1800
        assert fan_data["total_runtime_hours"] == 0.50
        assert fan_data["completed_sessions"] == 2
        assert fan_data["interrupted_sessions"] == 0
        assert fan_data["is_currently_on"] is False

        # Verify light_01 hand calculation
        light_data = breakdown["devices"]["light_01"]
        assert light_data["total_runtime_sec"] == 900
        assert light_data["total_runtime_hours"] == 0.25
        assert light_data["completed_sessions"] == 1
        assert light_data["interrupted_sessions"] == 0
        assert light_data["is_currently_on"] is False

        # Verify ac_01 and pc_01 are 0
        assert breakdown["devices"]["ac_01"]["total_runtime_sec"] == 0
        assert breakdown["devices"]["pc_01"]["total_runtime_sec"] == 0

        # Verify mandatory disclaimer and labels (Invariant: No energy/cost claims)
        labels = breakdown["labels"]
        assert "estimates based on commanded relay state" in labels["runtime_disclaimer"].lower()
        assert "energy (kwh) and cost calculations are excluded" in labels["energy_notice"].lower()
    finally:
        conn.close()

def test_outage_handling_marks_interrupted_session():
    """
    T11: When power outage or data gap occurs, open sessions must be marked
    interrupted with end_known = 0, never silently dropped or assumed indefinitely ON.
    """
    conn = get_db_connection()
    try:
        # Start device ON at t=1793578000
        process_device_state_event({
            "event_id": "ev_outage_on",
            "timestamp_utc": 1793578000,
            "device_id": "light_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "switch_on"
        }, custom_conn=conn)

        # Simulate data gap/outage at t=1793578700 (700 seconds later)
        closed = handle_outage_or_data_gap(
            gap_start_ts=1793578700,
            gap_end_ts=1793578900,
            custom_conn=conn
        )
        assert closed == 1

        cur = conn.cursor()
        cur.execute("SELECT * FROM runtime_sessions WHERE device_id = 'light_01'")
        sess = cur.fetchone()
        assert sess is not None
        assert sess["end_known"] == 0
        assert sess["end_time_utc"] == 1793578700
        assert sess["estimated_duration_sec"] == 700

        # Verify daily breakdown reports it as interrupted
        breakdown = get_daily_runtime_breakdown("2026-11-02", custom_conn=conn)
        light_data = breakdown["devices"]["light_01"]
        assert light_data["completed_sessions"] == 0
        assert light_data["interrupted_sessions"] == 1
        assert light_data["total_runtime_sec"] == 700
    finally:
        conn.close()
