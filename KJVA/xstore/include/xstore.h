/* xstore.h — consumer-build XSTORE shim (filesystem-backed key-value). */
#ifndef GENOS_XSTORE_SHIM_H
#define GENOS_XSTORE_SHIM_H

#include "pal.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef int32_t xstore_status_t;
#define XSTORE_OK              0
#define XSTORE_ERR_INVAL      -1
#define XSTORE_ERR_NOT_FOUND  -2
#define XSTORE_ERR_IO         -3

typedef struct xstore_ctx { void *_impl; } xstore_ctx_t;

typedef struct {
    void  *data;
    size_t len;
} xstore_val_t;

xstore_status_t xstore_get(const char *key, void *buf, size_t buf_len, size_t *out_len);
xstore_status_t xstore_put(const char *key, const void *buf, size_t len);
xstore_status_t xstore_delete(const char *key);

#ifdef __cplusplus
}
#endif
#endif
