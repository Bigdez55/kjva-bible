/*
 * pal_posix.c — Comprehensive POSIX-backed PAL implementation.
 */

#include "pal.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>
#include <pthread.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netdb.h>
#include <arpa/inet.h>

#define PAL_POSIX_MAX_HANDLES 8192u

typedef struct {
    void           *addr;
    size_t          bytes;
    uint64_t        page_size;
    uint64_t        num_pages;
    pal_obj_type_t  type;
    int             fd;       /* for file/socket handles */
    bool            in_use;
} pal_posix_entry_t;

static pal_posix_entry_t s_handles[PAL_POSIX_MAX_HANDLES];
static pthread_mutex_t   s_handles_lock = PTHREAD_MUTEX_INITIALIZER;
static uint64_t          s_uptime_base_ns = 0;

/* ── status strings ──────────────────────────────────────────────── */
const char *pal_strerror(pal_status_t s) {
    switch (s) {
        case PAL_OK: return "OK";
        case PAL_ERR_NOMEM: return "ENOMEM";
        case PAL_ERR_INVAL: return "EINVAL";
        case PAL_ERR_PERM: return "EPERM";
        case PAL_ERR_BUSY: return "EBUSY";
        case PAL_ERR_TIMEOUT: return "ETIMEDOUT";
        case PAL_ERR_NOT_FOUND: return "ENOENT";
        case PAL_ERR_EXISTS: return "EEXIST";
        case PAL_ERR_IO: return "EIO";
        case PAL_ERR_NOT_SUPPORTED: return "ENOSYS";
        case PAL_ERR_INTERRUPTED: return "EINTR";
        case PAL_ERR_OVERFLOW: return "EOVERFLOW";
        case PAL_ERR_EOF: return "EOF";
        default: return "UNKNOWN";
    }
}

void pal_panic(const char *msg) {
    fprintf(stderr, "[PAL_PANIC] %s\n", msg ? msg : "(no message)");
    abort();
}

/* ── handle table ────────────────────────────────────────────────── */
static pal_handle_t handle_alloc(void *addr, size_t bytes,
                                  uint64_t page_size, uint64_t num_pages,
                                  pal_obj_type_t type, int fd) {
    pthread_mutex_lock(&s_handles_lock);
    for (uint32_t i = 1; i < PAL_POSIX_MAX_HANDLES; i++) {
        if (!s_handles[i].in_use) {
            s_handles[i].addr      = addr;
            s_handles[i].bytes     = bytes;
            s_handles[i].page_size = page_size;
            s_handles[i].num_pages = num_pages;
            s_handles[i].type      = type;
            s_handles[i].fd        = fd;
            s_handles[i].in_use    = true;
            pthread_mutex_unlock(&s_handles_lock);
            return (pal_handle_t)i;
        }
    }
    pthread_mutex_unlock(&s_handles_lock);
    return PAL_HANDLE_INVALID;
}

static pal_posix_entry_t *handle_lookup(pal_handle_t h) {
    if (h == PAL_HANDLE_INVALID || h >= PAL_POSIX_MAX_HANDLES) return NULL;
    return s_handles[h].in_use ? &s_handles[h] : NULL;
}

static void handle_release(pal_handle_t h) {
    if (h == PAL_HANDLE_INVALID || h >= PAL_POSIX_MAX_HANDLES) return;
    pthread_mutex_lock(&s_handles_lock);
    memset(&s_handles[h], 0, sizeof(s_handles[h]));
    pthread_mutex_unlock(&s_handles_lock);
}

pal_status_t pal_handle_type(pal_handle_t h, pal_obj_type_t *out_type) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e) return PAL_ERR_NOT_FOUND;
    if (out_type) *out_type = e->type;
    return PAL_OK;
}

pal_status_t pal_handle_close(pal_handle_t h) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e) return PAL_OK;
    switch (e->type) {
        case PAL_OBJ_PAGES:
        case PAL_OBJ_MAPPING:
            if (e->addr) munmap(e->addr, e->bytes);
            break;
        case PAL_OBJ_FILE:
        case PAL_OBJ_SOCKET:
            if (e->fd >= 0) close(e->fd);
            break;
        default: break;
    }
    handle_release(h);
    return PAL_OK;
}

/* ── physical memory ────────────────────────────────────────────── */
pal_status_t pal_pages_alloc(uint64_t num_pages, uint64_t page_size,
                              uint32_t flags, uint32_t numa_node,
                              pal_handle_t *out_handle) {
    (void)numa_node; (void)flags;
    if (num_pages == 0 || !out_handle) return PAL_ERR_INVAL;
    if (page_size == 0) page_size = PAL_PAGE_SIZE_4K;
    size_t bytes = (size_t)(num_pages * page_size);
    void *addr = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
                       MAP_ANONYMOUS | MAP_PRIVATE, -1, 0);
    if (addr == MAP_FAILED) return PAL_ERR_NOMEM;
    pal_handle_t h = handle_alloc(addr, bytes, page_size, num_pages, PAL_OBJ_PAGES, -1);
    if (h == PAL_HANDLE_INVALID) { munmap(addr, bytes); return PAL_ERR_NOMEM; }
    *out_handle = h;
    return PAL_OK;
}

