#ifndef STATE_H
#define STATE_H

#include <stdint.h>
#include <stdbool.h>

struct DeviceRuntimeState {
    const char* id;
    uint8_t pin;
    bool isON;
    uint32_t lastSwitchEpoch;
    uint32_t lastManualCmdEpoch;
};

void initState();
void setControllerMode(const char* newMode);
const char* getControllerMode();

bool setDeviceState(
    const char* deviceId,
    const char* state,
    const char* source,
    const char* reasonCode,
    uint32_t ts
);

const char* getDeviceState(const char* deviceId);
uint32_t getLastSwitchEpoch(const char* deviceId);
uint32_t getLastManualCmdEpoch();
bool isDeviceON(const char* deviceId);

#endif // STATE_H
