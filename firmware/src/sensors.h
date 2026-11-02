#ifndef SENSORS_H
#define SENSORS_H

#include <stdint.h>
#include <stdbool.h>

struct SensorSnapshot {
    uint32_t timestampUtc;
    int pirMotion;          // 0 or 1
    int ldrRaw;             // 0 to 1023
    int lightPct;           // 0 to 100%
    float temperatureC;     // Celsius
    float humidityPct;      // %
    uint32_t lastMotionAt;  // Epoch seconds
    bool dhtValid;
    bool ldrValid;
    bool valid;             // Overall validity
    const char* quality;    // "ok", "degraded", "fault"
};

void initSensors();
void updateSensors(uint32_t currentEpochSec);
SensorSnapshot getLatestSnapshot();
bool isSensorDataFresh(uint32_t currentEpochSec);

#endif // SENSORS_H
