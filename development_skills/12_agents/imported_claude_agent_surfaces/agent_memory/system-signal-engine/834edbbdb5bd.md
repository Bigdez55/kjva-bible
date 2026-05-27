# Sprint 3 XNET RFC Conformance Audit — 2026-03-06

## Batch: SSE-S3-RFC-2026-0306-001
- TEI: 2.15, R2: 0.74, Gate: PASS
- 62 requirements checked: 49 PASS, 3 PARTIAL, 7 FAIL, 2 DOC LIMIT
- Aggregate conformance: 80.6%

## Per-Protocol Scores
- ARP (RFC 826): 11/11 = 100% -- production-grade
- TCP (RFC 793/5681/6298/6928): 15/18 = 85.7%
- SWIM (Iyer 2002): 8/10 = 80.0%
- DNS (RFC 1035/5452): 9/12 = 77.8%
- mDNS (RFC 6762): 6/11 = 60.0% -- lowest, needs Sprint 4 work

## Critical Non-Compliant Items (9 total)
- NCF-01 (TCP HIGH): Nagle not implemented; opt_nodelay field exists, zero logic
- NCF-02 (TCP MED): Zero window probe not implemented; connection stalls on window=0
- NCF-03 (TCP LOW): Fast recovery sets cwnd=MSS not ssthresh
- NCF-04 (DNS MED): SERVFAIL silently dropped, should retry next nameserver
- NCF-05 (DNS MED): CNAME chase declared but not implemented
- NCF-06 (mDNS HIGH): Conflict resolution stuck permanently; no rename+re-probe
- NCF-07 (mDNS MED): Responds to ALL queries, not just matching names
- NCF-08 (mDNS LOW): 1 initial announcement, RFC requires 2
- NCF-09 (SWIM MED): PING_REQ relay handler empty; indirect probing non-functional

## P0 for Sprint 4
- NCF-06: mDNS conflict resolution (2h)
- NCF-09: SWIM PING_REQ relay forwarding (1h)

## File Paths Audited
- net/xnet/transport/tcp.c (1342 lines)
- net/xnet/app/dns.c (624 lines)
- net/xnet/mesh/mdns.c (560 lines)
- net/xnet/mesh/gossip.c (809 lines)
- net/xnet/link/arp.c (500 lines)
- net/xnet/include/xnet.h (708 lines)

## Key Patterns Confirmed
- ISN generation: clock + counter + random (RFC 6528 compliant)
- Jacobson/Karels RTO: alpha=1/8, beta=1/4 exactly matching RFC 6298
- initcwnd = 10*MSS (RFC 6928)
- DNS QID: pal_random_bytes (Kaminsky fix, RFC 5452)
- ARP merge-flag pattern: only creates entry when targeted (anti-poisoning)
- SWIM incarnation override on self-SUSPECT
- gossip_rand PRNG race still open (CAS loop needed, per S3-PKG-02)
