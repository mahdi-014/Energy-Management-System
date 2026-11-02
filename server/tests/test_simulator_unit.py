import pytest
from simulator.mock_esp import MockESP8266

def test_simulator_initial_state():
    mock = MockESP8266()
    assert mock.mode == "AUTO"
    assert mock.device_states["light_01"] == "OFF"
    assert mock.device_states["fan_01"] == "OFF"
    assert mock.device_states["ac_01"] == "OFF"
    assert mock.device_states["pc_01"] == "OFF"
    
    # AC and PC auto eligibility must be False
    assert mock.auto_eligible["light_01"] is True
    assert mock.auto_eligible["fan_01"] is True
    assert mock.auto_eligible["ac_01"] is False
    assert mock.auto_eligible["pc_01"] is False

def test_simulator_offline_queue_and_data_gap():
    mock = MockESP8266()
    mock.is_connected = False
    
    # Enqueue 50 events (buffer capacity)
    for i in range(50):
        mock._enqueue_event("sensor", {"sample_num": i})
        
    assert len(mock.event_queue) == 50
    assert mock.data_gap_occurred is False
    assert mock.gap_dropped_count == 0
    
    # Enqueue 5 additional events -> queue remains at 50, drops 5 oldest, data_gap flagged
    for i in range(50, 55):
        mock._enqueue_event("sensor", {"sample_num": i})
        
    assert len(mock.event_queue) == 50
    assert mock.data_gap_occurred is True
    assert mock.gap_dropped_count == 5
    # The oldest event in queue should now be sample_num 5
    assert mock.event_queue[0][1]["sample_num"] == 5

