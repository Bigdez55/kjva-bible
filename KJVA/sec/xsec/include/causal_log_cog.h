/* causal_log_cog.h — consumer-build stub for XSEC causal-log cognitive ring. */
#ifndef GENOS_CAUSAL_LOG_COG_SHIM_H
#define GENOS_CAUSAL_LOG_COG_SHIM_H
#include "pal.h"
#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint64_t ts_ns;
    uint32_t event_id;
    uint32_t severity;
} causal_log_entry_t;

int causal_log_emit(uint32_t event_id, uint32_t severity, const void *data, size_t len);

#ifdef __cplusplus
}
#endif
#endif
