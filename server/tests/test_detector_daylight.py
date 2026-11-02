import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.base import set_config_value
from app.detectors.daylight import evaluate_daylight_anomaly

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_tc04_t4_t5_daylight_gating_confirmation_and_hysteresis():
    """
    TC-04, T4, T5:
    1. Uncalibrated: Locked/inactive (ADR-007).
    2. Calibrated:
       - Transient bright daylight (< 3 min) ignored.
       - Sustained bright daylight (>= 3 min) generates daylight_waste alert.
       - Hysteresis: Falling below on_threshold clears alert.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000

        # 1. Uncalibrated test (default flag is false)
        res_uncalib = evaluate_daylight_anomaly(
            current_ts=t0 + 200,
            latest_ldr_raw=800,  # very bright
            light_state="ON",
            custom_conn=conn
        )
        assert res_uncalib is None  # Gated by calibration flag

        # 2. Unlock via calibration flag
        set_config_value("daylight_calibration_flag", "true", changed_by="test", custom_conn=conn)

        # 3. Light is OFF -> no anomaly
        res_off = evaluate_daylight_anomaly(
            current_ts=t0 + 200,
            latest_ldr_raw=800,
            light_state="OFF",
            custom_conn=conn
        )
        assert res_off is None

        # 4. Light is ON, but transient spike (only 1 point, no confirmed 3 min history)
        res_transient = evaluate_daylight_anomaly(
            current_ts=t0,
            latest_ldr_raw=800,
            light_state="ON",
            custom_conn=conn
        )
        # Without confirmation history in DB, not confirmed yet
        assert res_transient is None

        # 5. Insert samples across 3-minute confirmation window (t0 to t0 + 180)
        # Ingest 4 samples across 180 seconds above off_threshold (450)
        cur = conn.cursor()
        for offset in (0, 60, 120, 180):
            cur.execute("""
                INSERT INTO sensor_samples (
                    sample_id, room_id, timestamp_utc, ldr_raw, sensor_quality
                ) VALUES (?, 'room1', ?, 750, 'ok')
            """, (f"smpl_ldr_{offset}", t0 + offset))
        conn.commit()

        # Now evaluate at t0 + 185
        res_confirmed = evaluate_daylight_anomaly(
            current_ts=t0 + 185,
            latest_ldr_raw=750,
            light_state="ON",
            custom_conn=conn
        )
        assert res_confirmed is not None
        assert res_confirmed["device_id"] == "light_01"
        assert res_confirmed["severity"] == "warning"

        cur.execute("SELECT * FROM anomaly_events WHERE anomaly_type = 'daylight_waste' AND status = 'open'")
        anom_row = cur.fetchone()
        assert anom_row is not None
        assert anom_row["device_id"] == "light_01"

        # 6. Hysteresis: Room becomes dark (LDR drops below on_threshold 350, e.g. 200)
        res_cleared = evaluate_daylight_anomaly(
            current_ts=t0 + 250,
            latest_ldr_raw=200,
            light_state="ON",
            custom_conn=conn
        )
        assert res_cleared is None

        # Verify alert was marked resolved
        cur.execute("SELECT status FROM anomaly_events WHERE anomaly_id = ?", (anom_row["anomaly_id"],))
        assert cur.fetchone()["status"] == "resolved"
    finally:
        conn.close()

