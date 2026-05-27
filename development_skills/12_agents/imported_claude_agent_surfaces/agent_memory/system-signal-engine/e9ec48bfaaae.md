# Gaming Design Vision Compliance Audit — 2026-03-02

## Audit Scope
5 gaming-centric design mandates from GEN.OS design vision vs codebase evidence.

## Verdict Summary
| Mandate | Verdict |
|---------|---------|
| 1. Game-mode resource allocation | MISSING |
| 2. No VMP/Hyper-V overhead | PARTIAL |
| 3. Background resource minimization | MISSING |
| 4. Handheld PC (TDP/fan/controller) | MISSING |
| 5. Linux gaming OS standard | MISSING |

## Key Quantitative Findings

### Idle RAM Baseline
- Kernel + systemd: ~100 MB
- k3s + containerd: ~500 MB
- Ollama (model loaded): ~2250 MB
- Ollama (service only): ~40 MB
- labwc + pipewire + NM: ~60 MB
- 6 Python services: ~90 MB
- Other (bluez, dbus, upower): ~20 MB
- **Total (model loaded): ~3060 MB** (38% of 8 GB)
- **Total (model unloaded): ~810 MB** (10% of 8 GB)
- Comparable to Windows 11 when Ollama model loaded

### Background Services at Boot: 20+
- 9 custom GEN.OS services
- k3s + containerd (2)
- Ollama (1)
- System (NM, pipewire, bluez, dbus, upower, etc.)
- 7-9 services stoppable during gaming, but NO stop mechanism exists

### Scheduler Analysis
- contra_rotation.c: thermal-only phases (COMPUTE/COOLDOWN/LOAD)
- Two modes: consumer-thermal, enterprise-NCCL
- NO game mode, NO foreground priority, NO cpufreq integration
- cpufreq.h included in linux-validation version but unused
- PAL-native version has no frequency concept at all

### Missing Gaming Infrastructure (zero code exists)
- Game/high-demand app detection
- Service suppression ("game mode" target)
- Proton / Wine / DXVK / gamescope
- Controller/gamepad drivers (only intel_igpu.c + nvme.c in drv/)
- TDP/RAPL control
- Fan curve control (HP ACPI may not expose)
- VRR/adaptive sync configuration
- Direct scanout / compositor bypass
- Performance overlay (MangoHud)
- Immutable rootfs

### What Does Exist (partial credit)
- mesa-vulkan-drivers in packages.list (Vulkan prerequisite)
- libinput-tools in packages.list (basic input)
- DRM/KMS with VSync (xdisp_drm_wait_vsync)
- No Hyper-V (Linux, not Windows)
- Thermal monitoring (thermal_guardian + contra_rotation)

## Signal Metrics
- TEI: 2.65 (PASS)
- R2: 0.82 (ANALYZABLE)
- Gate: PASS (both vectors aligned)
- Nature: Architectural direction gap, not implementation bug

## Remediation Priority
- P0: game-mode systemd target, k3s soft dependency, cpufreq integration
- P1: Proton/DXVK/gamescope packaging, VRR enable
- P2: RAPL TDP, controller drivers, fan curve
- P3: merge dual thermal poll, Ollama lazy load, immutable root
