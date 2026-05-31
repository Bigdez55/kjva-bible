# Sprint 3 XNET Networking Stack Audit — 2026-03-06

## Batch: SSE-S3-XNET-AUDIT-2026-0306
- Scope: 12 files, 7,406 LOC in net/xnet/
- TEI: 2.35, R2: 0.72, Gate: PASS
- Grade: B+
- Findings: 3 P0, 5 P1, 5 P2, 5 P3 (18 total)

## Key Results
- RFC 793: 11/11 states, 16/16 transitions, FULL COMPLIANCE
- Jacobson/Karels RTO: RFC 6298 CORRECT
- CRC32 race fix: VERIFIED (double-checked locking + branchless)
- DNS pointer compression: 3-layer defense, max 64 jumps
- UDP ephemeral port: pal_random_bytes() per RFC 6056
- ARP state machine: 4 states (FREE/PENDING/RESOLVED/STALE) all correct
- DNS cache eviction: LRU by cached_at_ns timestamp

## P0 Findings
1. tcp.c:332 - TCP ephemeral port is SEQUENTIAL (not randomized like UDP)
2. tcp.c:1042 - xnet_tcp_accept() unbounded spin-wait (no timeout)
3. ip4.c:428 - Fragment reassembly singleton g_frag_out_buf serializes all streams

## P1 Findings
1. dns.c:256 - DNS resolver single-query-at-a-time (global g_dns_pending)
2. socket.c:106 - UDP recv is single-datagram buffer (last-wins)
3. gossip.c:162 - gossip_rand() PRNG load/store race (still OPEN from S3 audit)
4. mdns.c:458 - mDNS never parses query names, responds to ALL queries
5. gossip.c:69 - xnet_htonll() swaps halves incorrectly (interop risk)

## Performance
- Theoretical max single-connection: ~256 Mbps (16KB cwnd cap)
- Wire speed possible with 64KB buffers
- Primary bottleneck: 16KB cwnd + single g_tcp_lock
- Byte-at-a-time ring buffer copy ~40x slower than SSE memcpy

## Connection Limits
- TCP: 128 TCBs, ~92KB each, ~11.5MB total
- Sockets: 256 descriptors
- UDP: 64 sockets
- ARP: 256 entries, 30-min TTL
- Routes: 32 entries, longest-prefix-match
- DNS: 128 cache entries

## Architecture Notes
- File layout: core/ link/ inet/ transport/ api/ app/ mesh/ include/
- All inline helpers (memset/memcpy) duplicated across 11 .c files
- No TLS integration in socket API (Sprint 4 deliverable)
- No IPv4 forwarding (packets not for us are dropped)
- gossip.c uses SWIM protocol (not Phi-accrual as spec'd)
