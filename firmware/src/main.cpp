#include <Arduino.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#include "config.h"
#include "sensors.h"
#include "mqtt_comm.h"

// 16x2 I2C Character LCD (PCF8574 address 0x27)
static LiquidCrystal_I2C lcd(0x27, 16, 2);

static unsigned long prevTelemetryMillis = 0;
static unsigned long prevLcdMillis = 0;
static bool lcdPageToggle = false;

void setup() {
    Serial.begin(115200);
    delay(50);
    Serial.println();
    Serial.println(F("========================================"));
    Serial.println(F("DC Office Energy Management System (DCEMS)"));
    Serial.println(F("Firmware Version: 1.0.0 (Phase 1 Monitor)"));
    Serial.println(F("========================================"));

    // ==========================================
    // CRITICAL SAFETY BOOT INVARIANT
    // Drive all relays to de-energized (OFF) state
    // BEFORE starting network or peripheral init.
    // Active-LOW logic: HIGH = Relay De-energized.
    // ==========================================
    digitalWrite(PIN_RELAY_LT, RELAY_INACTIVE_LEVEL);
    digitalWrite(PIN_RELAY_FN, RELAY_INACTIVE_LEVEL);
    digitalWrite(PIN_RELAY_PC, RELAY_INACTIVE_LEVEL);
    digitalWrite(PIN_RELAY_AC, RELAY_INACTIVE_LEVEL);
    pinMode(PIN_RELAY_LT, OUTPUT);
    pinMode(PIN_RELAY_FN, OUTPUT);
    pinMode(PIN_RELAY_PC, OUTPUT);
    pinMode(PIN_RELAY_AC, OUTPUT);

    // Initialize I2C LCD
    Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(F("DCEMS NodeMCU"));
    lcd.setCursor(0, 1);
    lcd.print(F("Booting safe..."));

    // Initialize sensors
    initSensors();

    // Initialize network & MQTT communications
    initMqttComm();

    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(F("DCEMS Room 1"));
    lcd.setCursor(0, 1);
    lcd.print(F("WiFi Connecting"));

    Serial.println(F("Relays initialized safe. Starting main loop..."));
}

void updateLcdDisplay(const SensorSnapshot& snap) {
    lcd.clear();
    if (!lcdPageToggle) {
        // Page 1: Environmental telemetry
        lcd.setCursor(0, 0);
        lcd.print(F("T:"));
        if (snap.dhtValid) {
            lcd.print(snap.temperatureC, 1);
            lcd.print(F("C "));
        } else {
            lcd.print(F("--.-C "));
        }
        lcd.print(F("H:"));
        if (snap.dhtValid) {
            lcd.print((int)snap.humidityPct);
            lcd.print(F("%"));
        } else {
            lcd.print(F("--%"));
        }

        lcd.setCursor(0, 1);
        lcd.print(F("L:"));
        if (snap.ldrValid) {
            lcd.print(snap.lightPct);
            lcd.print(F("% "));
        } else {
            lcd.print(F("--% "));
        }
        lcd.print(F("Mot:"));
        lcd.print((snap.pirMotion == 1) ? F("YES") : F("NO"));
    } else {
        // Page 2: System status
        lcd.setCursor(0, 0);
        lcd.print(F("Mode: AUTO"));
        lcd.setCursor(0, 1);
        lcd.print(F("MQTT: "));
        lcd.print(isMqttConnected() ? F("CONNECTED") : F("DISCONN"));
    }
    lcdPageToggle = !lcdPageToggle;
}

void loop() {
    unsigned long nowMs = millis();
    uint32_t nowEpoch = getCurrentEpochUtc();

    // 1. Maintain network & MQTT connection
    updateMqttComm();

    // 2. Sample sensors non-blockingly
    updateSensors(nowEpoch);

    // 3. Periodic telemetry publish every 30 seconds
    if (nowMs - prevTelemetryMillis >= INTERVAL_TELEMETRY_MS || prevTelemetryMillis == 0) {
        prevTelemetryMillis = nowMs;
        SensorSnapshot snap = getLatestSnapshot();
        publishSensorTelemetry(snap);
        Serial.print(F("[TELEMETRY] Sent snapshot. LDR: "));
        Serial.print(snap.ldrRaw);
        Serial.print(F(" Temp: "));
        Serial.print(snap.temperatureC);
        Serial.print(F(" PIR: "));
        Serial.println(snap.pirMotion);
    }

    // 4. Update LCD display every 5 seconds
    if (nowMs - prevLcdMillis >= INTERVAL_LCD_MS || prevLcdMillis == 0) {
        prevLcdMillis = nowMs;
        SensorSnapshot snap = getLatestSnapshot();
        updateLcdDisplay(snap);
    }
}
