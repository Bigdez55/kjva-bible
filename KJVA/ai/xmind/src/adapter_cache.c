/* adapter_cache.c — bounded LRU cache of named adapters (§11.1 Add).
 * Holds BORROWED adapter pointers (owned by the caller). For hot-swapping adapters
 * without re-loading. NO-OP-safe; does not affect inference unless explicitly used. */
#include "xmind_adapter_ir.h"

#include <string.h>

#define XMIND_ADAPTER_CACHE_MAX 8u

typedef struct {
    char                key[17];
    const xmind_lora_t *adapter;
    uint64_t            tick;
    int                 used;
} xmind_adapter_slot_t;

static xmind_adapter_slot_t s_slots[XMIND_ADAPTER_CACHE_MAX];
static uint64_t             s_tick = 0u;

void xmind_adapter_cache_reset(void) {
    memset(s_slots, 0, sizeof(s_slots));
    s_tick = 0u;
}

int xmind_adapter_cache_put(const char *key, const xmind_lora_t *adapter) {
    uint32_t i;
    uint32_t lru = 0u;
    uint64_t lru_tick = (uint64_t)-1;

    if ((key == (const char *)0) || (adapter == (const xmind_lora_t *)0)) {
        return -1;
    }
    for (i = 0u; i < XMIND_ADAPTER_CACHE_MAX; i++) {
        if (s_slots[i].used && (strncmp(s_slots[i].key, key, 16u) == 0)) {
            s_slots[i].adapter = adapter;
            s_slots[i].tick = ++s_tick;
            return 0;
        }
        if (!s_slots[i].used) {
            lru = i;
            lru_tick = 0u;
        } else if (s_slots[i].tick < lru_tick) {
            lru_tick = s_slots[i].tick;
            lru = i;
        }
    }
    strncpy(s_slots[lru].key, key, 16u);
    s_slots[lru].key[16] = '\0';
    s_slots[lru].adapter = adapter;
    s_slots[lru].tick = ++s_tick;
    s_slots[lru].used = 1;
    return 0;
}

const xmind_lora_t *xmind_adapter_cache_get(const char *key) {
    uint32_t i;
    if (key == (const char *)0) {
        return (const xmind_lora_t *)0;
    }
    for (i = 0u; i < XMIND_ADAPTER_CACHE_MAX; i++) {
        if (s_slots[i].used && (strncmp(s_slots[i].key, key, 16u) == 0)) {
            s_slots[i].tick = ++s_tick;
            return s_slots[i].adapter;
        }
    }
    return (const xmind_lora_t *)0;
}

uint32_t xmind_adapter_cache_count(void) {
    uint32_t i;
    uint32_t n = 0u;
    for (i = 0u; i < XMIND_ADAPTER_CACHE_MAX; i++) {
        if (s_slots[i].used) {
            n++;
        }
    }
    return n;
}
