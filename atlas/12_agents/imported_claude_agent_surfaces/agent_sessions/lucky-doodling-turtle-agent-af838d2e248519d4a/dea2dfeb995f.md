# Signal Validation Report Plan — RFC-002 v5 Technologies

## Task
Perform signal validation for the integration of 10 new RFC-002 v5 technologies into GEN.OS.

## Source Files Analyzed
1. `/tmp/rfc002_analysis/gen-os/tools/monitoring/thermal_guardian.py` — ThermalGuardian, DeviceThermal, 3-state thermal signal
2. `/tmp/rfc002_analysis/gen-os/tools/ep_rdma/fabric_energy_controller.py` — EPRDMAController, FabricMetrics, 4-state fabric energy telemetry
3. `/tmp/rfc002_analysis/gen-os/kernel/vdram/contra_rotation.c` — contra_rotation_sched, cr_device, CR_PHASE_COMPUTE/COOLDOWN/LOAD
4. `platform/services/telemetry/` — 5-module telemetry pipeline (baseline, causal triples, TEI, signal scorer, variance decomp)
5. `platform/services/provenance/app.py` — Bitemporal PostgreSQL provenance with SHA-256 audit chain

## Identified RFC-002 Signal Sources
From the 3 new files, signals map to these technology domains:

### Technology 1: Thermal Guardian (thermal_guardian.py)
- Signals: gpu_temp_c, cpu_temp_c, per-device thermal phase (OK/WARN/CRITICAL), alert state
- Thresholds: SAFE=60°C, WARN=75°C, CRITICAL=80°C
- Polling: 500ms interval, writes /tmp/genos_thermal_state.json

### Technology 2: EP-RDMA Controller (fabric_energy_controller.py)
- Signals: current_lanes (2-8), FabricState (DENSE/IDLE/COOLDOWN/TRANSITION), total_energy_joules, baseline_energy_joules, savings_pct, lane_transitions, idle_time_s, dense_time_s, current_power_w
- Gate criterion: >20% power savings for Demo 9
- Claimed range: 25-40% overall savings → ANTI-OVER-OPTIMIZATION AUDIT REQUIRED

### Technology 3: Contra-Rotation Scheduler (contra_rotation.c)
- Signals: per-device CR_PHASE (COMPUTE=0, COOLDOWN=1, LOAD=2), thermal_throttles counter, total_schedules, nccl_last_collective_ns, current_rdma_lanes, compute_time_ns, cooldown_time_ns, load_time_ns
- Modes: consumer-thermal (HP EliteBook) and enterprise-NCCL

## Anti-Over-Optimization Concerns
1. EP-RDMA "25-40% power savings" — source is inline code comment, not measurement
2. EP-RDMA savings_pct is computed vs a fixed 400W baseline (8 lanes * 50W/lane) — this is theoretical, not empirically measured
3. 75% reduction during idle (8 lanes → 2 lanes, 400W → 100W) is mathematically correct BUT requires actual idle utilization ≥ 30% of run time to achieve 25% overall
4. POWER_PER_LANE_W = 50W empirical constant — no source or confidence interval cited
5. DPU simulation mode returns simulated data by default (device not present on HP EliteBook)
6. Thermal Guardian simulation mode returns random.uniform data — NOT real hardware

## TEI Impact Analysis
Existing TEI uses 5 metrics: cpu_utilization, memory_utilization, io_wait, service_response_time, compositor_frame_time
- New signals do NOT map directly to any existing TEI metric — they require new TEI dimensions
- Thermal phase changes WILL affect cpu_utilization and compositor_frame_time
- EP-RDMA lane scaling CANNOT affect HP EliteBook TEI directly (no BlueField-4 DPU present on consumer device)
- Contra-rotation load phase affects disk_io_latency via vDRAM prefetch

## Signal Gate Analysis (Protocol 3)
For each signal, Telemetry Vector + Event Vector must BOTH align:
- Thermal CRITICAL (GPU ≥ 80°C) → HIGH intensity, should PASS gate
- Thermal WARN (GPU 75-80°C) → MEDIUM intensity, requires additional confirmation
- EP-RDMA savings_pct → MARGINAL until out-of-sample validation (over-opt risk)
- Contra-rotation phase transition → Medium intensity, event vector available

## Provenance Bitemporal Integrity
- Provenance service has proper action_time vs record_time separation
- SHA-256 audit chain with serialized writes (_chain_lock) — VERIFIED
- Bitemporal constraint for benchmark replay: valid_time ≤ sim_ts AND transaction_time ≤ sim_ts maps to action_time/record_time — SUPPORTED

## Output
Full SYSTEM SIGNAL REPORT in standard format for all new RFC-002 signals.
