import pytest
from app.db import get_db_connection, run_migrations
from app.analysis import process_device_state_event
from app.main import get_device_events, get_runtime_analysis, get_runtime_sessions
from app.mqtt_client import _live_state_lock, _live_system_status

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    with _live_state_lock:
        _live_system_status["devices"] = {
            "light_01": "OFF",
            "fan_01": "OFF",
            "ac_01": "OFF",
            "pc_01": "OFF"
        }
    yield test_db
    with _live_state_lock:
        _live_system_status["devices"] = {
            "light_01": "OFF",
            "fan_01": "OFF",
            "ac_01": "OFF",
            "pc_01": "OFF"
        }

def test_api_events_filtering():
    """
    Tests GET /api/events filtering by device_id and state_source.
    """
    conn = get_db_connection()
    try:
        process_device_state_event({
            "event_id": "ev_1",
            "timestamp_utc": 1000,
            "device_id": "light_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "switch_on"
        }, custom_conn=conn)

        process_device_state_event({
            "event_id": "ev_2",
            "timestamp_utc": 1050,
            "device_id": "fan_01",
            "requested_state": "ON",
            "state_source": "local_rule",
            "reason_code": "motion"
        }, custom_conn=conn)

        # 1. Fetch all events
        all_events = get_device_events()
        assert len(all_events) == 2

        # 2. Filter by device_id
        light_events = get_device_events(device_id="light_01")
        assert len(light_events) == 1
        assert light_events[0]["device_id"] == "light_01"

        # 3. Filter by state_source
        rule_events = get_device_events(state_source="local_rule")
        assert len(rule_events) == 1
        assert rule_events[0]["device_id"] == "fan_01"
    finally:
        conn.close()

def test_api_analysis_runtime_endpoint():
    """
    Tests GET /api/analysis/runtime returns structured daily analysis
    with the required honest disclaimer.
    """
    conn = get_db_connection()
    try:
        process_device_state_event({
            "event_id": "ev_r1",
            "timestamp_utc": 1793578000,
            "device_id": "fan_01",
            "requested_state": "ON",
            "state_source": "manual"
        }, custom_conn=conn)
        process_device_state_event({
            "event_id": "ev_r2",
            "timestamp_utc": 1793578600,
            "device_id": "fan_01",
            "requested_state": "OFF",
            "state_source": "manual"
        }, custom_conn=conn)

        res = get_runtime_analysis(date_utc="2026-11-02")
        assert res["date_utc"] == "2026-11-02"
        assert "devices" in res
        assert res["devices"]["fan_01"]["total_runtime_sec"] == 600
        assert "estimates based on commanded relay state" in res["labels"]["runtime_disclaimer"].lower()
    finally:
        conn.close()

def test_api_analysis_sessions_endpoint():
    """
    Tests GET /api/analysis/sessions audit list.
    """
    conn = get_db_connection()
    try:
        process_device_state_event({
            "event_id": "ev_s1",
            "timestamp_utc": 1000,
            "device_id": "ac_01",
            "requested_state": "ON",
            "state_source": "manual"
        }, custom_conn=conn)

        sessions = get_runtime_sessions(device_id="ac_01")
        assert len(sessions) == 1
        assert sessions[0]["device_id"] == "ac_01"
        assert sessions[0]["start_time_utc"] == 1000
    finally:
        conn.close()
