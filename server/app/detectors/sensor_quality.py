import time
import logging
import sqlite3
from typing import Dict, Any, Optional

from app.detectors.base import get_config_value, create_or_update_anomaly, resolve_anomaly

logger = logging.getLogger("dcems.detectors.sensor_quality")

def evaluate_sensor_quality_anomaly(
    current_ts: int,
    latest_sample: Optional[Dict[str, Any]],
    custom_conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    """
    Evaluates sensor quality and staleness conditions:
    - Missing or stale telemetry (>60s).
    - Sensor error/fault conditions (DHT failure, LDR ADC invalid, or 'degraded'/'fault' quality).
    - Severity: warning.
    - Used to notify operator and suppress automated control actions (TC-08, T8).
    """
    conn = custom_conn
    should_close = False
    if conn is None:
        from app.db import get_db_connection
        conn = get_db_connection()
        should_close = True

    stale_sec = int(get_config_value("sensor_stale_sec", "60", conn))

    try:
        # If no sample provided, query latest sample from DB
        if latest_sample is None:
            cur = conn.cursor()
            cur.execute("""
                SELECT timestamp_utc, pir_motion, ldr_raw, temperature_c, humidity_pct, sensor_quality
                FROM sensor_samples
                ORDER BY timestamp_utc DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                latest_sample = dict(row)

        if not latest_sample:
            # No readings have ever been received
            evidence = {
                "issue": "no_telemetry_recorded",
                "note": "Controller has never published valid telemetry."
            }
            anom_id = create_or_update_anomaly(
                device_id=None,
                anomaly_type="sensor_issue",
                severity="warning",
                observed_value="no telemetry",
                threshold_value="active telemetry required",
                evidence=evidence,
                detector_type="rule",
                ts=current_ts,
                custom_conn=conn
            )
            return {"anomaly_id": anom_id, "issue": "no_telemetry", "severity": "warning"}

        sample_ts = latest_sample.get("timestamp_utc", 0)
        age_sec = max(0, current_ts - sample_ts)

        if age_sec > stale_sec:
            evidence = {
                "issue": "stale_telemetry",
                "last_seen_utc": sample_ts,
                "age_sec": age_sec,
                "stale_threshold_sec": stale_sec,
                "note": "Sensor telemetry is stale (>60s). Safety gate suppresses automated actions."
            }
            anom_id = create_or_update_anomaly(
                device_id=None,
                anomaly_type="sensor_issue",
                severity="warning",
                observed_value=f"{age_sec}s stale",
                threshold_value=f"<= {stale_sec}s",
                evidence=evidence,
                detector_type="rule",
                ts=current_ts,
                custom_conn=conn
            )
            return {"anomaly_id": anom_id, "issue": "stale_telemetry", "severity": "warning"}

        # Check for sensor quality flags or missing values
        quality = latest_sample.get("sensor_quality", "ok")
        temp = latest_sample.get("temperature_c")
        ldr = latest_sample.get("ldr_raw")

        if quality in ("fault", "degraded") or temp is None or ldr is None:
            evidence = {
                "issue": "sensor_reading_fault_or_out_of_bounds",
                "quality": quality,
                "temperature_c": temp,
                "ldr_raw": ldr,
                "note": "Sensor readings invalid or degraded. Missing data recorded as NULL."
            }
            anom_id = create_or_update_anomaly(
                device_id=None,
                anomaly_type="sensor_issue",
                severity="warning",
                observed_value=f"quality: {quality}",
                threshold_value="quality: ok",
                evidence=evidence,
                detector_type="rule",
                ts=current_ts,
                custom_conn=conn
            )
            return {"anomaly_id": anom_id, "issue": "sensor_fault", "severity": "warning"}

        # Telemetry is fresh and healthy: resolve active sensor_issue alert
        resolve_anomaly(None, "sensor_issue", resolved_ts=current_ts, custom_conn=conn)
        return None
    finally:
        if should_close:
            conn.close()

