/* xnet.h — consumer-build XNET shim (Berkeley sockets). */
#ifndef GENOS_XNET_H
#define GENOS_XNET_H

#include "pal.h"
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int32_t xnet_status_t;
#define XNET_OK              0
#define XNET_ERR_INVAL      -1
#define XNET_ERR_IO         -2
#define XNET_ERR_AGAIN      -3
#define XNET_ERR_CLOSED     -4

typedef enum { XNET_AF_INET = 2, XNET_AF_INET6 = 10 } xnet_af_t;
typedef enum { XNET_SOCK_STREAM = 1, XNET_SOCK_DGRAM = 2 } xnet_sock_type_t;

typedef int32_t xnet_socket_t;
#define XNET_INVALID_SOCKET (-1)

typedef struct {
    uint16_t port;
    uint32_t addr_v4;   /* host byte order */
} xnet_sockaddr_t;

typedef struct {
    uint16_t sin_family;
    uint16_t sin_port;
    uint32_t sin_addr;
} xnet_sockaddr_in_t;

uint16_t      xnet_htons(uint16_t h);
xnet_socket_t xnet_socket(xnet_af_t af, xnet_sock_type_t type);
xnet_status_t xnet_bind(xnet_socket_t s, const xnet_sockaddr_t *addr);
xnet_status_t xnet_listen(xnet_socket_t s, int backlog);
xnet_socket_t xnet_accept(xnet_socket_t s, xnet_sockaddr_t *out_peer);
xnet_status_t xnet_connect(xnet_socket_t s, const xnet_sockaddr_t *addr);
ssize_t       xnet_recv(xnet_socket_t s, void *buf, size_t len, int flags);
ssize_t       xnet_send(xnet_socket_t s, const void *buf, size_t len, int flags);
xnet_status_t xnet_close(xnet_socket_t s);
xnet_status_t xnet_set_nonblock(xnet_socket_t s, bool nonblock);
xnet_status_t xnet_setsockopt(xnet_socket_t s, int level, int optname, const void *val, size_t len);
xnet_status_t xnet_ipv6_set_forwarding(bool enable);

#ifdef __cplusplus
}
#endif
#endif
