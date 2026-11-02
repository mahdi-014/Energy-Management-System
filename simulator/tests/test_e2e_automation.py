import json
import time
import pytest

from simulator.mock_esp import MockESP8266
from app.db import run_migrations, get_db_connection
from app.policy import (
    validate_server_proposal,
    issue_device_command,
    process_command_ack
)

def test_tc12_e2e_proposal_gate_relay_ack_cycle(tmp_path, monkeypatch):
    """
    TC-12: Full proposal -> safety gate -> relay transition -> ACK cycle
    1. Commissioning: enable auto_action_enabled for fan_01
    2. Server detects vacancy candidate and proposes fan_01 OFF
    3. Server validates proposal against device policy
    4. Command issued with unique action_id and TTL
    5. Mock ESP receives command payload via its command handler
    6. Mock ESP 8-point safety gate evaluates and accepts
    7. Mock ESP switches relay state from ON to OFF
    8. Mock ESP generates and publishes ACK
    9. Server processes ACK and updates control_actions record to success
    10. Duplicate replay is rejected with 'duplicate_action_id'
    11. Expired command is rejected with 'command_expired'
    """
    db_file = tmp_path / "tc12_test.db"
    monkeypatch.setattr("app.config.settings.db_path", str(db_file))
    run_migrations(custom_path=str(db_file))
    conn = get_db_connection(custom_path=str(db_file))

    # 1. Commission fan_01 policy: enable auto action
    conn.execute("UPDATE device_policies SET auto_action_enabled = 1 WHERE device_id = 'fan_01'")
    conn.commit()

    # 2. Setup Mock ESP
    esp = MockESP8266(room_id="room1")
    esp.mode = "AUTO"
    esp.device_states["fan_01"] = "ON"
    now = int(time.time())
    esp.last_switch_time["fan_01"] = now - 300  # ON for 5 minutes (> min_on_time)

    # 3. Server validates proposal
    val = validate_server_proposal("fan_01", "OFF", custom_conn=conn)
    assert val["allowed"] is True
    assert val["reason"] == "policy_precheck_passed"

    # 4. Issue command from server
    cmd_res = issue_device_command(
        device_id="fan_01",
        requested_state="OFF",
        source="server_proposal",
        reason="vacancy_confirmed_15min",
        ttl_sec=60,
        custom_conn=conn
    )
    assert cmd_res["success"] is True
    action_id = cmd_res["action_id"]

    # 5. Build payload as received over MQTT
    cmd_payload = {
        "action_id": action_id,
        "command_type": "device_command",
        "device_id": "fan_01",
        "requested_state": "OFF",
        "issued_at": cmd_res["issued_at"],
        "expires_at": cmd_res["expires_at"],
        "reason": "vacancy_confirmed_15min",
        "policy_version": cmd_res["policy_version"],
        "source": "server_proposal"
    }

    # 6 & 7. ESP safety gate evaluates and executes relay transition
    ack = esp.handle_command_payload(cmd_payload)
    assert ack["result"] == "accepted"
    assert ack["action_id"] == action_id
    assert esp.device_states["fan_01"] == "OFF"

    # 8 & 9. Server ingests ACK
    ack_bytes = json.dumps(ack).encode("utf-8")
    process_command_ack(ack_bytes, custom_conn=conn)

    cur = conn.cursor()
    cur.execute("SELECT execution_result FROM control_actions WHERE action_id = ?", (action_id,))
    row = cur.fetchone()
    assert row is not None
    assert row["execution_result"] == "success"

    # 10. Replay identical command -> rejected as duplicate
    dup_ack = esp.handle_command_payload(cmd_payload)
    assert dup_ack["result"] == "duplicate"
    assert dup_ack["reason"] == "duplicate_action_id"

    # 11. Command with expired TTL -> rejected
    exp_payload = {
        "action_id": "act_expired_tc12",
        "command_type": "device_command",
        "device_id": "fan_01",
        "requested_state": "ON",
        "issued_at": now - 120,
        "expires_at": now - 30,
        "source": "server_proposal"
    }
    exp_ack = esp.handle_command_payload(exp_payload)
    assert exp_ack["result"] == "expired"
    assert exp_ack["reason"] == "command_expired"

    conn.close()
