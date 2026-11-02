import time
import json
import uuid
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from app.db import get_db_connection

logger = logging.getLogger("dcems.analysis")

CANONICAL_DEVICES = ("light_01", "fan_01", "ac_01", "pc_01")

def process_device_state_event(
    event_dict: Dict[str, Any],
    custom_conn: Optional[sqlite3.Connection] = None
) -> bool:
    """
    Ingests a device state transition event into device_state_events and updates
    runtime_sessions tracking.
    Enforces deduplication by event_id.
    """
    event_id = event_dict.get("event_id")
    device_id = event_dict.get("device_id")
    requested_state = event_dict.get("requested_state")

    if not event_id or device_id not in CANONICAL_DEVICES or requested_state not in ("ON", "OFF"):
        logger.warning(f"Invalid device state event payload: {event_dict}")
        return False

    ts = int(event_dict.get("timestamp_utc", time.time()))
    state_source = event_dict.get("state_source", "manual")
    if state_source not in ("manual", "local_rule", "server_proposal"):
        state_source = "manual"

    reason_code = str(event_dict.get("reason_code", "unspecified"))
    controller_mode = event_dict.get("controller_mode", "AUTO")
    if controller_mode not in ("AUTO", "MANUAL"):
        controller_mode = "AUTO"

    command_status = event_dict.get("command_status", "applied")
    if command_status not in ("pending", "applied", "failed", "unknown"):
        command_status = "applied"

    observed_state = event_dict.get("observed_state", "assumed")
    if observed_state not in ("assumed", "unknown", "confirmed"):
        observed_state = "assumed"

    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)

    try:
        cur = conn.cursor()

        # Deduplication check
        cur.execute("SELECT 1 FROM device_state_events WHERE event_id = ?", (event_id,))
        if cur.fetchone():
            logger.info(f"Duplicate event_id ignored: {event_id}")
            return False

        # Insert state event
        cur.execute("""
            INSERT INTO device_state_events (
                event_id, timestamp_utc, device_id, requested_state,
                state_source, reason_code, controller_mode,
                command_status, observed_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, ts, device_id, requested_state,
            state_source, reason_code, controller_mode,
            command_status, observed_state
        ))

        # Runtime session lifecycle management
        if requested_state == "ON":
            # Check for existing unclosed session for this device
            cur.execute("""
                SELECT session_id, start_time_utc FROM runtime_sessions
                WHERE device_id = ? AND end_time_utc IS NULL
                ORDER BY start_time_utc DESC LIMIT 1
            """, (device_id,))
            open_sess = cur.fetchone()

            if open_sess:
                # Prior session was not cleanly closed with OFF; mark it interrupted
                prior_sess_id = open_sess["session_id"]
                prior_start = open_sess["start_time_utc"]
                dur = max(0, ts - prior_start)
                cur.execute("""
                    UPDATE runtime_sessions
                    SET end_time_utc = ?, estimated_duration_sec = ?, end_known = 0
                    WHERE session_id = ?
                """, (ts, dur, prior_sess_id))

            # Start new open session
            new_sess_id = f"sess_{device_id}_{ts}_{uuid.uuid4().hex[:6]}"
            cur.execute("""
                INSERT INTO runtime_sessions (
                    session_id, device_id, start_time_utc,
                    end_time_utc, end_known, estimated_duration_sec
                ) VALUES (?, ?, ?, NULL, 1, NULL)
            """, (new_sess_id, device_id, ts))

        elif requested_state == "OFF":
            # Find the active open session for this device
            cur.execute("""
                SELECT session_id, start_time_utc FROM runtime_sessions
                WHERE device_id = ? AND end_time_utc IS NULL
                ORDER BY start_time_utc DESC LIMIT 1
            """, (device_id,))
            open_sess = cur.fetchone()

            if open_sess:
                sess_id = open_sess["session_id"]
                start_ts = open_sess["start_time_utc"]
                duration_sec = max(0, ts - start_ts)
                cur.execute("""
                    UPDATE runtime_sessions
                    SET end_time_utc = ?, estimated_duration_sec = ?, end_known = 1
                    WHERE session_id = ?
                """, (ts, duration_sec, sess_id))
            else:
                # OFF with no matching open ON session
                unmatched_sess_id = f"sess_unmatched_{device_id}_{ts}_{uuid.uuid4().hex[:6]}"
                cur.execute("""
                    INSERT INTO runtime_sessions (
                        session_id, device_id, start_time_utc,
                        end_time_utc, end_known, estimated_duration_sec
                    ) VALUES (?, ?, ?, ?, 0, 0)
                """, (unmatched_sess_id, device_id, ts, ts))

        conn.commit()

        # Update in-memory live status cache if available
        try:
            from app.mqtt_client import _live_state_lock, _live_system_status
            with _live_state_lock:
                _live_system_status["devices"][device_id] = requested_state
                _live_system_status["mode"] = controller_mode
        except Exception:
            pass

        return True

    finally:
        if should_close_conn:
            conn.close()

def handle_outage_or_data_gap(
    gap_start_ts: Optional[int],
    gap_end_ts: Optional[int],
    custom_conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Marks any currently open sessions as interrupted (end_known = 0) when an
    outage or RAM ring buffer data gap occurs.
    Returns the number of sessions closed.
    """
    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)
    closed_count = 0

    end_ts = gap_end_ts or int(time.time())
    start_ts = gap_start_ts or end_ts

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT session_id, device_id, start_time_utc
            FROM runtime_sessions
            WHERE end_time_utc IS NULL
        """)
        open_sessions = cur.fetchall()

        for sess in open_sessions:
            sess_id = sess["session_id"]
            sess_start = sess["start_time_utc"]
            eff_end = max(sess_start, start_ts)
            dur = max(0, eff_end - sess_start)

            cur.execute("""
                UPDATE runtime_sessions
                SET end_time_utc = ?, estimated_duration_sec = ?, end_known = 0
                WHERE session_id = ?
            """, (eff_end, dur, sess_id))
            closed_count += 1

        conn.commit()
        return closed_count
    finally:
        if should_close_conn:
            conn.close()

def get_daily_runtime_breakdown(
    date_utc: Optional[str] = None,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Aggregates runtime per device for a specific UTC date (YYYY-MM-DD).
    Strictly adheres to:
    1. T = t_OFF - t_ON
    2. Missing data / outages marked as interrupted (end_known = 0).
    3. Mandatory honest disclaimer attached. Zero kWh or cost speculation.
    """
    if date_utc is None:
        target_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        target_date_str = date_utc

    try:
        day_start = int(datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        target_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_start = int(datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())

    day_end = day_start + 86400
    now_ts = int(time.time())

    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)

    devices_data: Dict[str, Any] = {}

    try:
        cur = conn.cursor()

        for dev in CANONICAL_DEVICES:
            cur.execute("""
                SELECT session_id, start_time_utc, end_time_utc, end_known, estimated_duration_sec
                FROM runtime_sessions
                WHERE device_id = ?
                  AND start_time_utc < ?
                  AND (end_time_utc IS NULL OR end_time_utc > ?)
                ORDER BY start_time_utc ASC
            """, (dev, day_end, day_start))
            sessions = cur.fetchall()

            total_sec = 0
            completed_count = 0
            interrupted_count = 0
            is_currently_on = False
            session_list: List[Dict[str, Any]] = []

            for sess in sessions:
                s_start = sess["start_time_utc"]
                s_end = sess["end_time_utc"]
                end_known = bool(sess["end_known"])

                clamped_start = max(s_start, day_start)

                if s_end is None:
                    # Session is still actively open
                    is_currently_on = True
                    effective_end = min(now_ts, day_end)
                    duration_for_day = max(0, effective_end - clamped_start)
                    total_sec += duration_for_day
                    session_list.append({
                        "session_id": sess["session_id"],
                        "start_utc": s_start,
                        "end_utc": None,
                        "duration_sec": duration_for_day,
                        "status": "active"
                    })
                else:
                    effective_end = min(s_end, day_end)
                    duration_for_day = max(0, effective_end - clamped_start)
                    total_sec += duration_for_day

                    if end_known:
                        completed_count += 1
                        status_str = "completed"
                    else:
                        interrupted_count += 1
                        status_str = "interrupted"

                    session_list.append({
                        "session_id": sess["session_id"],
                        "start_utc": s_start,
                        "end_utc": s_end,
                        "duration_sec": duration_for_day,
                        "status": status_str
                    })

            devices_data[dev] = {
                "device_id": dev,
                "total_runtime_sec": total_sec,
                "total_runtime_hours": round(total_sec / 3600.0, 2),
                "completed_sessions": completed_count,
                "interrupted_sessions": interrupted_count,
                "is_currently_on": is_currently_on,
                "sessions_count": len(sessions)
            }

        return {
            "date_utc": target_date_str,
            "query_timestamp_utc": now_ts,
            "devices": devices_data,
            "labels": {
                "runtime_disclaimer": "All runtime metrics are estimates based on commanded relay state.",
                "measurement_basis": "estimate_based_on_commanded_state",
                "energy_notice": "Energy (kWh) and cost calculations are excluded from MVP."
            }
        }
    finally:
        if should_close_conn:
            conn.close()

