/*
 * stubs.c — consumer-build no-op implementations for XSEC, XSTORE, XJIT.
 * Routes ERROR/CRIT audit emission to stderr for visibility.
 */

#include "xsec.h"
#include "xstore.h"
#include "causal_log_cog.h"
#include "xnet.h"
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <unistd.h>

/* ── XSEC audit ring ────────────────────────────────────────────── */
xsec_status_t xsec_audit_emit(xsec_audit_severity_t sev, const char *subsystem,
                               const char *event, const void *data, size_t len) {
    (void)data; (void)len;
    if (sev >= XSEC_AUDIT_ERROR) {
        fprintf(stderr, "[XSEC sev=%d] %s :: %s\n", sev,
                subsystem ? subsystem : "?",
                event ? event : "?");
    }
    return XSEC_OK;
}

xsec_status_t xsec_audit_log(xsec_audit_event_t event_id,
                              xsec_module_id_t module,
                              const char *detail) {
    /* Always emit audit_log for visibility (lowercase to differ from emit) */
    fprintf(stderr, "[xsec_log event=0x%08x module=0x%08x] %s\n",
            event_id, module, detail ? detail : "(no detail)");
    return XSEC_OK;
}

/* Real FIPS 180-4 SHA-256 — self-contained, no external crypto dependency. Replaces the prior
 * FNV-1a stand-in so content integrity is cryptographically sound in the consumer build:
 * R1_PER's dual-integrity tamper gate, the §8.3 weight source_hash, and the continuity
 * attestation chain now use a collision-resistant hash. Matches the FIPS test vectors and
 * `shasum -a 256`. */
static const uint32_t XSEC_SHA256_K[64] = {
    0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
    0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
    0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
    0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
    0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
    0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
    0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
    0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
};
#define XSEC_ROR32(x,n) (((x) >> (n)) | ((x) << (32 - (n))))

