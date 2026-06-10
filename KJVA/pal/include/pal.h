/*
 * pal.h — Consumer-Build POSIX PAL Shim (comprehensive).
 *
 * Drop-in replacement for the freestanding pal.h interface. Backed by POSIX (mmap, pthread,
 * stdio, sockets, /dev/urandom). Lets XMIND inference engine compile on
 * macOS/Linux/WSL2 with NO changes to the 23 freestanding C source files.
 *
 * Activate via -DXMIND_POSIX_BUILD=1 (sets at Makefile level).
 */

#ifndef GENOS_PAL_H
#define GENOS_PAL_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <inttypes.h>
#include <sys/types.h>

#ifndef NULL
#define NULL ((void*)0)
#endif

#ifndef ULL
#define ULL(x) ((unsigned long long)(x))
#define LL(x)  ((long long)(x))
#endif

/* ─── Status codes ─────────────────────────────────────────────────── */
typedef int32_t pal_status_t;
#define PAL_OK                  0
#define PAL_ERR_NOMEM          -1
#define PAL_ERR_INVAL          -2
#define PAL_ERR_PERM           -3
#define PAL_ERR_BUSY           -4
#define PAL_ERR_TIMEOUT        -5
#define PAL_ERR_NOT_FOUND      -6
#define PAL_ERR_EXISTS         -7
#define PAL_ERR_IO             -8
#define PAL_ERR_NOT_SUPPORTED  -9
#define PAL_ERR_INTERRUPTED   -10
#define PAL_ERR_OVERFLOW      -11
#define PAL_ERR_EOF           -12
const char *pal_strerror(pal_status_t s);
void pal_panic(const char *msg) __attribute__((noreturn));

/* ─── Handles ──────────────────────────────────────────────────────── */
typedef uint64_t pal_handle_t;
#define PAL_HANDLE_INVALID  ((pal_handle_t)0)
typedef enum {
    PAL_OBJ_PAGES, PAL_OBJ_MAPPING, PAL_OBJ_THREAD, PAL_OBJ_CHANNEL,
    PAL_OBJ_TIMER, PAL_OBJ_EVENT, PAL_OBJ_DEVICE, PAL_OBJ_FILE, PAL_OBJ_SOCKET,
    PAL_OBJ_COUNT
} pal_obj_type_t;
pal_status_t pal_handle_type(pal_handle_t handle, pal_obj_type_t *out_type);
pal_status_t pal_handle_close(pal_handle_t handle);

/* ─── Physical memory ──────────────────────────────────────────────── */
#define PAL_PAGE_SIZE_4K    4096ULL
#define PAL_PAGE_SIZE_2M    (2ULL * 1024 * 1024)
#define PAL_PAGE_SIZE_1G    (1ULL * 1024 * 1024 * 1024)
#define PAL_NUMA_ANY        ((uint32_t)-1)
typedef enum {
    PAL_MEM_NORMAL = 0, PAL_MEM_DMA = (1<<0), PAL_MEM_UNCACHED = (1<<1),
    PAL_MEM_WRITE_COMBINE = (1<<2), PAL_MEM_ZEROED = (1<<3),
} pal_mem_flags_t;
typedef struct {
    uint64_t phys_addr; uint64_t num_pages; uint64_t page_size;
} pal_page_info_t;
pal_status_t pal_pages_alloc(uint64_t n, uint64_t ps, uint32_t fl, uint32_t numa, pal_handle_t *out);
pal_status_t pal_pages_free(pal_handle_t h);
pal_status_t pal_pages_info(pal_handle_t h, pal_page_info_t *out);

/* ─── Heap (convenience) ───────────────────────────────────────────── */
void *pal_heap_alloc(size_t sz);
void  pal_heap_free(void *ptr);

/* ─── Virtual memory ───────────────────────────────────────────────── */
typedef enum {
    PAL_MAP_READ = (1<<0), PAL_MAP_WRITE = (1<<1), PAL_MAP_EXEC = (1<<2),
    PAL_MAP_USER = (1<<3), PAL_MAP_FIXED = (1<<4),
} pal_map_flags_t;
pal_status_t pal_map_pages(pal_handle_t ph, uintptr_t va, uint64_t off, uint64_t n,
                            uint32_t fl, pal_handle_t *out_h, uintptr_t *out_va);
pal_status_t pal_unmap(pal_handle_t mh);
pal_status_t pal_map_protect(pal_handle_t mh, uint32_t nf);

