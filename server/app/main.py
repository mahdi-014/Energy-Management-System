import time
import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.db import get_db_connection, run_migrations
from app.auth import authenticate_user, create_access_token, get_current_user, seed_default_users

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Run schema migrations and seed initial default users & config
    run_migrations()
    conn = get_db_connection()
    try:
        seed_default_users(conn)
    finally:
        conn.close()
    yield
    # Shutdown logic if needed

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

# Mount static dashboard if directory exists
dashboard_dir = Path(__file__).resolve().parent.parent.parent / "dashboard"
if dashboard_dir.exists():
    app.mount("/", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")

