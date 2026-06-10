/* xnet_posix.c — Berkeley sockets backing. */
#include "xnet.h"
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

static int af_to_posix(xnet_af_t af) { return (af == XNET_AF_INET6) ? AF_INET6 : AF_INET; }
static int type_to_posix(xnet_sock_type_t t) { return (t == XNET_SOCK_DGRAM) ? SOCK_DGRAM : SOCK_STREAM; }

uint16_t xnet_htons(uint16_t h) { return htons(h); }

xnet_socket_t xnet_socket(xnet_af_t af, xnet_sock_type_t type) {
    int s = socket(af_to_posix(af), type_to_posix(type), 0);
    if (s < 0) return XNET_INVALID_SOCKET;
    int one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    return (xnet_socket_t)s;
}

xnet_status_t xnet_bind(xnet_socket_t s, const xnet_sockaddr_t *addr) {
    if (s < 0 || !addr) return XNET_ERR_INVAL;
    struct sockaddr_in sin;
    memset(&sin, 0, sizeof(sin));
    sin.sin_family      = AF_INET;
    sin.sin_port        = htons(addr->port);
    sin.sin_addr.s_addr = htonl(addr->addr_v4);
    if (bind(s, (struct sockaddr *)&sin, sizeof(sin)) != 0) return XNET_ERR_IO;
    return XNET_OK;
}

xnet_status_t xnet_listen(xnet_socket_t s, int backlog) {
    if (s < 0) return XNET_ERR_INVAL;
    if (listen(s, backlog) != 0) return XNET_ERR_IO;
    return XNET_OK;
}

xnet_socket_t xnet_accept(xnet_socket_t s, xnet_sockaddr_t *out_peer) {
    if (s < 0) return XNET_INVALID_SOCKET;
    struct sockaddr_in sin;
    socklen_t slen = sizeof(sin);
    int c = accept(s, (struct sockaddr *)&sin, &slen);
    if (c < 0) return XNET_INVALID_SOCKET;
    if (out_peer) {
        out_peer->port    = ntohs(sin.sin_port);
        out_peer->addr_v4 = ntohl(sin.sin_addr.s_addr);
    }
    return (xnet_socket_t)c;
}

xnet_status_t xnet_connect(xnet_socket_t s, const xnet_sockaddr_t *addr) {
    if (s < 0 || !addr) return XNET_ERR_INVAL;
    struct sockaddr_in sin;
    memset(&sin, 0, sizeof(sin));
    sin.sin_family      = AF_INET;
    sin.sin_port        = htons(addr->port);
    sin.sin_addr.s_addr = htonl(addr->addr_v4);
    if (connect(s, (struct sockaddr *)&sin, sizeof(sin)) != 0) return XNET_ERR_IO;
    return XNET_OK;
}

ssize_t xnet_recv(xnet_socket_t s, void *buf, size_t len, int flags) {
    if (s < 0 || !buf) return XNET_ERR_INVAL;
    ssize_t n = recv(s, buf, len, flags);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return XNET_ERR_AGAIN;
    if (n == 0) return XNET_ERR_CLOSED;
    return n;
}

ssize_t xnet_send(xnet_socket_t s, const void *buf, size_t len, int flags) {
    if (s < 0 || !buf) return XNET_ERR_INVAL;
    ssize_t n = send(s, buf, len, flags);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return XNET_ERR_AGAIN;
    return n;
}

xnet_status_t xnet_close(xnet_socket_t s) {
    if (s < 0) return XNET_OK;
    close(s);
    return XNET_OK;
}

xnet_status_t xnet_set_nonblock(xnet_socket_t s, bool nonblock) {
    if (s < 0) return XNET_ERR_INVAL;
    int flags = fcntl(s, F_GETFL, 0);
    if (flags < 0) return XNET_ERR_IO;
    if (nonblock) flags |= O_NONBLOCK; else flags &= ~O_NONBLOCK;
    if (fcntl(s, F_SETFL, flags) < 0) return XNET_ERR_IO;
    return XNET_OK;
}

xnet_status_t xnet_setsockopt(xnet_socket_t s, int level, int optname, const void *val, size_t len) {
    if (s < 0 || !val) return XNET_ERR_INVAL;
    if (setsockopt(s, level, optname, val, (socklen_t)len) != 0) return XNET_ERR_IO;
    return XNET_OK;
}

xnet_status_t xnet_ipv6_set_forwarding(bool enable) { (void)enable; return XNET_OK; }
