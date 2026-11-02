-- Migration 002: Seed Data for DCEMS Database
-- Initializes default policies, configuration keys, and initial device records.

-- Default Device Policies (ALL start with auto_action_enabled = 0 for safety)
INSERT OR IGNORE INTO device_policies (
    device_id, auto_off_on_vacancy, vacancy_action_after_min, max_continuous_on_min,
    min_on_time_min, min_off_time_min, alert_enabled, auto_action_enabled, policy_version, updated_at
) VALUES 
('light_01', 1, 15, NULL, 2, 1, 1, 0, 1, strftime('%s', 'now')),
('fan_01',   1, 15, NULL, 2, 1, 1, 0, 1, strftime('%s', 'now')),
('ac_01',    0, 15, NULL, 5, 3, 1, 0, 1, strftime('%s', 'now')),
('pc_01',    0, 15, NULL, 0, 0, 1, 0, 1, strftime('%s', 'now'));

-- Core Config Table Defaults
INSERT OR IGNORE INTO config (key, value, changed_at, changed_by, history) VALUES
('vacancy_candidate_sec', '300', strftime('%s', 'now'), 'system_init', '[]'),
('vacancy_warning_sec', '600', strftime('%s', 'now'), 'system_init', '[]'),
('vacancy_action_sec', '900', strftime('%s', 'now'), 'system_init', '[]'),
('daylight_confirmation_sec', '180', strftime('%s', 'now'), 'system_init', '[]'),
('daylight_calibration_flag', 'false', strftime('%s', 'now'), 'system_init', '[]'),
('daylight_on_threshold', '350', strftime('%s', 'now'), 'system_init', '[]'),
('daylight_off_threshold', '450', strftime('%s', 'now'), 'system_init', '[]'),
('rapid_cycling_threshold', '4', strftime('%s', 'now'), 'system_init', '[]'),
('rapid_cycling_window_sec', '600', strftime('%s', 'now'), 'system_init', '[]'),
('manual_hold_sec', '600', strftime('%s', 'now'), 'system_init', '[]'),
('sensor_stale_sec', '60', strftime('%s', 'now'), 'system_init', '[]'),
('telemetry_interval_sec', '30', strftime('%s', 'now'), 'system_init', '[]');
