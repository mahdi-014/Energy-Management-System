import json
import sqlite3
import time
import pytest

from app.db import run_migrations, get_db_connection
from app.policy import (
    validate_server_proposal,
    issue_device_command,
    issue_mode_command,
    process_command_ack,
)

@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "policy_test.db"
    monkeypatch.setattr("app.config.settings.db_path", str(db_file))
    run_migrations(custom_path=str(db_file))
    conn = get_db_connection(custom_path=str(db_file))
    yield conn
    conn.close()

def test_validate_server_proposal_ac_pc_ineligible(test_db):
    res_ac = validate_server_proposal("ac_01", "OFF", custom_conn=test_db)
    assert not res_ac["allowed"]
    assert res_ac["reason"] == "device_alert_only_ineligible_for_auto_action"

    res_pc = validate_server_proposal("pc_01", "OFF", custom_conn=test_db)
    assert not res_pc["allowed"]
    assert res_pc["reason"] == "device_alert_only_ineligible_for_auto_action"

def test_validate_server_proposal_default_disabled(test_db):
    # Default commissioning policy has auto_action_enabled = 0
    res = validate_server_proposal("fan_01", "OFF", custom_conn=test_db)
    assert not res["allowed"]
    assert res["reason"] == "device_policy_auto_action_disabled"

def test_validate_server_proposal_enabled_and_manual_override(test_db):
    now = int(time.time())
    # Enable auto action for fan_01
    test_db.execute("UPDATE device_policies SET auto_action_enabled = 1 WHERE device_id = 'fan_01'")
    test_db.commit()

    res = validate_server_proposal("fan_01", "OFF", custom_conn=test_db)
    assert res["allowed"]
    assert res["reason"] == "policy_precheck_passed"

    # Now add active manual override
    test_db.execute("""
        INSERT INTO manual_overrides (override_id, device_id, start_time_utc, expiry_time_utc, reason, created_by)
        VALUES ('ovr_test', 'fan_01', ?, ?, 'testing', 'tester')
    """, (now - 10, now + 500))
    test_db.commit()

    res_ovr = validate_server_proposal("fan_01", "OFF", custom_conn=test_db)
    assert not res_ovr["allowed"]
    assert res_ovr["reason"] == "active_manual_override"

def test_issue_device_command_t13_safeguard(test_db):
    # T13: AC and PC power-off blocked by default
    res_ac = issue_device_command("ac_01", "OFF", source="manual", custom_conn=test_db)
    assert not res_ac["success"]
    assert res_ac["result"] == "blocked"
    assert res_ac["reason"] == "ac_pc_power_off_blocked_by_policy"

    res_pc = issue_device_command("pc_01", "OFF", source="manual", custom_conn=test_db)
    assert not res_pc["success"]
    assert res_pc["result"] == "blocked"
    assert res_pc["reason"] == "ac_pc_power_off_blocked_by_policy"

    # Verify audit entries recorded
    cur = test_db.cursor()
    cur.execute("SELECT * FROM control_actions WHERE device_id = 'ac_01'")
    row = cur.fetchone()
    assert row is not None
    assert row["policy_decision"] == "blocked"
    assert row["execution_result"] == "not_executed"

def test_issue_device_command_allowed_and_ack_processing(test_db):
    res = issue_device_command("light_01", "ON", source="manual", custom_conn=test_db)
    assert res["success"]
    act_id = res["action_id"]

    # Verify pending state in DB
    cur = test_db.cursor()
    cur.execute("SELECT * FROM control_actions WHERE action_id = ?", (act_id,))
    row = cur.fetchone()
    assert row is not None
    assert row["policy_decision"] == "allowed"
    assert row["execution_result"] == "not_executed"

    # Process ACK: accepted
    ack_payload = json.dumps({
        "action_id": act_id,
        "result": "accepted",
        "state": "ON",
        "ts": int(time.time())
    }).encode("utf-8")
    process_command_ack(ack_payload, custom_conn=test_db)

    cur.execute("SELECT execution_result FROM control_actions WHERE action_id = ?", (act_id,))
    row = cur.fetchone()
    assert row["execution_result"] == "success"

def test_issue_mode_command_lifecycle(test_db):
    res_man = issue_mode_command("MANUAL", source="manual", custom_conn=test_db)
    assert res_man["success"]
    assert res_man["mode"] == "MANUAL"

    res_auto = issue_mode_command("AUTO", source="manual", custom_conn=test_db)
    assert res_auto["success"]
    assert res_auto["mode"] == "AUTO"

    # Invalid mode rejected
    res_inv = issue_mode_command("TURBO", custom_conn=test_db)
    assert not res_inv["success"]
    assert res_inv["reason"] == "invalid_mode"
