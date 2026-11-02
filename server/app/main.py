import time
import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.db import get_db_connection, run_migrations
from app.auth import authenticate_user, create_access_token, get_current_user, seed_default_users
from app.mqtt_client import start_mqtt_client, stop_mqtt_client, get_system_status
from app.analysis import get_daily_runtime_breakdown
from app.detectors import run_all_detectors, get_config_value, set_config_value

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run schema migrations and seed initial default users & config
    run_migrations()
    conn = get_db_connection()
    try:
        seed_default_users(conn)
    finally:
        conn.close()

    # Start background MQTT subscriber
    start_mqtt_client()
    yield
    # Shutdown logic
    stop_mqtt_client()

app = FastAPI(
    title="DCEMS Backend API",
    description="Safety-gated Energy Management System Backend for DC Office",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for local dashboard development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str

class DaylightCalibrationRequest(BaseModel):
    daylight_on_threshold: Optional[int] = 350
    daylight_off_threshold: Optional[int] = 450
    set_calibrated: bool = True

@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "dcems-backend",
        "timestamp_utc": int(time.time()),
        "room_id": settings.room_id
    }

@app.post("/api/auth/login", response_model=LoginResponse)
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    now = int(time.time())
    
    # Audit log entry
    conn = get_db_connection()
    try:
        if not user:
            conn.execute(
                "INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details) VALUES (?, ?, ?, ?, ?)",
                (f"log_{now}_{abs(hash(req.username)) % 100000}", now, "login", req.username, json.dumps({"success": False, "reason": "invalid_credentials"}))
            )
            conn.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )

        token = create_access_token(user_id=user["user_id"], username=user["username"], role=user["role"])
        conn.execute(
            "INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details) VALUES (?, ?, ?, ?, ?)",
            (f"log_{now}_{user['user_id']}", now, "login", user["username"], json.dumps({"success": True, "role": user["role"]}))
        )
        conn.commit()
        return LoginResponse(
            access_token=token,
            role=user["role"],
            username=user["username"]
        )
    finally:
        conn.close()

@app.get("/api/auth/me")
def get_current_user_profile(user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "user_id": user.get("sub"),
        "username": user.get("username"),
        "role": user.get("role")
    }

@app.get("/api/live")
def get_live_telemetry() -> Dict[str, Any]:
    """
    Returns the real-time live telemetry snapshot, online status,
    staleness indicator, commanded device states, and mandatory disclaimer.
    """
    sys_status = get_system_status()
    latest_sensor = sys_status.get("latest_sensor")

    # If cache has no sensor yet, attempt fallback query to DB
    if not latest_sensor:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT sample_id, timestamp_utc, device_ts, pir_motion, ldr_raw,
                       ambient_light_level, temperature_c, humidity_pct,
                       last_motion_at, occupancy_state, sensor_quality
                FROM sensor_samples
                ORDER BY timestamp_utc DESC LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                latest_sensor = dict(row)
        finally:
            conn.close()

    now = int(time.time())
    is_stale = sys_status["is_stale"]
    if latest_sensor and latest_sensor.get("timestamp_utc"):
        if (now - latest_sensor["timestamp_utc"]) > 60:
            is_stale = True

    return {
        "room_id": settings.room_id,
        "is_online": sys_status["is_online"],
        "is_stale": is_stale,
        "last_seen_utc": sys_status["last_seen_utc"],
        "last_heartbeat_utc": sys_status["last_heartbeat_utc"],
        "uptime_sec": sys_status["uptime_sec"],
        "mode": sys_status["mode"],
        "devices": sys_status["devices"],
        "sensor": latest_sensor,
        "labels": {
            "occupancy_disclaimer": "PIR detects motion, not people.",
            "runtime_disclaimer": "All runtime metrics are estimates based on commanded relay state."
        }
    }

