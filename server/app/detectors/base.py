import json
import time
import uuid
import logging
import sqlite3
from typing import Dict, Any, Optional, List

from app.db import get_db_connection

logger = logging.getLogger("dcems.detectors")

VALID_ANOMALY_TYPES = (
    "vacancy_runtime",
    "daylight_waste",
    "long_runtime",
    "rapid_cycling",
    "sensor_issue"
)

VALID_SEVERITIES = ("info", "warning", "high", "diagnostic")

def get_config_value(key: str, default: str, custom_conn: Optional[sqlite3.Connection] = None) -> str:
    """
    Retrieves configuration value from SQLite config table.
    """
    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cur.fetchone()
        if row and row["value"] is not None:
            return str(row["value"])
        return default
    finally:
        if should_close:
            conn.close()

def set_config_value(
    key: str,
    value: str,
    changed_by: str = "system",
    custom_conn: Optional[sqlite3.Connection] = None
) -> bool:
    """
    Sets a configuration value in the config table with revision history.
    """
    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)
    now = int(time.time())
    try:
        cur = conn.cursor()
        cur.execute("SELECT value, history FROM config WHERE key = ?", (key,))
        row = cur.fetchone()

        history_list = []
        if row:
            old_val = row["value"]
            raw_hist = row["history"]
            if raw_hist:
                try:
                    history_list = json.loads(raw_hist)
                except Exception:
                    history_list = []
            history_list.append({
                "value": old_val,
                "changed_at": now,
                "changed_by": changed_by
            })

            cur.execute("""
                UPDATE config
                SET value = ?, changed_at = ?, changed_by = ?, history = ?
                WHERE key = ?
            """, (value, now, changed_by, json.dumps(history_list), key))
        else:
            cur.execute("""
                INSERT INTO config (key, value, changed_at, changed_by, history)
                VALUES (?, ?, ?, ?, '[]')
            """, (key, value, now, changed_by))

        conn.commit()
        return True
    finally:
        if should_close:
            conn.close()

def create_or_update_anomaly(
    device_id: Optional[str],
    anomaly_type: str,
    severity: str,
    observed_value: str,
    threshold_value: str,
    evidence: Dict[str, Any],
    detector_type: str = "rule",
    ts: Optional[int] = None,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Optional[str]:
    """
    Creates an anomaly record or updates an existing open/acknowledged alert.
    Enforces deduplication: At most 1 active alert per (device_id, anomaly_type)
    to suppress alert spam.
    """
    if anomaly_type not in VALID_ANOMALY_TYPES:
        logger.warning(f"Invalid anomaly type: {anomaly_type}")
        return None

    if severity not in VALID_SEVERITIES:
        severity = "info"

    now = ts or int(time.time())
    evidence_json = json.dumps(evidence)

    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)

    try:
        cur = conn.cursor()

        # Check for existing active alert for this device and type
        if device_id:
            cur.execute("""
                SELECT anomaly_id, status FROM anomaly_events
                WHERE device_id = ? AND anomaly_type = ? AND status IN ('open', 'acknowledged')
                ORDER BY timestamp_utc DESC LIMIT 1
            """, (device_id, anomaly_type))
        else:
            cur.execute("""
                SELECT anomaly_id, status FROM anomaly_events
                WHERE device_id IS NULL AND anomaly_type = ? AND status IN ('open', 'acknowledged')
                ORDER BY timestamp_utc DESC LIMIT 1
            """, (anomaly_type,))

        existing = cur.fetchone()
        if existing:
            # Active alert already exists: refresh context and return existing ID without duplicate alert spam
            anom_id = existing["anomaly_id"]
            cur.execute("""
                UPDATE anomaly_events
                SET timestamp_utc = ?, observed_value = ?, threshold_value = ?, evidence = ?, severity = ?
                WHERE anomaly_id = ?
            """, (now, observed_value, threshold_value, evidence_json, severity, anom_id))
            conn.commit()
            return anom_id

        # Insert new anomaly event
        new_id = f"anom_{anomaly_type}_{uuid.uuid4().hex[:8]}"
        cur.execute("""
            INSERT INTO anomaly_events (
                anomaly_id, timestamp_utc, device_id, anomaly_type,
                severity, detector_type, observed_value, threshold_value,
                evidence, status, resolved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', NULL)
        """, (
            new_id, now, device_id, anomaly_type,
            severity, detector_type, observed_value, threshold_value,
            evidence_json
        ))
        conn.commit()
        return new_id
    finally:
        if should_close:
            conn.close()

def resolve_anomaly(
    device_id: Optional[str],
    anomaly_type: str,
    resolved_ts: Optional[int] = None,
    custom_conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Resolves any open or acknowledged anomalies for a given (device_id, anomaly_type).
    Returns number of rows updated.
    """
    now = resolved_ts or int(time.time())
    conn = custom_conn or get_db_connection()
    should_close = (custom_conn is None)

    try:
        cur = conn.cursor()
        if device_id:
            cur.execute("""
                UPDATE anomaly_events
                SET status = 'resolved', resolved_at = ?
                WHERE device_id = ? AND anomaly_type = ? AND status IN ('open', 'acknowledged')
            """, (now, device_id, anomaly_type))
        else:
            cur.execute("""
                UPDATE anomaly_events
                SET status = 'resolved', resolved_at = ?
                WHERE device_id IS NULL AND anomaly_type = ? AND status IN ('open', 'acknowledged')
            """, (now, anomaly_type))

        rows_updated = cur.rowcount
        conn.commit()
        return rows_updated
    finally:
        if should_close:
            conn.close()

