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

#endif // MQTT_COMM_H
