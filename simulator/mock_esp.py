import json
import time
import uuid
import threading
from typing import Dict, Any, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

class MockESP8266:
    """
    Host-side ESP8266 Simulator.
    Emulates sensor telemetry, retain state, Last Will and Testament,
    and the 8-point authoritative safety gate on dcems/room1/#.
    """
    def __init__(
        self,
        broker_host: str = "127.0.0.1",
        broker_port: int = 1883,
        username: str = "dcems_esp8266",
        password: str = "dcems_device_password_here",
        room_id: str = "room1"
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.room_id = room_id

        # Controller internal state
        self.mode = "AUTO"  # AUTO or MANUAL
        self.device_states = {
            "light_01": "OFF",
            "fan_01": "OFF",
            "ac_01": "OFF",
            "pc_01": "OFF"
        }
        self.auto_eligible = {
            "light_01": True,
            "fan_01": True,
            "ac_01": False,  # Compile-time safety lock
            "pc_01": False   # Compile-time safety lock
        }
        
        # Ring buffer of recent action IDs (size 16) for deduplication
        self.recent_action_ids = []
        self.max_action_ids = 16
        
        # Bounded RAM event buffer for offline resilience (max 50 events)
        self.event_queue = []
        self.max_queue_size = 50
        self.data_gap_occurred = False
        self.gap_dropped_count = 0
        self.gap_start_ts = None

        self.last_motion_time = int(time.time())
        self.last_manual_command_time = {}
        self.last_switch_time = {d: int(time.time()) for d in self.device_states}
        
        self.client = None
        self.is_connected = False
        self._running = False
        self._thread = None

    def start(self):
        if mqtt is None:
            raise RuntimeError("paho-mqtt library is not installed.")
        self.client = mqtt.Client(client_id=f"mock_esp_{uuid.uuid4().hex[:8]}", clean_session=True)
        if self.username:
            self.client.username_pw_set(self.username, self.password)

        # Configure Last Will and Testament
        lwt_payload = json.dumps({
            "status": "offline",
            "ts": int(time.time()),
            "reason": "unexpected_disconnect"
        })
        self.client.will_set(f"dcems/{self.room_id}/status", lwt_payload, qos=1, retain=True)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self._running = True
        self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()

    def stop(self):
        self._running = False
        if self.client:
            # Publish graceful offline status
            offline_payload = json.dumps({
                "status": "offline",
                "ts": int(time.time()),
                "reason": "graceful_shutdown"
            })
            self.client.publish(f"dcems/{self.room_id}/status", offline_payload, qos=1, retain=True)
            self.client.loop_stop()
            self.client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            # Publish online heartbeat
            online_payload = json.dumps({
                "status": "online",
                "ts": int(time.time()),
                "firmware_version": "1.0.0-mock",
                "uptime_sec": 1
            })
            self.client.publish(f"dcems/{self.room_id}/status", online_payload, qos=1, retain=True)

            # Publish initial device state (retained)
            self.publish_state()

            # Subscribe to command topic
            self.client.subscribe(f"dcems/{self.room_id}/cmd", qos=1)

            # Flush queued offline events if any
            self._flush_event_queue()
        else:
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False

    def _on_message(self, client, userdata, msg):
        # Stub for cmd handling (fully fleshed out in Phase 4)
        pass

    def publish_state(self):
        if not self.client or not self.is_connected:
            return
        payload = json.dumps({
            "ts": int(time.time()),
            "mode": self.mode,
            "devices": self.device_states,
            "observed_state": "assumed"
        })
        self.client.publish(f"dcems/{self.room_id}/state", payload, qos=1, retain=True)

    def publish_sensor_snapshot(self, pir: int = 0, ldr: int = 500, temp: float = 27.0, hum: float = 60.0):
        now = int(time.time())
        if pir == 1:
            self.last_motion_time = now

        payload = {
            "event_id": str(uuid.uuid4()),
            "ts": now,
            "room_id": self.room_id,
            "pir": pir,
            "ldr": ldr,
            "temp": temp,
            "hum": hum,
            "last_motion_at": self.last_motion_time,
            "valid": True,
            "quality": "ok"
        }
        topic = f"dcems/{self.room_id}/sensors"
        
        if self.is_connected:
            self.client.publish(topic, json.dumps(payload), qos=0)
        else:
            self._enqueue_event("sensor", payload)

    def _enqueue_event(self, event_type: str, data: Dict[str, Any]):
        if len(self.event_queue) >= self.max_queue_size:
            # Drop oldest and flag data gap
            if not self.data_gap_occurred:
                self.data_gap_occurred = True
                self.gap_start_ts = int(time.time())
            self.event_queue.pop(0)
            self.gap_dropped_count += 1
        self.event_queue.append((event_type, data))

    def _flush_event_queue(self):
        while self.event_queue and self.is_connected:
            _, data = self.event_queue.pop(0)
            self.client.publish(f"dcems/{self.room_id}/events", json.dumps(data), qos=1)
        if self.data_gap_occurred and self.is_connected:
            gap_payload = {
                "event_id": str(uuid.uuid4()),
                "ts": int(time.time()),
                "type": "data_gap",
                "gap_start_ts": self.gap_start_ts,
                "gap_end_ts": int(time.time()),
                "dropped_events_count": self.gap_dropped_count,
                "reason": "ram_queue_overflow_during_disconnect"
            }
            self.client.publish(f"dcems/{self.room_id}/events", json.dumps(gap_payload), qos=1)
            self.data_gap_occurred = False
            self.gap_dropped_count = 0
            self.gap_start_ts = None
