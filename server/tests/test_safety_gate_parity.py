import time
import pytest
from simulator.mock_esp import MockESP8266

def test_safety_gate_point_1_device_allowlist_auto_eligible():
    """
    Point 1: Ineligible devices (ac_01, pc_01) reject automated actions.
    """
    esp = MockESP8266(room_id="room1")
    now = int(time.time())
    esp.device_states["ac_01"] = "OFF"
    esp.device_states["pc_01"] = "OFF"
    esp.last_switch_time["ac_01"] = now - 500
    esp.last_switch_time["pc_01"] = now - 500
    
    # Attempt automated proposal to switch ON AC
    cmd_ac = {
        "action_id": "act_test_p1_ac",
        "device_id": "ac_01",
        "requested_state": "ON",
        "source": "server_proposal",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack = esp.handle_command_payload(cmd_ac)
    assert ack["result"] == "blocked"
    assert ack["reason"] == "device_not_auto_eligible"

    # Attempt automated proposal to switch ON PC
    cmd_pc = {
        "action_id": "act_test_p1_pc",
        "device_id": "pc_01",
        "requested_state": "ON",
        "source": "server_proposal",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack_pc = esp.handle_command_payload(cmd_pc)
    assert ack_pc["result"] == "blocked"
    assert ack_pc["reason"] == "device_not_auto_eligible"

def test_safety_gate_point_2_controller_mode_blocks_auto():
    """
    Point 2: Controller mode == MANUAL halts automated actions.
    """
    esp = MockESP8266(room_id="room1")
    esp.mode = "MANUAL"
    esp.device_states["fan_01"] = "ON"
    esp.last_switch_time["fan_01"] = int(time.time()) - 200
    now = int(time.time())

    cmd = {
        "action_id": "act_test_p2_mode",
        "device_id": "fan_01",
        "requested_state": "OFF",
        "source": "server_proposal",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack = esp.handle_command_payload(cmd)
    assert ack["result"] == "blocked"
    assert ack["reason"] == "controller_in_manual_mode"

def test_safety_gate_point_3_manual_override_hold():
    """
    Point 3: Active manual command hold lockout blocks automated actions.
    """
    esp = MockESP8266(room_id="room1")
    esp.mode = "AUTO"
    esp.device_states["fan_01"] = "ON"
    now = int(time.time())
    esp.last_switch_time["fan_01"] = now - 300
    esp.last_manual_command_time = now - 60  # Manual command 60s ago (< 600s hold)
    esp.manual_hold_sec = 600

    cmd = {
        "action_id": "act_test_p3_hold",
        "device_id": "fan_01",
        "requested_state": "OFF",
        "source": "server_proposal",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack = esp.handle_command_payload(cmd)
    assert ack["result"] == "blocked"
    assert ack["reason"] == "manual_override_active"

def test_safety_gate_point_5_min_switching_intervals():
    """
    Point 5: Min ON and Min OFF intervals prevent chatter.
    """
    esp = MockESP8266(room_id="room1")
    esp.mode = "AUTO"
    now = int(time.time())
    
    # 1. Min ON violated: fan_01 turned ON 30 seconds ago (min_on_time = 120s)
    esp.device_states["fan_01"] = "ON"
    esp.last_switch_time["fan_01"] = now - 30
    esp.min_on_time["fan_01"] = 120

    cmd = {
        "action_id": "act_test_p5_on",
        "device_id": "fan_01",
        "requested_state": "OFF",
        "source": "manual",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack = esp.handle_command_payload(cmd)
    assert ack["result"] == "blocked"
    assert ack["reason"] == "min_on_time_violated"

    # 2. Min OFF violated: fan_01 turned OFF 20 seconds ago (min_off_time = 60s)
    esp.device_states["fan_01"] = "OFF"
    esp.last_switch_time["fan_01"] = now - 20
    esp.min_off_time["fan_01"] = 60

    cmd2 = {
        "action_id": "act_test_p5_off",
        "device_id": "fan_01",
        "requested_state": "ON",
        "source": "manual",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack2 = esp.handle_command_payload(cmd2)
    assert ack2["result"] == "blocked"
    assert ack2["reason"] == "min_off_time_violated"

def test_safety_gate_point_6_duplicate_and_expired_commands():
    """
    Point 6: Commands that are duplicates or expired are rejected.
    """
    esp = MockESP8266(room_id="room1")
    esp.device_states["light_01"] = "OFF"
    esp.last_switch_time["light_01"] = int(time.time()) - 200
    now = int(time.time())

    # Expired command
    cmd_exp = {
        "action_id": "act_expired_01",
        "device_id": "light_01",
        "requested_state": "ON",
        "source": "manual",
        "issued_at": now - 120,
        "expires_at": now - 30
    }
    ack_exp = esp.handle_command_payload(cmd_exp)
    assert ack_exp["result"] == "expired"
    assert ack_exp["reason"] == "command_expired"

    # Valid command succeeds
    cmd_valid = {
        "action_id": "act_first_01",
        "device_id": "light_01",
        "requested_state": "ON",
        "source": "manual",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack_valid = esp.handle_command_payload(cmd_valid)
    assert ack_valid["result"] == "accepted"
    assert esp.device_states["light_01"] == "ON"

    # Replay of identical action_id rejected as duplicate
    ack_dup = esp.handle_command_payload(cmd_valid)
    assert ack_dup["result"] == "duplicate"
    assert ack_dup["reason"] == "duplicate_action_id"

def test_safety_gate_point_7_redundant_transition():
    """
    Point 7: Redundant state changes (ON->ON or OFF->OFF) are rejected.
    """
    esp = MockESP8266(room_id="room1")
    esp.device_states["light_01"] = "ON"
    esp.last_switch_time["light_01"] = int(time.time()) - 200
    now = int(time.time())

    cmd = {
        "action_id": "act_redundant_01",
        "device_id": "light_01",
        "requested_state": "ON",
        "source": "manual",
        "issued_at": now,
        "expires_at": now + 60
    }
    ack = esp.handle_command_payload(cmd)
    assert ack["result"] == "blocked"
    assert ack["reason"] == "redundant_transition"

def test_safety_gate_point_8_test_t13_ac_pc_power_off_safeguard():
    """
    Point 8 & Test T13: Power-OFF commands for AC and PC are blocked by default.
    """
    esp = MockESP8266(room_id="room1")
    esp.device_states["ac_01"] = "ON"
    esp.device_states["pc_01"] = "ON"
    now = int(time.time())
    esp.last_switch_time["ac_01"] = now - 500
    esp.last_switch_time["pc_01"] = now - 500

    # AC OFF blocked
    ack_ac = esp.handle_command_payload({
        "action_id": "act_t13_ac",
        "device_id": "ac_01",
        "requested_state": "OFF",
        "source": "manual",
        "issued_at": now,
        "expires_at": now + 60
    })
    assert ack_ac["result"] == "blocked"
    assert ack_ac["reason"] == "ac_pc_power_off_blocked_by_policy"
    assert esp.device_states["ac_01"] == "ON"

    # PC OFF blocked
    ack_pc = esp.handle_command_payload({
        "action_id": "act_t13_pc",
        "device_id": "pc_01",
        "requested_state": "OFF",
        "source": "manual",
        "issued_at": now,
        "expires_at": now + 60
    })
    assert ack_pc["result"] == "blocked"
    assert ack_pc["reason"] == "ac_pc_power_off_blocked_by_policy"
    assert esp.device_states["pc_01"] == "ON"
