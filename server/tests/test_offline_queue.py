import json
import pytest
from app.db import get_db_connection, run_migrations
from app.analysis import process_device_state_event, handle_outage_or_data_gap
from simulator.mock_esp import MockESP8266

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_dcems.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_t11_offline_queue_overflow_and_data_gap_catchup():
    """
    T11: Offline resilience and bounded event queue overflow handling.
    1. Controller is offline.
    2. Events are queued in bounded 50-item RAM buffer.
    3. Exceeding capacity drops oldest events and records data gap.
    4. Upon reconnection, data_gap event is emitted and backend marks
       unclosed sessions as interrupted.
    """
    esp = MockESP8266(room_id="room1")
    esp.is_connected = False  # Simulating network disconnection

    # Turn light ON at t=1000
    esp.set_device_state("light_01", "ON", source="manual", ts=1000)
    assert len(esp.event_queue) == 2  # event + state snapshot

    # Produce 55 sensor snapshots to overflow the 50-item RAM queue
    for i in range(55):
        esp.publish_sensor_snapshot(pir=0, ldr=500, temp=25.0, hum=60.0)

    # Queue must be bounded to max_queue_size (50)
    assert len(esp.event_queue) == 50
    assert esp.data_gap_occurred is True
    assert esp.gap_dropped_count > 0

    # Backend db setup
    conn = get_db_connection()
    try:
        # Ingest the initial ON event that made it to DB before the gap
        on_event = {
            "event_id": "evt_1000_1",
            "timestamp_utc": 1000,
            "device_id": "light_01",
            "requested_state": "ON",
            "state_source": "manual",
            "reason_code": "switch_on"
        }
        process_device_state_event(on_event, custom_conn=conn)

        # Now simulate backend receiving the data_gap event generated upon reconnect
        gap_data = {
            "type": "data_gap",
            "gap_start_ts": esp.gap_start_ts,
            "gap_end_ts": 2000,
            "dropped_events_count": esp.gap_dropped_count,
            "reason": "ram_queue_overflow_during_disconnect"
        }

        closed = handle_outage_or_data_gap(
            gap_start_ts=gap_data["gap_start_ts"],
            gap_end_ts=gap_data["gap_end_ts"],
            custom_conn=conn
        )

        assert closed == 1

        cur = conn.cursor()
        cur.execute("SELECT * FROM runtime_sessions WHERE device_id = 'light_01'")
        row = cur.fetchone()
        assert row is not None
        assert row["end_known"] == 0
        assert row["end_time_utc"] is not None
    finally:
        conn.close()
