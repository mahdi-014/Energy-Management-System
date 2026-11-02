#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

// ==========================================
// PHYSICAL PIN DEFINITIONS (NodeMCU ESP-12E)
// Grounded in verified prototype wiring
// ==========================================
#ifdef ARDUINO
#include <Arduino.h>
#define PIN_PIR       14  // D5 (GPIO14) - Active-HIGH Motion pulse
#define PIN_LDR       A0  // A0 (ADC0)   - Analog light level (0-1023)
#define PIN_DHT        0  // D3 (GPIO0)  - DHT11 bi-directional bus (boot-strap pullup)
#define PIN_RELAY_LT  16  // D0 (GPIO16) - Relay 1: light_01
#define PIN_RELAY_FN  12  // D6 (GPIO12) - Relay 2: fan_01
#define PIN_RELAY_PC  13  // D7 (GPIO13) - Relay 3: pc_01 (Alert-Only)
#define PIN_RELAY_AC  15  // D8 (GPIO15) - Relay 4: ac_01 (Alert-Only)
#define PIN_LCD_SDA    4  // D2 (GPIO4)  - I2C Data line
#define PIN_LCD_SCL    5  // D1 (GPIO5)  - I2C Clock line
#else
// Host testing mock pins
#define PIN_PIR       14
#define PIN_LDR       0
#define PIN_DHT        0
#define PIN_RELAY_LT  16
#define PIN_RELAY_FN  12
#define PIN_RELAY_PC  13
#define PIN_RELAY_AC  15
#define PIN_LCD_SDA    4
#define PIN_LCD_SCL    5
#define LOW            0
#define HIGH           1
#endif

// ==========================================
// RELAY ELECTRICAL LOGIC
// Active-LOW module verified from prototype
// ==========================================
#define RELAY_ACTIVE_LEVEL   LOW
#define RELAY_INACTIVE_LEVEL HIGH

// ==========================================
// TIMING CONSTANTS & SCHEDULING (Milliseconds)
// ==========================================
#define INTERVAL_LDR_MS          200UL   // Moving average sample rate
#define INTERVAL_DHT_MS         2500UL   // DHT11 minimum acquisition interval
#define INTERVAL_TELEMETRY_MS  30000UL   // Periodic MQTT snapshot publish
#define INTERVAL_HEARTBEAT_MS  30000UL   // MQTT online status heartbeat
#define INTERVAL_LCD_MS         5000UL   // LCD page cycle rate
#define LDR_FILTER_SAMPLES        10     // Moving average buffer size

// ==========================================
// SAFETY TIMING THRESHOLDS (Seconds)
// ==========================================
#define SENSOR_STALE_SEC          60     // Readings older than 60s marked invalid
#define VACANCY_CANDIDATE_SEC    300     // 5 minutes of no motion
#define VACANCY_WARNING_SEC      600     // 10 minutes of no motion
#define VACANCY_CONFIRMED_SEC    900     // 15 minutes of no motion
#define MANUAL_HOLD_SEC          600     // 10 minutes lockout after manual command
#define MIN_SWITCH_FAN_SEC       120     // 2 minutes minimum ON/OFF interval
#define MIN_SWITCH_LIGHT_SEC      60     // 1 minute minimum switching interval

// ==========================================
// SENSOR BOUNDS & VALIDATION RANGES
// ==========================================
#define DHT_TEMP_MIN_C          0.0f
#define DHT_TEMP_MAX_C         50.0f
#define DHT_HUM_MIN_PCT        20.0f
#define DHT_HUM_MAX_PCT        90.0f
#define LDR_ADC_MIN                0
#define LDR_ADC_MAX             1023

// Daylight rule hysteresis thresholds (TODO_CONFIRM via room calibration)
#define DEFAULT_DAYLIGHT_ON_THRESHOLD   350
#define DEFAULT_DAYLIGHT_OFF_THRESHOLD  450
#define DAYLIGHT_CONFIRMATION_SEC       180

// ==========================================
// CANONICAL DEVICE IDENTIFIERS
// ==========================================
#define DEV_LIGHT "light_01"
#define DEV_FAN   "fan_01"
#define DEV_AC    "ac_01"
#define DEV_PC    "pc_01"

// Compile-time device eligibility
struct DeviceConfig {
    const char* id;
    uint8_t pin;
    bool autoEligible;
    uint32_t minOnTimeSec;
    uint32_t minOffTimeSec;
};

// AC and PC are hard-locked to autoEligible = false
static const DeviceConfig DEVICE_TABLE[4] = {
    {DEV_LIGHT, PIN_RELAY_LT, true,  MIN_SWITCH_LIGHT_SEC, MIN_SWITCH_LIGHT_SEC},
    {DEV_FAN,   PIN_RELAY_FN, true,  MIN_SWITCH_FAN_SEC,   60},
    {DEV_AC,    PIN_RELAY_AC, false, 300,                  300}, // Alert-Only
    {DEV_PC,    PIN_RELAY_PC, false, 0,                    0}   // Alert-Only
};

#endif // CONFIG_H

