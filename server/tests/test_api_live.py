import json
import time
import pytest

from app.db import run_migrations, get_db_connection
from app.config import settings
from app.main import get_live_telemetry, get_sensor_readings
from app.mqtt_client import process_sensor_message, _live_state_lock, _live_system_status

@pytest.fixture
def live_api_db(tmp_path):
    db_file = tmp_path / "live_api_test.db"
    settings.db_path = str(db_file)
    run_migrations(custom_path=str(db_file))
    
    with _live_state_lock:
        _live_system_status["is_online"] = True
        _live_system_status["last_seen_utc"] = int(time.time())
        _live_system_status["latest_sensor"] = None
    yield db_file
    with _live_state_lock:
        _live_system_status["latest_sensor"] = None

def test_get_live_telemetry_schema_and_labels(live_api_db):
    """FR-18: Verify mandatory disclaimers and live telemetry schema."""
    now = int(time.time())
    payload = {
        "event_id": "evt_live_01",
        "ts": now,
        "room_id": "room1",
        "pir": 0,
        "ldr": 600,
        "temp": 28.0,
        "hum": 65.0,
        "last_motion_at": now - 60,
        "valid": True,
        "quality": "ok"
    }
    process_sensor_message(json.dumps(payload).encode("utf-8"), server_receipt_ts=now)

    res = get_live_telemetry()
    assert res["room_id"] == "room1"
    assert res["is_online"] is True
    assert res["is_stale"] is False
    assert "devices" in res
    assert res["devices"]["light_01"] == "OFF"
    assert res["sensor"] is not None
    assert res["sensor"]["temperature_c"] == 28.0

    # Invariant: Disclaimers must be present
    assert "PIR detects motion, not people" in res["labels"]["occupancy_disclaimer"]
    assert "estimates based on commanded relay state" in res["labels"]["runtime_disclaimer"]

def test_get_sensor_readings_history(live_api_db):
    base_ts = 1793600000
    for i in range(5):
        payload = {
            "event_id": f"evt_hist_{i}",
            "ts": base_ts + i * 30,
            "room_id": "room1",
            "pir": i % 2,
            "ldr": 500 + i * 10,
            "temp": 25.0 + i * 0.5,
            "hum": 50.0 + i,
            "last_motion_at": base_ts + i * 30,
            "valid": True,
            "quality": "ok"
        }
        process_sensor_message(json.dumps(payload).encode("utf-8"), server_receipt_ts=base_ts + i * 30)

    # Query all
    readings = get_sensor_readings(limit=10)
    assert len(readings) == 5
    # Should be chronological
    assert readings[0]["timestamp_utc"] == base_ts
    assert readings[-1]["timestamp_utc"] == base_ts + 120

    # Query with filter
    filtered = get_sensor_readings(from_ts=base_ts + 30, to_ts=base_ts + 90, limit=10)
    assert len(filtered) == 3
    assert filtered[0]["timestamp_utc"] == base_ts + 30
    assert filtered[-1]["timestamp_utc"] == base_ts + 90
