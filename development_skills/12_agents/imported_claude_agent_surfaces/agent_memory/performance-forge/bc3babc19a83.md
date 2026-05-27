# Apex Performance Forge -- Agent Memory

Notes:
- Agent threads always have their cwd reset between bash calls; use absolute file paths only.
- Avoid emojis. No colon before tool calls.

## Full-System Benchmark (2026-04-11)

- [Full report](full-system-benchmark-2026-04-11.md) -- 13-subsystem deep analysis, 302K LOC C
- XMIND 3B: ~9.4 tok/s (AVX2), 2.53 GB total (weights+KV@2048), fits in 16 GB
- XMIND 13B: ~1.8 tok/s, 10.6 GB (marginal), 70B+ impractical on 16 GB
- Syscall: ~40 ns null, ~80-150 ns typical; kmalloc: ~25 ns hot slab
- Boot: ~3.5-6.1 sec total (WITHIN 12s budget)
- OS idle: ~58 MB RAM; AI active: ~2.53 GB
- TOP BUG: XSTORE WAL checkpoint threshold (48000) > ring size (4096) -- will overflow
- TOP P0: TCP ring byte-by-byte (12x slow); XMIND silu/softmax not AVX2
- Untapped HW: SSE4.2 CRC32C, AVX2 for silu/softmax/rmsnorm, GPU compute

## BSS Crisis 286MB Analysis (2026-03-29)

- [Full report](bss-crisis-286mb-analysis.md) -- Complete BSS breakdown, 24 arrays cataloged
- ROOT CAUSE: XSTORE WAL ring 65536 * 4384B = 274 MB (95% of BSS)
- Fix: WAL_RING_SIZE 65536->4096 (-257 MB), TCP_TCB_MAX 128->32 (-8.6 MB), font arena heap (-4 MB)
- Post-fix BSS: ~16 MB (from 286 MB), well within 256 MB kern_span
- P0-MEM-01 from Sprint 13 STILL OPEN -- same finding, same fix

## Docker Boot Benchmark (2026-03-29)

- [Full report](docker-boot-benchmark-2026-03-29.md) -- 5-run diagnostic on genos-live:latest
- macOS arm64 -> Rosetta -> QEMU TCG = double-emulation, ELF kern_span fails
- AetherBoot stages 0-3 PASS (serial, TPM, GOP, ACPI, memmap, XKABI, TSC, KASLR)
- KASLR: 4/5 unique 2MB-aligned slides, RDRAND confirmed working
- Codebase: 281 .c + 96 .h = 181,668 LOC; xenos.elf 1.3 MB / BOOTX64.EFI 35 KB
- For reliable benchmarking: use native x86_64 + KVM (GitHub Codespaces)

## Build Speed Phase 2+3: PCH + Unity Builds (2026-03-28)

- [Full report](build-speed-pch-unity.md) -- PCH for xenos.h + 3 unity files replacing 29 compilations
- PCH: `$(BUILD)/xenos.pch` from xenos.h+pal.h, used via `-include-pch` on kernel .o rules
- Unity: `UNITY_BUILD=1` -> 119 objects (vs 145 normal), 18% fewer compiler invocations
- Static collision fix: `net/xnet/include/xnet_mem.h` extracts 8 copy-pasted utility inlines from 11 XNET files
- AES-NI and XNET drivers stay separate (different CFLAGS / hardware statics)

## Boot Deep Analysis (2026-03-28)

- [Full report](boot-deep-analysis-2026-03-28.md) -- Cycle-accurate 14-step kernel + 10-stage GENSD analysis
- QEMU/TCG-to-bare-metal scaling: 657x (7 MHz vs 4.6 GHz)
- Projected bare-metal kernel init: 17.2ms (79M cycles) -> 795 us after optimizations
- Top 3 kernel bottlenecks: PMM buddy O(N) insert (42%), LAPIC 10ms calibration (32%), cap-table (23%)
- Top 3 GENSD bottlenecks: Shell 552ms, Network 485ms (defer), Display 441ms
- BSS 209MB zeroed twice (AetherBoot + entry.asm 4MB cap) -- demand-page saves 7ms
- Plan: `/Users/desmondearly/.claude/plans/idempotent-leaping-pearl-agent-a17f2cba302d309a4.md`

