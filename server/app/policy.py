import json
import time
import uuid
import logging
import sqlite3
from typing import Dict, Any, Optional, List

from app.config import settings
from app.db import get_db_connection

logger = logging.getLogger("dcems.policy")

CANONICAL_DEVICES = ("light_01", "fan_01", "ac_01", "pc_01")
ALERT_ONLY_DEVICES = ("ac_01", "pc_01")

def validate_server_proposal(
    device_id: str,
    proposed_state: str,
    trigger_anomaly_id: Optional[str] = None,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Validates a proposed automated action against server-side policy.
    - AC and PC are strictly ineligible for auto-actions.
    - Default policy has auto_action_enabled = 0 (Alert-Only).
    - Checks for active manual overrides.
    """
    if device_id not in CANONICAL_DEVICES or proposed_state not in ("ON", "OFF"):
        return {
            "allowed": False,
            "reason": "invalid_device_or_state",
            "policy_version": 1
        }

    # Hard-locked alert-only loads
    if device_id in ALERT_ONLY_DEVICES:
        return {
            "allowed": False,
            "reason": "device_alert_only_ineligible_for_auto_action",
            "policy_version": 1
        }

    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)
    now = int(time.time())

    try:
        cur = conn.cursor()

        # Check device policy table
        cur.execute("""
            SELECT auto_action_enabled, auto_off_on_vacancy, policy_version
            FROM device_policies
            WHERE device_id = ?
        """, (device_id,))
        policy_row = cur.fetchone()

        if not policy_row:
            return {"allowed": False, "reason": "policy_not_found", "policy_version": 1}

        pol_ver = policy_row["policy_version"]
        auto_enabled = bool(policy_row["auto_action_enabled"])

        # Default commissioning safety: auto_action_enabled must be explicitly 1
        if not auto_enabled:
            return {
                "allowed": False,
                "reason": "device_policy_auto_action_disabled",
                "policy_version": pol_ver
            }

        # Check active manual override
        cur.execute("""
            SELECT override_id FROM manual_overrides
            WHERE device_id = ? AND expiry_time_utc > ?
        """, (device_id, now))
        if cur.fetchone():
            return {
                "allowed": False,
                "reason": "active_manual_override",
                "policy_version": pol_ver
            }

        return {
            "allowed": True,
            "reason": "policy_precheck_passed",
            "policy_version": pol_ver
        }
    finally:
        if should_close:
            conn.close()

def issue_device_command(
    device_id: str,
    requested_state: str,
    source: str = "manual",
    reason: str = "operator_toggle",
    trigger_anomaly_id: Optional[str] = None,
    ttl_sec: int = 60,
    actor: str = "dashboard_user",
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Validates policy rules, generates signed action command, records audit record,
    and publishes command to dcems/room1/cmd.
    - Test T13: AC and PC power-off commands from dashboard are BLOCKED by default.
    """
    if device_id not in CANONICAL_DEVICES or requested_state not in ("ON", "OFF"):
        return {"success": False, "reason": "invalid_parameters"}

    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)
    now = int(time.time())

    try:
        cur = conn.cursor()

        # Policy Pre-checks
        if source == "server_proposal":
            check = validate_server_proposal(device_id, requested_state, trigger_anomaly_id, custom_conn=conn)
            if not check["allowed"]:
                action_id = f"act_blocked_{uuid.uuid4().hex[:8]}"
                cur.execute("""
                    INSERT INTO control_actions (
                        action_id, timestamp_utc, device_id, trigger_anomaly_id,
                        proposed_state, policy_decision, decision_reason,
                        policy_version, execution_result
                    ) VALUES (?, ?, ?, ?, ?, 'blocked', ?, ?, 'not_executed')
                """, (action_id, now, device_id, trigger_anomaly_id, requested_state, check["reason"], check["policy_version"]))
                conn.commit()
                return {
                    "success": False,
                    "action_id": action_id,
                    "result": "blocked",
                    "reason": check["reason"]
                }
            policy_version = check["policy_version"]
        else:
            # Manual / Dashboard Command
            # Test T13: AC and PC power-off commands from dashboard are BLOCKED by default
            if device_id in ALERT_ONLY_DEVICES and requested_state == "OFF":
                action_id = f"act_t13_blocked_{uuid.uuid4().hex[:8]}"
                reason_code = "ac_pc_power_off_blocked_by_policy"
                cur.execute("""
                    INSERT INTO control_actions (
                        action_id, timestamp_utc, device_id, trigger_anomaly_id,
                        proposed_state, policy_decision, decision_reason,
                        policy_version, execution_result
                    ) VALUES (?, ?, ?, NULL, ?, 'blocked', ?, 1, 'not_executed')
                """, (action_id, now, device_id, requested_state, reason_code))

                cur.execute("""
                    INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details)
                    VALUES (?, ?, 'command', ?, ?)
                """, (f"log_cmd_{action_id}", now, actor, json.dumps({
                    "action": "manual_device_toggle",
                    "device_id": device_id,
                    "requested_state": requested_state,
                    "result": "blocked",
                    "reason": reason_code
                })))
                conn.commit()
                return {
                    "success": False,
                    "action_id": action_id,
                    "result": "blocked",
                    "reason": reason_code
                }

            policy_version = 1

        action_id = f"act_{uuid.uuid4().hex[:12]}"
        expires_at = now + ttl_sec

        # Record proposed action in control_actions
        cur.execute("""
            INSERT INTO control_actions (
                action_id, timestamp_utc, device_id, trigger_anomaly_id,
                proposed_state, policy_decision, decision_reason,
                policy_version, execution_result
            ) VALUES (?, ?, ?, ?, ?, 'allowed', ?, ?, 'not_executed')
        """, (action_id, now, device_id, trigger_anomaly_id, requested_state, reason, policy_version))

        # Audit log entry
        cur.execute("""
            INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details)
            VALUES (?, ?, 'command', ?, ?)
        """, (f"log_cmd_{action_id}", now, actor, json.dumps({
            "action": "issue_command",
            "action_id": action_id,
            "device_id": device_id,
            "requested_state": requested_state,
            "source": source
        })))
        conn.commit()

        # Build MQTT command payload
        cmd_payload = {
            "action_id": action_id,
            "command_type": "device_command",
            "device_id": device_id,
            "requested_state": requested_state,
            "issued_at": now,
            "expires_at": expires_at,
            "reason": reason,
            "policy_version": policy_version,
            "source": source
        }

        # Publish via background MQTT client if available
        try:
            from app.mqtt_client import _mqtt_client_instance
            if _mqtt_client_instance and _mqtt_client_instance.is_connected():
                topic = f"dcems/{settings.room_id}/cmd"
                _mqtt_client_instance.publish(topic, json.dumps(cmd_payload), qos=1)
        except Exception as e:
            logger.warning(f"Could not publish command to MQTT broker: {e}")

        return {
            "success": True,
            "action_id": action_id,
            "status": "sent",
            "device_id": device_id,
            "requested_state": requested_state,
            "issued_at": now,
            "expires_at": expires_at,
            "policy_version": policy_version
        }
    finally:
        if should_close:
            conn.close()

