import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.cycling import evaluate_cycling_anomalies

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_tc06_rapid_cycling_diagnostic_detection():
    """
    TC-06: Rapid switching detection (>4 transitions in 10 min):
    - Diagnostic alert generated with severity = 'diagnostic'.
    - Relays are never switched or modified.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000
        cur = conn.cursor()

        # Insert 3 transitions for fan_01 in 10 minutes -> below threshold (<= 4)
        for i in range(3):
            cur.execute("""
                INSERT INTO device_state_events (
                    event_id, timestamp_utc, device_id, requested_state,
                    state_source, reason_code, controller_mode, command_status, observed_state
                ) VALUES (?, ?, 'fan_01', 'ON', 'manual', 'test', 'AUTO', 'applied', 'assumed')
            """, (f"ev_cycle_{i}", t0 + (i * 60)))
        conn.commit()

        anoms_3 = evaluate_cycling_anomalies(t0 + 300, custom_conn=conn)
        assert len(anoms_3) == 0

        # Add 2 more transitions within the 10-minute window -> total 5 transitions (> 4)
        for i in range(3, 5):
            cur.execute("""
                INSERT INTO device_state_events (
                    event_id, timestamp_utc, device_id, requested_state,
                    state_source, reason_code, controller_mode, command_status, observed_state
                ) VALUES (?, ?, 'fan_01', 'OFF', 'manual', 'test', 'AUTO', 'applied', 'assumed')
            """, (f"ev_cycle_{i}", t0 + (i * 60)))
        conn.commit()

        anoms_5 = evaluate_cycling_anomalies(t0 + 300, custom_conn=conn)
        assert len(anoms_5) == 1
        assert anoms_5[0]["device_id"] == "fan_01"
        assert anoms_5[0]["severity"] == "diagnostic"
        assert anoms_5[0]["transition_count"] == 5

        cur.execute("SELECT * FROM anomaly_events WHERE anomaly_type = 'rapid_cycling' AND status = 'open'")
        row = cur.fetchone()
        assert row is not None
        assert row["severity"] == "diagnostic"
        assert "5 switches" in row["observed_value"]
    finally:
        conn.close()