pal_status_t pal_pages_free(pal_handle_t h) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e) return PAL_OK;
    if (e->addr) munmap(e->addr, e->bytes);
    handle_release(h);
    return PAL_OK;
}

pal_status_t pal_pages_info(pal_handle_t h, pal_page_info_t *out) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e || !out) return PAL_ERR_NOT_FOUND;
    out->phys_addr = (uint64_t)(uintptr_t)e->addr;
    out->num_pages = e->num_pages;
    out->page_size = e->page_size;
    return PAL_OK;
}

/* ── heap (libc-backed) ─────────────────────────────────────────── */
void *pal_heap_alloc(size_t sz) { return malloc(sz); }
void  pal_heap_free(void *ptr)  { free(ptr); }

/* ── virtual memory (POSIX: map = view of allocation) ───────────── */
pal_status_t pal_map_pages(pal_handle_t ph, uintptr_t va, uint64_t off,
                            uint64_t n, uint32_t fl, pal_handle_t *out_h,
                            uintptr_t *out_va) {
    (void)fl; (void)va;
    pal_posix_entry_t *e = handle_lookup(ph);
    if (!e) return PAL_ERR_NOT_FOUND;
    if (off + n > e->num_pages) return PAL_ERR_INVAL;
    uintptr_t base = (uintptr_t)e->addr + (off * e->page_size);
    pal_handle_t mh = handle_alloc((void *)base, n * e->page_size,
                                    e->page_size, n, PAL_OBJ_MAPPING, -1);
    if (mh == PAL_HANDLE_INVALID) return PAL_ERR_NOMEM;
    if (out_h)  *out_h  = mh;
    if (out_va) *out_va = base;
    return PAL_OK;
}

pal_status_t pal_unmap(pal_handle_t h) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e) return PAL_OK;
    if (e->type == PAL_OBJ_MAPPING) { handle_release(h); return PAL_OK; }
    return pal_pages_free(h);
}

pal_status_t pal_map_protect(pal_handle_t h, uint32_t nf) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e) return PAL_ERR_NOT_FOUND;
    int prot = 0;
    if (nf & PAL_MAP_READ)  prot |= PROT_READ;
    if (nf & PAL_MAP_WRITE) prot |= PROT_WRITE;
    if (nf & PAL_MAP_EXEC)  prot |= PROT_EXEC;
    return mprotect(e->addr, e->bytes, prot) == 0 ? PAL_OK : PAL_ERR_PERM;
}

/* ── file-backed mmap (matches the freestanding contract) ────────────────── */
pal_status_t pal_mmap(pal_file_t *fh, uint64_t offset, uint64_t length,
                       uint32_t prot, uint32_t flags,
                       pal_handle_t *out_mh, void **out_va) {
    (void)flags;
    if (!fh || !fh->_open || length == 0 || !out_mh || !out_va) return PAL_ERR_INVAL;
    int posix_prot = 0;
    if (prot & PAL_MMAP_PROT_READ)  posix_prot |= PROT_READ;
    if (prot & PAL_MMAP_PROT_WRITE) posix_prot |= PROT_WRITE;
    if (prot & PAL_MMAP_PROT_EXEC)  posix_prot |= PROT_EXEC;
    if (posix_prot == 0) posix_prot = PROT_READ;

    void *addr = mmap(NULL, (size_t)length, posix_prot, MAP_PRIVATE, fh->_fd, (off_t)offset);
    if (addr == MAP_FAILED) {
        *out_va = PAL_MMAP_FAILED;
        return PAL_ERR_NOMEM;
    }
    pal_handle_t h = handle_alloc(addr, (size_t)length, PAL_PAGE_SIZE_4K,
                                    ((size_t)length + 4095) / 4096,
                                    PAL_OBJ_MAPPING, -1);
    if (h == PAL_HANDLE_INVALID) { munmap(addr, (size_t)length); return PAL_ERR_NOMEM; }
    *out_mh = h;
    *out_va = addr;
    return PAL_OK;
}

pal_status_t pal_mmap_unmap(pal_handle_t mh, void *va, uint64_t length) {
    pal_posix_entry_t *e = handle_lookup(mh);
    if (!e) {
        /* Fallback: direct unmap if handle gone */
        if (va && length > 0) munmap(va, (size_t)length);
        return PAL_OK;
    }
    munmap(e->addr, e->bytes);
    handle_release(mh);
    return PAL_OK;
}