def process_command_ack(
    payload_bytes: bytes,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    """
    Ingests and processes command acknowledgments from dcems/room1/ack:
    - Updates execution_result in control_actions table.
    """
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"Failed to parse ACK JSON: {e}")
        return None

    action_id = data.get("action_id")
    result = data.get("result", "unknown")
    reason = data.get("reason", "")
    ack_ts = data.get("ts", int(time.time()))

    if not action_id:
        return None

    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)

    try:
        cur = conn.cursor()

        exec_status = "not_executed"
        if result == "accepted":
            exec_status = "success"
        elif result == "blocked":
            exec_status = "failed"
        elif result == "expired":
            exec_status = "expired"

        cur.execute("""
            UPDATE control_actions
            SET execution_result = ?, decision_reason = CASE WHEN ? != '' THEN ? ELSE decision_reason END
            WHERE action_id = ?
        """, (exec_status, reason, reason, action_id))

        conn.commit()
        return data
    finally:
        if should_close:
            conn.close()

def issue_mode_command(
    new_mode: str,
    source: str = "manual",
    actor: str = "dashboard_user",
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Changes controller mode between AUTO and MANUAL.
    """
    if new_mode not in ("AUTO", "MANUAL"):
        return {"success": False, "reason": "invalid_mode"}

    now = int(time.time())
    action_id = f"act_mode_{uuid.uuid4().hex[:8]}"

    payload = {
        "action_id": action_id,
        "command_type": "set_mode",
        "mode": new_mode,
        "issued_at": now,
        "expires_at": now + 60,
        "source": source
    }

    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)

    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details)
            VALUES (?, ?, 'command', ?, ?)
        """, (f"log_{action_id}", now, actor, json.dumps({
            "action": "set_controller_mode",
            "new_mode": new_mode
        })))
        conn.commit()

        # Update live memory cache
        try:
            from app.mqtt_client import _live_state_lock, _live_system_status, _mqtt_client_instance
            with _live_state_lock:
                _live_system_status["mode"] = new_mode

            if _mqtt_client_instance and _mqtt_client_instance.is_connected():
                topic = f"dcems/{settings.room_id}/cmd"
                _mqtt_client_instance.publish(topic, json.dumps(payload), qos=1)
        except Exception:
            pass

        return {
            "success": True,
            "action_id": action_id,
            "mode": new_mode,
            "issued_at": now
        }
    finally:
        if should_close:
            conn.close()

