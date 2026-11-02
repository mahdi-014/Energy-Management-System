#include "sensors.h"
#include "config.h"

#ifdef ARDUINO
#include <Arduino.h>
#include <DHT.h>

static DHT dht(PIN_DHT, DHT11);
#endif

// Moving-average filter state for LDR
static int ldrSamples[LDR_FILTER_SAMPLES];
static uint8_t ldrIndex = 0;
static long ldrSum = 0;
static int currentLdrFiltered = 500;

// State tracking
static SensorSnapshot latestSnapshot = {
    0, 0, 500, 50, 26.0f, 60.0f, 0, false, false, false, "fault"
};

static unsigned long lastLdrMillis = 0;
static unsigned long lastDhtMillis = 0;
static unsigned long lastSensorSampleMillis = 0;

void initSensors() {
#ifdef ARDUINO
    pinMode(PIN_PIR, INPUT);
    pinMode(PIN_LDR, INPUT);
    dht.begin();

    // Prime LDR moving-average buffer
    int initialAdc = analogRead(PIN_LDR);
    ldrSum = 0;
    for (uint8_t i = 0; i < LDR_FILTER_SAMPLES; i++) {
        ldrSamples[i] = initialAdc;
        ldrSum += initialAdc;
    }
    currentLdrFiltered = initialAdc;
#endif
    lastLdrMillis = 0;
    lastDhtMillis = 0;
    lastSensorSampleMillis = 0;
}

void updateSensors(uint32_t currentEpochSec) {
    unsigned long nowMs = 0;
#ifdef ARDUINO
    nowMs = millis();

    // 1. LDR 10-sample moving average filter (every 200 ms)
    if (nowMs - lastLdrMillis >= INTERVAL_LDR_MS || lastLdrMillis == 0) {
        lastLdrMillis = nowMs;
        int raw = analogRead(PIN_LDR);
        if (raw >= LDR_ADC_MIN && raw <= LDR_ADC_MAX) {
            ldrSum -= ldrSamples[ldrIndex];
            ldrSamples[ldrIndex] = raw;
            ldrSum += raw;
            ldrIndex = (ldrIndex + 1) % LDR_FILTER_SAMPLES;
            currentLdrFiltered = (int)(ldrSum / LDR_FILTER_SAMPLES);
            
            latestSnapshot.ldrRaw = currentLdrFiltered;
            // Map 0-1023 to 0-100% brightness
            latestSnapshot.lightPct = (int)map(currentLdrFiltered, 0, 1023, 0, 100);
            if (latestSnapshot.lightPct < 0) latestSnapshot.lightPct = 0;
            if (latestSnapshot.lightPct > 100) latestSnapshot.lightPct = 100;
            latestSnapshot.ldrValid = true;
        } else {
            latestSnapshot.ldrValid = false;
        }
    }

    // 2. DHT11 periodic acquisition (every 2500 ms)
    if (nowMs - lastDhtMillis >= INTERVAL_DHT_MS || lastDhtMillis == 0) {
        lastDhtMillis = nowMs;
        float t = dht.readTemperature();
        float h = dht.readHumidity();

        if (!isnan(t) && !isnan(h) &&
            t >= DHT_TEMP_MIN_C && t <= DHT_TEMP_MAX_C &&
            h >= DHT_HUM_MIN_PCT && h <= DHT_HUM_MAX_PCT) {
            latestSnapshot.temperatureC = t;
            latestSnapshot.humidityPct = h;
            latestSnapshot.dhtValid = true;
        } else {
            latestSnapshot.dhtValid = false;
        }
    }

    // 3. PIR motion detection (continuous polling to prevent missing quick pulses)
    int pirReading = digitalRead(PIN_PIR);
    latestSnapshot.pirMotion = (pirReading == HIGH) ? 1 : 0;
    if (latestSnapshot.pirMotion == 1) {
        latestSnapshot.lastMotionAt = currentEpochSec;
    }
#else
    // Host mock updates
    latestSnapshot.ldrValid = true;
    latestSnapshot.dhtValid = true;
    latestSnapshot.pirMotion = 0;
#endif

    latestSnapshot.timestampUtc = currentEpochSec;
    lastSensorSampleMillis = nowMs;

    // Evaluate overall quality
    if (latestSnapshot.dhtValid && latestSnapshot.ldrValid) {
        latestSnapshot.valid = true;
        latestSnapshot.quality = "ok";
    } else if (latestSnapshot.dhtValid || latestSnapshot.ldrValid) {
        latestSnapshot.valid = false;
        latestSnapshot.quality = "degraded";
    } else {
        latestSnapshot.valid = false;
        latestSnapshot.quality = "fault";
    }
}

SensorSnapshot getLatestSnapshot() {
    return latestSnapshot;
}

bool isSensorDataFresh(uint32_t currentEpochSec) {
    if (latestSnapshot.timestampUtc == 0) return false;
    return (currentEpochSec >= latestSnapshot.timestampUtc) &&
           ((currentEpochSec - latestSnapshot.timestampUtc) <= SENSOR_STALE_SEC);
}

