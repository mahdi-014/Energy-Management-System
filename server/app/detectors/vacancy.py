import time
import logging
import sqlite3
from typing import Dict, Any, Optional, List

from app.detectors.base import get_config_value, create_or_update_anomaly, resolve_anomaly

logger = logging.getLogger("dcems.detectors.vacancy")

CANONICAL_DEVICES = ("light_01", "fan_01", "ac_01", "pc_01")

def evaluate_vacancy_anomalies(
    current_ts: int,
    last_motion_at: Optional[int],
    device_states: Dict[str, str],
    custom_conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """
    Evaluates multi-stage vacancy conditions:
    1. No motion 5 min (>= 300s) -> Vacancy Candidate stage
    2. No motion 10 min (>= 600s) -> Warning stage if device is ON (severity: info)
    3. No motion 15 min (>= 900s) -> Confirmed vacancy action candidate (severity: warning)

    Strictly Alert-Only in Phase 3. Never switches relays.
    """
    if last_motion_at is None or last_motion_at <= 0:
        return []

    elapsed_sec = max(0, current_ts - last_motion_at)

    candidate_sec = int(get_config_value("vacancy_candidate_sec", "300", custom_conn))
    warning_sec = int(get_config_value("vacancy_warning_sec", "600", custom_conn))
    action_sec = int(get_config_value("vacancy_action_sec", "900", custom_conn))

    anomalies_detected: List[Dict[str, Any]] = []

    for dev in CANONICAL_DEVICES:
        is_on = (device_states.get(dev) == "ON")

        if not is_on:
            # Device is OFF; resolve any active vacancy alert for it
            resolve_anomaly(dev, "vacancy_runtime", resolved_ts=current_ts, custom_conn=custom_conn)
            continue

        if elapsed_sec < candidate_sec:
            # Motion observed recently; resolve any active vacancy alert
            resolve_anomaly(dev, "vacancy_runtime", resolved_ts=current_ts, custom_conn=custom_conn)
            continue

        if elapsed_sec >= action_sec:
            # Stage 3: Confirmed Vacancy (> 15 min) with load energized
            evidence = {
                "stage": "action_candidate",
                "last_motion_at": last_motion_at,
                "elapsed_sec": elapsed_sec,
                "device_state": "ON",
                "candidate_sec": candidate_sec,
                "warning_sec": warning_sec,
                "action_sec": action_sec,
                "note": "PIR detects motion, not people. Alert only; detection != authorization."
            }
            anom_id = create_or_update_anomaly(
                device_id=dev,
                anomaly_type="vacancy_runtime",
                severity="warning",
                observed_value=f"{elapsed_sec}s no motion",
                threshold_value=f"{action_sec}s",
                evidence=evidence,
                detector_type="rule",
                ts=current_ts,
                custom_conn=custom_conn
            )
            if anom_id:
                anomalies_detected.append({
                    "anomaly_id": anom_id,
                    "device_id": dev,
                    "stage": "action_candidate",
                    "severity": "warning"
                })

        elif elapsed_sec >= warning_sec:
            # Stage 2: Vacancy Warning (10-15 min) with load energized
            evidence = {
                "stage": "warning",
                "last_motion_at": last_motion_at,
                "elapsed_sec": elapsed_sec,
                "device_state": "ON",
                "candidate_sec": candidate_sec,
                "warning_sec": warning_sec,
                "action_sec": action_sec,
                "note": "PIR detects motion, not people. Load is running in candidate vacant space."
            }
            anom_id = create_or_update_anomaly(
                device_id=dev,
                anomaly_type="vacancy_runtime",
                severity="info",
                observed_value=f"{elapsed_sec}s no motion",
                threshold_value=f"{warning_sec}s",
                evidence=evidence,
                detector_type="rule",
                ts=current_ts,
                custom_conn=custom_conn
            )
            if anom_id:
                anomalies_detected.append({
                    "anomaly_id": anom_id,
                    "device_id": dev,
                    "stage": "warning",
                    "severity": "info"
                })

    return anomalies_detected

