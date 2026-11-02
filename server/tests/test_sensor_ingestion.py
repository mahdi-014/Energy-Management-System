import json
import time
import sqlite3
import pytest
from pathlib import Path

from app.db import run_migrations, get_db_connection
from app.config import settings
from app.mqtt_client import process_sensor_message, derive_occupancy_state

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "sensor_test.db"
    settings.db_path = str(db_file)
    run_migrations(custom_path=str(db_file))
    yield db_file

def test_sensor_ingestion_valid_payload(test_db):
    """FR-02: Sensor readings recorded with UTC timestamps."""
    now = int(time.time())
    payload = {
        "event_id": "evt_test_01",
        "ts": now - 2,
        "room_id": "room1",
        "pir": 1,
        "ldr": 512,
        "light_pct": 50,
        "temp": 26.5,
        "hum": 55.0,
        "last_motion_at": now - 2,
        "valid": True,
        "quality": "ok"
    }

    result = process_sensor_message(json.dumps(payload).encode("utf-8"), server_receipt_ts=now)
    assert result is not None
    assert result["temperature_c"] == 26.5
    assert result["humidity_pct"] == 55.0
    assert result["ldr_raw"] == 512
    assert result["pir_motion"] == 1
    assert result["occupancy_state"] == "occupied_recently"

    # Query SQLite directly to verify database persistence
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sensor_samples WHERE sample_id = 'evt_test_01'")
        row = cur.fetchone()
        assert row is not None
        assert row["temperature_c"] == 26.5
        assert row["humidity_pct"] == 55.0
        assert row["ldr_raw"] == 512
        assert row["pir_motion"] == 1
        assert row["timestamp_utc"] == now
        assert row["device_ts"] == now - 2
    finally:
        conn.close()

def test_sensor_ingestion_null_not_zero_on_invalid(test_db):
    """Safety Invariant: Missing or corrupted readings must be NULL, NEVER 0."""
    now = int(time.time())
    payload = {
        "event_id": "evt_corrupt_02",
        "ts": now,
        "room_id": "room1",
        "pir": 99,           # Invalid PIR value
        "ldr": 1500,         # Out of bounds (> 1023)
        "light_pct": -5,     # Out of bounds
        "temp": 85.0,        # Out of bounds (> 50C)
        "hum": "invalid",    # Non-numeric
        "last_motion_at": None,
        "valid": False,
        "quality": "fault"
    }

    result = process_sensor_message(json.dumps(payload).encode("utf-8"), server_receipt_ts=now)
    assert result is not None

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT pir_motion, ldr_raw, ambient_light_level, temperature_c, humidity_pct FROM sensor_samples WHERE sample_id = 'evt_corrupt_02'")
        row = cur.fetchone()
        assert row is not None
        assert row["pir_motion"] is None
        assert row["ldr_raw"] is None
        assert row["ambient_light_level"] is None
        assert row["temperature_c"] is None
        assert row["humidity_pct"] is None
    finally:
        conn.close()

def test_derive_occupancy_state():
    """Verify occupancy state transitions based on PIR motion timing."""
    now = 10000

    # Recent motion (< 5 min / 300 s)
    assert derive_occupancy_state(pir_motion=1, last_motion_at=now - 50, current_ts=now, quality="ok") == "occupied_recently"
    assert derive_occupancy_state(pir_motion=0, last_motion_at=now - 250, current_ts=now, quality="ok") == "occupied_recently"

    # Vacancy candidate (between 5 and 15 min / 300s - 900s)
    assert derive_occupancy_state(pir_motion=0, last_motion_at=now - 301, current_ts=now, quality="ok") == "vacancy_candidate"
    assert derive_occupancy_state(pir_motion=0, last_motion_at=now - 899, current_ts=now, quality="ok") == "vacancy_candidate"

    # Vacant confirmed (>= 15 min / 900s)
    assert derive_occupancy_state(pir_motion=0, last_motion_at=now - 901, current_ts=now, quality="ok") == "vacant_confirmed"

    # Fault or no motion timestamp
    assert derive_occupancy_state(pir_motion=0, last_motion_at=None, current_ts=now, quality="ok") == "unknown"
    assert derive_occupancy_state(pir_motion=0, last_motion_at=now - 100, current_ts=now, quality="fault") == "unknown"

