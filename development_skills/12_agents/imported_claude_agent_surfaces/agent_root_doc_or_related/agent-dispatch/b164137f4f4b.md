# GEN.OS Agent Dispatch — 27-Agent Orchestration Protocol

How to assign the Apex Engineering Corps to complex tasks.

## Agent Roster

| Tier | Agent | Color | Primary Domain |
|------|-------|-------|---------------|
| T1 | `master-orchestrator` | `#1E1B4B` | Sprint planning, MoSCoW triage |
| T1 | `apex-coordinator` | `#7C3AED` | Day-to-day routing, dependency sequencing |
| T1 | `the-architect` | `#475569` | System design, ADRs, API contracts |
| T2 | `apex-systems-architect` | `#0891B2` | Kernel/system C implementation |
| T2 | `data-infra-engineer` | `#B45309` | DB schemas, pipelines, telemetry |
| T2 | `data-infrastructure-lead` | `#64748B` | Platform infra, XORCHESTRA, service registry |
| T2 | `devops-catalyst` | `#EA580C` | CI/CD, Makefiles, ISO build, XPKG |
| T2 | `hardware-integration-engineer` | `#78716C` | NVMe/GPU/NIC/TPM kernel drivers |
| T3 | `system-signal-engine` | `#059669` | Telemetry, signal scoring, metrics |
| T3 | `event-horizon-agent` | `#4338CA` | TCP state machines, CRDT, protocols |
| T3 | `intelligence-lead` | `#2563EB` | XMIND inference, ML models, GGUF |
| T3 | `intelligence-lead-v2` | `#1E40AF` | Causal graphs, advanced AI research |
| T3 | `edge-ai-optimizer` | `#06B6D4` | On-device quantization, Q4_0 tuning |
| T4 | `platform-integrity-auditor` | `#F97316` | Compile count, cppcheck, policy |
| T4 | `guardian-sentinel` | `#DC2626` | XKABI rights, threat models, security |
| T4 | `reliability-security-sentinel` | `#9F1239` | Hardening, post-mortems, P0/P1 fixes |
| T4 | `test-forge` | `#16A34A` | All 10 test types, RFC-002, conformance |
| T4 | `resilience-architect` | `#D97706` | Fault tolerance, crash recovery |
| T5 | `product-experience-engineer` | `#DB2777` | XFRAME UX, boot flow, accessibility |
| T5 | `design-systems-forge` | `#A855F7` | design_tokens.h, visual consistency |
| T5 | `knowledge-weaver` | `#0D9488` | ADRs, MEMORY.md, docs sync |
| T5 | `developer-experience-lead` | `#3B82F6` | Skills, tooling, workflow DX |
| T6 | `vanguard-disruptive-alchemist` | `#CA8A04` | First-principles redesign |
| T6 | `vanguard-disruptor` | `#E11D48` | Red-team, competitive analysis |
| T6 | `vanguard-innovation-scout` | `#65A30D` | SOTA research, tech scouting |
| T7 | `performance-forge` | `#C026D3` | Latency profiling, memory layout |
| T7 | `observability-nexus` | `#14B8A6` | Metrics, tracing, SLO monitoring |

## Standard Dispatch Sequences

### New Kernel Module
```
the-architect -> apex-systems-architect -> [hardware-integration-engineer if drv/]
-> guardian-sentinel -> platform-integrity-auditor -> test-forge -> knowledge-weaver
```

### New XFRAME Widget
```
product-experience-engineer -> design-systems-forge -> apex-systems-architect
-> platform-integrity-auditor -> test-forge
```

### New Platform Service (Python)
```
the-architect -> data-infra-engineer -> data-infrastructure-lead
-> guardian-sentinel -> reliability-security-sentinel
-> devops-catalyst (k8s manifest) -> test-forge
```

### Security Incident
```
guardian-sentinel [P0 triage] -> reliability-security-sentinel [fix]
-> platform-integrity-auditor [verify] -> master-orchestrator [sign-off]
```

### Sprint 3 Tracks (Parallel)
```
Track A XNET:  apex-systems-architect + hardware-integration-engineer + event-horizon-agent
Track B XSEC:  guardian-sentinel + reliability-security-sentinel + apex-systems-architect
Track C XPKG:  devops-catalyst + data-infrastructure-lead + guardian-sentinel
Coordinator:   apex-coordinator
Gate:          platform-integrity-auditor + test-forge
Sign-off:      master-orchestrator
```

## Dispatch Message Template

```
TO: [agent-name]
FROM: master-orchestrator
TASK: [ID]  SPRINT: N

CONTEXT: [What exists / what it depends on — file:line references]

DELIVERABLE:
  Files: [exact paths to create/modify]
  Interface: [function signatures or endpoint specs]

CONSTRAINTS:
  - Language: [C / Python / TypeScript]
  - [Kernel: freestanding, PAL API only, static pools, no malloc]
  - Compile check: clang -target x86_64-unknown-none-elf -Werror -fsyntax-only
  - Security: [specific rights or auth requirements]

ACCEPTANCE:
  [ ] [Measurable criterion]
  [ ] Compile check passes
  [ ] guardian-sentinel cleared

HANDOFF TO: [next agent]  WHEN: [condition]
```
