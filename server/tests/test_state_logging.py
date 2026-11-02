import sqlite3
import pytest
from app.db import get_db_connection, run_migrations
from app.analysis import process_device_state_event

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_tc01_off_to_on_event_logging():
    """
    TC-01: Device changes OFF -> ON.
    Timestamped state event recorded in DB with correct source and status.
    """
    conn = get_db_connection()
    try:
        event = {
            "event_id": "evt_test_001",
            "timestamp_utc": 1761800000,
            "device_id": "light_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "wall_switch_toggle",
            "controller_mode": "AUTO",
            "command_status": "applied",
            "observed_state": "assumed"
        }

        success = process_device_state_event(event, custom_conn=conn)
        assert success is True

        cur = conn.cursor()
        cur.execute("SELECT * FROM device_state_events WHERE event_id = ?", ("evt_test_001",))
        row = cur.fetchone()
        assert row is not None
        assert row["device_id"] == "light_01"
        assert row["requested_state"] == "ON"
        assert row["state_source"] == "manual"
        assert row["reason_code"] == "wall_switch_toggle"
        assert row["controller_mode"] == "AUTO"
        assert row["command_status"] == "applied"
        assert row["observed_state"] == "assumed"

        # Check that an open runtime session was created
        cur.execute("SELECT * FROM runtime_sessions WHERE device_id = 'light_01' AND end_time_utc IS NULL")
        sess = cur.fetchone()
        assert sess is not None
        assert sess["start_time_utc"] == 1761800000
        assert sess["end_known"] == 1
    finally:
        conn.close()

def test_tc02_on_to_off_event_logging():
    """
    TC-02: Device changes ON -> OFF.
    Completed runtime session calculated and stored in runtime_sessions.
    """
    conn = get_db_connection()
    try:
        # 1. Turn ON at t=1000
        ev_on = {
            "event_id": "evt_test_on",
            "timestamp_utc": 1761801000,
            "device_id": "fan_01",
            "requested_state": "ON",
            "state_source": "local_rule",
            "reason_code": "motion_trigger",
            "controller_mode": "AUTO"
        }
        assert process_device_state_event(ev_on, custom_conn=conn) is True

        # 2. Turn OFF at t=1600 (10 minutes later)
        ev_off = {
            "event_id": "evt_test_off",
            "timestamp_utc": 1761801600,
            "device_id": "fan_01",
            "requested_state": "OFF",
            "state_source": "local_rule",
            "reason_code": "vacancy_auto_off",
            "controller_mode": "AUTO"
        }
        assert process_device_state_event(ev_off, custom_conn=conn) is True

        cur = conn.cursor()
        # Verify event logged
        cur.execute("SELECT * FROM device_state_events WHERE event_id = ?", ("evt_test_off",))
        off_row = cur.fetchone()
        assert off_row is not None
        assert off_row["requested_state"] == "OFF"

        # Verify completed session
        cur.execute("SELECT * FROM runtime_sessions WHERE device_id = 'fan_01' ORDER BY start_time_utc DESC")
        sess = cur.fetchone()
        assert sess is not None
        assert sess["start_time_utc"] == 1761801000
        assert sess["end_time_utc"] == 1761801600
        assert sess["estimated_duration_sec"] == 600
        assert sess["end_known"] == 1
    finally:
        conn.close()

def test_invalid_device_or_state_rejected():
    conn = get_db_connection()
    try:
        # Invalid device
        bad_dev = {
            "event_id": "evt_bad_dev",
            "timestamp_utc": 1761800000,
            "device_id": "heater_01",
            "requested_state": "ON"
        }
        assert process_device_state_event(bad_dev, custom_conn=conn) is False

        # Invalid state
        bad_state = {
            "event_id": "evt_bad_state",
            "timestamp_utc": 1761800000,
            "device_id": "light_01",
            "requested_state": "DIM_50"
        }
        assert process_device_state_event(bad_state, custom_conn=conn) is False
    finally:
        conn.close()

