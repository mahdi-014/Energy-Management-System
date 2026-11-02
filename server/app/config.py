import os
from typing import Dict, Set
from pydantic import BaseModel, Field

# Canonical Constants
CANONICAL_DEVICES: Set[str] = {"light_01", "fan_01", "ac_01", "pc_01"}
CANONICAL_MODES: Set[str] = {"AUTO", "MANUAL"}
CANONICAL_STATES: Set[str] = {"ON", "OFF"}

# Compile-time / Server-side Hardcoded Eligibility Matrix
AUTO_ELIGIBLE_MAP: Dict[str, bool] = {
    "light_01": True,
    "fan_01": True,
    "ac_01": False,   # Strictly Alert-Only: Auto-switching forbidden
    "pc_01": False,   # Strictly Alert-Only: Auto-switching forbidden
}

class Settings(BaseModel):
    # Server Binding
    host: str = Field(default=os.getenv("DCEMS_HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("DCEMS_PORT", "8000")))
    db_path: str = Field(default=os.getenv("DCEMS_DB_PATH", "data/dcems.db"))

    # MQTT Settings
    mqtt_broker: str = Field(default=os.getenv("DCEMS_MQTT_BROKER", "127.0.0.1"))
    mqtt_port: int = Field(default=int(os.getenv("DCEMS_MQTT_PORT", "1883")))
    mqtt_user: str = Field(default=os.getenv("DCEMS_MQTT_USER", "dcems_server"))
    mqtt_password: str = Field(default=os.getenv("DCEMS_MQTT_PASSWORD", "dcems_mqtt_secret_password_here"))

    # Security & Tokens
    jwt_secret: str = Field(default=os.getenv("DCEMS_JWT_SECRET", "super_secret_signing_key_at_least_32_chars_long"))
    jwt_algorithm: str = Field(default=os.getenv("DCEMS_JWT_ALGORITHM", "HS256"))
    token_expire_minutes: int = Field(default=int(os.getenv("DCEMS_TOKEN_EXPIRE_MINUTES", "480")))

    # Initial Credentials
    admin_user: str = Field(default=os.getenv("DCEMS_ADMIN_USER", "admin"))
    admin_password: str = Field(default=os.getenv("DCEMS_ADMIN_PASSWORD", "AdminPass_DCEMS_2026!"))
    viewer_user: str = Field(default=os.getenv("DCEMS_VIEWER_USER", "viewer"))
    viewer_password: str = Field(default=os.getenv("DCEMS_VIEWER_PASSWORD", "ViewerPass_DCEMS_2026!"))

    # Room Scope
    room_id: str = Field(default=os.getenv("DCEMS_ROOM_ID", "room1"))
    enable_adaptive_baseline: bool = Field(default=os.getenv("DCEMS_ENABLE_ADAPTIVE_BASELINE", "false").lower() == "true")

settings = Settings()

