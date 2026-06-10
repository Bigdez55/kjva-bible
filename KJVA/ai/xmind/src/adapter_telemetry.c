/* adapter_telemetry.c — adapter contribution telemetry (§11.1 Add, §11.2 step 15). */
#include "xmind_adapter_telemetry.h"

#include <string.h>

static uint64_t s_total = 0u;
static char     s_last[128] = {0};

void xmind_adapter_telemetry_reset(void) {
    s_total = 0u;
    s_last[0] = '\0';
}

void xmind_adapter_telemetry_record(const char *tensor_name) {
    s_total++;
    if (tensor_name != (const char *)0) {
        strncpy(s_last, tensor_name, sizeof(s_last) - 1u);
        s_last[sizeof(s_last) - 1u] = '\0';
    }
}

uint64_t xmind_adapter_telemetry_total(void) { return s_total; }

const char *xmind_adapter_telemetry_last(void) { return s_last; }
