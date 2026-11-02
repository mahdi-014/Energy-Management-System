#include "rules.h"
#include "safety_gate.h"
#include "state.h"
#include "config.h"
#include "mqtt_comm.h"

// Local daylight tracking
static uint32_t daylightAboveThresholdStart = 0;
static bool daylightCalibrated = false;

void initRules() {
    daylightAboveThresholdStart = 0;
    daylightCalibrated = false;
}

void evaluateLocalRules(const SensorSnapshot* snapshot, uint32_t currentEpoch) {
    if (!snapshot || currentEpoch == 0) return;

    // Safety gate evaluation context
    SafetyGateContext ctx;
    ctx.controllerMode = getControllerMode();
    ctx.currentEpoch = currentEpoch;
    ctx.timeSynced = isTimeSynced();
    ctx.lastManualCmdEpoch = getLastManualCmdEpoch();
    ctx.manualHoldSec = MANUAL_HOLD_SEC;
    ctx.sensorDataValid = snapshot->valid;
    ctx.sensorSnapshotEpoch = snapshot->timestampUtc;
    ctx.sensorStaleThresholdSec = SENSOR_STALE_SEC;
    ctx.actionId = NULL;
    ctx.expiresAt = 0;
    ctx.isDuplicate = false;
    ctx.isServerProposal = false;

    // Rule 1: Confirmed Vacancy (>= 900s without motion)
    if (snapshot->lastMotionAt > 0 && currentEpoch >= snapshot->lastMotionAt) {
        uint32_t elapsedNoMotion = currentEpoch - snapshot->lastMotionAt;
        if (elapsedNoMotion >= VACANCY_CONFIRMED_SEC) {
            // Check light_01
            if (isDeviceON(DEV_LIGHT)) {
                SafetyGateResult r = validateAutoAction(DEV_LIGHT, "OFF", &ctx);
                if (r.allowed) {
                    setDeviceState(DEV_LIGHT, "OFF", "local_rule", "vacancy_confirmed_auto_off", currentEpoch);
                }
            }
            // Check fan_01
            if (isDeviceON(DEV_FAN)) {
                SafetyGateResult r = validateAutoAction(DEV_FAN, "OFF", &ctx);
                if (r.allowed) {
                    setDeviceState(DEV_FAN, "OFF", "local_rule", "vacancy_confirmed_auto_off", currentEpoch);
                }
            }
        }
    }

    // Rule 2: Confirmed Daylight (requires calibration flag true)
    if (daylightCalibrated && snapshot->ldrValid) {
        if (snapshot->ldrRaw >= DEFAULT_DAYLIGHT_OFF_THRESHOLD) {
            if (daylightAboveThresholdStart == 0) {
                daylightAboveThresholdStart = currentEpoch;
            } else if ((currentEpoch - daylightAboveThresholdStart) >= DAYLIGHT_CONFIRMATION_SEC) {
                if (isDeviceON(DEV_LIGHT)) {
                    SafetyGateResult r = validateAutoAction(DEV_LIGHT, "OFF", &ctx);
                    if (r.allowed) {
                        setDeviceState(DEV_LIGHT, "OFF", "local_rule", "daylight_confirmed_auto_off", currentEpoch);
                    }
                }
            }
        } else if (snapshot->ldrRaw < DEFAULT_DAYLIGHT_ON_THRESHOLD) {
            // Hysteresis reset
            daylightAboveThresholdStart = 0;
        }
    } else {
        daylightAboveThresholdStart = 0;
    }
}
