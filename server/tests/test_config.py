import pytest
from app.config import settings, CANONICAL_DEVICES, CANONICAL_MODES, CANONICAL_STATES, AUTO_ELIGIBLE_MAP

def test_canonical_device_identifiers():
    """FR-01: The system shall identify each monitored device using a unique device identifier."""
    expected = {"light_01", "fan_01", "ac_01", "pc_01"}
    assert CANONICAL_DEVICES == expected

def test_canonical_controller_modes():
    assert CANONICAL_MODES == {"AUTO", "MANUAL"}

def test_canonical_device_states():
    assert CANONICAL_STATES == {"ON", "OFF"}

def test_hardcoded_auto_eligibility():
    """Safety Invariant: AC and PC must never be eligible for automated switching."""
    assert AUTO_ELIGIBLE_MAP["light_01"] is True
    assert AUTO_ELIGIBLE_MAP["fan_01"] is True
    assert AUTO_ELIGIBLE_MAP["ac_01"] is False
    assert AUTO_ELIGIBLE_MAP["pc_01"] is False

def test_settings_defaults():
    assert settings.room_id == "room1"
    assert settings.jwt_algorithm == "HS256"
    assert settings.token_expire_minutes > 0
    assert len(settings.jwt_secret) >= 32

