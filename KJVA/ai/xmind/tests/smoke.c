/*
 * smoke.c — Minimal smoke test for the XMIND build.
 *
 * Verifies: PAL shim alloc/free, basic console + random + time, xm_heap
 * round-trip. Does NOT load weights — that's a separate inference test.
 *
 * Build via the ai/xmind Makefile:  make test
 */
#include "pal.h"
#include <stdio.h>
#include <string.h>

extern void *xm_heap_alloc(uint64_t sz);
extern void  xm_heap_free(void *ptr);

int main(void) {
    pal_console_puts("[smoke] XMIND build — sanity check\n");

    /* 1. PAL pages_alloc/free */
    pal_handle_t h = PAL_HANDLE_INVALID;
    pal_status_t s = pal_pages_alloc(4, PAL_PAGE_SIZE_4K, PAL_MEM_ZEROED,
                                      PAL_NUMA_ANY, &h);
    if (s != PAL_OK || h == PAL_HANDLE_INVALID) {
        fprintf(stderr, "[smoke] FAIL pal_pages_alloc s=%d\n", s);
        return 1;
    }
    pal_console_printf("[smoke] PAL pages_alloc ok, handle=%llu\n",
                       (unsigned long long)h);
    pal_pages_free(h);

    /* 2. xm_heap round-trip */
    void *p = xm_heap_alloc(64 * 1024);
    if (!p) { fprintf(stderr, "[smoke] FAIL xm_heap_alloc\n"); return 2; }
    memset(p, 0xAB, 64 * 1024);
    pal_console_printf("[smoke] xm_heap_alloc(64KB) = %p\n", p);
    xm_heap_free(p);

    /* 3. Random + time */
    uint8_t rnd[16];
    if (pal_random_bytes(rnd, sizeof(rnd)) != PAL_OK) {
        fprintf(stderr, "[smoke] FAIL pal_random_bytes\n"); return 3;
    }
    pal_console_printf("[smoke] random16: ");
    for (int i = 0; i < 16; i++) pal_console_printf("%02x", rnd[i]);
    pal_console_puts("\n");

    pal_console_printf("[smoke] uptime_ns=%llu\n",
                       (unsigned long long)pal_uptime_ns());

    pal_console_puts("[smoke] PASS\n");
    return 0;
}
