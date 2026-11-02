#include <string.h>
#include "state.h"
#include "config.h"
#include "mqtt_comm.h"

#ifdef ARDUINO
#include <Arduino.h>
#endif

static const char* currentMode = "AUTO";
static uint32_t globalLastManualCmdEpoch = 0;

static DeviceRuntimeState devices[4] = {
    {DEV_LIGHT, PIN_RELAY_LT, false, 0, 0},
    {DEV_FAN,   PIN_RELAY_FN, false, 0, 0},
    {DEV_AC,    PIN_RELAY_AC, false, 0, 0},
    {DEV_PC,    PIN_RELAY_PC, false, 0, 0}
};

void initState() {
    currentMode = "AUTO";
    globalLastManualCmdEpoch = 0;
    for (int i = 0; i < 4; i++) {
        devices[i].isON = false;
        devices[i].lastSwitchEpoch = 0;
        devices[i].lastManualCmdEpoch = 0;
#ifdef ARDUINO
        digitalWrite(devices[i].pin, RELAY_INACTIVE_LEVEL);
        pinMode(devices[i].pin, OUTPUT);
#endif
    }
}

void setControllerMode(const char* newMode) {
    if (newMode && (strcmp(newMode, "AUTO") == 0 || strcmp(newMode, "MANUAL") == 0)) {
        currentMode = (strcmp(newMode, "MANUAL") == 0) ? "MANUAL" : "AUTO";
    }
}

const char* getControllerMode() {
    return currentMode;
}

static int findDeviceIndex(const char* deviceId) {
    if (!deviceId) return -1;
    for (int i = 0; i < 4; i++) {
        if (strcmp(devices[i].id, deviceId) == 0) {
            return i;
        }
    }
    return -1;
}

const char* getDeviceState(const char* deviceId) {
    int idx = findDeviceIndex(deviceId);
    if (idx < 0) return "OFF";
    return devices[idx].isON ? "ON" : "OFF";
}

bool isDeviceON(const char* deviceId) {
    int idx = findDeviceIndex(deviceId);
    if (idx < 0) return false;
    return devices[idx].isON;
}

uint32_t getLastSwitchEpoch(const char* deviceId) {
    int idx = findDeviceIndex(deviceId);
    if (idx < 0) return 0;
    return devices[idx].lastSwitchEpoch;
}

uint32_t getLastManualCmdEpoch() {
    return globalLastManualCmdEpoch;
}

bool setDeviceState(
    const char* deviceId,
    const char* state,
    const char* source,
    const char* reasonCode,
    uint32_t ts
) {
    int idx = findDeviceIndex(deviceId);
    if (idx < 0 || !state) return false;

    bool targetON = (strcmp(state, "ON") == 0);
    // Ignore redundant transitions (e.g. OFF -> OFF)
    if (devices[idx].isON == targetON) {
        return false;
    }

    // Apply hardware relay output
    devices[idx].isON = targetON;
    devices[idx].lastSwitchEpoch = ts;

#ifdef ARDUINO
    digitalWrite(devices[idx].pin, targetON ? RELAY_ACTIVE_LEVEL : RELAY_INACTIVE_LEVEL);
#endif

    // Track manual hold
    if (source && strcmp(source, "manual") == 0) {
        devices[idx].lastManualCmdEpoch = ts;
        globalLastManualCmdEpoch = ts;
    }

    // Forward event to MQTT module
    publishStateChangeEvent(deviceId, state, source, reasonCode, currentMode, ts);
    publishDeviceStateSnapshot(currentMode, ts);

    return true;
}
