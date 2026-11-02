-- Migration 001: Initial Schema for DCEMS SQLite Database
-- Invariant: UTC timestamps stored as ISO-8601 strings or epoch integers.
-- Invariant: Missing or corrupted sensor data stored as NULL, NEVER 0.

PRAGMA foreign_keys = ON;

-- 1. Sensor Samples Table
CREATE TABLE IF NOT EXISTS sensor_samples (
    sample_id TEXT PRIMARY KEY,
    room_id TEXT NOT NULL,
    timestamp_utc INTEGER NOT NULL,          -- Server receipt time in epoch seconds
    device_ts INTEGER,                       -- Device reported epoch seconds
    pir_motion INTEGER CHECK (pir_motion IN (0, 1) OR pir_motion IS NULL),
    ldr_raw INTEGER CHECK (ldr_raw >= 0 AND ldr_raw <= 1023 OR ldr_raw IS NULL),
    ambient_light_level REAL,                -- Calibrated illuminance / %
    temperature_c REAL CHECK ((temperature_c >= 0.0 AND temperature_c <= 60.0) OR temperature_c IS NULL),
    humidity_pct REAL CHECK ((humidity_pct >= 10.0 AND humidity_pct <= 100.0) OR humidity_pct IS NULL),
    last_motion_at INTEGER,                  -- Epoch seconds of latest motion
    occupancy_state TEXT CHECK (occupancy_state IN ('occupied_recently', 'vacancy_candidate', 'vacant_confirmed', 'unknown')),
    sensor_quality TEXT CHECK (sensor_quality IN ('ok', 'degraded', 'fault'))
);

CREATE INDEX IF NOT EXISTS idx_sensor_samples_ts ON sensor_samples(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_sensor_samples_room ON sensor_samples(room_id, timestamp_utc);

-- 2. Device State Events Table
CREATE TABLE IF NOT EXISTS device_state_events (
    event_id TEXT PRIMARY KEY,
    timestamp_utc INTEGER NOT NULL,
    device_id TEXT NOT NULL CHECK (device_id IN ('light_01', 'fan_01', 'ac_01', 'pc_01')),
    requested_state TEXT NOT NULL CHECK (requested_state IN ('ON', 'OFF')),
    state_source TEXT NOT NULL CHECK (state_source IN ('manual', 'local_rule', 'server_proposal')),
    reason_code TEXT NOT NULL,
    controller_mode TEXT NOT NULL CHECK (controller_mode IN ('AUTO', 'MANUAL')),
    command_status TEXT NOT NULL CHECK (command_status IN ('pending', 'applied', 'failed', 'unknown')),
    observed_state TEXT NOT NULL CHECK (observed_state IN ('assumed', 'unknown', 'confirmed'))
);

CREATE INDEX IF NOT EXISTS idx_device_state_events_device ON device_state_events(device_id, timestamp_utc);

-- 3. Anomaly Events Table
CREATE TABLE IF NOT EXISTS anomaly_events (
    anomaly_id TEXT PRIMARY KEY,
    timestamp_utc INTEGER NOT NULL,
    device_id TEXT CHECK (device_id IN ('light_01', 'fan_01', 'ac_01', 'pc_01') OR device_id IS NULL),
    anomaly_type TEXT NOT NULL CHECK (anomaly_type IN ('vacancy_runtime', 'daylight_waste', 'long_runtime', 'rapid_cycling', 'sensor_issue')),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'high', 'diagnostic')),
    detector_type TEXT NOT NULL CHECK (detector_type IN ('rule', 'statistical')),
    observed_value TEXT,                    -- Numeric or JSON value
    threshold_value TEXT,                   -- Configured or statistical threshold
    evidence TEXT,                          -- JSON string with context readings
    status TEXT NOT NULL CHECK (status IN ('open', 'acknowledged', 'resolved', 'false_positive')),
    resolved_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_anomaly_events_status ON anomaly_events(status, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_anomaly_events_device ON anomaly_events(device_id, timestamp_utc);

-- 4. Control Actions Audit Table
CREATE TABLE IF NOT EXISTS control_actions (
    action_id TEXT PRIMARY KEY,
    timestamp_utc INTEGER NOT NULL,
    device_id TEXT NOT NULL CHECK (device_id IN ('light_01', 'fan_01', 'ac_01', 'pc_01')),
    trigger_anomaly_id TEXT REFERENCES anomaly_events(anomaly_id),
    proposed_state TEXT NOT NULL CHECK (proposed_state IN ('ON', 'OFF')),
    policy_decision TEXT NOT NULL CHECK (policy_decision IN ('allowed', 'blocked')),
    decision_reason TEXT NOT NULL,
    policy_version INTEGER NOT NULL DEFAULT 1,
    execution_result TEXT NOT NULL CHECK (execution_result IN ('success', 'failed', 'expired', 'not_executed'))
);

CREATE INDEX IF NOT EXISTS idx_control_actions_device ON control_actions(device_id, timestamp_utc);

-- 5. Device Policies Table (Versioned)
CREATE TABLE IF NOT EXISTS device_policies (
    device_id TEXT PRIMARY KEY CHECK (device_id IN ('light_01', 'fan_01', 'ac_01', 'pc_01')),
    auto_off_on_vacancy INTEGER NOT NULL DEFAULT 0,
    vacancy_action_after_min INTEGER NOT NULL DEFAULT 15,
    max_continuous_on_min INTEGER,          -- NULL means unconfigured
    min_on_time_min INTEGER NOT NULL DEFAULT 2,
    min_off_time_min INTEGER NOT NULL DEFAULT 1,
    alert_enabled INTEGER NOT NULL DEFAULT 1,
    auto_action_enabled INTEGER NOT NULL DEFAULT 0, -- Default FALSE for safety
    policy_version INTEGER NOT NULL DEFAULT 1,
    updated_at INTEGER NOT NULL
);

-- 6. Manual Overrides Table
CREATE TABLE IF NOT EXISTS manual_overrides (
    override_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL CHECK (device_id IN ('light_01', 'fan_01', 'ac_01', 'pc_01')),
    start_time_utc INTEGER NOT NULL,
    expiry_time_utc INTEGER NOT NULL,
    reason TEXT,
    created_by TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_manual_overrides_expiry ON manual_overrides(device_id, expiry_time_utc);

-- 7. Runtime Sessions Table
CREATE TABLE IF NOT EXISTS runtime_sessions (
    session_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL CHECK (device_id IN ('light_01', 'fan_01', 'ac_01', 'pc_01')),
    start_time_utc INTEGER NOT NULL,
    end_time_utc INTEGER,                   -- NULL if still open
    end_known INTEGER NOT NULL DEFAULT 1,   -- 0 if interrupted by reboot/outage
    estimated_duration_sec INTEGER          -- tOFF - tON
);

CREATE INDEX IF NOT EXISTS idx_runtime_sessions_device ON runtime_sessions(device_id, start_time_utc);

-- 8. Configuration Key-Value Table with Audit History
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    changed_at INTEGER NOT NULL,
    changed_by TEXT NOT NULL,
    history TEXT                            -- JSON array of previous revisions
);

-- 9. Audit Log Table
CREATE TABLE IF NOT EXISTS audit_log (
    log_id TEXT PRIMARY KEY,
    timestamp_utc INTEGER NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('login', 'command', 'settings_change', 'anomaly_action')),
    actor TEXT NOT NULL,
    details TEXT                            -- JSON payload
);

CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(timestamp_utc);

-- 10. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'viewer')),
    created_at INTEGER NOT NULL
);

