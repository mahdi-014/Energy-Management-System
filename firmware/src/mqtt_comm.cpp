#include "mqtt_comm.h"
#include "config.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

#ifdef ARDUINO
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <WiFiUdp.h>
#include <NTPClient.h>
#include <ArduinoJson.h>

static WiFiClient espClient;
static PubSubClient mqttClient(espClient);
static WiFiUDP ntpUDP;
// NTP client with 0 offset (UTC time)
static NTPClient timeClient(ntpUDP, "pool.ntp.org", 0, 60000);
#endif

static bool timeSynced = false;
static unsigned long lastMqttRetryMillis = 0;
static unsigned long lastHeartbeatMillis = 0;
static uint32_t messageSequence = 0;

void initMqttComm() {
#ifdef ARDUINO
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    mqttClient.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
    mqttClient.setBufferSize(512);

    timeClient.begin();
#endif
}

bool isTimeSynced() {
    return timeSynced;
}

uint32_t getCurrentEpochUtc() {
#ifdef ARDUINO
    if (timeSynced) {
        return (uint32_t)timeClient.getEpochTime();
    }
#endif
    return 0;
}

bool isMqttConnected() {
#ifdef ARDUINO
    return mqttClient.connected();
#else
    return false;
#endif
}

void publishStatusHeartbeat() {
#ifdef ARDUINO
    if (!mqttClient.connected()) return;

    StaticJsonDocument<256> doc;
    doc["status"] = "online";
    doc["ts"] = getCurrentEpochUtc();
    doc["firmware_version"] = "1.0.0";
    doc["uptime_sec"] = millis() / 1000UL;
    doc["room_id"] = ROOM_IDENTIFIER;

    char buffer[256];
    size_t n = serializeJson(doc, buffer);
    mqttClient.publish("dcems/" ROOM_IDENTIFIER "/status", buffer, true);
#endif
}

void publishSensorTelemetry(const SensorSnapshot& snapshot) {
#ifdef ARDUINO
    if (!mqttClient.connected()) return;

    StaticJsonDocument<512> doc;
    messageSequence++;
    
    char eventId[32];
    snprintf(eventId, sizeof(eventId), "evt_%lu_%u", snapshot.timestampUtc, messageSequence);

    doc["event_id"] = eventId;
    doc["ts"] = snapshot.timestampUtc;
    doc["room_id"] = ROOM_IDENTIFIER;
    doc["pir"] = snapshot.pirMotion;
    
    if (snapshot.ldrValid) {
        doc["ldr"] = snapshot.ldrRaw;
        doc["light_pct"] = snapshot.lightPct;
    } else {
        doc["ldr"] = nullptr;
        doc["light_pct"] = nullptr;
    }

    if (snapshot.dhtValid) {
        doc["temp"] = serialized(String(snapshot.temperatureC, 1));
        doc["hum"] = serialized(String(snapshot.humidityPct, 1));
    } else {
        doc["temp"] = nullptr;
        doc["hum"] = nullptr;
    }

    doc["last_motion_at"] = snapshot.lastMotionAt;
    doc["valid"] = snapshot.valid;
    doc["quality"] = snapshot.quality;

    char buffer[512];
    serializeJson(doc, buffer);
    mqttClient.publish("dcems/" ROOM_IDENTIFIER "/sensors", buffer, false);
#endif
}

void updateMqttComm() {
#ifdef ARDUINO
    unsigned long nowMs = millis();

    // Check Wi-Fi connection
    if (WiFi.status() == WL_CONNECTED) {
        // Sync time if not yet synced
        if (!timeSynced) {
            if (timeClient.update()) {
                if (timeClient.getEpochTime() > 1700000000) {
                    timeSynced = true;
                }
            }
        }

        // MQTT Connection management
        if (!mqttClient.connected()) {
            if (nowMs - lastMqttRetryMillis >= 5000UL || lastMqttRetryMillis == 0) {
                lastMqttRetryMillis = nowMs;

                String clientId = "dcems_esp8266_";
                clientId += String(ESP.getChipId(), HEX);

                // Configure Last Will and Testament
                StaticJsonDocument<128> lwtDoc;
                lwtDoc["status"] = "offline";
                lwtDoc["ts"] = getCurrentEpochUtc();
                lwtDoc["reason"] = "unexpected_disconnect";
                char lwtBuffer[128];
                serializeJson(lwtDoc, lwtBuffer);

                if (mqttClient.connect(
                        clientId.c_str(),
                        MQTT_USERNAME,
                        MQTT_PASSWORD,
                        "dcems/" ROOM_IDENTIFIER "/status",
                        1,
                        true,
                        lwtBuffer)) {
                    // Connected: immediately publish online heartbeat
                    publishStatusHeartbeat();
                    // Subscribe to command topic
                    mqttClient.subscribe("dcems/" ROOM_IDENTIFIER "/cmd", 1);
                }
            }
        } else {
            mqttClient.loop();

            // Periodic heartbeat every 30s
            if (nowMs - lastHeartbeatMillis >= INTERVAL_HEARTBEAT_MS || lastHeartbeatMillis == 0) {
                lastHeartbeatMillis = nowMs;
                publishStatusHeartbeat();
            }
        }
    }
#endif
}