@app.get("/api/readings")
def get_sensor_readings(
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Returns time-series sensor samples for charting.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM sensor_samples WHERE 1=1"
        params: List[Any] = []
        if from_ts is not None:
            query += " AND timestamp_utc >= ?"
            params.append(from_ts)
        if to_ts is not None:
            query += " AND timestamp_utc <= ?"
            params.append(to_ts)
        query += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        # Return chronological order for charts
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()

@app.get("/api/events")
def get_device_events(
    device_id: Optional[str] = None,
    state_source: Optional[str] = None,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Returns historical device state transition events.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM device_state_events WHERE 1=1"
        params: List[Any] = []
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        if state_source:
            query += " AND state_source = ?"
            params.append(state_source)
        if from_ts is not None:
            query += " AND timestamp_utc >= ?"
            params.append(from_ts)
        if to_ts is not None:
            query += " AND timestamp_utc <= ?"
            params.append(to_ts)
        query += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.get("/api/analysis/runtime")
def get_runtime_analysis(date_utc: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns aggregated runtime metrics per device for a specific UTC date.
    Strictly follows T = tOFF - tON, honest estimates only, no kWh or cost.
    """
    return get_daily_runtime_breakdown(date_utc)

@app.get("/api/analysis/sessions")
def get_runtime_sessions(
    device_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Returns recent runtime sessions for auditability.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM runtime_sessions WHERE 1=1"
        params: List[Any] = []
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        query += " ORDER BY start_time_utc DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

@app.get("/api/anomalies")
def get_anomalies(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Returns detected anomaly alerts. Strictly alert-only.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        query = "SELECT * FROM anomaly_events WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if device_id:
            query += " AND device_id = ?"
            params.append(device_id)
        query += " ORDER BY timestamp_utc DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("evidence"):
                try:
                    d["evidence"] = json.loads(d["evidence"])
                except Exception:
                    pass
            result.append(d)
        return result
    finally:
        conn.close()

@app.post("/api/anomalies/{anomaly_id}/ack")
def acknowledge_anomaly(anomaly_id: str) -> Dict[str, Any]:
    """
    Acknowledges an active anomaly alert and logs to audit trail.
    """
    conn = get_db_connection()
    now = int(time.time())
    try:
        cur = conn.cursor()
        cur.execute("SELECT anomaly_id, status FROM anomaly_events WHERE anomaly_id = ?", (anomaly_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Anomaly event not found")

        cur.execute("UPDATE anomaly_events SET status = 'acknowledged' WHERE anomaly_id = ?", (anomaly_id,))
        cur.execute("""
            INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details)
            VALUES (?, ?, 'anomaly_action', 'dashboard_user', ?)
        """, (f"log_ack_{now}_{anomaly_id[:8]}", now, json.dumps({"action": "acknowledge", "anomaly_id": anomaly_id})))
        conn.commit()
        return {"status": "acknowledged", "anomaly_id": anomaly_id, "timestamp_utc": now}
    finally:
        conn.close()

@app.post("/api/settings/calibrate-daylight")
def calibrate_daylight(req: DaylightCalibrationRequest) -> Dict[str, Any]:
    """
    Calibrates daylight waste thresholds and unlocks the daylight detector.
    """
    conn = get_db_connection()
    now = int(time.time())
    try:
        if req.daylight_on_threshold is not None:
            set_config_value("daylight_on_threshold", str(req.daylight_on_threshold), changed_by="calibration_wizard", custom_conn=conn)
        if req.daylight_off_threshold is not None:
            set_config_value("daylight_off_threshold", str(req.daylight_off_threshold), changed_by="calibration_wizard", custom_conn=conn)

        flag_val = "true" if req.set_calibrated else "false"
        set_config_value("daylight_calibration_flag", flag_val, changed_by="calibration_wizard", custom_conn=conn)

        conn.execute("""
            INSERT INTO audit_log (log_id, timestamp_utc, event_type, actor, details)
            VALUES (?, ?, 'settings_change', 'dashboard_operator', ?)
        """, (f"log_calib_{now}", now, json.dumps({
            "action": "calibrate_daylight",
            "flag": flag_val,
            "on_threshold": req.daylight_on_threshold,
            "off_threshold": req.daylight_off_threshold
        })))
        conn.commit()

        return {
            "success": True,
            "daylight_calibration_flag": (flag_val == "true"),
            "daylight_on_threshold": req.daylight_on_threshold,
            "daylight_off_threshold": req.daylight_off_threshold,
            "message": "Daylight calibration applied successfully."
        }
    finally:
        conn.close()

@app.get("/api/settings/calibration-status")
def get_calibration_status() -> Dict[str, Any]:
    """
    Returns current daylight calibration flag, thresholds, and latest LDR reading.
    """
    conn = get_db_connection()
    try:
        calib_flag = get_config_value("daylight_calibration_flag", "false", conn).strip().lower() == "true"
        on_th = int(get_config_value("daylight_on_threshold", "350", conn))
        off_th = int(get_config_value("daylight_off_threshold", "450", conn))
        confirm_sec = int(get_config_value("daylight_confirmation_sec", "180", conn))

        cur = conn.cursor()
        cur.execute("SELECT ldr_raw, timestamp_utc FROM sensor_samples ORDER BY timestamp_utc DESC LIMIT 1")
        row = cur.fetchone()
        latest_ldr = row["ldr_raw"] if row else None

        return {
            "daylight_calibration_flag": calib_flag,
            "daylight_on_threshold": on_th,
            "daylight_off_threshold": off_th,
            "daylight_confirmation_sec": confirm_sec,
            "latest_ldr_raw": latest_ldr,
            "status_text": "Calibrated & Active" if calib_flag else "Uncalibrated - Daylight detector locked for safety"
        }
    finally:
        conn.close()

# Mount static dashboard if directory exists
dashboard_dir = Path(__file__).resolve().parent.parent.parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")