pal_status_t pal_munmap(void *addr, size_t size) {
    if (!addr) return PAL_OK;
    return munmap(addr, size) == 0 ? PAL_OK : PAL_ERR_INVAL;
}

/* ── file I/O (pointer-based — matches the freestanding contract) ─────────── */
pal_status_t pal_file_open(pal_file_t *out_fh, const char *path, uint32_t flags) {
    if (!path || !out_fh) return PAL_ERR_INVAL;
    int posix_flags;
    if (flags == PAL_FILE_READ) posix_flags = O_RDONLY;
    else if (flags == PAL_FILE_WRITE) posix_flags = O_WRONLY | O_CREAT | O_TRUNC;
    else posix_flags = O_RDWR | O_CREAT;
    int fd = open(path, posix_flags, 0644);
    if (fd < 0) return (errno == ENOENT) ? PAL_ERR_NOT_FOUND : PAL_ERR_IO;
    out_fh->_fd    = fd;
    out_fh->_flags = flags;
    out_fh->_open  = 1;
    return PAL_OK;
}

pal_status_t pal_file_close(pal_file_t *fh) {
    if (!fh || !fh->_open) return PAL_OK;
    close(fh->_fd);
    fh->_fd = -1; fh->_open = 0;
    return PAL_OK;
}

pal_status_t pal_file_read(pal_file_t *fh, void *buf, uint64_t len, uint64_t *out_got) {
    if (!fh || !fh->_open || !buf) return PAL_ERR_INVAL;
    ssize_t r = read(fh->_fd, buf, (size_t)len);
    if (r < 0) return PAL_ERR_IO;
    if (out_got) *out_got = (uint64_t)r;
    return (r == 0 && len > 0) ? PAL_ERR_EOF : PAL_OK;
}

pal_status_t pal_file_seek(pal_file_t *fh, int64_t off, pal_seek_whence_t w) {
    if (!fh || !fh->_open) return PAL_ERR_INVAL;
    int whence = (w == PAL_SEEK_CUR) ? SEEK_CUR : (w == PAL_SEEK_END) ? SEEK_END : SEEK_SET;
    off_t p = lseek(fh->_fd, (off_t)off, whence);
    if (p < 0) return PAL_ERR_IO;
    return PAL_OK;
}

pal_status_t pal_file_stat(const char *path, pal_file_stat_t *out) {
    if (!path || !out) return PAL_ERR_INVAL;
    struct stat st;
    if (stat(path, &st) != 0) return (errno == ENOENT) ? PAL_ERR_NOT_FOUND : PAL_ERR_IO;
    out->size     = (uint64_t)st.st_size;
    out->mtime_ns = (uint64_t)st.st_mtime * 1000000000ull;
    out->is_dir   = S_ISDIR(st.st_mode);
    return PAL_OK;
}

/* ── console ────────────────────────────────────────────────────── */
void pal_console_puts(const char *s) { if (s) fputs(s, stdout); fflush(stdout); }
void pal_console_printf(const char *fmt, ...) {
    va_list ap; va_start(ap, fmt); vprintf(fmt, ap); va_end(ap); fflush(stdout);
}

/* ── time ───────────────────────────────────────────────────────── */
uint64_t pal_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}
uint64_t pal_time_now_ns(void) { return pal_time_ns(); }
uint64_t pal_uptime_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t now = (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
    if (s_uptime_base_ns == 0) s_uptime_base_ns = now;
    return now - s_uptime_base_ns;
}
pal_status_t pal_sleep_ns(uint64_t ns) {
    struct timespec ts = { (time_t)(ns / 1000000000ull), (long)(ns % 1000000000ull) };
    while (nanosleep(&ts, &ts) == -1 && errno == EINTR) {}
    return PAL_OK;
}