## Boot Speed Wave 1 (2026-03-27)

- [Full report](boot-speed-wave1.md) — 3 AetherBoot optimizations, ~185-235ms savings
- OPT-1.1: CPUID 0x15/0x16 TSC calibration replaces 100ms BS->Stall (-100ms)
- OPT-1.2: Deferred serial 4KB ring buffer, 39 calls deferred, 17 FATAL stay blocking (-80-120ms)
- OPT-1.3: rep movsq/stosq for ELF copy + BSS zero (-5-15ms)
- Handoff struct extended: deferred_serial_phys + deferred_serial_len (both aetherboot + xenos.h)
- P1-TSC-01 from Sprint 13 audit: RESOLVED by OPT-1.1
- Compile: clang --target=x86_64-unknown-windows -Werror PASS (0 warnings)
- TODO: kernel-side drain in kmain Step 1

## Sprint 44 Phase 2e Performance Audit (2026-03-21)

- Full report: `.claude/agent-memory/performance-forge/sprint44-perf-audit.md`
- Scope: 64 new TSX (28,347 LOC) + 1 C test (phase2e_tests.c)
- Verdict: 3 P0 FIXED, 5 P1 documented, 8 P2 advisory
- P0-REACT-01: NearbyShare.tsx orphaned setInterval in sendFile/handleAccept (FIXED)
- P0-REACT-02: NetworkDiagnostics.tsx orphaned setTimeout in traceroute/DNS (FIXED)
- P0-REACT-03: ScreenCast.tsx orphaned setTimeout in handleConnect (FIXED)
- Anti-pattern: setInterval/setTimeout in event handlers without ref tracking
- XFRAME node budget: UNAFFECTED (TSX renders in Chromium DOM, not XFRAME pool)
- C test BSS: 33.4 KB (reasonable), stack allocs all under 100 bytes
- Bundle: ~250 KB minified (acceptable)
- backdrop-filter blur(24px) on ActivationLock: ~4-8ms GPU, acceptable for static

## Sprint 40 XISC Native Layer Performance Audit (2026-03-20)

- Full report: `.claude/agent-memory/performance-forge/sprint40-xisc-native-perf-audit.md`
- ADR: `docs/adr/ADR-S40-PERF-01-native-layer-performance.md`
- Benchmark: `xisc/benchmarks/bench_native_layer.c`
- Verdict: ALL 6 OPTs IMPLEMENTED (2026-03-20) -- was CONDITIONAL GO
- Codebase: 14 files in xisc/runtime/xkabi_native/, 10 files modified
- Total static memory: ~3.5 MB -> ~732 KB (79% reduction via OPT-06 audit ring)
- OPT-01: Object lookup O(1) via obj_index in handle entry (was O(N))
- OPT-02: Handle alloc O(1) via freelist (was O(N) scan)
- OPT-03: Object alloc O(1) via freelist (was O(N) scan)
- OPT-04: Channel two-phase memcpy (was byte-by-byte, ~100x speedup)
- OPT-05: Removed SPSC channel spinlock (~50ns/op saved, was correctness bug)
- OPT-06: Audit ring 65536 -> 4096 entries (saved 2.88 MB)
- Added native_object_lookup_fast() inline for O(1) object access with ABA guard
- Compilation: 14 files pass clang -ffreestanding -Werror -fsyntax-only
- Pattern: same byte-by-byte copy anti-pattern as TCP ring_write in Sprint 3

## Sprint 15 AVX2 Matmul Audit (2026-03-07)

- Full report: `.claude/agent-memory/performance-forge/sprint15-avx2-matmul-audit.md`
- Deliverable: jit/xjit/src/avx2_matmul.c (593 LOC, compiles clean)
- XJIT had ZERO SIMD support before Sprint 15
- 7 AVX2 instruction emitters + VEX encoding + CPUID detection
- Scalar Q4_0 matmul: ~1.5 GFLOPS, AVX2 float32: ~25-30 GFLOPS sustained
- Token/sec: scalar ~2-3, AVX2 ~10-15 (Llama 3.2 3B on i5-8265U)
- Boot chain: 10 sequential stages, 3 parallel pairs identified

## Sprint 13 Final E2E Audit (2026-03-07)

