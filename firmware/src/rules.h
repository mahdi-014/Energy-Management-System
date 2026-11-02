#ifndef RULES_H
#define RULES_H

#include <stdint.h>
#include <stdbool.h>
#include "sensors.h"

#ifdef __cplusplus
extern "C" {
#endif

void initRules();
void evaluateLocalRules(const SensorSnapshot* snapshot, uint32_t currentEpoch);

#ifdef __cplusplus
}
#endif

#endif // RULES_H

