import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.runtime import evaluate_runtime_anomalies

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_tc05_runtime_threshold_detection():
    """
    TC-05: Continuous runtime threshold violation detection:
    - Default policy: max_continuous_on_min is NULL -> no alerts.
    - Configured: e.g. 60 minutes -> triggers info alert when exceeded.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000
        cur = conn.cursor()

        # Insert open session for fan_01 starting at t0
        cur.execute("""
            INSERT INTO runtime_sessions (session_id, device_id, start_time_utc, end_time_utc, end_known)
            VALUES ('sess_fan_long', 'fan_01', ?, NULL, 1)
        """, (t0,))
        conn.commit()

        # 1. Default policy: max_continuous_on_min is NULL
        anoms_unconf = evaluate_runtime_anomalies(t0 + 7200, custom_conn=conn)  # 2 hours later
        assert len(anoms_unconf) == 0

        # 2. Configure max_continuous_on_min = 60 for fan_01
        cur.execute("UPDATE device_policies SET max_continuous_on_min = 60 WHERE device_id = 'fan_01'")
        conn.commit()

        # 3. Running for 45 minutes (< 60 min) -> no alert
        anoms_45 = evaluate_runtime_anomalies(t0 + (45 * 60), custom_conn=conn)
        assert len(anoms_45) == 0

        # 4. Running for 75 minutes (> 60 min) -> long_runtime alert generated
        anoms_75 = evaluate_runtime_anomalies(t0 + (75 * 60), custom_conn=conn)
        assert len(anoms_75) == 1
        assert anoms_75[0]["device_id"] == "fan_01"
        assert anoms_75[0]["severity"] == "info"

        cur.execute("SELECT * FROM anomaly_events WHERE anomaly_type = 'long_runtime' AND status = 'open'")
        row = cur.fetchone()
        assert row is not None
        assert row["device_id"] == "fan_01"
        assert row["severity"] == "info"

        # 5. Device turned OFF (session closed)
        cur.execute("UPDATE runtime_sessions SET end_time_utc = ? WHERE session_id = 'sess_fan_long'", (t0 + 4600,))
        conn.commit()

        anoms_closed = evaluate_runtime_anomalies(t0 + 4700, custom_conn=conn)
        assert len(anoms_closed) == 0

        # Verify alert was marked resolved
        cur.execute("SELECT status FROM anomaly_events WHERE anomaly_id = ?", (row["anomaly_id"],))
        assert cur.fetchone()["status"] == "resolved"
    finally:
        conn.close()

