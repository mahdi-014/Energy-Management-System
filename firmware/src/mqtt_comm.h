#ifndef MQTT_COMM_H
#define MQTT_COMM_H

#include <stdint.h>
#include <stdbool.h>
#include "sensors.h"

void initMqttComm();
void updateMqttComm();
bool isMqttConnected();
bool isTimeSynced();
uint32_t getCurrentEpochUtc();

void publishSensorTelemetry(const SensorSnapshot& snapshot);
void publishStatusHeartbeat();

void publishDeviceStateSnapshot(const char* mode, uint32_t ts);
void publishStateChangeEvent(
    const char* deviceId,
    const char* requestedState,
    const char* source,
    const char* reasonCode,
    const char* controllerMode,
    uint32_t ts
);

#endif // MQTT_COMM_H
