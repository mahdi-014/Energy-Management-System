#ifndef SAFETY_GATE_H
#define SAFETY_GATE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Outcome structure returned by the safety gate
typedef struct {
    bool allowed;
    const char* reasonCode;
} SafetyGateResult;

// Evaluation context containing all runtime constraints
typedef struct {
    const char* controllerMode;        // "AUTO" or "MANUAL"
    uint32_t currentEpoch;             // Current UTC epoch seconds from NTP
    bool timeSynced;                   // True if NTP time has been synced
    uint32_t lastManualCmdEpoch;       // Timestamp of most recent manual command
    uint32_t manualHoldSec;            // Lockout duration after manual command (default 600s)
    bool sensorDataValid;              // True if sensor readings pass validity & bounds check
    uint32_t sensorSnapshotEpoch;      // Timestamp of the latest sensor snapshot
    uint32_t sensorStaleThresholdSec;  // Maximum permitted age of sensor reading (default 60s)
    const char* actionId;              // Unique command identifier
    uint32_t expiresAt;                // UTC epoch seconds at which command expires
    bool isDuplicate;                  // True if actionId was already processed
    bool isServerProposal;             // True if proposed by server automated policy
} SafetyGateContext;

// Pure deterministic validation functions
SafetyGateResult validateAutoAction(
    const char* deviceId,
    const char* proposedState,
    const SafetyGateContext* ctx
);

SafetyGateResult validateManualCommand(
    const char* deviceId,
    const char* proposedState,
    const SafetyGateContext* ctx
);

// Recent Action ID ring buffer for deduplication (32 entries)
void initActionIdBuffer();
bool isDuplicateActionId(const char* actionId);
void recordActionId(const char* actionId);

#ifdef __cplusplus
}
#endif

#endif // SAFETY_GATE_H
