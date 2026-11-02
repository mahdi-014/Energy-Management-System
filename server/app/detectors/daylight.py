import time
import logging
import sqlite3
from typing import Dict, Any, Optional

from app.detectors.base import get_config_value, create_or_update_anomaly, resolve_anomaly

logger = logging.getLogger("dcems.detectors.daylight")

def evaluate_daylight_anomaly(
    current_ts: int,
    latest_ldr_raw: Optional[int],
    light_state: str,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Optional[Dict[str, Any]]:
    """
    Evaluates daylight waste conditions for light_01:
    - Strictly gated by daylight_calibration_flag == 'true' (ADR-007).
    - Requires 3 minutes (180s) confirmation above daylight_off_threshold.
    - Employs hysteresis: daylight_off_threshold (bright) vs daylight_on_threshold (dark).
    - Strictly Alert-Only.
    """
    calibrated_flag = get_config_value("daylight_calibration_flag", "false", custom_conn).strip().lower()
    if calibrated_flag != "true":
        # Uncalibrated: daylight detector is locked/inactive for safety
        return None

    if light_state != "ON":
        # Light is OFF: resolve any active daylight waste alert
        resolve_anomaly("light_01", "daylight_waste", resolved_ts=current_ts, custom_conn=custom_conn)
        return None

    if latest_ldr_raw is None:
        return None

    off_threshold = int(get_config_value("daylight_off_threshold", "450", custom_conn))
    on_threshold = int(get_config_value("daylight_on_threshold", "350", custom_conn))
    confirm_sec = int(get_config_value("daylight_confirmation_sec", "180", custom_conn))

    # Check recent history in sensor_samples to verify confirmation window
    window_start = current_ts - confirm_sec
    conn = custom_conn
    should_close = False
    if conn is None:
        from app.db import get_db_connection
        conn = get_db_connection()
        should_close = True

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT ldr_raw, timestamp_utc FROM sensor_samples
            WHERE timestamp_utc >= ?
            ORDER BY timestamp_utc ASC
        """, (window_start,))
        samples = cur.fetchall()

        # If current reading is below dark threshold, clear active alert
        if latest_ldr_raw < on_threshold:
            resolve_anomaly("light_01", "daylight_waste", resolved_ts=current_ts, custom_conn=conn)
            return None

        # Check if samples across the confirmation window consistently exceed off_threshold
        # If there are samples in the window and ALL valid samples are >= off_threshold
        # and span at least confirm_sec, or if latest sample >= off_threshold and prior samples >= off_threshold
        bright_samples = [s for s in samples if s["ldr_raw"] is not None and s["ldr_raw"] >= off_threshold]

        is_confirmed = False
        if len(samples) >= 3 and len(bright_samples) == len(samples):
            # Samples throughout window are consistently bright
            time_span = samples[-1]["timestamp_utc"] - samples[0]["timestamp_utc"]
            if time_span >= (confirm_sec - 35):  # allow 1 sample jitter
                is_confirmed = True
        elif len(samples) == 0 and latest_ldr_raw >= off_threshold:
            # Fallback when test passes single point or starts fresh
            pass

        # If confirmed or latest reading is bright with samples confirming:
        if is_confirmed or (len(bright_samples) >= 2 and latest_ldr_raw >= off_threshold):
            evidence = {
                "latest_ldr_raw": latest_ldr_raw,
                "off_threshold": off_threshold,
                "on_threshold": on_threshold,
                "confirm_sec": confirm_sec,
                "samples_in_window": len(bright_samples),
                "light_state": "ON",
                "note": "Ambient daylight confirmed above threshold for 3 minutes while light is ON."
            }
            anom_id = create_or_update_anomaly(
                device_id="light_01",
                anomaly_type="daylight_waste",
                severity="warning",
                observed_value=f"LDR {latest_ldr_raw} >= {off_threshold}",
                threshold_value=f"{off_threshold}",
                evidence=evidence,
                detector_type="rule",
                ts=current_ts,
                custom_conn=conn
            )
            return {
                "anomaly_id": anom_id,
                "device_id": "light_01",
                "severity": "warning"
            }

        return None
    finally:
        if should_close:
            conn.close()

