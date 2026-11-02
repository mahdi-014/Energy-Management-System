import json
import time
import uuid
import logging
import threading
from typing import Dict, Any, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

from app.config import settings
from app.db import get_db_connection
from app.analysis import process_device_state_event, handle_outage_or_data_gap
from app.detectors import run_all_detectors
from app.policy import process_command_ack

logger = logging.getLogger("dcems.mqtt")

# In-memory live state cache for fast API reads
_live_state_lock = threading.Lock()
_live_system_status: Dict[str, Any] = {
    "is_online": False,
    "last_seen_utc": None,
    "last_heartbeat_utc": None,
    "firmware_version": "unknown",
    "uptime_sec": 0,
    "mode": "AUTO",
    "devices": {
        "light_01": "OFF",
        "fan_01": "OFF",
        "ac_01": "OFF",
        "pc_01": "OFF"
    },
    "latest_sensor": None
}

_mqtt_client_instance: Optional[Any] = None
_internal_simulator_instance: Optional[Any] = None
_internal_sim_thread: Optional[threading.Thread] = None
_internal_sim_running: bool = False

def get_internal_simulator() -> Optional[Any]:
    global _internal_simulator_instance
    return _internal_simulator_instance

def start_internal_simulator():
    global _internal_sim_thread, _internal_sim_running
    if _internal_sim_running:
        return
    _internal_sim_running = True
    _internal_sim_thread = threading.Thread(target=_run_internal_simulator, name="DCEMS-InternalSim", daemon=True)
    _internal_sim_thread.start()

def stop_internal_simulator():
    global _internal_sim_running, _internal_sim_thread, _internal_simulator_instance
    _internal_sim_running = False
    _internal_sim_thread = None
    _internal_simulator_instance = None

def _run_internal_simulator():
    global _internal_simulator_instance, _internal_sim_running
    try:
        from simulator.mock_esp import MockESP8266
    except Exception as e:
        logger.warning(f"MockESP8266 simulator module not found: {e}. Internal simulation disabled.")
        return

    logger.info("Initializing background MockESP8266 simulation fallback engine.")
    _internal_simulator_instance = MockESP8266(room_id=settings.room_id)

    # Initial online status and state
    now = int(time.time())
    process_status_message(json.dumps({
        "status": "online",
        "ts": now,
        "firmware_version": "1.0.0-mock",
        "uptime_sec": 1,
        "room_id": settings.room_id
    }).encode("utf-8"))

    process_state_message(json.dumps({
        "ts": now,
        "mode": _internal_simulator_instance.mode,
        "devices": dict(_internal_simulator_instance.device_states),
        "observed_state": "assumed"
    }).encode("utf-8"))

    step = 0
    while _internal_sim_running:
        time.sleep(3.0)
        if not _internal_sim_running:
            break
        step += 1
        now = int(time.time())
        try:
            # Vary PIR motion, LDR daylight, temperature, and humidity
            pir_val = 1 if (step % 6 in (0, 1)) else 0
            ldr_val = 520 + int(35 * ((step % 10) - 5))
            temp_val = 27.5 + round(0.4 * ((step % 8) - 4), 1)
            hum_val = 62.0 + round(0.8 * ((step % 6) - 3), 1)

            snapshot = _internal_simulator_instance.publish_sensor_snapshot(
                pir=pir_val,
                ldr=ldr_val,
                temp=temp_val,
                hum=hum_val
            )
            process_sensor_message(json.dumps(snapshot).encode("utf-8"))

            # Periodic heartbeat
            if step % 5 == 0:
                process_status_message(json.dumps({
                    "status": "online",
                    "ts": now,
                    "firmware_version": "1.0.0-mock",
                    "uptime_sec": step * 3,
                    "room_id": settings.room_id
                }).encode("utf-8"))

            # Run detectors periodically
            run_all_detectors(current_ts=now)
        except Exception as e:
            logger.debug(f"Internal simulator step exception: {e}")

def get_system_status() -> Dict[str, Any]:
    with _live_state_lock:
        status_copy = dict(_live_system_status)
        status_copy["devices"] = dict(_live_system_status["devices"])
        if _live_system_status["latest_sensor"]:
            status_copy["latest_sensor"] = dict(_live_system_status["latest_sensor"])
        
        # Calculate staleness
        now = int(time.time())
        is_stale = True
        if status_copy["last_seen_utc"] is not None:
            is_stale = (now - status_copy["last_seen_utc"]) > 60

        status_copy["is_stale"] = is_stale
        return status_copy