- Full report: `.claude/agent-memory/performance-forge/sprint13-final-perf-audit.md`
- Verdict: CONDITIONAL GO (3 P0, 4 P1, 6 P2)
- Codebase: 72,077 LOC production C
- Boot time: ~3.2s firmware-to-idle (WITHIN 12s budget)
- HPET resolution: ~70 ns/tick (14.318 MHz typical) -- WITHIN BUDGET
- Compositor: 60 FPS for typical desktop, OVER BUDGET for full-screen blend (~15-20 ms)

### P0 Blockers (Sprint 13)
- P0-MEM-01: XSTORE WAL ring = 274 MB (65536 x 4384B entries) -- reduce to 4096 entries
- P0-MEM-02: XBLOB hash index = 56 MB (1M slots) -- reduce to 16K slots
- P0-PGTABLE-01: HHDM maps only 4 GB of 8-16 GB physical RAM -- extend PDPT to 16 entries

### P1 Issues (Sprint 13)
- P1-COMP-01: Scalar blend_pixel() exceeds frame budget at full-screen damage
- P1-TIMER-01: LAPIC calibration uses volatile loop (~0.77ms not 10ms) -- wire XHPET
- P1-TSC-01: 100ms Stall avoidable via CPUID leaf 0x15 on Whiskey Lake
- P1-MEM-03: TCP TCB table = 11.5 MB (carried from Sprint 3)

### Key Memory Figures (Sprint 13)
- Kernel+drivers: ~700 KB
- XNET+XSEC: ~11.8 MB (mostly TCP TCBs)
- XSTORE+XBLOB: ~334 MB (WAL 274MB + index 56MB + cache 4MB) -- P0
- XMIND active: ~2,360 MB (weights 1.8GB + embeddings 384MB + KV cache 176MB)
- Display+Shell: ~20 MB (double FB 18MB + surfaces + fonts)
- Total idle: ~367 MB, Total AI active: ~2,727 MB
- Fits in 8 GB after P0 fixes (367-334+5 = ~38 MB idle, ~2,398 MB AI active)

### KV Cache Exact Calculation
- 2 (K+V) x 28 layers x 2048 ctx x 8 kv_heads x 96 head_dim x 4 bytes = 176,160,768 bytes = ~168 MB

## Sprint 3 Performance Audits

- Initial audit (2026-03-05): `.claude/agent-memory/performance-forge/sprint03-performance-audit.md`
- Security fix impact: `.claude/agent-memory/performance-forge/sprint03-security-fix-perf-impact.md`
- Deep audit (2026-03-06): `.claude/agent-memory/performance-forge/sprint03-deep-audit-2026-03-06.md`

### Critical Findings (carried forward to Sprint 4)

- TCP TCB table = ~11.5MB static BSS (128 TCBs * ~92KB each)
  - Recommendation: reduce to 32 TCBs + smaller buffers = ~960KB
- GHASH is bit-by-bit O(128), needs 4-bit table (4x) or PCLMULQDQ (160x)
- AES CT S-box: 70,656 iterations/block = ~177 KB/s software path
  - AES-NI: ~4 cycles/byte = ~975 MB/s -- MANDATORY for Sprint 4
  - i5-8265U (Whiskey Lake) confirmed AES-NI + PCLMULQDQ support
- ChaCha20-Poly1305 poly_scratch: 32KB STACK alloc (was static, now fixed)
  - STILL a stack overflow risk on 8-16KB kernel stacks
  - Fix: streaming Poly1305 (no scratch buffer)
- XPKG dep_graph: ~82KB STACK alloc -- will overflow kernel stack
  - Fix: static allocation or caller-provided buffer
- TCP cwnd capped at SNDBUF_SIZE (16KB) -- limits throughput on WAN
  - Fix: cap at min(65535, peer_window)
- TCP ring_write/ring_read: byte-by-byte copy (12x slower than two-phase)
- TCP no fast recovery (RFC 5681) -- falls to slow start on triple dup ACK
- IP frag table uses bool[] not bitmap: wastes 112KB
- dep_resolve conflict detection is O(V^2), graph_find_node is O(V) per call
- Total XNET+XSEC static memory: ~12.7MB reducible to ~1.7MB (87%)

