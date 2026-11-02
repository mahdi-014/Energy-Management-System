#include <string.h>
#include "safety_gate.h"
#include "config.h"
#include "state.h"

#define ACTION_ID_BUF_SIZE 32
#define ACTION_ID_STR_LEN  48

static char actionIdRingBuffer[ACTION_ID_BUF_SIZE][ACTION_ID_STR_LEN];
static int ringHead = 0;
static int ringCount = 0;

void initActionIdBuffer() {
    ringHead = 0;
    ringCount = 0;
    for (int i = 0; i < ACTION_ID_BUF_SIZE; i++) {
        actionIdRingBuffer[i][0] = '\0';
    }
}

bool isDuplicateActionId(const char* actionId) {
    if (!actionId || actionId[0] == '\0') return false;
    for (int i = 0; i < ringCount; i++) {
        if (strncmp(actionIdRingBuffer[i], actionId, ACTION_ID_STR_LEN) == 0) {
            return true;
        }
    }
    return false;
}

void recordActionId(const char* actionId) {
    if (!actionId || actionId[0] == '\0') return;
    strncpy(actionIdRingBuffer[ringHead], actionId, ACTION_ID_STR_LEN - 1);
    actionIdRingBuffer[ringHead][ACTION_ID_STR_LEN - 1] = '\0';

    ringHead = (ringHead + 1) % ACTION_ID_BUF_SIZE;
    if (ringCount < ACTION_ID_BUF_SIZE) {
        ringCount++;
    }
}

static const DeviceConfig* findDeviceConfig(const char* deviceId) {
    if (!deviceId) return NULL;
    for (int i = 0; i < 4; i++) {
        if (strcmp(DEVICE_TABLE[i].id, deviceId) == 0) {
            return &DEVICE_TABLE[i];
        }
    }
    return NULL;
}

SafetyGateResult validateAutoAction(
    const char* deviceId,
    const char* proposedState,
    const SafetyGateContext* ctx
) {
    // 0. Parameter null checks
    if (!deviceId || !proposedState || !ctx) {
        return (SafetyGateResult){false, "invalid_arguments"};
    }

    const DeviceConfig* cfg = findDeviceConfig(deviceId);
    if (!cfg) {
        return (SafetyGateResult){false, "unknown_device"};
    }

    // Check 1: Device Allowlist (autoEligible)
    if (!cfg->autoEligible) {
        return (SafetyGateResult){false, "device_not_auto_eligible"};
    }

    // Check 8: Device-Specific Safeguards (Hard AC/PC lockout)
    if (strcmp(deviceId, DEV_AC) == 0) {
        return (SafetyGateResult){false, "ac_safety_lockout"};
    }
    if (strcmp(deviceId, DEV_PC) == 0) {
        return (SafetyGateResult){false, "pc_data_safety_lockout"};
    }

    // Check 2: Controller Mode == AUTO
    if (!ctx->controllerMode || strcmp(ctx->controllerMode, "AUTO") != 0) {
        return (SafetyGateResult){false, "controller_in_manual_mode"};
    }

    // Check 3: No Active Manual Override / Manual Hold
    if (ctx->lastManualCmdEpoch > 0) {
        if (ctx->currentEpoch >= ctx->lastManualCmdEpoch) {
            uint32_t elapsedManual = ctx->currentEpoch - ctx->lastManualCmdEpoch;
            if (elapsedManual < ctx->manualHoldSec) {
                return (SafetyGateResult){false, "manual_override_active"};
            }
        }
    }

    // Check 4: Required Sensor Data Valid AND Fresh
    if (!ctx->sensorDataValid) {
        return (SafetyGateResult){false, "sensor_data_invalid"};
    }
    if (ctx->currentEpoch >= ctx->sensorSnapshotEpoch) {
        uint32_t ageSec = ctx->currentEpoch - ctx->sensorSnapshotEpoch;
        if (ageSec > ctx->sensorStaleThresholdSec) {
            return (SafetyGateResult){false, "sensor_data_stale"};
        }
    }

    // Check 7: Transition Valid for Current State (no OFF->OFF or ON->ON)
    bool currentON = isDeviceON(deviceId);
    bool targetON = (strcmp(proposedState, "ON") == 0);
    if (currentON == targetON) {
        return (SafetyGateResult){false, "redundant_transition"};
    }

    // Check 5: Minimum ON / OFF Interval Satisfied
    uint32_t lastSwitch = getLastSwitchEpoch(deviceId);
    if (lastSwitch > 0 && ctx->currentEpoch >= lastSwitch) {
        uint32_t elapsedSwitch = ctx->currentEpoch - lastSwitch;
        if (!targetON && currentON) {
            // Proposing OFF: verify minOnTimeSec
            if (elapsedSwitch < cfg->minOnTimeSec) {
                return (SafetyGateResult){false, "min_on_time_violated"};
            }
        } else if (targetON && !currentON) {
            // Proposing ON: verify minOffTimeSec
            if (elapsedSwitch < cfg->minOffTimeSec) {
                return (SafetyGateResult){false, "min_off_time_violated"};
            }
        }
    }

    // Check 6: Command Not Duplicate and Not Expired (if command ID present)
    if (ctx->actionId && ctx->actionId[0] != '\0') {
        if (ctx->isDuplicate || isDuplicateActionId(ctx->actionId)) {
            return (SafetyGateResult){false, "duplicate_action_id"};
        }
        if (!ctx->timeSynced) {
            return (SafetyGateResult){false, "time_unsynced"};
        }
        if (ctx->expiresAt > 0 && ctx->currentEpoch > ctx->expiresAt) {
            return (SafetyGateResult){false, "command_expired"};
        }
    }

    // All 8 checks passed!
    return (SafetyGateResult){true, "allowed"};
}

