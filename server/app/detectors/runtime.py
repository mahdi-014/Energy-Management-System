import time
import logging
import sqlite3
from typing import Dict, Any, Optional, List

from app.detectors.base import create_or_update_anomaly, resolve_anomaly

logger = logging.getLogger("dcems.detectors.runtime")

CANONICAL_DEVICES = ("light_01", "fan_01", "ac_01", "pc_01")

def evaluate_runtime_anomalies(
    current_ts: int,
    custom_conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """
    Evaluates maximum continuous runtime threshold violations.
    - Configured per device in device_policies.max_continuous_on_min.
    - NULL means unconfigured (no alert generated).
    - Severity: info (purely informational; long runtime does not prove waste).
    """
    conn = custom_conn
    should_close = False
    if conn is None:
        from app.db import get_db_connection
        conn = get_db_connection()
        should_close = True

    detected_anomalies: List[Dict[str, Any]] = []

    try:
        cur = conn.cursor()

        # Fetch open runtime sessions
        cur.execute("""
            SELECT session_id, device_id, start_time_utc
            FROM runtime_sessions
            WHERE end_time_utc IS NULL
        """)
        open_sessions = {row["device_id"]: row for row in cur.fetchall()}

        for dev in CANONICAL_DEVICES:
            # Check policy configuration for max_continuous_on_min
            cur.execute("""
                SELECT max_continuous_on_min FROM device_policies
                WHERE device_id = ?
            """, (dev,))
            pol_row = cur.fetchone()
            max_min = pol_row["max_continuous_on_min"] if pol_row else None

            if dev not in open_sessions or max_min is None or max_min <= 0:
                # Device is OFF or threshold unconfigured: resolve any open long_runtime alert
                resolve_anomaly(dev, "long_runtime", resolved_ts=current_ts, custom_conn=conn)
                continue

            sess = open_sessions[dev]
            start_ts = sess["start_time_utc"]
            duration_sec = max(0, current_ts - start_ts)
            threshold_sec = max_min * 60

            if duration_sec > threshold_sec:
                evidence = {
                    "session_id": sess["session_id"],
                    "start_time_utc": start_ts,
                    "duration_sec": duration_sec,
                    "duration_min": round(duration_sec / 60.0, 1),
                    "max_continuous_on_min": max_min,
                    "note": "Informational alert: continuous runtime exceeds configured policy limit. Does not prove waste."
                }

                anom_id = create_or_update_anomaly(
                    device_id=dev,
                    anomaly_type="long_runtime",
                    severity="info",
                    observed_value=f"{round(duration_sec / 60.0, 1)} min",
                    threshold_value=f"{max_min} min",
                    evidence=evidence,
                    detector_type="rule",
                    ts=current_ts,
                    custom_conn=conn
                )
                if anom_id:
                    detected_anomalies.append({
                        "anomaly_id": anom_id,
                        "device_id": dev,
                        "severity": "info",
                        "duration_min": round(duration_sec / 60.0, 1)
                    })
            else:
                resolve_anomaly(dev, "long_runtime", resolved_ts=current_ts, custom_conn=conn)

        return detected_anomalies
    finally:
        if should_close:
            conn.close()

