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

# Mount static dashboard if directory exists
dashboard_dir = Path(__file__).resolve().parent.parent.parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")
