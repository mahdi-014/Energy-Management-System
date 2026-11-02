import time
import sqlite3
from typing import Dict, Any, Optional, List

from app.detectors.base import (
    get_config_value,
    set_config_value,
    create_or_update_anomaly,
    resolve_anomaly
)
from app.detectors.vacancy import evaluate_vacancy_anomalies
from app.detectors.daylight import evaluate_daylight_anomaly
from app.detectors.runtime import evaluate_runtime_anomalies
from app.detectors.cycling import evaluate_cycling_anomalies
from app.detectors.sensor_quality import evaluate_sensor_quality_anomaly

def run_all_detectors(
    current_ts: Optional[int] = None,
    custom_conn: Optional[sqlite3.Connection] = None
) -> Dict[str, Any]:
    """
    Executes all 5 deterministic anomaly detectors in a unified pass:
    - Strictly Alert-Only. Detection != Authorization.
    - Zero ML claims; deterministic, explainable rule logic only.
    """
    ts = current_ts or int(time.time())
    conn = custom_conn
    should_close = False
    if conn is None:
        from app.db import get_db_connection
        conn = get_db_connection()
        should_close = True

    results: Dict[str, Any] = {
        "timestamp_utc": ts,
        "anomalies": []
    }

    try:
        cur = conn.cursor()

        # 1. Fetch latest sensor sample
        cur.execute("""
            SELECT timestamp_utc, pir_motion, ldr_raw, ambient_light_level,
                   temperature_c, humidity_pct, last_motion_at, sensor_quality
            FROM sensor_samples
            ORDER BY timestamp_utc DESC LIMIT 1
        """)
        row = cur.fetchone()
        latest_sample = dict(row) if row else None

        # 2. Fetch current commanded device states
        cur.execute("""
            SELECT d.device_id,
                   COALESCE((
                       SELECT requested_state
                       FROM device_state_events
                       WHERE device_id = d.device_id
                       ORDER BY timestamp_utc DESC LIMIT 1
                   ), 'OFF') as current_state
            FROM (
                SELECT 'light_01' as device_id UNION
                SELECT 'fan_01' UNION
                SELECT 'ac_01' UNION
                SELECT 'pc_01'
            ) d
        """)
        device_states = {r["device_id"]: r["current_state"] for r in cur.fetchall()}

        # 3. Detector E: Sensor Quality & Staleness
        sq_res = evaluate_sensor_quality_anomaly(ts, latest_sample, custom_conn=conn)
        if sq_res:
            results["anomalies"].append(sq_res)

        # 4. Detector A: Multi-Stage Vacancy
        last_motion = latest_sample.get("last_motion_at") if latest_sample else None
        vac_res = evaluate_vacancy_anomalies(ts, last_motion, device_states, custom_conn=conn)
        results["anomalies"].extend(vac_res)

        # 5. Detector B: Daylight Confirmation & Hysteresis
        ldr_val = latest_sample.get("ldr_raw") if latest_sample else None
        daylight_res = evaluate_daylight_anomaly(ts, ldr_val, device_states.get("light_01", "OFF"), custom_conn=conn)
        if daylight_res:
            results["anomalies"].append(daylight_res)

        # 6. Detector C: Maximum Continuous Runtime
        rt_res = evaluate_runtime_anomalies(ts, custom_conn=conn)
        results["anomalies"].extend(rt_res)

        # 7. Detector D: Rapid Cycling
        cyc_res = evaluate_cycling_anomalies(ts, custom_conn=conn)
        results["anomalies"].extend(cyc_res)

        return results
    finally:
        if should_close:
            conn.close()