def _calculate_median(values: List[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)

def get_hourly_runtime_distribution(
    date_local: Optional[str] = None,
    tz_offset_hours: int = 6,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Computes 24 one-hour bins (0..23) of estimated runtime in minutes for each device.
    Local timezone defaults to Asia/Dhaka (UTC+6).
    """
    now_utc = int(time.time())
    now_local_ts = now_utc + (tz_offset_hours * 3600)

    if date_local is None:
        target_date_str = datetime.fromtimestamp(now_local_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    else:
        target_date_str = date_local

    try:
        # Midnight local parsed as naive UTC
        local_midnight_naive = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        local_midnight_utc = int(local_midnight_naive.timestamp()) - (tz_offset_hours * 3600)
    except ValueError:
        target_date_str = datetime.fromtimestamp(now_local_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        local_midnight_naive = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        local_midnight_utc = int(local_midnight_naive.timestamp()) - (tz_offset_hours * 3600)

    day_end_utc = local_midnight_utc + 86400

    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)

    hours_labels = [f"{h:02d}:00" for h in range(24)]
    device_hourly: Dict[str, List[float]] = {dev: [0.0] * 24 for dev in CANONICAL_DEVICES}
    device_totals: Dict[str, float] = {dev: 0.0 for dev in CANONICAL_DEVICES}

    try:
        cur = conn.cursor()

        for dev in CANONICAL_DEVICES:
            cur.execute("""
                SELECT session_id, start_time_utc, end_time_utc
                FROM runtime_sessions
                WHERE device_id = ?
                  AND start_time_utc < ?
                  AND (end_time_utc IS NULL OR end_time_utc > ?)
                ORDER BY start_time_utc ASC
            """, (dev, day_end_utc, local_midnight_utc))
            sessions = cur.fetchall()

            for h in range(24):
                bin_start = local_midnight_utc + (h * 3600)
                bin_end = bin_start + 3600

                overlap_sec_bin = 0
                for sess in sessions:
                    s_start = sess["start_time_utc"]
                    s_end = sess["end_time_utc"] if sess["end_time_utc"] is not None else now_utc

                    overlap_start = max(s_start, bin_start)
                    overlap_end = min(s_end, bin_end)

                    if overlap_end > overlap_start:
                        overlap_sec_bin += (overlap_end - overlap_start)

                minutes = round(min(60.0, overlap_sec_bin / 60.0), 1)
                device_hourly[dev][h] = minutes
                device_totals[dev] += minutes

            device_totals[dev] = round(device_totals[dev], 1)

        return {
            "date_local": target_date_str,
            "timezone": f"Asia/Dhaka (UTC+{tz_offset_hours})",
            "hours": hours_labels,
            "devices": device_hourly,
            "total_runtime_minutes": device_totals,
            "labels": {
                "runtime_disclaimer": "All runtime metrics are estimates based on commanded relay state.",
                "measurement_basis": "estimate_based_on_commanded_state",
                "energy_notice": "Zero power (kWh) or monetary cost is measured or implied.",
                "unit": "minutes"
            }
        }
    finally:
        if should_close_conn:
            conn.close()

def get_adaptive_baseline(
    device_id: str,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Computes data-driven adaptive runtime baseline using Median and MAD
    (Median Absolute Deviation) according to specification:
    - Only activates if >= 20 comparable completed sessions exist.
    - Protected behind feature flag (DEFAULT: OFF).
    """
    if device_id not in CANONICAL_DEVICES:
        return {"status": "invalid_device", "device_id": device_id}

    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)

    try:
        cur = conn.cursor()

        # Check feature flag in config table
        cur.execute("SELECT value FROM config WHERE key = 'adaptive_baseline_enabled'")
        row = cur.fetchone()
        flag_enabled = (row["value"].strip().lower() == "true") if row else False

        if not flag_enabled:
            return {
                "device_id": device_id,
                "feature_flag_enabled": False,
                "status": "disabled",
                "message": "Adaptive baseline feature flag is disabled by default."
            }

        # Query completed sessions (end_known = 1)
        cur.execute("""
            SELECT estimated_duration_sec
            FROM runtime_sessions
            WHERE device_id = ? AND end_known = 1 AND estimated_duration_sec > 0
            ORDER BY start_time_utc DESC
            LIMIT 100
        """, (device_id,))
        rows = cur.fetchall()
        count = len(rows)

        if count < 20:
            return {
                "device_id": device_id,
                "feature_flag_enabled": True,
                "status": "insufficient_data",
                "completed_sessions_count": count,
                "required_sessions_count": 20,
                "message": f"Requires >= 20 completed sessions for baseline stability. Currently {count}/20."
            }

        durations = [float(r["estimated_duration_sec"]) for r in rows]
        median_dur = _calculate_median(durations)
        abs_deviations = [abs(d - median_dur) for d in durations]
        mad = _calculate_median(abs_deviations)

        # Upper threshold: Median + 3 * (1.4826 * MAD)
        normal_scale_mad = 1.4826 * mad
        upper_threshold_sec = round(median_dur + (3.0 * normal_scale_mad), 1)

        return {
            "device_id": device_id,
            "feature_flag_enabled": True,
            "status": "active",
            "completed_sessions_count": count,
            "median_sec": round(median_dur, 1),
            "median_min": round(median_dur / 60.0, 1),
            "mad_sec": round(mad, 1),
            "upper_threshold_sec": upper_threshold_sec,
            "upper_threshold_min": round(upper_threshold_sec / 60.0, 1),
            "message": "Adaptive baseline active and calculated via Median + MAD."
        }
    finally:
        if should_close_conn:
            conn.close()

def get_all_adaptive_baselines(
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Aggregates adaptive baseline calculations across all canonical devices.
    """
    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)
    try:
        cur = conn.cursor()
        # Check feature flag in config table
        cur.execute("SELECT value FROM config WHERE key = 'adaptive_baseline_enabled'")
        row = cur.fetchone()
        flag_enabled = (row["value"].strip().lower() == "true") if row else False

        baselines = {}
        for dev in CANONICAL_DEVICES:
            baselines[dev] = get_adaptive_baseline(dev, custom_conn=conn)

        return {
            "feature_flag_enabled": flag_enabled,
            "devices": baselines
        }
    finally:
        if should_close_conn:
            conn.close()

def set_adaptive_baseline_flag(
    enabled: bool,
    actor: str = "operator",
    custom_conn: Optional[sqlite3.Connection] = None
) -> bool:
    """
    Toggles the adaptive baseline feature flag in the config table with audit logging.
    """
    conn = custom_conn or get_db_connection()
    should_close_conn = (custom_conn is None)
    val_str = "true" if enabled else "false"
    now = int(time.time())

    try:
        cur = conn.cursor()
        cur.execute("SELECT value, history FROM config WHERE key = 'adaptive_baseline_enabled'")
        row = cur.fetchone()
        history = []
        if row:
            if row["history"]:
                try:
                    history = json.loads(row["history"])
                except Exception:
                    history = []
            history.append({
                "value": row["value"],
                "changed_at": now,
                "changed_by": actor
            })
            cur.execute("""
                UPDATE config
                SET value = ?, changed_at = ?, changed_by = ?, history = ?
                WHERE key = 'adaptive_baseline_enabled'
            """, (val_str, now, actor, json.dumps(history)))
        else:
            cur.execute("""
                INSERT INTO config (key, value, changed_at, changed_by, history)
                VALUES ('adaptive_baseline_enabled', ?, ?, ?, '[]')
            """, (val_str, now, actor))

        cur.execute("""
            INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details)
            VALUES (?, ?, 'settings_change', ?, ?)
        """, (f"log_baseline_{now}_{uuid.uuid4().hex[:6]}", now, actor, json.dumps({
            "key": "adaptive_baseline_enabled",
            "new_value": val_str
        })))

        conn.commit()
        return True
    finally:
        if should_close_conn:
            conn.close()