def derive_occupancy_state(pir_motion: Optional[int], last_motion_at: Optional[int], current_ts: int, quality: str) -> str:
    """
    Derives occupancy inference from PIR motion history.
    PIR detects motion, not people.
    """
    if quality == "fault" or last_motion_at is None or last_motion_at == 0:
        return "unknown"
    
    elapsed = max(0, current_ts - last_motion_at)
    if elapsed < 300:  # < 5 minutes
        return "occupied_recently"
    elif elapsed < 900:  # < 15 minutes
        return "vacancy_candidate"
    else:
        return "vacant_confirmed"

def process_sensor_message(payload_bytes: bytes, server_receipt_ts: Optional[int] = None) -> Optional[Dict[str, Any]]:
    server_ts = server_receipt_ts or int(time.time())
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse sensor JSON: {e}")
        return None

    sample_id = data.get("event_id") or f"smpl_{uuid.uuid4().hex[:12]}"
    room_id = data.get("room_id", settings.room_id)
    device_ts = data.get("ts")

    # Invariant: Corrupted or out-of-bounds readings stored as NULL, never 0
    raw_pir = data.get("pir")
    pir_motion = raw_pir if raw_pir in (0, 1) else None

    raw_ldr = data.get("ldr")
    ldr_raw = raw_ldr if (isinstance(raw_ldr, (int, float)) and 0 <= raw_ldr <= 1023) else None

    ambient_light_level = data.get("light_pct")
    if ambient_light_level is not None and not (0 <= ambient_light_level <= 100):
        ambient_light_level = None

    raw_temp = data.get("temp")
    temp_c = None
    if raw_temp is not None:
        try:
            val = float(raw_temp)
            if 0.0 <= val <= 50.0:
                temp_c = val
        except ValueError:
            temp_c = None

    raw_hum = data.get("hum")
    hum_pct = None
    if raw_hum is not None:
        try:
            val = float(raw_hum)
            if 10.0 <= val <= 100.0:
                hum_pct = val
        except ValueError:
            hum_pct = None

    last_motion_at = data.get("last_motion_at")
    quality = data.get("quality", "ok" if (temp_c is not None and ldr_raw is not None) else "degraded")
    
    occupancy = derive_occupancy_state(pir_motion, last_motion_at, server_ts, quality)

    # Persist to SQLite
    conn = get_db_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO sensor_samples (
                sample_id, room_id, timestamp_utc, device_ts,
                pir_motion, ldr_raw, ambient_light_level,
                temperature_c, humidity_pct, last_motion_at,
                occupancy_state, sensor_quality
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sample_id, room_id, server_ts, device_ts,
            pir_motion, ldr_raw, ambient_light_level,
            temp_c, hum_pct, last_motion_at,
            occupancy, quality
        ))
        conn.commit()
    finally:
        conn.close()

    # Update in-memory live cache
    with _live_state_lock:
        _live_system_status["is_online"] = True
        _live_system_status["last_seen_utc"] = server_ts
        _live_system_status["latest_sensor"] = {
            "sample_id": sample_id,
            "timestamp_utc": server_ts,
            "device_ts": device_ts,
            "pir_motion": pir_motion,
            "ldr_raw": ldr_raw,
            "ambient_light_level": ambient_light_level,
            "temperature_c": temp_c,
            "humidity_pct": hum_pct,
            "last_motion_at": last_motion_at,
            "occupancy_state": occupancy,
            "sensor_quality": quality
        }

    # Trigger deterministic alert-only anomaly detectors
    try:
        run_all_detectors(current_ts=server_ts)
    except Exception as e:
        logger.error(f"Detector run error after sensor snapshot: {e}")

    return _live_system_status["latest_sensor"]

