import time
import logging
import sqlite3
from typing import Dict, Any, Optional, List

from app.detectors.base import get_config_value, create_or_update_anomaly, resolve_anomaly

logger = logging.getLogger("dcems.detectors.cycling")

CANONICAL_DEVICES = ("light_01", "fan_01", "ac_01", "pc_01")

def evaluate_cycling_anomalies(
    current_ts: int,
    custom_conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """
    Evaluates rapid cycling conditions (>4 transitions in 10 minutes).
    - Severity: diagnostic (diagnostic only; never triggers relay switching).
    - Useful for detecting relay chatter, sensor bounce, or erratic wall switches.
    """
    conn = custom_conn
    should_close = False
    if conn is None:
        from app.db import get_db_connection
        conn = get_db_connection()
        should_close = True

    detected_anomalies: List[Dict[str, Any]] = []

    window_sec = int(get_config_value("rapid_cycling_window_sec", "600", conn))
    threshold_count = int(get_config_value("rapid_cycling_threshold", "4", conn))
    window_start = current_ts - window_sec

    try:
        cur = conn.cursor()

        for dev in CANONICAL_DEVICES:
            cur.execute("""
                SELECT COUNT(*) as transition_count
                FROM device_state_events
                WHERE device_id = ? AND timestamp_utc >= ?
            """, (dev, window_start))
            row = cur.fetchone()
            count = row["transition_count"] if row else 0

            if count > threshold_count:
                evidence = {
                    "device_id": dev,
                    "transition_count": count,
                    "window_sec": window_sec,
                    "threshold": threshold_count,
                    "note": "Diagnostic alert: excessive relay cycling observed. Never triggers automated switching."
                }

                anom_id = create_or_update_anomaly(
                    device_id=dev,
                    anomaly_type="rapid_cycling",
                    severity="diagnostic",
                    observed_value=f"{count} switches in {window_sec // 60}m",
                    threshold_value=f"> {threshold_count} switches",
                    evidence=evidence,
                    detector_type="rule",
                    ts=current_ts,
                    custom_conn=conn
                )
                if anom_id:
                    detected_anomalies.append({
                        "anomaly_id": anom_id,
                        "device_id": dev,
                        "severity": "diagnostic",
                        "transition_count": count
                    })
            else:
                resolve_anomaly(dev, "rapid_cycling", resolved_ts=current_ts, custom_conn=conn)

        return detected_anomalies
    finally:
        if should_close:
            conn.close()
