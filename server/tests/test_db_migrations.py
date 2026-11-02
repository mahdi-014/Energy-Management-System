import sqlite3
import pytest
from pathlib import Path
from app.db import run_migrations, get_db_connection

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_dcems.db"
    mig_dir = Path(__file__).resolve().parent.parent / "migrations"
    run_migrations(custom_path=str(db_file), migrations_dir=str(mig_dir))
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    yield conn
    conn.close()

def test_migration_tables_exist(temp_db):
    cur = temp_db.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row["name"] for row in cur.fetchall()}
    
    expected_tables = {
        "sensor_samples",
        "device_state_events",
        "anomaly_events",
        "control_actions",
        "device_policies",
        "manual_overrides",
        "runtime_sessions",
        "config",
        "audit_log",
        "users",
        "_schema_migrations"
    }
    assert expected_tables.issubset(tables)

def test_device_policies_seeded(temp_db):
    cur = temp_db.cursor()
    cur.execute("SELECT device_id, auto_off_on_vacancy, auto_action_enabled FROM device_policies;")
    rows = {row["device_id"]: dict(row) for row in cur.fetchall()}
    
    assert set(rows.keys()) == {"light_01", "fan_01", "ac_01", "pc_01"}
    
    # Safety invariant: auto_action_enabled must default to 0 for all devices
    for dev_id, policy in rows.items():
        assert policy["auto_action_enabled"] == 0
        
    # AC and PC must not have auto_off_on_vacancy enabled
    assert rows["ac_01"]["auto_off_on_vacancy"] == 0
    assert rows["pc_01"]["auto_off_on_vacancy"] == 0

def test_sensor_samples_null_allowed_and_bounds_check(temp_db):
    cur = temp_db.cursor()
    
    # Valid sample with NULL sensor readings (sensor failure scenario)
    cur.execute("""
        INSERT INTO sensor_samples (sample_id, room_id, timestamp_utc, pir_motion, ldr_raw, temperature_c, humidity_pct, sensor_quality)
        VALUES ('s_001', 'room1', 1793600000, NULL, NULL, NULL, NULL, 'fault');
    """)
    temp_db.commit()
    
    cur.execute("SELECT pir_motion, ldr_raw, temperature_c FROM sensor_samples WHERE sample_id = 's_001';")
    row = cur.fetchone()
    assert row["pir_motion"] is None
    assert row["ldr_raw"] is None
    assert row["temperature_c"] is None

    # Invalid ldr_raw (out of bounds > 1023) should violate CHECK constraint
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute("""
            INSERT INTO sensor_samples (sample_id, room_id, timestamp_utc, ldr_raw)
            VALUES ('s_002', 'room1', 1793600010, 1050);
        """)
        temp_db.commit()

def test_device_state_events_device_constraint(temp_db):
    cur = temp_db.cursor()
    
    # Invalid device_id must be rejected by CHECK constraint
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute("""
            INSERT INTO device_state_events (event_id, timestamp_utc, device_id, requested_state, state_source, reason_code, controller_mode, command_status, observed_state)
            VALUES ('evt_001', 1793600000, 'heater_99', 'ON', 'manual', 'test', 'AUTO', 'applied', 'assumed');
        """)
        temp_db.commit()

def test_config_table_seeded(temp_db):
    cur = temp_db.cursor()
    cur.execute("SELECT key, value FROM config WHERE key = 'vacancy_candidate_sec';")
    row = cur.fetchone()
    assert row is not None
    assert row["value"] == "300"