static void xsec_sha256_transform(uint32_t h[8], const uint8_t blk[64]) {
    uint32_t w[64];
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)blk[i*4] << 24) | ((uint32_t)blk[i*4+1] << 16) |
               ((uint32_t)blk[i*4+2] << 8) | (uint32_t)blk[i*4+3];
    for (int i = 16; i < 64; i++) {
        uint32_t s0 = XSEC_ROR32(w[i-15],7) ^ XSEC_ROR32(w[i-15],18) ^ (w[i-15] >> 3);
        uint32_t s1 = XSEC_ROR32(w[i-2],17) ^ XSEC_ROR32(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],hh=h[7];
    for (int i = 0; i < 64; i++) {
        uint32_t S1 = XSEC_ROR32(e,6) ^ XSEC_ROR32(e,11) ^ XSEC_ROR32(e,25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t t1 = hh + S1 + ch + XSEC_SHA256_K[i] + w[i];
        uint32_t S0 = XSEC_ROR32(a,2) ^ XSEC_ROR32(a,13) ^ XSEC_ROR32(a,22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = S0 + maj;
        hh=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=d; h[4]+=e; h[5]+=f; h[6]+=g; h[7]+=hh;
}

void xsec_sha256_init(xsec_sha256_ctx_t *ctx) {
    if (!ctx) return;
    ctx->h[0]=0x6a09e667u; ctx->h[1]=0xbb67ae85u; ctx->h[2]=0x3c6ef372u; ctx->h[3]=0xa54ff53au;
    ctx->h[4]=0x510e527fu; ctx->h[5]=0x9b05688cu; ctx->h[6]=0x1f83d9abu; ctx->h[7]=0x5be0cd19u;
    ctx->total_len = 0;
    ctx->buf_len = 0;
}
void xsec_sha256_update(xsec_sha256_ctx_t *ctx, const void *data, size_t len) {
    if (!ctx || !data) return;
    const uint8_t *p = (const uint8_t *)data;
    ctx->total_len += (uint64_t)len;
    while (len > 0) {
        uint32_t take = 64u - ctx->buf_len;
        if ((uint64_t)take > len) take = (uint32_t)len;
        memcpy(ctx->buf + ctx->buf_len, p, take);
        ctx->buf_len += take; p += take; len -= take;
        if (ctx->buf_len == 64u) { xsec_sha256_transform(ctx->h, ctx->buf); ctx->buf_len = 0u; }
    }
}
void xsec_sha256_final(xsec_sha256_ctx_t *ctx, uint8_t out[32]) {
    if (!ctx || !out) return;
    uint64_t bitlen = ctx->total_len * 8u;
    uint8_t pad = 0x80u;
    xsec_sha256_update(ctx, &pad, 1);          /* append the '1' bit */
    uint8_t zero = 0u;
    while (ctx->buf_len != 56u) xsec_sha256_update(ctx, &zero, 1);  /* zero-pad to 56 mod 64 */
    uint8_t lenbe[8];
    for (int i = 0; i < 8; i++) lenbe[i] = (uint8_t)(bitlen >> (56 - i*8));
    xsec_sha256_update(ctx, lenbe, 8);         /* 64-bit big-endian bit length */
    for (int i = 0; i < 8; i++) {              /* output h, big-endian */
        out[i*4]   = (uint8_t)(ctx->h[i] >> 24);
        out[i*4+1] = (uint8_t)(ctx->h[i] >> 16);
        out[i*4+2] = (uint8_t)(ctx->h[i] >> 8);
        out[i*4+3] = (uint8_t)(ctx->h[i]);
    }
}
xsec_status_t xsec_sha256(const void *data, size_t len, uint8_t out[32]) {
    if (!data || !out) return XSEC_ERR_INVAL;
    xsec_sha256_ctx_t ctx;
    xsec_sha256_init(&ctx);
    xsec_sha256_update(&ctx, data, len);
    xsec_sha256_final(&ctx, out);
    return XSEC_OK;
}
/* SHA-384 is on no consumer-build security path (no callers). Until a real SHA-512 core is
 * linked, keep an honestly-labeled NON-crypto fold so the symbol resolves — do NOT use it for
 * integrity decisions. */
xsec_status_t xsec_sha384(const void *data, size_t len, uint8_t out[48]) {
    if (!data || !out) return XSEC_ERR_INVAL;
    const uint8_t *p = (const uint8_t *)data;
    for (int k = 0; k < 6; k++) {
        uint64_t h = 0xcbf29ce484222325ull ^ (uint64_t)k;
        for (size_t i = 0; i < len; i++) { h ^= p[i]; h *= 0x100000001b3ull; }
        memcpy(out + k*8, &h, 8);
    }
    return XSEC_OK;
}

int causal_log_emit(uint32_t event_id, uint32_t severity, const void *data, size_t len) {
    (void)event_id; (void)severity; (void)data; (void)len; return 0;
}

/* ── XSTORE — no-op consumer build ──────────────────────────────── */
xstore_status_t xstore_get(const char *key, void *buf, size_t buf_len, size_t *out_len) {
    (void)key; (void)buf; (void)buf_len;
    if (out_len) *out_len = 0;
    return XSTORE_ERR_NOT_FOUND;
}
xstore_status_t xstore_put(const char *key, const void *buf, size_t len) {
    (void)key; (void)buf; (void)len; return XSTORE_OK;
}
xstore_status_t xstore_delete(const char *key) { (void)key; return XSTORE_OK; }

/* ── XJIT — symbols referenced by tensor.c; provide POSIX-safe scalar ─ */
uint8_t xjit_avx2_available(void) { return 0; /* always scalar on consumer */ }

float xjit_dot_f32_scalar(const float *a, const float *b, uint32_t n) {
    float s = 0.0f;
    for (uint32_t i = 0; i < n; i++) s += a[i] * b[i];
    return s;
}
/* AVX2 stubs — never called when xjit_avx2_available()==0; just satisfy linker */
float xjit_dot_f32_avx2(const float *a, const float *b, uint32_t n) {
    return xjit_dot_f32_scalar(a, b, n);
}
float xjit_dot_q4_0_avx2(const uint8_t *quants, float scale,
                          const float *input, uint32_t n) {
    /* Scalar Q4_0 fused dot: dequant nibble = (val - 8) * scale */
    float s = 0.0f;
    for (uint32_t i = 0; i < n; i++) {
        uint8_t nibble = (i & 1) ? (quants[i/2] >> 4) : (quants[i/2] & 0x0F);
        float w = ((int)nibble - 8) * scale;
        s += w * input[i];
    }
    return s;
}
void xjit_matvec_f32_scalar(float *out, const float *mat,
                             const float *vec, uint32_t rows, uint32_t cols) {
    for (uint32_t r = 0; r < rows; r++) {
        float s = 0.0f;
        for (uint32_t c = 0; c < cols; c++) s += mat[r*cols + c] * vec[c];
        out[r] = s;
    }
}
void xjit_matvec_f32_avx2(float *out, const float *mat,
                           const float *vec, uint32_t rows, uint32_t cols) {
    xjit_matvec_f32_scalar(out, mat, vec, rows, cols);
}

void *xjit_get_avx2_dispatch(void) { return NULL; }
void *xjit_get_fma3_dispatch(void) { return NULL; }

/* ── Context bridge — referenced by inference.c/harness.c when IPC is on. ──
 * Consumer build does NOT include context_bridge.c; provide no-op stubs so
 * the inference path links cleanly. Full Council bridging requires the freestanding stack. */
int  xmind_context_retrieve(const void *req, void *out) { (void)req; (void)out; return 0; }
void xmind_context_release(void *result) { (void)result; }
int  xmind_context_consolidate(const void *req, void *res) { (void)req; (void)res; return 0; }

/* ── Telemetry — referenced by heptagon.c; no-op on consumer build. ── */
void xmind_telemetry_emit(const void *h, const void *pkt) { (void)h; (void)pkt; }
