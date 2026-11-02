import json
import time
import pytest

from app.mqtt_client import process_sensor_message, get_system_status, _live_state_lock, _live_system_status
from app.db import run_migrations
from app.config import settings

@pytest.fixture
def clean_status(tmp_path):
    db_file = tmp_path / "stale_test.db"
    settings.db_path = str(db_file)
    run_migrations(custom_path=str(db_file))
    
    with _live_state_lock:
        _live_system_status["is_online"] = True
        _live_system_status["last_seen_utc"] = None
        _live_system_status["latest_sensor"] = None
    yield
    with _live_state_lock:
        _live_system_status["last_seen_utc"] = None
        _live_system_status["latest_sensor"] = None

def test_stale_when_no_readings(clean_status):
    status = get_system_status()
    assert status["is_stale"] is True

def test_fresh_reading_not_stale(clean_status):
    """T1: Fresh sensor readings marked valid and active."""
    now = int(time.time())
    payload = {
        "event_id": "evt_fresh_01",
        "ts": now,
        "room_id": "room1",
        "pir": 0,
        "ldr": 450,
        "temp": 25.0,
        "hum": 50.0,
        "last_motion_at": now - 100,
        "valid": True,
        "quality": "ok"
    }
    process_sensor_message(json.dumps(payload).encode("utf-8"), server_receipt_ts=now)

    status = get_system_status()
    assert status["is_stale"] is False
    assert status["last_seen_utc"] == now

def test_stale_after_60_seconds_t1(clean_status):
    """T1: Readings older than 60s are flagged as stale."""
    now = int(time.time())
    old_ts = now - 65  # 65 seconds ago (> 60s)
    
    payload = {
        "event_id": "evt_old_01",
        "ts": old_ts,
        "room_id": "room1",
        "pir": 0,
        "ldr": 450,
        "temp": 25.0,
        "hum": 50.0,
        "last_motion_at": old_ts,
        "valid": True,
        "quality": "ok"
    }
    process_sensor_message(json.dumps(payload).encode("utf-8"), server_receipt_ts=old_ts)

    status = get_system_status()
    assert status["is_stale"] is True
