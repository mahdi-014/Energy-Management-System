import hmac
import hashlib
import base64
import json
import time
import secrets
import sqlite3
from typing import Optional, Dict, Any, Tuple
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings
from app.db import get_db_connection

security_bearer = HTTPBearer(auto_error=False)

def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        hash_name="sha256",
        password=password.encode("utf-8"),
        salt=salt.encode("utf-8"),
        iterations=100000
    )
    return key.hex(), salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(new_hash, stored_hash)

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")

def _b64decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))

def create_access_token(user_id: str, username: str, role: str, expires_in_minutes: Optional[int] = None) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    exp_minutes = expires_in_minutes or settings.token_expire_minutes
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + (exp_minutes * 60)
    }
    encoded_header = _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
    
    signature = hmac.new(
        key=settings.jwt_secret.encode("utf-8"),
        msg=signing_input,
        digestmod=hashlib.sha256
    ).digest()
    encoded_signature = _b64encode(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"

def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        encoded_header, encoded_payload, encoded_signature = parts
        signing_input = f"{encoded_header}.{encoded_payload}".encode("utf-8")
        expected_sig = hmac.new(
            key=settings.jwt_secret.encode("utf-8"),
            msg=signing_input,
            digestmod=hashlib.sha256
        ).digest()
        actual_sig = _b64decode(encoded_signature)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:
        return None

def seed_default_users(conn: sqlite3.Connection):
    cur = conn.cursor()
    # Seed Admin
    cur.execute("SELECT user_id FROM users WHERE username = ?", (settings.admin_user,))
    if not cur.fetchone():
        pwd_hash, salt = hash_password(settings.admin_password)
        cur.execute(
            "INSERT INTO users (user_id, username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("usr_admin_01", settings.admin_user, pwd_hash, salt, "admin", int(time.time()))
        )
    # Seed Viewer
    cur.execute("SELECT user_id FROM users WHERE username = ?", (settings.viewer_user,))
    if not cur.fetchone():
        pwd_hash, salt = hash_password(settings.viewer_password)
        cur.execute(
            "INSERT INTO users (user_id, username, password_hash, salt, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("usr_viewer_01", settings.viewer_user, pwd_hash, salt, "viewer", int(time.time()))
        )
    conn.commit()

def authenticate_user(username: str, password: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    close_after = False
    if conn is None:
        conn = get_db_connection()
        close_after = True
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, username, password_hash, salt, role FROM users WHERE username = ?", (username,))
        user = cur.fetchone()
        if not user:
            return None
        if verify_password(password, user["password_hash"], user["salt"]):
            return {
                "user_id": user["user_id"],
                "username": user["username"],
                "role": user["role"]
            }
        return None
    finally:
        if close_after:
            conn.close()

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)) -> Dict[str, Any]:
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrative privileges required"
        )
    return user
