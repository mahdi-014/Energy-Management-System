#include <string.h>
#include <stdio.h>
#include "mqtt_comm.h"
#include "config.h"
#include "state.h"
#include "safety_gate.h"
#include "rules.h"
#include "sensors.h"

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
static NTPClient timeClient(ntpUDP, "pool.ntp.org", 0, 60000);
#endif

// Bounded RAM queue for offline resilience (max 50 events)
#define MAX_QUEUE_SIZE 50
struct QueueItem {
    char topic[48];
    char payload[256];
    bool retained;
};

static QueueItem eventQueue[MAX_QUEUE_SIZE];
static uint8_t queueHead = 0;
static uint8_t queueCount = 0;

static bool dataGapOccurred = false;
static uint32_t gapStartTs = 0;
static uint16_t droppedEventsCount = 0;

static bool timeSynced = false;
static unsigned long lastMqttRetryMillis = 0;
static unsigned long lastHeartbeatMillis = 0;
static uint32_t messageSequence = 0;

static void enqueueEvent(const char* topic, const char* payload, bool retained) {
    if (queueCount >= MAX_QUEUE_SIZE) {
        // Queue is full: drop oldest event and record data gap
        if (!dataGapOccurred) {
            dataGapOccurred = true;
            gapStartTs = getCurrentEpochUtc();
        }
        queueHead = (queueHead + 1) % MAX_QUEUE_SIZE;
        queueCount--;
        droppedEventsCount++;
    }

    uint8_t writeIdx = (queueHead + queueCount) % MAX_QUEUE_SIZE;
    strncpy(eventQueue[writeIdx].topic, topic, sizeof(eventQueue[writeIdx].topic) - 1);
    eventQueue[writeIdx].topic[sizeof(eventQueue[writeIdx].topic) - 1] = '\0';

    strncpy(eventQueue[writeIdx].payload, payload, sizeof(eventQueue[writeIdx].payload) - 1);
    eventQueue[writeIdx].payload[sizeof(eventQueue[writeIdx].payload) - 1] = '\0';

    eventQueue[writeIdx].retained = retained;
    queueCount++;
}

static void flushEventQueue() {
#ifdef ARDUINO
    while (queueCount > 0 && mqttClient.connected()) {
        QueueItem& item = eventQueue[queueHead];
        mqttClient.publish(item.topic, item.payload, item.retained);
        queueHead = (queueHead + 1) % MAX_QUEUE_SIZE;
        queueCount--;
    }

    if (dataGapOccurred && mqttClient.connected()) {
        StaticJsonDocument<256> doc;
        char gapId[32];
        uint32_t now = getCurrentEpochUtc();
        snprintf(gapId, sizeof(gapId), "gap_%lu", now);

        doc["event_id"] = gapId;
        doc["ts"] = now;
        doc["type"] = "data_gap";
        doc["gap_start_ts"] = gapStartTs;
        doc["gap_end_ts"] = now;
        doc["dropped_events_count"] = droppedEventsCount;
        doc["reason"] = "ram_queue_overflow_during_disconnect";

        char buffer[256];
        serializeJson(doc, buffer);
        mqttClient.publish("dcems/" ROOM_IDENTIFIER "/events", buffer, false);

        dataGapOccurred = false;
        droppedEventsCount = 0;
        gapStartTs = 0;
    }
}

static void onMqttMessage(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, "dcems/" ROOM_IDENTIFIER "/cmd") != 0) return;

    StaticJsonDocument<512> doc;
    DeserializationError err = deserializeJson(doc, payload, length);
    if (err) return;

    uint32_t now = getCurrentEpochUtc();
    const char* actionId = doc["action_id"] | "";
    const char* cmdType = doc["command_type"] | "";
    const char* source = doc["source"] | "manual";

    // 1. Controller Mode Change
    if (strcmp(cmdType, "set_mode") == 0 || doc.containsKey("mode")) {
        const char* mode = doc["mode"] | "";
        if (strcmp(mode, "AUTO") == 0 || strcmp(mode, "MANUAL") == 0) {
            setControllerMode(mode);
            publishDeviceStateSnapshot(mode, now);
            StaticJsonDocument<256> ackDoc;
            ackDoc["action_id"] = actionId;
            ackDoc["result"] = "accepted";
            ackDoc["ts"] = now;
            char ackBuf[256];
            serializeJson(ackDoc, ackBuf);
            mqttClient.publish("dcems/" ROOM_IDENTIFIER "/ack", ackBuf, false);
        } else {
            StaticJsonDocument<256> ackDoc;
            ackDoc["action_id"] = actionId;
            ackDoc["result"] = "blocked";
            ackDoc["reason"] = "invalid_mode";
            ackDoc["ts"] = now;
            char ackBuf[256];
            serializeJson(ackDoc, ackBuf);
            mqttClient.publish("dcems/" ROOM_IDENTIFIER "/ack", ackBuf, false);
        }
        return;
    }

    // 2. Device Control Command
    const char* deviceId = doc["device_id"] | "";
    const char* requestedState = doc["requested_state"] | "";
    uint32_t expiresAt = doc["expires_at"] | 0;

    SensorSnapshot snap = getLatestSnapshot();
    SafetyGateContext ctx;
    ctx.controllerMode = getControllerMode();
    ctx.currentEpoch = now;
    ctx.timeSynced = isTimeSynced();
    ctx.lastManualCmdEpoch = getLastManualCmdEpoch();
    ctx.manualHoldSec = MANUAL_HOLD_SEC;
    ctx.sensorDataValid = snap.valid;
    ctx.sensorSnapshotEpoch = snap.timestampUtc;
    ctx.sensorStaleThresholdSec = SENSOR_STALE_SEC;
    ctx.actionId = actionId;
    ctx.expiresAt = expiresAt;
    ctx.isDuplicate = isDuplicateActionId(actionId);
    ctx.isServerProposal = (strcmp(source, "server_proposal") == 0);

    SafetyGateResult gateRes;
    if (ctx.isServerProposal) {
        gateRes = validateAutoAction(deviceId, requestedState, &ctx);
    } else {
        gateRes = validateManualCommand(deviceId, requestedState, &ctx);
    }

    StaticJsonDocument<256> ackDoc;
    ackDoc["action_id"] = actionId;
    ackDoc["device_id"] = deviceId;
    ackDoc["ts"] = now;

    if (gateRes.allowed) {
        const char* reason = doc["reason"] | "cmd";
        setDeviceState(deviceId, requestedState, source, reason, now);
        recordActionId(actionId);
        ackDoc["result"] = "accepted";
        ackDoc["state"] = requestedState;
    } else {
        ackDoc["result"] = (strcmp(gateRes.reasonCode, "command_expired") == 0) ? "expired" :
                           (strcmp(gateRes.reasonCode, "duplicate_action_id") == 0) ? "duplicate" : "blocked";
        ackDoc["reason"] = gateRes.reasonCode;
    }

    char ackBuf[256];
    serializeJson(ackDoc, ackBuf);
    mqttClient.publish("dcems/" ROOM_IDENTIFIER "/ack", ackBuf, false);
}
#endif
}