def process_status_message(payload_bytes: bytes, server_receipt_ts: Optional[int] = None):
    server_ts = server_receipt_ts or int(time.time())
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse status JSON: {e}")
        return

    status_str = data.get("status", "offline")
    is_online = (status_str == "online")

    with _live_state_lock:
        _live_system_status["is_online"] = is_online
        _live_system_status["last_seen_utc"] = server_ts
        if is_online:
            _live_system_status["last_heartbeat_utc"] = server_ts
            _live_system_status["firmware_version"] = data.get("firmware_version", "1.0.0")
            _live_system_status["uptime_sec"] = data.get("uptime_sec", 0)

def process_state_message(payload_bytes: bytes, server_receipt_ts: Optional[int] = None):
    server_ts = server_receipt_ts or int(time.time())
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse state JSON: {e}")
        return

    mode = data.get("mode", "AUTO")
    devices = data.get("devices", {})

    with _live_state_lock:
        _live_system_status["mode"] = mode
        for dev, state in devices.items():
            if dev in _live_system_status["devices"]:
                _live_system_status["devices"][dev] = state

def process_event_message(payload_bytes: bytes, server_receipt_ts: Optional[int] = None):
    server_ts = server_receipt_ts or int(time.time())
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse event JSON: {e}")
        return

    event_type = data.get("type")
    if event_type == "data_gap":
        logger.warning(f"Data gap detected from firmware: {data}")
        gap_start = data.get("gap_start_ts")
        gap_end = data.get("gap_end_ts", server_ts)
        handle_outage_or_data_gap(gap_start, gap_end)
    elif "requested_state" in data:
        process_device_state_event(data)

    try:
        run_all_detectors(current_ts=server_ts)
    except Exception as e:
        logger.error(f"Detector run error after state event: {e}")

def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to Mosquitto MQTT broker.")
        stop_internal_simulator()
        room = settings.room_id
        client.subscribe(f"dcems/{room}/sensors", qos=0)
        client.subscribe(f"dcems/{room}/status", qos=1)
        client.subscribe(f"dcems/{room}/state", qos=1)
        client.subscribe(f"dcems/{room}/events", qos=1)
        client.subscribe(f"dcems/{room}/ack", qos=1)
    else:
        logger.error(f"Failed to connect to MQTT broker, return code {rc}")
        start_internal_simulator()

def _on_message(client, userdata, msg):
    topic = msg.topic
    room = settings.room_id
    if topic == f"dcems/{room}/sensors":
        process_sensor_message(msg.payload)
    elif topic == f"dcems/{room}/status":
        process_status_message(msg.payload)
    elif topic == f"dcems/{room}/state":
        process_state_message(msg.payload)
    elif topic == f"dcems/{room}/events":
        process_event_message(msg.payload)
    elif topic == f"dcems/{room}/ack":
        process_command_ack(msg.payload)

def start_mqtt_client() -> Optional[Any]:
    global _mqtt_client_instance
    if mqtt is None:
        logger.warning("paho-mqtt not available; starting internal simulation engine.")
        start_internal_simulator()
        return None

    try:
        client = mqtt.Client(client_id=f"dcems_backend_{uuid.uuid4().hex[:8]}")
        if settings.mqtt_user:
            client.username_pw_set(settings.mqtt_user, settings.mqtt_password)

        client.on_connect = _on_connect
        client.on_message = _on_message

        client.connect_async(settings.mqtt_broker, settings.mqtt_port, keepalive=60)
        client.loop_start()
        _mqtt_client_instance = client

        # Watchdog: if not connected within 1.5s, start fallback simulation loop
        def _broker_watchdog():
            time.sleep(1.5)
            if _mqtt_client_instance is None or not _mqtt_client_instance.is_connected():
                logger.info(f"External MQTT broker at {settings.mqtt_broker}:{settings.mqtt_port} not connected. Activating internal simulator fallback.")
                start_internal_simulator()

        threading.Thread(target=_broker_watchdog, name="DCEMS-BrokerWatchdog", daemon=True).start()
        return client
    except Exception as e:
        logger.warning(f"Could not start MQTT client: {e}. Activating internal simulator fallback.")
        start_internal_simulator()
        return None

def stop_mqtt_client():
    global _mqtt_client_instance
    stop_internal_simulator()
    if _mqtt_client_instance:
        try:
            _mqtt_client_instance.loop_stop()
            _mqtt_client_instance.disconnect()
        except Exception:
            pass
        _mqtt_client_instance = None