/* ── threading ──────────────────────────────────────────────────── */
typedef struct { pal_thread_fn entry; void *arg; } pal_thread_trampoline_t;
static void *pal_thread_trampoline_fn(void *arg) {
    pal_thread_trampoline_t *t = (pal_thread_trampoline_t *)arg;
    t->entry(t->arg);
    free(t);
    return NULL;
}
pal_status_t pal_thread_create(const pal_thread_config_t *cfg, pal_handle_t *out_handle) {
    if (!cfg || !cfg->entry || !out_handle) return PAL_ERR_INVAL;
    pal_thread_trampoline_t *t = malloc(sizeof(*t));
    if (!t) return PAL_ERR_NOMEM;
    t->entry = cfg->entry; t->arg = cfg->arg;
    pthread_t pt;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    if (cfg->stack_size > 0) pthread_attr_setstacksize(&attr, cfg->stack_size);
    int rc = pthread_create(&pt, &attr, pal_thread_trampoline_fn, t);
    pthread_attr_destroy(&attr);
    if (rc != 0) { free(t); return PAL_ERR_NOMEM; }
    pal_handle_t h = handle_alloc((void *)(uintptr_t)pt, 0, 0, 0, PAL_OBJ_THREAD, -1);
    if (h == PAL_HANDLE_INVALID) { pthread_detach(pt); return PAL_ERR_NOMEM; }
    *out_handle = h;
    return PAL_OK;
}
pal_status_t pal_thread_yield(void) { sched_yield(); return PAL_OK; }
pal_status_t pal_thread_join(pal_handle_t h) {
    pal_posix_entry_t *e = handle_lookup(h);
    if (!e || e->type != PAL_OBJ_THREAD) return PAL_ERR_NOT_FOUND;
    pthread_join((pthread_t)(uintptr_t)e->addr, NULL);
    handle_release(h);
    return PAL_OK;
}
pal_status_t pal_thread_exit(void) { pthread_exit(NULL); return PAL_OK; }

/* ── spinlocks ──────────────────────────────────────────────────── */
static pthread_mutex_t s_spinlock_init_lock = PTHREAD_MUTEX_INITIALIZER;

static pthread_mutex_t *spinlock_get_mtx(pal_spinlock_t *l) {
    pthread_mutex_lock(&s_spinlock_init_lock);
    if (l->_mtx == NULL) {
        pthread_mutex_t *m = malloc(sizeof(pthread_mutex_t));
        pthread_mutex_init(m, NULL);
        l->_mtx = m;
    }
    pthread_mutex_unlock(&s_spinlock_init_lock);
    return (pthread_mutex_t *)l->_mtx;
}
void pal_spin_lock(pal_spinlock_t *l)   { pthread_mutex_lock(spinlock_get_mtx(l)); }
void pal_spin_unlock(pal_spinlock_t *l) { pthread_mutex_unlock(spinlock_get_mtx(l)); }

/* ── random ─────────────────────────────────────────────────────── */
pal_status_t pal_random_bytes(void *buf, size_t len) {
    if (!buf || len == 0) return PAL_ERR_INVAL;
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) return PAL_ERR_IO;
    size_t off = 0;
    while (off < len) {
        ssize_t r = read(fd, (char *)buf + off, len - off);
        if (r <= 0) { if (errno == EINTR) continue; close(fd); return PAL_ERR_IO; }
        off += (size_t)r;
    }
    close(fd);
    return PAL_OK;
}

/* ── network (PAL TCP client convenience) ───────────────────────── */
pal_status_t pal_net_connect(const char *host, uint16_t port, uint32_t timeout_ms, pal_handle_t *out_sock) {
    (void)timeout_ms;
    if (!host || !out_sock) return PAL_ERR_INVAL;
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    char portstr[16];
    snprintf(portstr, sizeof(portstr), "%u", (unsigned)port);
    if (getaddrinfo(host, portstr, &hints, &res) != 0 || !res) return PAL_ERR_NOT_FOUND;
    int s = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (s < 0) { freeaddrinfo(res); return PAL_ERR_IO; }
    if (connect(s, res->ai_addr, res->ai_addrlen) != 0) {
        close(s); freeaddrinfo(res); return PAL_ERR_IO;
    }
    freeaddrinfo(res);
    pal_handle_t h = handle_alloc(NULL, 0, 0, 0, PAL_OBJ_SOCKET, s);
    if (h == PAL_HANDLE_INVALID) { close(s); return PAL_ERR_NOMEM; }
    *out_sock = h;
    return PAL_OK;
}

pal_status_t pal_net_read(pal_handle_t sock, void *buf, size_t len, size_t *out_got) {
    pal_posix_entry_t *e = handle_lookup(sock);
    if (!e || e->type != PAL_OBJ_SOCKET) return PAL_ERR_INVAL;
    ssize_t r = recv(e->fd, buf, len, 0);
    if (r < 0) return PAL_ERR_IO;
    if (out_got) *out_got = (size_t)r;
    return (r == 0) ? PAL_ERR_EOF : PAL_OK;
}

pal_status_t pal_net_write(pal_handle_t sock, const void *buf, size_t len, size_t *out_wrote) {
    pal_posix_entry_t *e = handle_lookup(sock);
    if (!e || e->type != PAL_OBJ_SOCKET) return PAL_ERR_INVAL;
    ssize_t w = send(e->fd, buf, len, 0);
    if (w < 0) return PAL_ERR_IO;
    if (out_wrote) *out_wrote = (size_t)w;
    return PAL_OK;
}

pal_status_t pal_net_close(pal_handle_t sock) { return pal_handle_close(sock); }