/* ─── File I/O ─────────────────────────────────────────────────────── */
#define PAL_FILE_IO_DEFINED 1
typedef struct { int _fd; uint32_t _flags; uint8_t _open; } pal_file_t;
#define PAL_FILE_READ   (1u<<0)
#define PAL_FILE_WRITE  (1u<<1)
#define PAL_FILE_RDWR   (PAL_FILE_READ | PAL_FILE_WRITE)
typedef enum {
    PAL_SEEK_SET = 0, PAL_SEEK_CUR = 1, PAL_SEEK_END = 2
} pal_seek_whence_t;
typedef struct {
    uint64_t size;
    uint64_t mtime_ns;
    bool     is_dir;
} pal_file_stat_t;
/* Note: pal_file_open signature matches the freestanding contract — out param FIRST */
pal_status_t pal_file_open(pal_file_t *out_fh, const char *path, uint32_t flags);
pal_status_t pal_file_close(pal_file_t *fh);
pal_status_t pal_file_read(pal_file_t *fh, void *buf, uint64_t len, uint64_t *out_got);
pal_status_t pal_file_seek(pal_file_t *fh, int64_t off, pal_seek_whence_t whence);
pal_status_t pal_file_stat(const char *path, pal_file_stat_t *out);

/* ─── mmap (file-backed, takes file handle) ────────────────────────── */
#define PAL_MMAP_DEFINED 1
#define PAL_MMAP_PROT_READ   (1u<<0)
#define PAL_MMAP_PROT_WRITE  (1u<<1)
#define PAL_MMAP_PROT_EXEC   (1u<<2)
#define PAL_MMAP_PRIVATE     (1u<<0)
#define PAL_MMAP_SHARED      (1u<<1)
#define PAL_MMAP_FAILED      ((void *)(intptr_t)-1)

pal_status_t pal_mmap(pal_file_t *fh, uint64_t offset, uint64_t length,
                       uint32_t prot, uint32_t flags,
                       pal_handle_t *out_mh, void **out_va);
pal_status_t pal_mmap_unmap(pal_handle_t mh, void *va, uint64_t length);
pal_status_t pal_munmap(void *addr, size_t size);

/* ─── Console ──────────────────────────────────────────────────────── */
void pal_console_puts(const char *s);
void pal_console_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

/* ─── Time ─────────────────────────────────────────────────────────── */
uint64_t pal_time_ns(void);
uint64_t pal_time_now_ns(void);   /* alias */
uint64_t pal_uptime_ns(void);
pal_status_t pal_sleep_ns(uint64_t ns);

/* ─── Threading ────────────────────────────────────────────────────── */
typedef void (*pal_thread_fn)(void *arg);
typedef enum {
    PAL_THREAD_REALTIME = 0, PAL_THREAD_NORMAL = 1, PAL_THREAD_BACKGROUND = 2,
} pal_thread_priority_t;
typedef struct {
    pal_thread_fn entry; void *arg; uint64_t stack_size;
    pal_thread_priority_t priority; uint32_t cpu_affinity;
} pal_thread_config_t;
pal_status_t pal_thread_create(const pal_thread_config_t *cfg, pal_handle_t *out);
pal_status_t pal_thread_yield(void);
pal_status_t pal_thread_join(pal_handle_t h);
pal_status_t pal_thread_exit(void);

/* ─── Spinlocks (POSIX backing: pthread_mutex_t) ────────────────────── */
typedef struct { void *_mtx; } pal_spinlock_t;
#define PAL_SPINLOCK_INIT { (void*)0 }
void pal_spin_lock(pal_spinlock_t *l);
void pal_spin_unlock(pal_spinlock_t *l);

/* ─── Random ───────────────────────────────────────────────────────── */
pal_status_t pal_random_bytes(void *buf, size_t len);

/* ─── Network (PAL convenience over Berkeley sockets) ─────────────── */
pal_status_t pal_net_connect(const char *host, uint16_t port, uint32_t timeout_ms, pal_handle_t *out_sock);
pal_status_t pal_net_read(pal_handle_t sock, void *buf, size_t len, size_t *out_got);
pal_status_t pal_net_write(pal_handle_t sock, const void *buf, size_t len, size_t *out_wrote);
pal_status_t pal_net_close(pal_handle_t sock);

#ifdef __cplusplus
}
#endif
#endif /* GENOS_PAL_H */
