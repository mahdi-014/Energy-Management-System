import pytest
from fastapi import HTTPException
from app.db import get_db_connection, run_migrations
from app.main import (
    control_device,
    control_mode,
    set_manual_override,
    get_control_actions,
    DeviceControlRequest,
    ModeControlRequest,
    OverrideRequest
)

@pytest.fixture(autouse=True)
def setup_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test_control.db"
    monkeypatch.setattr("app.config.settings.db_path", str(test_db))
    run_migrations(custom_path=str(test_db))
    yield test_db

def test_api_control_device_success():
    req = DeviceControlRequest(device_id="light_01", requested_state="ON", reason="test_light_on")
    user = {"username": "admin_test", "role": "admin"}
    res = control_device(req, user=user)

    assert res["success"] is True
    assert res["device_id"] == "light_01"
    assert res["requested_state"] == "ON"
    assert res["action_id"].startswith("act_")

def test_api_control_device_ac_pc_power_off_blocked_t13():
    user = {"username": "admin_test", "role": "admin"}

    # AC OFF blocked
    req_ac = DeviceControlRequest(device_id="ac_01", requested_state="OFF")
    with pytest.raises(HTTPException) as exc_info_ac:
        control_device(req_ac, user=user)
    assert exc_info_ac.value.status_code == 400
    assert "ac_pc_power_off_blocked_by_policy" in exc_info_ac.value.detail

    # PC OFF blocked
    req_pc = DeviceControlRequest(device_id="pc_01", requested_state="OFF")
    with pytest.raises(HTTPException) as exc_info_pc:
        control_device(req_pc, user=user)
    assert exc_info_pc.value.status_code == 400
    assert "ac_pc_power_off_blocked_by_policy" in exc_info_pc.value.detail

def test_api_control_mode_transitions():
    user = {"username": "admin_test", "role": "admin"}

    req_man = ModeControlRequest(mode="MANUAL")
    res_man = control_mode(req_man, user=user)
    assert res_man["success"] is True
    assert res_man["mode"] == "MANUAL"

    req_auto = ModeControlRequest(mode="AUTO")
    res_auto = control_mode(req_auto, user=user)
    assert res_auto["success"] is True
    assert res_auto["mode"] == "AUTO"

    req_inv = ModeControlRequest(mode="INVALID")
    with pytest.raises(HTTPException) as exc_info:
        control_mode(req_inv, user=user)
    assert exc_info.value.status_code == 400

def test_api_control_manual_override_and_audit():
    user = {"username": "admin_test", "role": "admin"}

    req_ovr = OverrideRequest(device_id="fan_01", hold_seconds=300, reason="staff_meeting")
    res_ovr = set_manual_override(req_ovr, user=user)
    assert "override_id" in res_ovr
    assert res_ovr["device_id"] == "fan_01"
    assert res_ovr["hold_seconds"] == 300

    # Issue a device command to generate action audit
    control_device(DeviceControlRequest(device_id="fan_01", requested_state="ON"), user=user)

    actions = get_control_actions(device_id="fan_01")
    assert len(actions) >= 1
    assert actions[0]["device_id"] == "fan_01"
    assert actions[0]["proposed_state"] == "ON"

