import pytest
from app.db import run_migrations, get_db_connection
from app.analysis import (
    get_adaptive_baseline,
    set_adaptive_baseline_flag,
    get_all_adaptive_baselines
)
from app.main import toggle_baseline_flag, get_baseline_analysis, BaselineFlagRequest

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "baseline_test.db"
    monkeypatch.setattr("app.config.settings.db_path", str(db_file))
    run_migrations(custom_path=str(db_file))
    conn = get_db_connection(custom_path=str(db_file))
    yield conn
    conn.close()

def test_adaptive_baseline_default_flag_off(test_db):
    """
    Spec Invariant: Adaptive baseline is protected behind a feature flag, DEFAULT OFF.
    """
    res = get_adaptive_baseline("fan_01", custom_conn=test_db)
    assert res["feature_flag_enabled"] is False
    assert res["status"] == "disabled"

def test_adaptive_baseline_insufficient_sessions_guard(test_db):
    """
    Spec Invariant: Requires >= 20 comparable sessions before activating.
    """
    set_adaptive_baseline_flag(True, custom_conn=test_db)

    # Insert 10 completed sessions (< 20)
    for i in range(10):
        test_db.execute("""
            INSERT INTO runtime_sessions (
                session_id, device_id, start_time_utc, end_time_utc,
                estimated_duration_sec, end_known
            ) VALUES (?, 'fan_01', ?, ?, 600, 1)
        """, (f"sess_base_{i}", 1793500000 + i * 1000, 1793500600 + i * 1000))
    test_db.commit()

    res = get_adaptive_baseline("fan_01", custom_conn=test_db)
    assert res["feature_flag_enabled"] is True
    assert res["status"] == "insufficient_data"
    assert res["completed_sessions_count"] == 10
    assert res["required_sessions_count"] == 20

def test_adaptive_baseline_hand_calculated_median_mad(test_db):
    """
    Spec Invariant: Empirical statistical outlier calculation:
    Median + 3 * (1.4826 * MAD).
    Hand-calculated fixture:
      10 sessions with duration 600s, 10 sessions with duration 1200s.
      Sorted: [600]*10 + [1200]*10.
      Median = (600 + 1200) / 2 = 900.0s.
      All absolute deviations: |600 - 900| = 300, |1200 - 900| = 300.
      MAD = 300.0s.
      Upper Threshold = 900.0 + 3 * (1.4826 * 300.0) = 900.0 + 1334.34 = 2234.34s (rounded to 2234.3s).
    """
    set_adaptive_baseline_flag(True, custom_conn=test_db)

    # Insert 10x 600s sessions
    for i in range(10):
        test_db.execute("""
            INSERT INTO runtime_sessions (
                session_id, device_id, start_time_utc, end_time_utc,
                estimated_duration_sec, end_known
            ) VALUES (?, 'fan_01', ?, ?, 600, 1)
        """, (f"sess_low_{i}", 1793500000 + i * 2000, 1793500600 + i * 2000))

    # Insert 10x 1200s sessions
    for i in range(10):
        test_db.execute("""
            INSERT INTO runtime_sessions (
                session_id, device_id, start_time_utc, end_time_utc,
                estimated_duration_sec, end_known
            ) VALUES (?, 'fan_01', ?, ?, 1200, 1)
        """, (f"sess_high_{i}", 1793530000 + i * 2000, 1793531200 + i * 2000))
    test_db.commit()

    res = get_adaptive_baseline("fan_01", custom_conn=test_db)
    assert res["status"] == "active"
    assert res["completed_sessions_count"] == 20
    assert res["median_sec"] == 900.0
    assert res["mad_sec"] == 300.0
    assert abs(res["upper_threshold_sec"] - 2234.3) <= 0.1

def test_api_adaptive_baseline_toggle(test_db):
    user = {"username": "admin", "role": "admin"}
    req_enable = BaselineFlagRequest(enabled=True)
    res_en = toggle_baseline_flag(req_enable, user=user)
    assert res_en["success"] is True
    assert res_en["adaptive_baseline_enabled"] is True

    summary = get_baseline_analysis()
    assert summary["feature_flag_enabled"] is True
    assert "devices" in summary
    assert "fan_01" in summary["devices"]

    req_disable = BaselineFlagRequest(enabled=False)
    res_dis = toggle_baseline_flag(req_disable, user=user)
    assert res_dis["adaptive_baseline_enabled"] is False
