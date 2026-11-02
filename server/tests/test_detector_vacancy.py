import pytest
from app.db import get_db_connection, run_migrations
from app.detectors.vacancy import evaluate_vacancy_anomalies

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_tc03_t2_vacancy_stages_progression():
    """
    TC-03 & T2: Multi-stage vacancy progression:
    - 5m: vacancy candidate (no alert yet)
    - 10m: warning stage (severity = info) if device is ON
    - 15m: confirmed vacancy action candidate (severity = warning) if device is ON
    - Strictly Alert-Only.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000
        device_states = {
            "light_01": "ON",
            "fan_01": "ON",
            "ac_01": "OFF",
            "pc_01": "OFF"
        }

        # Stage 0: 2 minutes after motion (< 5 min) -> no alert
        anoms_0 = evaluate_vacancy_anomalies(t0 + 120, t0, device_states, custom_conn=conn)
        assert len(anoms_0) == 0

        # Stage 1: 7 minutes after motion (5-10 min) -> vacancy candidate -> no alert yet
        anoms_1 = evaluate_vacancy_anomalies(t0 + 420, t0, device_states, custom_conn=conn)
        assert len(anoms_1) == 0

        # Stage 2: 11 minutes after motion (10-15 min) -> Warning stage -> severity info
        anoms_2 = evaluate_vacancy_anomalies(t0 + 660, t0, device_states, custom_conn=conn)
        assert len(anoms_2) == 2  # light_01 and fan_01
        for a in anoms_2:
            assert a["severity"] == "info"
            assert a["stage"] == "warning"

        # Check DB rows
        cur = conn.cursor()
        cur.execute("SELECT * FROM anomaly_events WHERE status = 'open'")
        rows_stage2 = cur.fetchall()
        assert len(rows_stage2) == 2
        for r in rows_stage2:
            assert r["severity"] == "info"
            assert r["anomaly_type"] == "vacancy_runtime"

        # Stage 3: 16 minutes after motion (> 15 min) -> Confirmed Vacancy -> severity warning
        anoms_3 = evaluate_vacancy_anomalies(t0 + 960, t0, device_states, custom_conn=conn)
        assert len(anoms_3) == 2
        for a in anoms_3:
            assert a["severity"] == "warning"
            assert a["stage"] == "action_candidate"

        # Deduplication check: existing rows were updated, not duplicated
        cur.execute("SELECT COUNT(*) as cnt FROM anomaly_events WHERE status = 'open'")
        assert cur.fetchone()["cnt"] == 2

        # Motion returns! New motion at t0 + 1000
        anoms_cleared = evaluate_vacancy_anomalies(t0 + 1010, t0 + 1000, device_states, custom_conn=conn)
        assert len(anoms_cleared) == 0

        # Verify previous alerts were marked resolved
        cur.execute("SELECT COUNT(*) as cnt FROM anomaly_events WHERE status = 'resolved'")
        assert cur.fetchone()["cnt"] == 2
    finally:
        conn.close()

def test_tc11_ac_pc_vacancy_alert_only():
    """
    TC-11: When AC or PC is left running during confirmed vacancy,
    an alert is generated for human awareness, but automated shutdown is strictly prohibited.
    """
    conn = get_db_connection()
    try:
        t0 = 1762040000
        device_states = {
            "light_01": "OFF",
            "fan_01": "OFF",
            "ac_01": "ON",
            "pc_01": "ON"
        }

        # 16 minutes without motion
        anoms = evaluate_vacancy_anomalies(t0 + 960, t0, device_states, custom_conn=conn)
        assert len(anoms) == 2
        dev_ids = {a["device_id"] for a in anoms}
        assert dev_ids == {"ac_01", "pc_01"}

        cur = conn.cursor()
        cur.execute("SELECT device_id, severity, anomaly_type, status FROM anomaly_events WHERE status = 'open'")
        rows = cur.fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r["anomaly_type"] == "vacancy_runtime"
            assert r["severity"] == "warning"
            assert r["status"] == "open"
    finally:
        conn.close()

