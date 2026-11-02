import json
import time
import pytest

from app.mqtt_client import process_status_message, get_system_status, _live_state_lock, _live_system_status

@pytest.fixture(autouse=True)
def reset_status():
    with _live_state_lock:
        _live_system_status["is_online"] = False
        _live_system_status["last_seen_utc"] = None
        _live_system_status["last_heartbeat_utc"] = None
        _live_system_status["uptime_sec"] = 0
    yield
    with _live_state_lock:
        _live_system_status["is_online"] = False

def test_lwt_offline_transition():
    now = int(time.time())
    offline_msg = {
        "status": "offline",
        "ts": now,
        "reason": "unexpected_disconnect"
    }
    process_status_message(json.dumps(offline_msg).encode("utf-8"), server_receipt_ts=now)
    
    status = get_system_status()
    assert status["is_online"] is False
    assert status["last_seen_utc"] == now

def test_heartbeat_online_transition():
    now = int(time.time())
    online_msg = {
        "status": "online",
        "ts": now,
        "firmware_version": "1.0.0",
        "uptime_sec": 420
    }
    process_status_message(json.dumps(online_msg).encode("utf-8"), server_receipt_ts=now)
    
    status = get_system_status()
    assert status["is_online"] is True
    assert status["firmware_version"] == "1.0.0"
    assert status["uptime_sec"] == 420
    assert status["last_heartbeat_utc"] == now

