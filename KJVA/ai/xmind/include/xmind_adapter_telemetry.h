/* xmind_adapter_telemetry.h — adapter contribution telemetry (§11.1 Add, §11.2 step 15).
 * Counts delta applications and tracks the most-recently-applied tensor. NEW header. */
#ifndef XMIND_ADAPTER_TELEMETRY_H
#define XMIND_ADAPTER_TELEMETRY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void        xmind_adapter_telemetry_reset(void);
void        xmind_adapter_telemetry_record(const char *tensor_name);
uint64_t    xmind_adapter_telemetry_total(void);
const char *xmind_adapter_telemetry_last(void);

#ifdef __cplusplus
}
#endif
#endif /* XMIND_ADAPTER_TELEMETRY_H */