## Sprint 3 TLS 1.3 Audit Log Impact (2026-03-06)
- Full report: `.claude/agent-memory/performance-forge/sprint03-tls13-audit-log-perf-impact.md`
- tls13.c has 20 xsec_audit_log calls (NOT 6): 18 error-path, 1 success, 1 lifecycle
- Normal handshake overhead: 2 calls = ~90 ns = 0.015% of 0.6 ms crypto time
- Steady-state data transfer: 0 audit calls = ZERO overhead
- audit.c write path: lock-free (atomic fetch-add), no spinlock contention
- Per-call cost: ~115 cycles = ~29 ns at 3.9 GHz
- sizeof(xsec_audit_entry_t) = 80 bytes; ring = 1024 x 80 = 80 KB (BSS)
- Ring-full behavior: overwrite oldest + increment dropped_events counter (no block)
- Thermal: 0.058 mW at 1000 calls/sec = unmeasurable
- Verdict: WITHIN BUDGET. No optimization required.

## Sprint 3 Security Fix Performance Verdicts
- P0 AES CT S-box: OVER BUDGET -- need AES-NI (P0 priority)
- P1 Ed25519 CertificateVerify: ACCEPTABLE (~175 us one-time/connection)
- P1 Hostname validation: NEGLIGIBLE (~0.15 us)
- S3 PAL syscall wiring: ACCEPTABLE (~150 ns per syscall)
- XENOS SYSCALL round-trip: ~250-400 cycles bare, ~450-800 with Spectre mitigations

## Sprint 3 P2 Hardening Performance Verdicts (2026-03-05)
- Full report: `.claude/agent-memory/performance-forge/sprint03-p2-hardening-perf-impact.md`
- gf_mul CT branchless: NEGLIGIBLE (~0-5 cycles/call, may be faster due to no mispredict)
- fe10_mul carry propagation: ACCEPTABLE (+3.3 us / +1.9% per Ed25519 verify)
- Poly1305 acc_top carry: ACCEPTABLE (+1.5 us / +5.3% per 16KB TLS record)
- TCP initcwnd=10 MSS: POSITIVE (-33.2ms for 1MB@10ms RTT, -166ms@50ms RTT)
- DNS CSPRNG QID: NEGLIGIBLE (+135 ns per query, RDRAND)
- Net thermal impact: < 0.5C under sustained crypto load
- Recommended: ChaCha20-Poly1305 as default TLS 1.3 cipher until AES-NI lands

## Key Constants (Sprint 3)
- TCP_TCB_MAX=128, TCP_RCVBUF/SNDBUF=16KB, TCP_REXMIT_QUEUE_MAX=32
- TCP_REORDER_MAX=8, TCP_MSS_DEFAULT=1460
- FRAG_TABLE_MAX=16, FRAG_MAX_SIZE=64KB
- GOSSIP_MAX_NODES=256, GOSSIP_INDIRECT_K=3
- XPKG_MAX_GRAPH_NODES=512, XPKG_MAX_DEPS_PER_PKG=16

## Kernel Skills Extraction (2026-03-31)

- [Full catalog](skills-extraction-2026-03-31.md) -- 57 skills from 20 kernel files (core/mm/drv/sched/fs)
- Categories: 12 debugging, 12 performance, 13 hardware, 10 memory, 6 security, 4 build
- Top perf: PMM O(1) buddy (250x), CPUID LAPIC calib (-10ms), 2MB HHDM (512x TLB), slab O(1), naked ctx switch
- Top debug: RDTSC boot telemetry, COM1 progressive signals, zero-dep panic, watchdog, _Static_assert
- Top hardware: volatile MMIO, HPET double-read, PCI cfg #1, TPM TIS FIFO, EC IBF/OBF, NVMe phase bit
- Top memory: HHDM direct map, in-page metadata, buddy coalescing, zone-aware DMA32, vDRAM zero-page fast path

## Project Conventions
- Language policy: Python, TypeScript, C ONLY
- All crypto: freestanding C, no libc, no third-party
- PAL API: pal_spin_lock/unlock, pal_random_bytes, pal_time_now_ns
- XSEC API: xsec_memcpy, xsec_memset, xsec_secure_zero, xsec_ct_eq
- Build: clang -target x86_64-unknown-none-elf -ffreestanding -Werror -fsyntax-only
- PAL-Aether pal_time_now_ns uses RDTSC directly (no syscall) -- good design
- PAL handle table: 65536 entries, spinlock-protected, static allocation
