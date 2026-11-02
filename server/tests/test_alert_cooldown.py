import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.base import create_or_update_anomaly, resolve_anomaly

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_alert_deduplication_and_cooldown():
    """
    FR-10: Alert deduplication and cooldown enforcement:
    - Multiple consecutive detector invocations under active anomaly condition
      must update the existing open alert rather than creating spam rows.
    - Exactly 1 open row per (device_id, anomaly_type) is maintained.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000

        # Simulate 10 consecutive ticks of an active vacancy anomaly
        first_id = None
        for i in range(10):
            tick_ts = t0 + (i * 30)
            anom_id = create_or_update_anomaly(
                device_id="light_01",
                anomaly_type="vacancy_runtime",
                severity="warning",
                observed_value=f"{900 + (i * 30)}s no motion",
                threshold_value="900s",
                evidence={"tick": i},
                detector_type="rule",
                ts=tick_ts,
                custom_conn=conn
            )
            if i == 0:
                first_id = anom_id
            else:
                # Must return the SAME anomaly_id
                assert anom_id == first_id

        # Verify database table has exactly 1 row, not 10 rows
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM anomaly_events WHERE device_id = 'light_01' AND anomaly_type = 'vacancy_runtime'")
        assert cur.fetchone()["cnt"] == 1

        # Verify the single row was updated with latest timestamp
        cur.execute("SELECT * FROM anomaly_events WHERE anomaly_id = ?", (first_id,))
        row = cur.fetchone()
        assert row["timestamp_utc"] == t0 + (9 * 30)
        assert row["status"] == "open"

        # Now condition resolves
        resolved_count = resolve_anomaly("light_01", "vacancy_runtime", resolved_ts=t0 + 400, custom_conn=conn)
        assert resolved_count == 1

        cur.execute("SELECT status, resolved_at FROM anomaly_events WHERE anomaly_id = ?", (first_id,))
        resolved_row = cur.fetchone()
        assert resolved_row["status"] == "resolved"
        assert resolved_row["resolved_at"] == t0 + 400
    finally:
        conn.close()
