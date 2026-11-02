import json
import time
import uuid
from typing import Dict, Any, Optional

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

class MockESP8266:
    """
    Host-side ESP8266 Simulator (Phase 2).
    Emulates sensor telemetry, relay state transitions, event emission,
    retained state, Last Will and Testament, and bounded offline queueing.
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
        
        # Bounded RAM event buffer for offline resilience (max 50 events)
        self.event_queue = []
        self.max_queue_size = 50
        self.data_gap_occurred = False
        self.gap_dropped_count = 0
        self.gap_start_ts = None

        self.last_motion_time = int(time.time())
        self.last_switch_time = {d: int(time.time()) for d in self.device_states}
        self.last_manual_command_time = 0
        
        self.client = None
        self.is_connected = False
        self._running = False
        self.message_seq = 0

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
            online_payload = json.dumps({
                "status": "online",
                "ts": int(time.time()),
                "firmware_version": "1.0.0-mock",
                "uptime_sec": 1,
                "room_id": self.room_id
            })
            self.client.publish(f"dcems/{self.room_id}/status", online_payload, qos=1, retain=True)

            self.publish_state()
            self.client.subscribe(f"dcems/{self.room_id}/cmd", qos=1)
            self._flush_event_queue()
        else:
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False

    def _on_message(self, client, userdata, msg):
        pass

    def publish_state(self):
        payload = {
            "ts": int(time.time()),
            "mode": self.mode,
            "devices": self.device_states,
            "observed_state": "assumed"
        }
        topic = f"dcems/{self.room_id}/state"
        payload_bytes = json.dumps(payload).encode("utf-8")

        if self.is_connected and self.client:
            self.client.publish(topic, payload_bytes, qos=1, retain=True)
        else:
            self._enqueue_event(topic, payload, retained=True)

    def set_device_state(
        self,
        device_id: str,
        state: str,
        source: str = "manual",
        reason: str = "operator_toggle",
        ts: Optional[int] = None
    ) -> bool:
        if device_id not in self.device_states:
            return False
        if self.device_states[device_id] == state:
            return False

        now = ts or int(time.time())
        self.message_seq += 1
        self.device_states[device_id] = state
        self.last_switch_time[device_id] = now
        if source == "manual":
            self.last_manual_command_time = now

        event_payload = {
            "event_id": f"evt_{now}_{self.message_seq}",
            "timestamp_utc": now,
            "device_id": device_id,
            "requested_state": state,
            "state_source": source,
            "reason_code": reason,
            "controller_mode": self.mode,
            "command_status": "applied",
            "observed_state": "assumed"
        }

        topic = f"dcems/{self.room_id}/events"
        payload_bytes = json.dumps(event_payload).encode("utf-8")

        if self.is_connected and self.client:
            self.client.publish(topic, payload_bytes, qos=1, retain=False)
            self.publish_state()
        else:
            self._enqueue_event(topic, event_payload, retained=False)
            self.publish_state()

        return True

    def publish_sensor_snapshot(
        self,
        pir: Optional[int] = 0,
        ldr: Optional[int] = 520,
        temp: Optional[float] = 27.5,
        hum: Optional[float] = 62.0,
        quality: Optional[str] = None
    ) -> Dict[str, Any]:
        now = int(time.time())
        self.message_seq += 1

        if pir == 1:
            self.last_motion_time = now

        light_pct = None
        if ldr is not None and 0 <= ldr <= 1023:
            light_pct = round((ldr / 1023.0) * 100)

        is_valid = True
        if ldr is None or not (0 <= ldr <= 1023):
            is_valid = False
        if temp is None or not (0.0 <= temp <= 50.0):
            is_valid = False
        if hum is None or not (20.0 <= hum <= 90.0):
            is_valid = False

        computed_quality = quality or ("ok" if is_valid else "degraded")

        payload = {
            "event_id": f"evt_{now}_{self.message_seq}",
            "ts": now,
            "room_id": self.room_id,
            "pir": pir,
            "ldr": ldr,
            "light_pct": light_pct,
            "temp": temp,
            "hum": hum,
            "last_motion_at": self.last_motion_time,
            "valid": is_valid,
            "quality": computed_quality
        }
        
        topic = f"dcems/{self.room_id}/sensors"
        payload_bytes = json.dumps(payload).encode("utf-8")

        if self.is_connected and self.client:
            self.client.publish(topic, payload_bytes, qos=0)
        else:
            self._enqueue_event(topic, payload, retained=False)

        return payload

    def _enqueue_event(self, topic: str, data: Dict[str, Any], retained: bool = False):
        if len(self.event_queue) >= self.max_queue_size:
            if not self.data_gap_occurred:
                self.data_gap_occurred = True
                self.gap_start_ts = int(time.time())
            self.event_queue.pop(0)
            self.gap_dropped_count += 1
        self.event_queue.append((topic, data, retained))

    def _flush_event_queue(self):
        while self.event_queue and self.is_connected:
            topic, data, retained = self.event_queue.pop(0)
            self.client.publish(topic, json.dumps(data), qos=1, retain=retained)
        if self.data_gap_occurred and self.is_connected:
            gap_payload = {
                "event_id": f"gap_{int(time.time())}",
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
