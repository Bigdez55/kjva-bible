/* xsec.h — consumer-build XSEC audit ring shim (no-op routing to stderr). */
#ifndef GENOS_XSEC_SHIM_H
#define GENOS_XSEC_SHIM_H

#include "pal.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef int32_t xsec_status_t;
#define XSEC_OK          0
#define XSEC_ERR_INVAL  -1

/* Severity */
typedef enum {
    XSEC_AUDIT_INFO  = 0,
    XSEC_AUDIT_WARN  = 1,
    XSEC_AUDIT_ERROR = 2,
    XSEC_AUDIT_CRIT  = 3,
} xsec_audit_severity_t;

/* Module IDs */
typedef uint32_t xsec_module_id_t;
#define XSEC_MODULE_COGNITIVE  0x1001

/* Event codes used by R1_PER / XCOG audit emission */
#define XSEC_AUDIT_XCOG_DIVERGENCE  0xC001
#define XSEC_AUDIT_XCOG_ENCODE      0xC002
#define XSEC_AUDIT_XCOG_ESCALATION  0xC003
#define XSEC_AUDIT_XCOG_FALLBACK    0xC004

/* Sizes */
#define XSEC_AUDIT_DETAIL_LEN  256u

/* Event-id type for compact audit logging */
typedef uint32_t xsec_audit_event_t;

xsec_status_t xsec_audit_emit(xsec_audit_severity_t sev, const char *subsystem,
                               const char *event, const void *data, size_t len);

/* Compact form: event_id, module, detail string */
xsec_status_t xsec_audit_log(xsec_audit_event_t event_id,
                              xsec_module_id_t module,
                              const char *detail);

/* SHA-256 / SHA-384 helpers (referenced for content hashing) */
xsec_status_t xsec_sha256(const void *data, size_t len, uint8_t out[32]);
xsec_status_t xsec_sha384(const void *data, size_t len, uint8_t out[48]);

/* Streaming SHA-256 — real FIPS 180-4 SHA-256 (the consumer build now links a self-contained
 * implementation; it was an FNV-1a fold). Opaque to callers: use init/update/final only. */
typedef struct {
    uint32_t h[8];        /* hash state */
    uint8_t  buf[64];     /* partial input block */
    uint64_t total_len;   /* total bytes hashed (for length padding) */
    uint32_t buf_len;     /* bytes currently buffered */
} xsec_sha256_ctx_t;

void xsec_sha256_init(xsec_sha256_ctx_t *ctx);
void xsec_sha256_update(xsec_sha256_ctx_t *ctx, const void *data, size_t len);
void xsec_sha256_final(xsec_sha256_ctx_t *ctx, uint8_t out[32]);

#ifdef __cplusplus
}
#endif
#endif