void initMqttComm() {
#ifdef ARDUINO
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    mqttClient.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
    mqttClient.setBufferSize(512);
    mqttClient.setCallback(onMqttMessage);

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
    serializeJson(doc, buffer);
    mqttClient.publish("dcems/" ROOM_IDENTIFIER "/status", buffer, true);
#endif
}

void publishDeviceStateSnapshot(const char* mode, uint32_t ts) {
    char buffer[256];
#ifdef ARDUINO
    StaticJsonDocument<256> doc;
    doc["ts"] = ts;
    doc["mode"] = mode;
    JsonObject devs = doc.createNestedObject("devices");
    devs["light_01"] = getDeviceState("light_01");
    devs["fan_01"] = getDeviceState("fan_01");
    devs["ac_01"] = getDeviceState("ac_01");
    devs["pc_01"] = getDeviceState("pc_01");
    doc["observed_state"] = "assumed";

    serializeJson(doc, buffer);

    if (mqttClient.connected()) {
        mqttClient.publish("dcems/" ROOM_IDENTIFIER "/state", buffer, true);
    } else {
        enqueueEvent("dcems/" ROOM_IDENTIFIER "/state", buffer, true);
    }
#endif
}

void publishStateChangeEvent(
    const char* deviceId,
    const char* requestedState,
    const char* source,
    const char* reasonCode,
    const char* controllerMode,
    uint32_t ts
) {
    char buffer[256];
#ifdef ARDUINO
    StaticJsonDocument<256> doc;
    messageSequence++;
    char eventId[32];
    snprintf(eventId, sizeof(eventId), "evt_%lu_%u", ts, messageSequence);

    doc["event_id"] = eventId;
    doc["timestamp_utc"] = ts;
    doc["device_id"] = deviceId;
    doc["requested_state"] = requestedState;
    doc["state_source"] = source;
    doc["reason_code"] = reasonCode;
    doc["controller_mode"] = controllerMode;
    doc["command_status"] = "applied";
    doc["observed_state"] = "assumed";

    serializeJson(doc, buffer);

    if (mqttClient.connected()) {
        mqttClient.publish("dcems/" ROOM_IDENTIFIER "/events", buffer, false);
    } else {
        enqueueEvent("dcems/" ROOM_IDENTIFIER "/events", buffer, false);
    }
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

    if (WiFi.status() == WL_CONNECTED) {
        if (!timeSynced) {
            if (timeClient.update()) {
                if (timeClient.getEpochTime() > 1700000000) {
                    timeSynced = true;
                }
            }
        }

        if (!mqttClient.connected()) {
            if (nowMs - lastMqttRetryMillis >= 5000UL || lastMqttRetryMillis == 0) {
                lastMqttRetryMillis = nowMs;

                String clientId = "dcems_esp8266_";
                clientId += String(ESP.getChipId(), HEX);

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
                    publishStatusHeartbeat();
                    mqttClient.subscribe("dcems/" ROOM_IDENTIFIER "/cmd", 1);
                    // Flush offline queued events
                    flushEventQueue();
                }
            }
        } else {
            mqttClient.loop();

            if (nowMs - lastHeartbeatMillis >= INTERVAL_HEARTBEAT_MS || lastHeartbeatMillis == 0) {
                lastHeartbeatMillis = nowMs;
                publishStatusHeartbeat();
            }
        }
    }
#endif
}