SafetyGateResult validateManualCommand(
    const char* deviceId,
    const char* proposedState,
    const SafetyGateContext* ctx
) {
    if (!deviceId || !proposedState || !ctx) {
        return (SafetyGateResult){false, "invalid_arguments"};
    }

    const DeviceConfig* cfg = findDeviceConfig(deviceId);
    if (!cfg) {
        return (SafetyGateResult){false, "unknown_device"};
    }

    // Check T13: AC/PC Power-OFF from dashboard/API is BLOCKED by default
    bool targetON = (strcmp(proposedState, "ON") == 0);
    if (!targetON) {
        if (strcmp(deviceId, DEV_AC) == 0 || strcmp(deviceId, DEV_PC) == 0) {
            return (SafetyGateResult){false, "ac_pc_power_off_blocked_by_policy"};
        }
    }

    // Transition Valid
    bool currentON = isDeviceON(deviceId);
    if (currentON == targetON) {
        return (SafetyGateResult){false, "redundant_transition"};
    }

    // Min switching interval (hardware protection against chatter)
    uint32_t lastSwitch = getLastSwitchEpoch(deviceId);
    if (lastSwitch > 0 && ctx->currentEpoch >= lastSwitch) {
        uint32_t elapsedSwitch = ctx->currentEpoch - lastSwitch;
        if (!targetON && currentON) {
            if (elapsedSwitch < cfg->minOnTimeSec) {
                return (SafetyGateResult){false, "min_on_time_violated"};
            }
        } else if (targetON && !currentON) {
            if (elapsedSwitch < cfg->minOffTimeSec) {
                return (SafetyGateResult){false, "min_off_time_violated"};
            }
        }
    }

    // Duplicate & Expiry Check
    if (ctx->actionId && ctx->actionId[0] != '\0') {
        if (ctx->isDuplicate || isDuplicateActionId(ctx->actionId)) {
            return (SafetyGateResult){false, "duplicate_action_id"};
        }
        if (ctx->expiresAt > 0 && ctx->timeSynced && ctx->currentEpoch > ctx->expiresAt) {
            return (SafetyGateResult){false, "command_expired"};
        }
    }

    return (SafetyGateResult){true, "allowed"};
}
