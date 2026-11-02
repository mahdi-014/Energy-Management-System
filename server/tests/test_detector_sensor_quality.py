import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.sensor_quality import evaluate_sensor_quality_anomaly

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_tc08_t8_sensor_quality_and_staleness_anomaly():
    """
    TC-08 & T8: Sensor quality degradation and staleness detection:
    - Generates sensor_issue alert when data is missing, stale (>60s), or out-of-bounds.
    - Used to suppress unsafe automated actions in safety gate.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000

        # 1. Fresh healthy sample (30s old, quality ok) -> no anomaly
        healthy_sample = {
            "timestamp_utc": t0 - 30,
            "pir_motion": 0,
            "ldr_raw": 550,
            "temperature_c": 28.5,
            "humidity_pct": 65.0,
            "sensor_quality": "ok"
        }
        res_ok = evaluate_sensor_quality_anomaly(t0, healthy_sample, custom_conn=conn)
        assert res_ok is None

        # 2. Stale sample (90s old > 60s threshold) -> sensor_issue alert
        stale_sample = {
            "timestamp_utc": t0 - 90,
            "pir_motion": 0,
            "ldr_raw": 550,
            "temperature_c": 28.5,
            "humidity_pct": 65.0,
            "sensor_quality": "ok"
        }
        res_stale = evaluate_sensor_quality_anomaly(t0, stale_sample, custom_conn=conn)
        assert res_stale is not None
        assert res_stale["severity"] == "warning"
        assert res_stale["issue"] == "stale_telemetry"

        cur = conn.cursor()
        cur.execute("SELECT * FROM anomaly_events WHERE anomaly_type = 'sensor_issue' AND status = 'open'")
        anom_row = cur.fetchone()
        assert anom_row is not None

        # 3. Faulty sample (fresh timestamp but temperature is NULL and quality is 'fault')
        fault_sample = {
            "timestamp_utc": t0 - 10,
            "pir_motion": 0,
            "ldr_raw": 550,
            "temperature_c": None,  # Corrupted/missing reading
            "humidity_pct": None,
            "sensor_quality": "fault"
        }
        res_fault = evaluate_sensor_quality_anomaly(t0, fault_sample, custom_conn=conn)
        assert res_fault is not None
        assert res_fault["severity"] == "warning"
        assert res_fault["issue"] == "sensor_fault"

        # 4. Sensor recovered: fresh healthy readings resume (10s old at t0 + 60)
        recovered_sample = {
            "timestamp_utc": t0 + 50,
            "pir_motion": 0,
            "ldr_raw": 550,
            "temperature_c": 28.5,
            "humidity_pct": 65.0,
            "sensor_quality": "ok"
        }
        res_recovered = evaluate_sensor_quality_anomaly(t0 + 60, recovered_sample, custom_conn=conn)
        assert res_recovered is None

        # Verify alert marked resolved
        cur.execute("SELECT status FROM anomaly_events WHERE anomaly_type = 'sensor_issue'")
        assert cur.fetchone()["status"] == "resolved"
    finally:
        conn.close()
