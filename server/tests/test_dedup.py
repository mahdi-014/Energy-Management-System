import pytest
from app.db import get_db_connection, run_migrations
from app.analysis import process_device_state_event

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_t12_event_deduplication():
    """
    T12: Storage integrity & duplicate rejection.
    Re-transmitting the exact same event_id (e.g. from MQTT QoS 1 retry or offline flush)
    must be ignored and must not corrupt runtime sessions or create duplicate DB rows.
    """
    conn = get_db_connection()
    try:
        ev = {
            "event_id": "evt_unique_101",
            "timestamp_utc": 1762040000,
            "device_id": "fan_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "user_button",
            "controller_mode": "AUTO"
        }

        # First delivery: success
        res1 = process_device_state_event(ev, custom_conn=conn)
        assert res1 is True

        # Second delivery (duplicate replay): rejected / ignored
        res2 = process_device_state_event(ev, custom_conn=conn)
        assert res2 is False

        cur = conn.cursor()
        # Exactly 1 row in device_state_events
        cur.execute("SELECT COUNT(*) as cnt FROM device_state_events WHERE event_id = 'evt_unique_101'")
        assert cur.fetchone()["cnt"] == 1

        # Exactly 1 open session in runtime_sessions
        cur.execute("SELECT COUNT(*) as cnt FROM runtime_sessions WHERE device_id = 'fan_01'")
        assert cur.fetchone()["cnt"] == 1
    finally:
        conn.close()

