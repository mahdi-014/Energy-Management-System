import time
from datetime import datetime, timezone
import pytest

from app.db import run_migrations, get_db_connection
from app.analysis import get_hourly_runtime_distribution, process_device_state_event

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "hourly_test.db"
    monkeypatch.setattr("app.config.settings.db_path", str(db_file))
    run_migrations(custom_path=str(db_file))
    conn = get_db_connection(custom_path=str(db_file))
    yield conn
    conn.close()

def test_t14_hourly_runtime_distribution_fixture(test_db):
    """
    Test T14: Validates hand-calculated hourly usage distribution math in local timezone.
    Local timezone: Asia/Dhaka (UTC+6).
    Fixture:
      Date: 2026-11-02
      Session 1: light_01 turned ON at 10:30 local and turned OFF at 11:45 local.
      Duration: 75 minutes.
      Expected in 10:00 bin: exactly 30.0 minutes.
      Expected in 11:00 bin: exactly 45.0 minutes.
      All other 22 hour bins: 0.0 minutes.
      Total for light_01: 75.0 minutes.
    """
    tz_offset_hours = 6
    target_date_str = "2026-11-02"

    # Midnight 2026-11-02 UTC is 1793577600
    # Local midnight (00:00 Asia/Dhaka) in UTC is: 1793577600 - (6 * 3600) = 1793556000
    local_midnight_utc = 1793556000

    # 10:30 local = local_midnight_utc + (10 * 3600) + (30 * 60) = 1793556000 + 36000 + 1800 = 1793593800
    # 11:45 local = local_midnight_utc + (11 * 3600) + (45 * 60) = 1793556000 + 39600 + 2700 = 1793598300
    t_on = 1793593800
    t_off = 1793598300

    # Ingest ON event
    process_device_state_event({
        "event_id": "evt_h_on_01",
        "timestamp_utc": t_on,
        "device_id": "light_01",
        "requested_state": "ON",
        "state_source": "manual"
    }, custom_conn=test_db)

    # Ingest OFF event
    process_device_state_event({
        "event_id": "evt_h_off_01",
        "timestamp_utc": t_off,
        "device_id": "light_01",
        "requested_state": "OFF",
        "state_source": "manual"
    }, custom_conn=test_db)

    # Query hourly distribution
    dist = get_hourly_runtime_distribution(
        date_local=target_date_str,
        tz_offset_hours=tz_offset_hours,
        custom_conn=test_db
    )

    assert dist["date_local"] == target_date_str
    assert dist["timezone"] == "Asia/Dhaka (UTC+6)"
    assert len(dist["hours"]) == 24

    light_bins = dist["devices"]["light_01"]
    assert len(light_bins) == 24

    # 10:00 bin (index 10) must have 30.0 mins
    assert light_bins[10] == 30.0

    # 11:00 bin (index 11) must have 45.0 mins
    assert light_bins[11] == 45.0

    # Other hours should be 0.0
    for h in range(24):
        if h not in (10, 11):
            assert light_bins[h] == 0.0

    # Total runtime
    assert dist["total_runtime_minutes"]["light_01"] == 75.0

    # Verify mandatory honest labels present
    labels = dist["labels"]
    assert "estimate" in labels["runtime_disclaimer"].lower()
    assert "energy_notice" in labels

