import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.base import create_or_update_anomaly
from app.main import (
    get_anomalies,
    acknowledge_anomaly,
    calibrate_daylight,
    get_calibration_status,
    DaylightCalibrationRequest
)

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_api_anomalies_list_and_filter():
    """
    Tests GET /api/anomalies filtering by status, severity, and device_id.
    """
    conn = get_db_connection()
    try:
        # Create 2 test anomalies
        create_or_update_anomaly(
            device_id="light_01",
            anomaly_type="vacancy_runtime",
            severity="warning",
            observed_value="950s",
            threshold_value="900s",
            evidence={"stage": "action_candidate"},
            custom_conn=conn
        )
        create_or_update_anomaly(
            device_id="fan_01",
            anomaly_type="rapid_cycling",
            severity="diagnostic",
            observed_value="5 switches",
            threshold_value="4",
            evidence={"count": 5},
            custom_conn=conn
        )

        # 1. Fetch all
        all_anoms = get_anomalies()
        assert len(all_anoms) == 2

        # 2. Filter by severity
        diag_anoms = get_anomalies(severity="diagnostic")
        assert len(diag_anoms) == 1
        assert diag_anoms[0]["anomaly_type"] == "rapid_cycling"

        # 3. Filter by device_id
        light_anoms = get_anomalies(device_id="light_01")
        assert len(light_anoms) == 1
        assert light_anoms[0]["device_id"] == "light_01"
    finally:
        conn.close()

def test_api_anomalies_acknowledge():
    """
    Tests POST /api/anomalies/{id}/ack updates status to 'acknowledged'
    and creates audit log entry.
    """
    conn = get_db_connection()
    try:
        anom_id = create_or_update_anomaly(
            device_id="pc_01",
            anomaly_type="vacancy_runtime",
            severity="warning",
            observed_value="1000s",
            threshold_value="900s",
            evidence={"test": 1},
            custom_conn=conn
        )

        res = acknowledge_anomaly(anom_id)
        assert res["status"] == "acknowledged"
        assert res["anomaly_id"] == anom_id

        # Verify DB status
        cur = conn.cursor()
        cur.execute("SELECT status FROM anomaly_events WHERE anomaly_id = ?", (anom_id,))
        assert cur.fetchone()["status"] == "acknowledged"

        # Verify audit log entry
        cur.execute("SELECT * FROM audit_log WHERE event_type = 'anomaly_action'")
        log_entry = cur.fetchone()
        assert log_entry is not None
        assert anom_id in log_entry["details"]
    finally:
        conn.close()

def test_api_daylight_calibration_workflow():
    """
    Tests GET and POST /api/settings/calibrate-daylight.
    """
    # 1. Initial status: uncalibrated
    initial_status = get_calibration_status()
    assert initial_status["daylight_calibration_flag"] is False
    assert "Uncalibrated" in initial_status["status_text"]

    # 2. Perform calibration
    req = DaylightCalibrationRequest(
        daylight_on_threshold=320,
        daylight_off_threshold=480,
        set_calibrated=True
    )
    calib_res = calibrate_daylight(req)
    assert calib_res["success"] is True
    assert calib_res["daylight_calibration_flag"] is True
    assert calib_res["daylight_on_threshold"] == 320
    assert calib_res["daylight_off_threshold"] == 480

    # 3. Updated status: calibrated & active
    updated_status = get_calibration_status()
    assert updated_status["daylight_calibration_flag"] is True
    assert updated_status["daylight_on_threshold"] == 320
    assert updated_status["daylight_off_threshold"] == 480
    assert "Calibrated & Active" in updated_status["status_text"]

    # 4. Verify audit trail
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_log WHERE event_type = 'settings_change'")
        entry = cur.fetchone()
        assert entry is not None
        assert "calibrate_daylight" in entry["details"]
    finally:
        conn.close()
