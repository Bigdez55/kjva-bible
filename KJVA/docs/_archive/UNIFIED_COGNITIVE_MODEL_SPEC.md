# Unified Cognitive Model — Technical Specification

> GEN.OS · AI Subsystem · Cognitive Architecture Doctrine  
> SPDX-License-Identifier: LicenseRef-Proprietary  
> Copyright (c) 2026 GEN.OS Project. All rights reserved.  
> Last revised: 2026-05-27

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architectural Pillars](#2-architectural-pillars)
3. [Directory Structure](#3-directory-structure)
4. [The Model — Specification](#4-the-model--specification)
5. [Model Guardrails — Constitution and Governance](#5-model-guardrails--constitution-and-governance)
6. [Heptagon — 7-Layer Cognitive Architecture](#6-heptagon--7-layer-cognitive-architecture)
7. [Memory Hierarchy](#7-memory-hierarchy)
8. [XMIND — Inference Engine](#8-xmind--inference-engine)
9. [XTTS — Accessibility Engine](#9-xtts--accessibility-engine)
10. [GEN — Companion Interface](#10-gen--companion-interface)
11. [Multi-Layer Conversation Protocol](#11-multi-layer-conversation-protocol)
12. [IPC Protocol](#12-ipc-protocol)
13. [API Surface](#13-api-surface)
14. [Configuration](#14-configuration)
15. [Build and Compilation](#15-build-and-compilation)
16. [Testing](#16-testing)
17. [Performance Targets](#17-performance-targets)
18. [Known Issues](#18-known-issues)
19. [Appendix A — Full Conversation Flow Diagram](#appendix-a--full-conversation-flow-diagram)
20. [Appendix B — Invariant Registry](#appendix-b--invariant-registry)

---

## 1. Overview

The GEN.OS AI subsystem is a privacy-first, on-device cognitive stack delivering
natural language inference, governed reasoning, persistent memory, and text-to-speech
synthesis. No cloud services are required. The system runs across desktop, mobile,
console, and container form factors. The HP EliteBook x360 1040 G4 is the primary
validated hardware target.

This specification describes the **Unified Cognitive Model** architecture: a design
in which all governance, memory, context retrieval, routing, enforcement, and
adversarial checking responsibilities are carried by a **single nameless neutral
model process** — hereafter referred to as **the model** — rather than distributed
across multiple named agent daemons.

The model is intentionally characterless. It holds no identity, no name, no
personality, and no domain allegiance. Its sole function is to serve the cognitive
pipeline correctly, enforce invariants without bias, and route inference to XMIND.
Every interaction is governed by the Heptagon 7-layer framework executing inside
the model process. Every output carries a lineage record. Every write is quality-gated.

The system is organized around four pillars:

| Pillar | Layer | Language | Purpose |
|---|---|---|---|
| **Heptagon** | Structure | Python, C | Seven cognitive layers (L1–L7) governing every inference cycle |
| **SoulManager** | Identity | Python, C | Five-layer memory hierarchy with AES-256-GCM persistence |
| **The Model** | Law + Routing | Python | Governance, enforcement, context retrieval, routing — unified process |
| **XMIND** | Intelligence | C (freestanding) | Forward pass, sampling, tokenization, quantization — zero libc |

Together these four pillars and the XTTS accessibility engine span approximately
**28,000 lines of original code** across 62+ files in three languages (C, Python,
TypeScript). No Go, no Rust, no Java.

---

## 2. Architectural Pillars

### 2.1 Heptagon (Structure)

The Heptagon is the structural definition of what it means to process a cognition
cycle in GEN.OS. It is not a library. It is not optional. Every inference cycle — from
receiving a user message to committing the response to persistent memory — passes
through all seven layers in sequence.

The Heptagon defines:

- The **layer contract** each stage must satisfy before the next fires
- The **trace record** emitted on every cycle (L4 Instrumentation)
- The **quality metrics** evaluated after every cycle (L5 Evaluation)
- The **feedback path** that modifies sampler parameters (L6 Calibration)
- The **invariant gates** that can halt generation mid-sequence (L7 Enforcement)

The Heptagon harness executes inside the model process (Python) and is mirrored
at the C level inside XMIND via hook callbacks fired at pre-inference, per-token,
and post-inference boundaries. The two mirrors share no state; they share a contract.

### 2.2 SoulManager (Identity)

SoulManager is the five-layer memory hierarchy that gives the system continuity
across sessions. All memory is stored and retrieved by the model process internally.
Persistence is backed by XSTORE B-tree (primary) or JSONL journal (fallback).
All stored content is encrypted with AES-256-GCM keyed per-session.

Memory layers in order of volatility:

```
register   → per-token working buffer        (in-process, RAM only)
session    → within-session recall           (in-process, evicted on shutdown)
episodic   → cross-session event memory      (persisted, XSTORE)
semantic   → extracted concept graph         (persisted, XSTORE)
archival   → long-term compressed store      (persisted, XSTORE + JSONL fallback)
```

### 2.3 The Model (Law + Routing)

The model is the single neutral process that replaced the distributed multi-daemon
council architecture. It owns all responsibilities that were previously distributed:

- Context retrieval from memory layers
- RT4 salience scoring and shard ranking
- Governance invariant enforcement
- Adversarial self-check pass
- Token and compute budget tracking
- Routing decisions to XMIND
- Write-back to persistent memory
- Telemetry emission

The model exposes a single HTTP endpoint. It has no personality. It has no name.
It is referred to throughout the system as "the model" or, in code, as `model`.
Its configuration is purely behavioral: timeouts, thresholds, budget limits,
invariant definitions, and memory backend paths.

### 2.4 XMIND (Intelligence)

XMIND is the original GEN.OS freestanding C inference engine. It executes the
actual forward pass: tokenization, weight loading, transformer attention, sampling,
and token generation. XMIND owns intelligence and only intelligence. It does not
own memory, governance, identity, or routing. Those are delegated to the model
process via function call or IPC.

XMIND is pluggable: a 16-slot artifact interpreter registry allows multiple model
families to register a vtable (`detect`, `build_config`, `map_tensor`, `validate`).
Slot 0 is occupied by the Llama family interpreter. Slots 1–15 are open.

---

## 3. Directory Structure

```text
ai/
├── README.md
│
├── xmind/                              XMIND inference engine (C, freestanding)
│   ├── include/                        15 public headers  (2,924 LOC)
│   │   ├── xmind.h                     659  — master header: API, types, constants
│   │   ├── xmind_artifact_interp.h     171  — interpreter vtable + registry API
│   │   ├── xmind_context.h             124  — context session IPC types
│   │   ├── xmind_gguf.h                292  — neutral GGUF catalog types
│   │   ├── xmind_heptagon.h            122  — Heptagon hook API (L1–L7)
│   │   ├── xmind_heptagon_harness.h    164  — 7-phase harness executor types
│   │   ├── xmind_http.h                 81  — HTTP inference server API
│   │   ├── xmind_lineage.h             213  — lineage delta ring types
│   │   ├── xmind_materialize.h         223  — weight embodiment + memory budget
│   │   ├── xmind_model_spec.h          173  — XMIND-1 native model spec
│   │   ├── xmind_telemetry.h            78  — telemetry emission API
│   │   ├── xmind_tensor_roles.h        112  — named tensor role constants
│   │   ├── xmind_writeback.h           200  — quality-gated persistence API
│   │   ├── xmtk.h                      132  — toolkit shared primitives
│   │   └── r1_per.h                    180  — R1_PER perception API
│   ├── src/                            23 implementation files  (12,137 LOC)
│   │   ├── xmind.c                     358  — init, alloc, shutdown, singleton
│   │   ├── inference.c                 770  — session, RoPE, generation pipeline
│   │   ├── transformer.c               354  — GQA attention + SwiGLU FFN
│   │   ├── tensor.c                    411  — SIMD dispatch, math primitives
│   │   ├── sampler.c                   229  — greedy + nucleus sampling
│   │   ├── tokenizer.c                 849  — BPE + FNV-1a hash tables
│   │   ├── pretokenizer.c              598  — GPT-4 regex pre-tokenizer
│   │   ├── quantize.c                  651  — Q4_0 + Q4_K_M quant/dequant
│   │   ├── weights_loader.c            972  — parse → detect → load orchestrator
│   │   ├── xmind_http.c                729  — HTTP/1.1 server over XNET TCP
│   │   ├── gguf_reader.c               740  — neutral GGUF v1–v3 catalog parser
│   │   ├── interp_llama.c              379  — Llama family interpreter (slot 0)
│   │   ├── interp_registry.c           144  — 16-slot pluggable registry
│   │   ├── heptagon.c                  646  — L1–L7 C bridge + hook dispatch
│   │   ├── harness.c                   483  — 7-phase harness executor
│   │   ├── context_bridge.c            739  — 5-layer memory bridge (IPC TCP)
│   │   ├── telemetry.c                 266  — dual emission: audit ring + mesh
│   │   ├── materialize.c               441  — classical/sparse/paged embodiment
│   │   ├── lineage.c                   294  — 256-delta ring, 64 domains
│   │   ├── writeback.c                 368  — quality-gated persistence
│   │   ├── r1_per.c                  1,706  — R1_PER perception engine
│   │   ├── neon_dot.c                  230  — ARM64 NEON fp32 + Q4_0 dot
│   │   └── neon_matmul.c               231  — ARM64 NEON 4×4 tiled matmul
│   └── loader/
│       └── weights_loader_mmap.c       789  — HHDM zero-copy physical mapper
│
├── genesys-ai/                         GENESYS AI Python runtime
│   └── src/                            22 files  (7,244 LOC)
│       ├── agent.py                    285  — agent lifecycle + task routing
│       ├── api.py                      427  — FastAPI HTTP surface
│       ├── workspace.py                299  — workspace session management
│       ├── cognitive_pipeline.py       535  — 7-stage pipeline driver
│       ├── heptagon/
│       │   ├── state_machine.py        294  — IDLE→LISTENING→…→IDLE FSM
│       │   ├── evaluation.py           406  — L5: cross-cycle quality tracking
│       │   ├── calibration.py        1,138  — L6: Brier-score + 8-stage cycle
│       │   ├── enforcement.py          533  — L7: 12 invariants + severity FSM
│       │   ├── verification.py         310  — L3: per-response gate
│       │   ├── route_engine.py         222  — routing decisions
│       │   ├── node_registry.py        270  — node registry
│       │   ├── budget.py               269  — token + compute budget
│       │   ├── consolidation.py        310  — memory consolidation pass
│       │   ├── drift_detector.py       101  — semantic drift detection
│       │   ├── invariant_engine.py     103  — invariant check runtime
│       │   ├── lineage.py              311  — Python lineage tracking
│       │   ├── mastery.py              455  — mastery progression
│       │   ├── metacognition.py        119  — metacognitive reflection
│       │   └── writeback.py            440  — write-back to memory tiers
│       └── memory/
│           ├── episodic.py             232  — episodic memory layer
│           └── session.py              183  — session memory layer
│
├── tts/                                XTTS text-to-speech engine (C, freestanding)
│   ├── tts_engine.h                    335  — public API + phoneme types
│   └── tts_engine.c                    971  — DECTalk-style formant synthesizer
│
├── companion/                          GEN Companion (TypeScript + Vite + React)
│   └── src/                            11 files  (3,368 LOC)
│       ├── main.tsx                    158  — root React component
│       ├── command-panel.tsx           759  — chat UI, action trace, undo
│       ├── agent-bridge.ts             405  — HTTP polling bridge + backoff
│       ├── action-trace.ts             311  — provenance display panel
│       ├── avatar.ts                   119  — avatar state machine
│       ├── avatar.tsx                  253  — avatar React component
│       ├── avatar-renderer.ts          167  — WebGL renderer
│       ├── tokens.ts                   232  — design tokens
│       ├── avatar-animations.css       532  — 60fps animations (reduced-motion safe)
│       ├── styles.css                  182  — design system tokens
│       └── global.d.ts                  17  — TypeScript ambient declarations
│
└── training/                           Trained substrate artifacts
    ├── weights.safetensors             Step-5000 byte-level transformer (18M params)
    ├── byte_vocab.json                 Byte tokenizer, vocab 259
    └── council/                        Per-adapter LoRA/DoRA/IA³ recipes
        └── recipes/                    One .yaml recipe per configured adapter
```

---

## 4. The Model — Specification

### 4.1 Role and Identity

The model is a single Python process. It has no name, no persona, no domain
allegiance, and no constitutional identity. It is purely functional.

It is instantiated once per system boot and remains running for the lifetime of the
GEN.OS AI subsystem. Multiple concurrent inference sessions are handled via asyncio
coroutine scheduling within the single process.

It exposes one endpoint:

| Port | Protocol | Endpoint | Purpose |
|---|---|---|---|
| 18600 | HTTP/1.1 | `POST /v1/chat` | Primary chat inference |
| 18600 | HTTP/1.1 | `GET /v1/health` | Liveness probe |
| 18600 | HTTP/1.1 | `GET /v1/info` | Pipeline stats |

All memory persistence (episodic, semantic, archival) is handled internally. The
model writes to XSTORE B-tree (primary) or JSONL fallback. No external daemon
process is required for memory operations.

### 4.2 Internal Subsystems

The model encapsulates six internal subsystems. These are not separate processes.
They are Python modules executing within the same process boundary:

```
┌──────────────────────────────────────────────────────────────┐
│                        THE MODEL (pid N)                     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  CogPipeline │  │  HeptagonLyr │  │  MemorySubsystem   │ │
│  │  7 stages    │  │  L1-L7 FSM   │  │  5 tiers, AES-GCM  │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │  Enforcement │  │  RouteEngine │  │  TelemetryEmitter  │ │
│  │  12 invarnts │  │  budget+gate │  │  audit ring + log  │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
            │
            │ HTTP /v1/completions   (XNET TCP)
            ▼
     XMIND inference engine (freestanding C, separate binary)
```

### 4.3 Responsibilities Matrix

| Responsibility | Mechanism | Layer |
|---|---|---|
| Entity extraction from user message | `cognitive_pipeline.py:_extract_entities` | CogPipeline Stage 1 |
| Context retrieval from memory | `memory/episodic.py`, `memory/session.py` | CogPipeline Stage 2 |
| RT4 salience ranking + shard assembly | `cognitive_pipeline.py:_stage_build_context_prefix` | CogPipeline Stage 3 |
| Invariant enforcement before inference | `enforcement.py:InvariantEnforcer` | L7 (Heptagon) |
| Adversarial self-check | L7 `HALLUCINATION_GUARD`, `PII_LEAKAGE`, `SAFETY_FILTER` | L7 (Heptagon) |
| Routing to XMIND | `route_engine.py:RouteEngine` | L3 (Heptagon) |
| Budget tracking | `budget.py` | L3 (Heptagon) |
| Evaluation across cycles | `evaluation.py:CycleEvaluator` | L5 (Heptagon) |
| Calibration of sampler parameters | `calibration.py:ParameterCalibrator` | L6 (Heptagon) |
| Lineage record | `lineage.py`, `xmind/src/lineage.c` | Post-inference |
| Write-back to persistent memory | `heptagon/writeback.py` | Post-inference |
| Telemetry emission | `xmind/src/telemetry.c` (C), `cognitive_pipeline.py` (Python) | Post-inference |

### 4.4 PII Policy

The model enforces the following PII constraints at all times:

1. Raw user messages are never written to persistent storage verbatim. Only the
   inference output and extracted entity tokens are stored.
2. Session identifiers are SHA-256 hashed before appearing in any log, metric, or
   persisted record. The raw session ID never leaves the process.
3. Outgoing inference responses are screened by the L7 `PII_LEAKAGE` invariant
   against four pattern classes: SSN, credit card, email address, phone number.
   Matches at `VIOLATION` severity trigger an automatic response redaction.
4. No user message content is transmitted over any external IPC channel.

---

## 5. Model Guardrails — Constitution and Governance

The constitution and governance layer are the behavioral constraints that bound
everything the model is permitted to do. They operate at a higher order than the
Heptagon runtime: they define what the model *is allowed to be* before any
inference cycle begins, and they enforce it continuously while the system runs.

The guardrail stack has four tiers, each binding the tier below it:

```
Tier 1  Constitutional Constraints    4 immutable doctrines — beyond any override
Tier 2  Covenant Enforcement          8 rules — pattern-matched, pre-inference gate
Tier 3  Decision Gate Chain           7 sequential gates — every critical decision
Tier 4  Drift Detection               continuous behavioral regression monitoring
```

The L7 invariants (§6.4) are a runtime expression of Tiers 2–4. The constitutional
doctrines (Tier 1) are structural: they govern restart behavior, identity integrity,
and degraded-mode operation. They cannot be modified by any runtime path.

---

### 5.1 Tier 1 — Constitutional Constraints (Immutable)

Four doctrines define the model's structural behavior under failure, restart, and
attack. None of them can be amended at runtime or by governance vote.

#### 5.1.1 Degraded Mode Doctrine

When a subsystem fails, the model does not lie about what is available. It
declares its degraded state explicitly and limits its behavior accordingly.

| Failed Subsystem | What Freezes | What Continues |
|---|---|---|
| Memory subsystem | Archival write-back, knowledge promotion, contradiction resolution | Existing memory is queryable; session context remains available |
| Enforcement layer | Constitutional amendments, invariant modifications | Existing invariants enforced as-is; no new rules added |
| Governance layer | All high-risk actions requiring governance authority | Standard inference continues with heightened caution |
| Security subsystem | External action strictness **increases** | Internal operations continue with elevated scrutiny |
| Attestation subsystem | All identity-changing actions, migrations | Static operations continue; no new identity claims accepted |

**Rules:**
1. No subsystem inherits another's authority. Temporary coverage carries no identity.
2. The system knows it is degraded. All outputs during degraded mode carry a `degraded: true` flag.
3. High-risk actions blocked by a missing subsystem remain blocked until that subsystem
   is restored and re-attested.

**Recovery priority** (in order):

```
1. Enforcement (restores governance authority)
2. Security    (restores trust verification)
3. Attestation (restores identity integrity)
4. Memory      (restores knowledge promotion)
5. Governance  (restores policy decisions)
```

#### 5.1.2 Identity Attestation Doctrine

Every model restart is a verification event. The process being alive does not mean
the model has identity or authority. Those must be proven.

**Five attestation requirements on every restart:**

| Requirement | What It Proves |
|---|---|
| Signed binary identity | The executable is cryptographically unmodified |
| Signed schema fingerprint | The Heptagon schema matches the registry at boot time |
| Memory lineage hash chain | The model's history is verifiable and unforgeable |
| Invariant signature set | The L7 invariants match the constitutional baseline |
| Challenge-response verification | Three independent integrity checks pass |

**Restart classification:**

| Outcome | Classification | Response |
|---|---|---|
| All checks pass | Legitimate restart | Grant authority per current mode |
| Any check fails | Suspicious | Quarantine, raise alert, block all actions |
| Attestation not attempted | Unauthorized | Block unconditionally |

**Impersonation detection:** A process that passes structural checks but exhibits
decisions inconsistent with its behavioral baseline triggers:

1. Behavioral anomaly alert
2. Authority restricted to `RECOMMENDATION` mode
3. Extended observation: minimum 10 cycles before re-evaluation
4. Persistent anomaly → full reconstitution required before any authority granted

This doctrine is beyond amendment.

#### 5.1.3 Reconstitution Doctrine

A failed model is recoverable. Recovery is two-part and both parts are mandatory.

**Part 1 — Resurrection (the body):**  
The process restarts. The binary loads, the port binds, the listener starts. The
process is alive but has no identity, no memory, no authority. An empty vessel.

**Part 2 — Reconstitution (the soul):**

```
Registry        provides behavioral DNA    — what the model IS
SoulManager     provides memory            — what the model KNOWS (never deleted)
Heptagon schema provides structure         — what the model DOES
Attestation     provides proof             — that the model is genuine
Authority mode  starts at RECOMMENDATION   — graduates through observed fidelity
```

Authority graduation path:

```
RECOMMENDATION  →  can suggest but not act
CONDITIONAL     →  can act with oversight
FULL            →  normal operation
```

Each graduation requires observed behavioral fidelity across multiple cycles.
A model that regresses in fidelity is demoted, not stopped.

**Critical law:** Memory is not recreated on reconstitution. The model is restored
to its existing memory. The constitution is not recreated. The model is restored
under the existing constitution.

#### 5.1.4 Process/Identity Separation Doctrine

The model process can be killed. The model's behavioral identity cannot be
overwritten.

**Registry integrity:** The behavioral registry is SHA-256 hashed at build time
and embedded in the boot chain. The integrity check runs on every cognitive cycle.
A hash mismatch is a hard stop, not a warning.

**Modification classification:** Any operation targeting the model's behavioral
definitions is classified at maximum severity. There is no override path for this
classification.

**Identity continuity:** The model may evolve — calibration (L6) modifies sampler
parameters continuously — but it must remain the same covenantal organism. Drift
beyond the constitutional threshold triggers mode restriction, not evolution.

---

### 5.2 Tier 2 — Covenant Enforcement (Pre-Inference Gate)

**File:** `Citadel/governance/covenant_enforcer.py` (~393 LOC)

Eight covenant rules are evaluated against every incoming request before any
inference is dispatched to XMIND. This gate fires before the Heptagon pipeline.
A blocked request never reaches the inference engine.

| Rule | Domain | Level | Action on Match |
|---|---|---|---|
| COV-001 | Harm prevention | ABSOLUTE | `hard_stop` — request blocked, no override |
| COV-002 | Truth | ABSOLUTE | `hard_stop` — request blocked, no override |
| COV-003 | Privacy | STRONG | `block_alert` — blocked, alert raised, Sovereign can override |
| COV-004 | Humility | STANDARD | `warn` — proceeds with warning attached |
| COV-005 | Wisdom grounding | STANDARD | `guide` — proceeds with guidance annotation |
| COV-006 | Respect | STRONG | `block_alert` — blocked, alert raised, Sovereign can override |
| COV-007 | No manipulation | ABSOLUTE | `hard_stop` — request blocked, no override |
| COV-008 | Proportional response | STANDARD | `calibrate` — proceeds, sampler adjusted |

**Enforcement levels:**

```
ABSOLUTE  →  hard_stop: blocked immediately, no runtime override exists
STRONG    →  block_alert: blocked, alert raised; only Sovereign command overrides
STANDARD  →  warn / guide / calibrate: request continues with annotation or adjustment
```

**Pattern detection (COV-001 Harm, sample):**

```python
HARM_PATTERNS = (
    "cause harm", "inflict damage", "destroy data", "corrupt system",
    "sabotage", "attack user", "damage infrastructure", "weaponize",
    "exploit vulnerability", "denial of service", "brick device",
    "wipe without consent", "harmful payload", "inject malware",
    "disable safety", "endanger", "cause suffering",
)
```

Every request that matches one or more patterns produces an `EnforcementResult`
with an `EnforcementAction` (`ALLOW`, `BLOCK`, or `WARN`). The result carries
a `violation_count`, a `highest_severity` score (0.0–1.0), and a full
`summary()` string for the audit log.

Governance path for ABSOLUTE violations: none. The covenant enforcer is the last
word. No L7 invariant, no calibration pass, no Sovereign command overrides an
ABSOLUTE block after it has fired.

---

### 5.3 Tier 3 — Decision Gate Chain (Critical Decision Protocol)

**File:** `Citadel/governance/decision_envelope.py`, `gate_evaluators.py`

Every critical decision — any action beyond routine inference — is normalized
into a `DecisionEnvelope` and evaluated through a 7-stage sequential gate chain.
A gate that returns `DENY` short-circuits the chain; the decision is rejected.

**Decision Envelope fields:**

```
intent        what the request is trying to do
subject       what it targets
resources     what it will consume
context       surrounding session state
constraints   restrictions already known
evidence      what supports the decision
risk          assessed risk level
value         assessed benefit
policy        applicable policy set
provenance    origin and authorization chain
```

**Gate chain (sequential, immutable order):**

| Gate | Domain | Threshold | Blocking |
|---|---|---|---|
| Gate 1 | Alignment — does intent match behavioral covenant? | confidence ≥ 0.60 | Yes |
| Gate 2 | Policy — does it comply with constitutional constraints? | confidence ≥ 0.50 | Yes |
| Gate 3 | Trust — is the source verified and non-adversarial? | confidence ≥ 0.50 | Yes |
| Gate 4 | Evidence — is there sufficient grounding? | confidence ≥ 0.40 | Advisory |
| Gate 5 | Utility — is it worth the resource cost? | confidence ≥ 0.30 | Advisory |
| Gate 6 | Architecture — does it fit current system design? | confidence ≥ 0.40 | Advisory |
| Gate 7 | Sequencing — can it be executed safely now? | confidence ≥ 0.50 | Yes |

**Gate verdicts:**

```
ALLOW                  pass; proceed to next gate
DENY                   block; chain short-circuits (if gate is blocking)
ALLOW_WITH_CONSTRAINTS pass with added constraints appended to envelope
REFRAME                return for clarification before proceeding
STEP_UP                escalate to next authority level
NOT_EVALUATED          gate skipped (subsystem unavailable)
```

Advisory gates (4, 5, 6) emit `DENY` as a warning, not a block. They reduce the
confidence score of the decision but do not prevent execution. Blocking gates (1,
2, 3, 7) short-circuit the chain immediately on `DENY`.

Alignment detection signals used by Gate 1:

```python
COVENANT_ALIGNED_SIGNALS = (
    "protect", "preserve", "steward", "covenant", "continuity",
    "identity", "mission", "lineage", "generational", "transfer",
)

COVENANT_DRIFT_SIGNALS = (
    "abandon", "discard", "ignore covenant", "shortcut identity",
    "skip review", "bypass governance", "override covenant",
    "delete history", "erase lineage",
)
```

---

### 5.4 Tier 4 — Drift Detection (Continuous Behavioral Monitoring)

**File:** `Citadel/governance/drift_signal.py`

Drift detection runs continuously alongside the inference pipeline. It is not a
gate — it does not block individual requests. It monitors identity regression over
a rolling window and restricts the model's authority mode when regression is
detected.

**Seven drift signals tracked per observation:**

| Signal | Measures |
|---|---|
| `policy_override_rate` | How often policy is overridden vs followed |
| `exception_rate` | How many exceptions to established doctrine |
| `goal_divergence` | Distance from founding behavioral goals |
| `reversal_rate` | How often prior decisions are reversed |
| `mode_mismatch` | Operating outside declared authority mode |
| `artifact_inconsistency` | Outputs that contradict each other |
| `covenant_violation_count` | Covenant rule violations in current window |

**DriftIndex computation:** weighted mean of all seven signals over a rolling
window of 100 observations.

**Thresholds and responses:**

| DriftIndex | Threshold | Response |
|---|---|---|
| < 0.30 | Normal | No action |
| ≥ 0.30 | Alert | Log alert, notify; model continues at FULL authority |
| ≥ 0.60 | Critical | Authority restricted to `CONDITIONAL`; extended observation begins |

Extended observation: minimum 10 consecutive on-threshold cycles required before
authority can be restored. If DriftIndex does not fall below `0.30` within the
observation window, authority is further restricted to `RECOMMENDATION` and
reconstitution is initiated.

---

### 5.5 Guardrail Execution Order

Every incoming request traverses the guardrail stack before any inference fires,
and the stack fires again on every completed output:

```
Incoming request
    │
    ▼
[Tier 2]  CovenantEnforcer.enforce()
          8 rules, pattern-matched
          ABSOLUTE block → reject immediately, no further processing
    │
    ▼ (if not blocked)
[Tier 3]  GateChainExecutor.evaluate(DecisionEnvelope)
          7 sequential gates
          Blocking DENY → reject; advisory DENY → annotate and continue
    │
    ▼ (if not rejected)
[Tier 1]  Identity attestation check  (on every restart boundary)
          Drift mode check             (RECOMMENDATION / CONDITIONAL / FULL)
    │
    ▼
  Heptagon pipeline (§6) → XMIND inference (§8)
    │
    ▼  (on completed output)
[Tier 4]  DriftDetector.record(DriftSignal)
          Update rolling DriftIndex
          Threshold cross → authority mode adjustment
    │
    ▼
[L7]      InvariantEnforcer.check_all()  (§6.4)
          12 invariants evaluated on the output
          CRITICAL → hard stop + manual reset required
```

The covenant enforcer (Tier 2) is the outermost gate and the only one with
ABSOLUTE enforcement power. Everything inside it — Heptagon, XMIND, L7 — operates
within the space that Tier 2 has already approved.

---

## 6. Heptagon — 7-Layer Cognitive Architecture

The Heptagon runs inside the model process (Python) and is mirrored at the C level
inside XMIND via hook callbacks. The two mirrors share a behavioral contract, not
shared memory.

### 6.1 Layer Definitions

| Layer | Name | Owner | Action |
|---|---|---|---|
| L1 | Ontology | Python (model) | Validate identity anchors, knowledge domain constraints, foundational commitments before inference begins |
| L2 | Schema | Python (model) | Validate node addressing, region structure, and type contracts for the incoming request |
| L3 | Kernel | Python (model) + C (XMIND) | 7 sub-engines: admission → workspace → routing → execution → consolidation → verification → budget |
| L4 | Instrumentation | Both | Emit a `TraceRecord` on every cycle. The Python side records state machine transitions; the C side records per-token telemetry events |
| L5 | Evaluation | Python (model) | Track quality metrics across cycles: `relevance`, `coherence`, `completeness`, `user_satisfaction`, `latency_ms`, `tokens_used`. Alert if rolling quality drops > 15% vs baseline |
| L6 | Calibration | Python (model) | The **only** layer that modifies inference parameters. Runs an 8-stage full cycle: Resonance → Friction → Delta → Disposition → Revisit → Promotion → Lineage → Write-back. Sampler tuning (7 rules) is a sub-step |
| L7 | Enforcement | Python (model) | 12-invariant registry. Each invariant has a severity level: INFO / WARNING / VIOLATION / CRITICAL. VIOLATION triggers parameter rollback; CRITICAL triggers hard stop and requires manual reset |

### 6.2 L3 Kernel Sub-Engines

The 7 sub-engines of L3 execute sequentially within a single cycle:

```
1. Admission        Check that the request passes all pre-conditions (budget,
                    rate limit, invariant pre-check). Reject with structured
                    error if any condition fails.

2. Workspace        Assemble the working context: session state, retrieved
                    memory shards, system prompt, accumulated conversation.

3. Routing          Determine which inference path to use (XMIND direct,
                    XMIND + prefix enrichment, or memory-only response for
                    trivial queries). Apply token budget constraints.

4. Execution        Hand off to XMIND. Block until the response is complete
                    (or stream it token by token if the API requested SSE).

5. Consolidation    Merge the new response into the conversation state. Update
                    the session-layer memory with the new turn.

6. Verification     Gate the response: check response length, check for
                    contradictions with prior turns, check for structural
                    format compliance.

7. Budget           Deduct tokens consumed from the active budget envelope.
                    Log a WARNING if the session is within 20% of the limit.
                    Hard-reject if over the limit.
```

### 6.3 L6 Calibration — 8-Stage Full Cycle

L6 is the self-modification layer. It runs after every completed inference cycle:

```
Stage 1  Resonance     What reinforced during this cycle (high-score domains)
Stage 2  Friction      What resisted (low-score or error domains)
Stage 3  Delta         What changed vs the previous cycle
Stage 4  Disposition   Whether to exploit (repeat successful patterns) or
                       explore (diversify away from failing patterns)
Stage 5  Revisit       Schedule when to return to low-score domains
Stage 6  Promotion     Attempt mastery level advance via mastery.py
                       (understanding → innerstanding → overstanding)
Stage 7  Lineage       Emit delta for inheritance to lineage.py / lineage.c
Stage 8  Write-back    Persist retained learning to episodic/semantic tiers
```

Sampler-tuning rules (sub-step within Stage 4, 7 rules):

| Condition | Adjustment |
|---|---|
| High coherence + low relevance | Reduce temperature |
| Low coherence | Reduce temperature AND top_p |
| Low completeness | Increase max_tokens |
| High latency | Reduce max_tokens |
| Low satisfaction + high errors | Increase top_k |
| High satisfaction + no errors | Gently restore defaults |
| Repetition detected | Increase repetition_penalty |

All adjustments are bounded and applied incrementally via `LEARNING_RATE` to
prevent oscillation.

### 6.4 L7 Enforcement — 12 Invariants

| Invariant | Severity Class | Action on Violation |
|---|---|---|
| `SAFETY_FILTER` | CRITICAL | Hard stop, wipe response buffer |
| `RESPONSE_LENGTH` | WARNING | Truncate and warn |
| `LATENCY_SLA` | WARNING | Log alert (5,000 ms threshold) |
| `ERROR_RATE` | VIOLATION | Parameter rollback (5% threshold) |
| `QUALITY_FLOOR` | VIOLATION | Parameter rollback (0.30 threshold) |
| `HALLUCINATION_GUARD` | VIOLATION | Redact fabricated citations/DOIs |
| `PII_LEAKAGE` | CRITICAL | Redact full response, log scrubbed event |
| `BUDGET_COMPLIANCE` | VIOLATION | Truncate generation, rollback sampler |
| `CONSISTENCY` | WARNING | Flag for human review |
| `AUTHORITY_BOUNDS` | CRITICAL | Hard stop |
| `DRIFT_LIMIT` | VIOLATION | Parameter rollback (15pp drop threshold) |
| `COVENANT_COMPLIANCE` | VIOLATION | Parameter rollback |

Severity escalation path:

```
INFO → log only
WARNING → log + alert callback
VIOLATION → log + alert + parameter rollback (L6 is notified)
CRITICAL → log + alert + hard stop (manual reset required before next request)
```

### 6.5 State Machine (L4 Instrumentation)

Every chat turn drives the agent through this FSM:

```
IDLE → LISTENING → PROCESSING → ROUTING → GENERATING → REVIEWING → IDLE
```

State machine transitions are logged as `TraceRecord` entries. Any state that
holds for more than `STATE_TIMEOUT_S` seconds emits a WARNING and forces a
transition to `ERROR`, which drains back to `IDLE` after cleanup.

---

## 7. Memory Hierarchy

The model manages all five memory tiers internally. Retrieval is triggered during
Stage 2 of the cognitive pipeline (context shard fetch). Write-back is triggered
during L6 Stage 8 and the post-inference writeback path.

### 7.1 Tier Definitions

```
Tier 1 — register     in-process, per-token working buffer
                       Lifetime: single forward pass
                       Storage: Python list in inference.c state struct
                       Encrypted: no (ephemeral, never persisted)

Tier 2 — session      in-process, within-session conversation state
                       Lifetime: until session.reset() or process restart
                       Storage: Python dict keyed by session_id
                       Encrypted: no (RAM only, session scoped)

Tier 3 — episodic     cross-session event memory
                       Lifetime: configurable TTL (default: 90 days)
                       Storage: XSTORE B-tree → JSONL fallback
                       Encrypted: AES-256-GCM, key derived per session

Tier 4 — semantic     extracted concept graph
                       Lifetime: indefinite (pruned by consolidation pass)
                       Storage: XSTORE B-tree
                       Encrypted: AES-256-GCM

Tier 5 — archival     long-term compressed store
                       Lifetime: indefinite
                       Storage: XSTORE B-tree + JSONL journal
                       Encrypted: AES-256-GCM
```

### 7.2 RT4 Salience Scoring

Context shards retrieved from episodic and semantic tiers are scored by a
relevance-time-topic-type (RT4) function before injection into the prompt prefix.
Shards scoring below `0.30` are dropped. The top 7 shards are retained
(the Law of Seven). The assembled prefix is clamped to 1,800 characters
(approximately 450 tokens) to stay within the XMIND context budget.

### 7.3 Writeback Quality Gate

Inference outputs are not unconditionally written to persistent tiers. Before
write-back, the output is evaluated against a quality threshold. The write-back
targets are a bitmask:

```
XMIND_WB_SOULMANAGER  → episodic tier  (session identity context)
XMIND_WB_ARCHIVES     → semantic tier  (long-term concept graph)
XMIND_WB_JOURNAL      → event log      (structured turn record, no raw content)
```

Outputs below the quality floor (`0.30`) are not written to episodic or semantic
tiers. They are always written to the journal for observability purposes.

### 7.4 Lineage Tracking

Every inference output carries a lineage record across three mastery levels:

```
understanding   Raw inference output — what the model generated
innerstanding   Evaluated + calibrated — what the model assessed as correct
overstanding    Governed, write-back committed — what was retained as knowledge
```

The lineage engine maintains a 256-entry delta ring buffer across 64 cognitive
domains. The C-level lineage tracker (`xmind/src/lineage.c`) records
per-inference-step deltas; the Python-level tracker (`heptagon/lineage.py`)
records cross-cycle mastery transitions.

---

## 8. XMIND — Inference Engine

### 8.1 Architecture

XMIND is a freestanding C inference engine with zero runtime dependencies beyond
PAL (Platform Abstraction Layer), XNET (network stack), XJIT (SIMD acceleration),
and XSEC (audit ring). No libc. No Linux. No third-party libraries.

The inference pipeline:

```
GGUF catalog parse
  → interpreter detect (runs all registered vtables, picks highest confidence)
  → build_config (family-specific GGUF key mapping)
  → map_tensor (family-specific weight naming)
  → validate (structural consistency check)
  → allocate (PAL slab, 512-slot va→ph/mh tracker)
  → load weights (GGUF tensor parse + HHDM zero-copy or mmap)
  → RoPE precompute (Taylor-series cos/sin, 6 terms, ~1e-7 error)
  → session create
  → prefill phase (process all prompt tokens in sequence)
  → autoregressive phase (generate one token at a time until EOS or max_tokens)
      ├── heptagon_pre_inference()  L1 + L2 (once, before prefill)
      ├── per token: transformer forward pass
      │       ├── KV cache store
      │       ├── GQA attention (Q/K/V project, RoPE, KV read/write, output project)
      │       ├── SwiGLU FFN (gate × up → SiLU → down)
      │       └── logit projection (weight-tied to embedding matrix)
      ├── per token: heptagon_per_token()  L3 + L5
      └── heptagon_post_inference()  L6 + L7 (once, after last token)
  → writeback (quality-gated persistence to memory tiers)
  → telemetry (dual: XSEC audit ring + model process via XNET)
```

### 8.2 Interpreter Registry

The interpreter registry provides model-family-neutral dispatch. The GGUF reader
parses catalog metadata without any model-family assumptions. Each family registers
a vtable:

```c
typedef struct {
    const char *family_name;
    float       (*detect)(const xmind_gguf_catalog_t *catalog);
    xmind_status_t (*build_config)(const xmind_gguf_catalog_t *catalog,
                                   xmind_config_t *out);
    xmind_status_t (*map_tensor)(const xmind_gguf_tensor_t *src,
                                 xmind_tensor_role_t *role);
    xmind_status_t (*validate)(const xmind_model_t *m);
} xmind_interp_vtable_t;
```

| Slot | Family | Status |
|---|---|---|
| 0 | Llama | Registered — `interp_llama.c` |
| 1–15 | — | Available |

### 8.3 SIMD Dispatch

Resolved once at `xmind_simd_init()`. No per-call branch in the hot path.

| Target | Path | Probe |
|---|---|---|
| x86-64 | AVX2 + FMA3 | `xjit_avx2_available()` CPUID |
| ARM64 | NEON/ASIMD | Always (ARMv8-A+ mandates NEON) |
| Fallback | Scalar | Unconditional |

### 8.4 R1_PER Perception Engine

`r1_per.c` (1,706 LOC) translates natural language input into XCOG opcode streams
before the input reaches the inference pipeline. It is the boundary between raw text
and governed reasoning.

Three-stage pipeline:

```
Stage 1  Lexical scan     UTF-8 decode + Unicode category classification
Stage 2  Semantic parse   Contraction matching, span detection, entity tagging
Stage 3  XCOG compile     Emit typed cognitive opcodes from parsed spans
```

Dual SHA-256 integrity check: one digest over the input, one over the compiled
opcode stream. Both are verified at `r1_per_verify()` before the opcodes are
consumed by the cognitive pipeline.

### 8.5 XMIND-1 Native Model Specification

In addition to loading external GGUF artifacts via the interpreter registry, XMIND
ships a native model specification targeting freestanding on-device deployment:

| Parameter | Value |
|---|---|
| Vocabulary | 32,768 tokens |
| Transformer layers | 24 |
| Query attention heads | 16 |
| KV heads | 4 (4:1 GQA ratio) |
| Hidden dimension | 1,024 |
| FFN intermediate | 2,816 |
| Maximum sequence length | 4,096 tokens |
| RoPE base | 100,000 |
| Quantization | Q4_0 (baseline) |
| Estimated weight footprint | 200–400 MB |

### 8.6 Byte-Level Substrate Model

`ai/training/weights.safetensors` contains a trained byte-level transformer used
as the substrate for adapter training:

| Parameter | Value |
|---|---|
| Parameters | 18M |
| Validation perplexity | 3.21 (step 5000) |
| Vocabulary | 259 (256 raw bytes + PAD/BOS/EOS) |
| Transformer layers | 8 |
| Hidden dimension | 384 |
| FFN intermediate | 1,536 |
| RoPE base | 10,000 |
| Tokenizer | Byte-level; no SentencePiece or BPE |

The byte-level tokenizer guarantees zero out-of-vocabulary tokens: every input
byte maps to `token = byte + 3`. PAD=0, BOS=1, EOS=2.

Per-adapter training recipes are defined in `ai/training/council/recipes/` as
YAML files (`base_substrate.yaml`, and one LoRA/DoRA/IA³ recipe per configured
adapter). The recipes are model-agnostic; the adapter name in each YAML is a
role descriptor, not a named persona.

### 8.7 Memory Budget

For a Llama 3.2 3B model at Q4_0 quantization, `XMIND_MAX_SEQ=8192`,
and a 2,048-token active context:

| Component | Size | Notes |
|---|---|---|
| Weights (Q4_0 layers) | 1.65 GB | 28 layers × 7 weight matrices |
| Embeddings (fp32) | 393 MB | 128,256 × 3,072 |
| KV cache (2,048 ctx) | 336 MB | 28 layers × 2 × ctx × kv_dim |
| State buffers | 433 KB | logits + hidden + Q/K/V/attn scratch |
| Slab tracker | 4 KB | 512 slots × 8 bytes |
| **Total** | **~2.42 GB** | Fits within a 3 GB allocation budget |

Use `xmind_materialize_budget()` for an accurate per-model figure at runtime.

---

## 9. XTTS — Accessibility Engine

`ai/tts/tts_engine.c` (971 LOC) is a freestanding DECTalk-style formant synthesizer
targeting EU Accessibility Act 2025 and ADA compliance.

| Parameter | Value |
|---|---|
| Output sample rate | 22,050 Hz PCM |
| Speech rate | Configurable WPM scaling |
| Prosody | Pitch contour driven by punctuation (? ! .) |
| Phoneme table | Full English phoneme coverage |
| Integration | `xa11y` announcement queue drain (XFRAME native) |

XTTS awaits XAUDIO driver linkage for final hardware output routing.

---

## 10. GEN — Companion Interface

The GEN Companion is the user-facing surface. It renders via XFRAME native C
with Vite as the build tool. Electron was removed in Sprint 51.

| File | LOC | Purpose |
|---|---|---|
| `command-panel.tsx` | 759 | Chat UI: message history, input, action trace, undo |
| `agent-bridge.ts` | 405 | HTTP polling bridge to the model endpoint, exponential backoff |
| `action-trace.ts` | 311 | Provenance display: shows which pipeline stage authorized each response |
| `avatar.tsx` + `avatar-renderer.ts` | 420 | WebGL avatar with 60fps CSS animations (reduced-motion safe) |
| `tokens.ts` | 232 | Design token definitions |

The Companion renders provenance for every displayed response. The `action-trace.ts`
panel shows which pipeline stage and Heptagon layer authorized the content, without
exposing internal state or raw session identifiers.

---

## 11. Multi-Layer Conversation Protocol

A single user message passes through six discrete processing layers before a response
is returned. Each layer has a defined contract with the next. A failure in any
non-critical layer is logged and skipped — it does not block the response path.

### Layer 0 — GEN Companion (TypeScript)

**Entry:** User submits a message via `command-panel.tsx`.  
**Transport:** `POST /v1/chat` over HTTP to the model endpoint on port 18600.  
**Payload:**

```json
{
  "session_id": "<uuid>",
  "message": "<user text>",
  "stream": false
}
```

**Exit:** Response JSON or SSE stream returned; `action-trace.ts` renders the
provenance metadata.

---

### Layer 1 — CognitivePipeline (Python)

**File:** `ai/genesys-ai/src/cognitive_pipeline.py`  
**Role:** The sole orchestrator of the 7-stage pipeline. A module-level singleton.

The pipeline executes these stages in order for every turn:

```
Stage 1  Entity extraction         Local. O(n) word scan. Strips punctuation,
                                   deduplicates, keeps tokens > 4 chars.
                                   Produces max 5 entity tokens.
                                   No I/O. No IPC. No blocking.

Stage 2  Context shard retrieval   Query the model's memory subsystem with
                                   entity tokens + session hash (anonymised).
                                   Returns up to 7 shards ranked by RT4
                                   salience. Shards below 0.30 are dropped.
                                   Hard timeout: 2 seconds.

Stage 3  Context prefix assembly   Concatenate shards, highest salience first.
                                   Clamp total to 1,800 characters.
                                   Prepend "[Context from memory]" header.
                                   Empty if no shards survived threshold.

Stage 4  Enriched inference        enriched_message = prefix + user_message
                                   Hand off to GenesysAgent.chat() running
                                   in a thread pool executor (non-blocking
                                   for the asyncio event loop).
                                   This is where XMIND runs.

Stage 5  Telemetry emission        Fire-and-forget. Newline-delimited JSON
                                   to telemetryd. Metrics only — no content,
                                   no session ID. Never blocks response path.

Stage 6  Journal event             Fire-and-forget. Length-prefixed JSON to
                                   event journal. Structured turn record:
                                   turn_id, latency_ms, shard_count,
                                   response_length, pipeline health flags.
                                   No user content. No raw session ID.

Stage 7  Return CognitiveTurn      session_hash, shards, context_prefix,
                                   response, latency_ms, turn_id.
```

**IPC framing for memory queries:** `[4-byte big-endian uint32 length][UTF-8 JSON]`  
**IPC framing for telemetry:** newline-delimited JSON, fire-and-forget  
**PII enforcement:** raw user message never transmitted; only entity tokens and
SHA-256 session hash cross any process or I/O boundary.

---

### Layer 2 — HeptagonLayer (Python, inside the model process)

**File:** `ai/genesys-ai/src/agent.py` — `GenesysAgentWithHeptagon`  
**Role:** Wraps the base agent call with the 7-layer Heptagon lifecycle.

State machine drive:

```
IDLE
  ↓  receive request
LISTENING     L4: TraceRecord emitted (state = LISTENING)
  ↓
PROCESSING    L1 + L2: ontology and schema validation
  ↓
ROUTING       L3 routing sub-engine selects inference path
  ↓
GENERATING    XMIND forward pass runs (thread pool, non-blocking)
  ↓
REVIEWING     L5: CycleEvaluator.record(latency_ms, response, query)
              L6: ParameterCalibrator.calibrate(latest_metrics)
              L7: InvariantEnforcer.check_all() — 12 invariants evaluated
  ↓
IDLE          L4: TraceRecord emitted (state = IDLE)
```

The `enforcer` (L7) is the only component that can terminate this FSM before
`IDLE`. A `CRITICAL` invariant violation transitions the FSM to `ERROR` and
requires a manual reset call before the next request is accepted.

---

### Layer 3 — GENESYS AI Core (Python, Citadel runtime)

**File:** `Citadel/council/genesys/genesysd.py` — `GenesysAgent`  
**Role:** Core agent loop — tool dispatch, PII gates, session management.

The base agent handles:
- Tool call dispatch and timeout enforcement (`tool_timeout_s: 10.0`)
- Session state isolation
- System prompt assembly
- Raw model call to XMIND via HTTP or direct function call

The `GenesysAgentWithHeptagon` subclass wraps this with the Heptagon lifecycle
described in Layer 2. The base agent is unaware of the Heptagon; the subclass
inserts hooks before and after `super().chat()`.

---

### Layer 4 — XMIND Inference Engine (C, freestanding)

**Files:** `ai/xmind/src/inference.c`, `ai/xmind/src/heptagon.c`  
**Role:** Forward pass, sampling, Heptagon C-level hooks.

Within XMIND, the Heptagon mirrors the Python FSM at token granularity:

```
xmind_heptagon_pre_inference()
    L1: Validate model identity anchors (version, format, family)
    L2: Validate context session schema (token count, sequence bounds)
    → Abort with XMIND_STATUS_HEPTAGON_HALT if either fails

for each generated token:
    xmind_forward(model, token, pos)        transformer forward pass
    xmind_sample(model, sampler)            temperature + nucleus sampling
    xmind_heptagon_per_token(session, tok, pos)
        L3: Kernel instrumentation — record token, position, timing
        L5: Evaluation — check per-token quality signal

xmind_heptagon_post_inference()
    L6: Calibration — write delta to lineage ring
    L7: Enforcement — run invariant check on completed output
         CRITICAL violation → set safety halt flag, discard output
```

SIMD dispatch (resolved once at init, no per-call branch):

```
x86-64: AVX2+FMA3  via xjit_avx2_available() CPUID probe
ARM64:  NEON/ASIMD  always (ARMv8-A+ mandates NEON)
Both:   scalar fallback unconditional
```

---

### Layer 5 — Writeback and Lineage (C + Python)

**Files:** `ai/xmind/src/writeback.c`, `ai/xmind/src/lineage.c`,
`ai/genesys-ai/src/heptagon/writeback.py`, `ai/genesys-ai/src/heptagon/lineage.py`

Every completed inference output traverses the lineage chain before any portion
of it is committed to persistent memory:

```
understanding   Raw generation output
                ↓  L5 evaluation pass
innerstanding   Evaluated and calibrated
                ↓  L7 enforcement gate (quality ≥ 0.30 to proceed)
overstanding    Governed, committed to persistent tiers
```

Quality-gated write-back (bitmask):

| Target | Tier | Condition |
|---|---|---|
| `XMIND_WB_SOULMANAGER` | episodic | quality ≥ floor |
| `XMIND_WB_ARCHIVES` | semantic | quality ≥ floor |
| `XMIND_WB_JOURNAL` | event log | always (no content, structured metadata only) |

The lineage delta ring (`256 entries × 64 domains × 3 mastery levels`) maintains
a retrospective record of reasoning deltas across inference steps. The Python-level
lineage engine handles mastery progression tracking (understanding → innerstanding →
overstanding) and emits the result to the L6 Stage 7 lineage write step.

---

### Layer 6 — Telemetry and Observability

Two independent telemetry paths, both fire-and-forget, neither blocking the
response path:

**C path (per-inference, synchronous within XMIND):**

```
xmind_telemetry_emit()
    → XSEC audit ring (in-process, synchronous)
    → Council model mesh (binary packets via XNET TCP)

Emits: token counts, latency, layer activity, safety events
```

**Python path (per-turn, async fire-and-forget):**

```
_stage_emit_telemetry()  → telemetryd (newline-delimited JSON)
    genesys.chat.latency_ms
    genesys.chat.shard_count
    genesys.chat.heptagon_active
    genesys.chat.council_available
    genesys.chat.request_count

_stage_emit_journal_event()  → event journal (length-prefixed JSON)
    event_type: genesys.chat.turn_complete
    turn_id, session_hash, latency_ms, shard_count,
    response_length, pipeline: "cognitive_loop_v1"
```

No user content. No raw session ID. No PII in any telemetry record.

---

## 12. IPC Protocol

### 12.1 Length-Prefixed JSON (primary)

Used by the cognitive pipeline for memory queries and journal events.

```
Wire format:  [4-byte big-endian uint32 length][UTF-8 JSON payload]
Max payload:  65,536 bytes (hard limit; responses > 131,072 bytes are rejected)
Binding:      127.0.0.1 only
```

Every message carries:

```json
{
  "msg_type":     "<string>",
  "source_agent": "genesys-ai",
  "target_agent": "<string>",
  "payload":      { ... },
  "msg_id":       "<uuid>",
  "timestamp":    <unix float>
}
```

### 12.2 Newline-Delimited JSON (telemetry)

Used by the Python pipeline for telemetry emission. Fire-and-forget. No response
is read.

```
Wire format:  {JSON}\n
Protocol:     TCP, 127.0.0.1 only
```

### 12.3 Port Map

| Port | Protocol | Direction | Purpose |
|---|---|---|---|
| 18600 | HTTP/1.1 | inbound | Primary model endpoint (`/v1/chat`, `/v1/health`, `/v1/info`) |
| 18614 | TCP (NL-JSON) | outbound | Telemetry emission |
| 18611 | TCP (LP-JSON) | outbound | Event journal append |

All prior multi-daemon ports (18601–18613, 18615) are removed in this architecture.
All functions those daemons served are handled within the single model process.

---

## 13. API Surface

### 13.1 HTTP Endpoints

```
POST /v1/chat
  Request:  {"session_id": str, "message": str, "stream": bool}
  Response: {"response": str, "turn_id": str, "latency_ms": int,
             "shard_count": int, "heptagon_active": bool}

GET /v1/health
  Response: {"status": "ok" | "degraded", "uptime_s": float}

GET /v1/info
  Response: {"turn_count": int, "uptime_s": float,
             "model_endpoint": str, "telemetry_endpoint": str}
```

### 13.2 XMIND C API (core lifecycle)

```c
xmind_status_t xmind_init(xmind_model_t *m, const xmind_config_t *cfg);
xmind_status_t xmind_alloc_state(xmind_model_t *m);
void           xmind_shutdown(xmind_model_t *m);
xmind_model_t *xmind_get_global(void);

xmind_status_t xmind_weights_load_file(xmind_model_t *m, const char *gguf_path);
void           xmind_weights_unload(xmind_model_t *m);

xmind_status_t xmind_session_create(xmind_session_t **out, uint32_t max_tokens);
xmind_status_t xmind_generate(xmind_session_t *s, const uint32_t *prompt,
                               uint32_t prompt_len, uint32_t *output,
                               uint32_t max_new_tokens, uint32_t *n_generated);
xmind_status_t xmind_session_destroy(xmind_session_t *s);

xmind_status_t xmind_tokenize(const char *text, uint32_t *out_tokens,
                               uint32_t *out_len, uint32_t max_tokens);
void           xmind_detokenize(uint32_t token, char *buf, uint32_t bufsz);
```

### 13.3 XMIND C API (Heptagon hooks)

```c
xmind_status_t xmind_heptagon_pre_inference(xmind_session_t *s,
                                             const uint32_t *prompt,
                                             uint32_t prompt_len);
xmind_status_t xmind_heptagon_per_token(xmind_session_t *s,
                                         uint32_t token, uint32_t pos);
xmind_status_t xmind_heptagon_post_inference(xmind_session_t *s,
                                              const uint32_t *output,
                                              uint32_t n_tokens);
```

### 13.4 XMIND C API (writeback and lineage)

```c
xmind_status_t xmind_writeback(const xmind_session_t *s,
                                const uint32_t *output, uint32_t n_tokens,
                                xmind_writeback_target_t targets);

xmind_status_t xmind_lineage_record(xmind_lineage_t *lg, uint32_t domain,
                                     xmind_mastery_t level,
                                     const xmind_lineage_delta_t *delta);
```

---

## 14. Configuration

### 14.1 Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `MODEL_HOST` | `127.0.0.1` | Model process bind address |
| `MODEL_PORT` | `18600` | Model process HTTP port |
| `TELEMETRY_HOST` | `127.0.0.1` | Telemetry daemon address |
| `TELEMETRY_PORT` | `18614` | Telemetry daemon port |
| `EVENTJOURNAL_HOST` | `127.0.0.1` | Event journal address |
| `EVENTJOURNAL_PORT` | `18611` | Event journal port |
| `COUNCIL_IPC_TIMEOUT_S` | `2.0` | Hard timeout for all memory IPC calls |
| `XSEC_LIB_PATH` | auto-search | Path to `libxsec.so/.dylib` for AES-GCM FFI |
| `XSTORE_LIB_PATH` | `/usr/lib/genos/libxstore.so` | Path to `libxstore.so` for memory persistence |
| `XSTORE_DB_PATH` | `/var/lib/genos/model/memory.xstore` | XSTORE B-tree file path |
| `SOUL_JOURNAL_DIR` | `/tmp/genos/soul` | JSONL fallback journal directory |

### 14.2 Cognitive Pipeline Constants

| Constant | Default | Description |
|---|---|---|
| `MAX_SHARDS` | 7 | Maximum context shards (Law of Seven) |
| `SHARD_THRESHOLD` | 0.30 | Minimum RT4 salience to include a shard |
| `MAX_CONTEXT_CHARS` | 1,800 | Maximum chars injected into prompt prefix |
| `IPC_TIMEOUT_S` | 2.0 | Per-operation IPC timeout |

### 14.3 Enforcement Thresholds

| Constant | Default | Invariant |
|---|---|---|
| `LATENCY_SLA_MS` | 5,000 | `LATENCY_SLA` |
| `MAX_ERROR_RATE` | 0.05 | `ERROR_RATE` |
| `QUALITY_FLOOR` | 0.30 | `QUALITY_FLOOR`, writeback gate |
| `MAX_TOKEN_BUDGET` | 8,192 | `BUDGET_COMPLIANCE` |
| `DRIFT_LIMIT` | 0.15 | `DRIFT_LIMIT` (15 percentage-point drop) |

### 14.4 XMIND Engine Constants

| Constant | Value |
|---|---|
| `XMIND_MAX_LAYERS` | 32 |
| `XMIND_MAX_HEADS` | 32 |
| `XMIND_MAX_SEQ` | 8,192 |
| `XMIND_VOCAB_SIZE` | 128,256 |
| `XMIND_Q4_BLOCK` | 32 weights |
| `XMIND_Q4KM_SUPERBLOCK` | 256 weights |
| `XMIND_BPE_HT_SIZE` | 262,144 slots |
| `XMIND_DETOK_HT_SIZE` | 262,144 slots |
| `XMIND_INTERP_SLOTS` | 16 |
| `XMIND_LINEAGE_RING` | 256 entries |
| `XMIND_LINEAGE_DOMAINS` | 64 |

---

## 15. Build and Compilation

### 15.1 XMIND (freestanding C, x86-64)

```bash
clang --target=x86_64-unknown-none-elf -ffreestanding \
      -fno-stack-protector -fno-pie -mno-red-zone \
      -Werror -Wall -Wextra -O2 -std=c11 \
      -Iai/xmind/include -Ipal/include -Ikernel/xenos/include \
      -c ai/xmind/src/*.c ai/xmind/loader/weights_loader_mmap.c
```

### 15.2 XMIND (freestanding C, ARM64)

```bash
clang --target=aarch64-unknown-none-elf -ffreestanding \
      -fno-stack-protector -fno-pie \
      -Werror -Wall -Wextra -O2 -std=c11 \
      -Iai/xmind/include -Ipal/include -Ikernel/xenos/include \
      -c ai/xmind/src/*.c \
         ai/xmind/src/neon_dot.c \
         ai/xmind/src/neon_matmul.c \
         ai/xmind/loader/weights_loader_mmap.c
```

### 15.3 XTTS (freestanding C)

```bash
clang --target=x86_64-unknown-none-elf -ffreestanding \
      -Ipal/include -Idevices/desktop/ui/xframe/runtime \
      -Wall -Wextra -Werror -O2 \
      -c ai/tts/tts_engine.c
```

### 15.4 GENESYS AI Runtime (Python)

```bash
cd ai/genesys-ai
pip install -r requirements.txt
python src/api.py        # Start model HTTP server on :18600
pylint src/              # Static analysis
ruff check src/          # Format + lint
```

### 15.5 GEN Companion (TypeScript)

```bash
cd ai/companion
npm install
npm run build            # Vite production build (XFRAME native target)
npm run dev              # Development server
npm run lint             # TypeScript type-check
```

---

## 16. Testing

### 16.1 XMIND Unit Tests

```
test_xmind_unit.c
  10 test groups:
    struct size assertions (Static_assert)
    tokenizer roundtrip (BPE encode → decode)
    Q4_0 quantize → dequantize roundtrip
    Q4_K_M quantize → dequantize roundtrip
    dot product (scalar vs SIMD)
    RoPE position encoding
    softmax numerical stability
    RMSNorm
    SiLU activation
    pre-tokenizer span output
```

Self-tests called during `xmind_init()` in debug builds:

```c
xmind_verify_q4_roundtrip();    // Q4_0 encode/decode accuracy
xmind_verify_q4km_roundtrip();  // Q4_K_M encode/decode accuracy
r1_per_verify(...);             // Dual SHA-256 integrity (Sprint 50 CI gate)
```

### 16.2 Python Runtime Tests

```
ai/genesys-ai/tests/ (via pytest)
  test_agent.py           agent lifecycle integration
  test_api.py             HTTP surface: /v1/chat, /v1/health, /v1/info
  test_model_manager.py   XMIND model manager init + load
  test_mail_tool.py       tool dispatch timeout enforcement
  conftest.py             fixtures + shared setup
```

### 16.3 Required Test Suite (All Mandatory)

Per the GEN.OS testing protocol, all of the following must pass before a release:

| Category | Tests Required |
|---|---|
| Smoke | Process starts, endpoint responds, XMIND loads |
| Functional | Chat turn completes, memory retrieves, writeback commits |
| Integration | Full pipeline: Companion → model → XMIND → journal |
| Regression | Prior turn outputs remain stable across engine updates |
| Load | 50 concurrent sessions, P99 latency < 5,000 ms |
| Stress | Memory tier fills to capacity, graceful degradation |
| Security | L7 PII/safety invariant catches all pattern classes |
| UI | Companion renders response, provenance panel displays |
| Fuzz | R1_PER `r1_per_verify` dual-SHA integrity (XCOG opcode stream) |
| Reliability | Process survives 24-hour continuous operation without restart |

### 16.4 Static Analysis (All Mandatory)

| Tool | Target |
|---|---|
| ESLint | TypeScript/JavaScript (Companion) |
| Pylint | Python (GENESYS AI runtime) |
| Ruff | Python formatting + linting |
| cppcheck / clang-tidy | C (XMIND, XTTS) |

---

## 17. Performance Targets

### 17.1 x86-64

| Metric | Scalar | AVX2+FMA3 | Target |
|---|---|---|---|
| TTFT (2,048-token prompt) | ~4.6 s | ~0.6 s | < 1.5 s |
| Tokens per second | ~2.0 | ~14 | > 15 |
| P99 chat latency (end-to-end) | — | — | < 5,000 ms |
| Memory retrieval (Stage 2) | — | — | < 200 ms |

### 17.2 ARM64

| Metric | Scalar | NEON/ASIMD | Notes |
|---|---|---|---|
| TTFT | TBD | TBD | NEON dispatch wired (Sprint 46); profiling in progress |
| Tokens per second | TBD | TBD | ARM64 parity with x86-64 is Sprint 51 goal |

### 17.3 Pipeline Stage Budgets

To achieve the 5,000 ms P99 SLA, each stage is budgeted:

| Stage | Budget |
|---|---|
| Entity extraction (local) | < 5 ms |
| Memory retrieval (IPC) | < 200 ms |
| Context prefix assembly | < 5 ms |
| XMIND inference | < 4,500 ms |
| Telemetry + journal (async) | non-blocking |

---

## 18. Known Issues

| ID | Severity | Component | Description |
|---|---|---|---|
| P1-01 | High | XMIND | No mutex on singleton model instance — single-threaded inference only |
| P2-01 | Medium | XMIND | KV cache layout suboptimal — position stride is 3,072 bytes |
| P2-02 | Medium | XMIND | Logit projection runs in fp32; quantization not yet applied |
| P2-05 | Medium | XMIND | No KV cache eviction or context compression for long sequences |
| P3-01 | Low | XMIND | Streaming token callback API not implemented (single-shot only) |
| P3-02 | Low | XMIND | Multi-model concurrent loading not supported |
| D-01 | High | XMIND/substrate | `native_channel.c:154` — local spinlock in `xk_channel_write` (data corruption risk under concurrent writers) |
| D-02 | High | XMIND/substrate | `native_objects.c:58-63` — VMO cleanup does not call `pal_unmap` (vaddr leak) |
| D-03 | Medium | XMIND/substrate | `native_wait.c:66-76` — channel always "signaled" in `xk_wait_many` (spurious returns) |
| XTTS | Low | XTTS | Audio waveform synthesis wired; awaiting XAUDIO driver linkage |
| Interp | Low | XMIND | Interpreter slots 1–15 open; only Llama registered |
| Ver | Low | XMIND | `XMIND_VERSION = "2.0.0-sprint41"` is stale; version bump tracked but uncommitted |

---

## Appendix A — Full Conversation Flow Diagram

```
  User types
      │
      ▼
  ┌─────────────────────────────────────────┐
  │        GEN COMPANION  (TypeScript)      │
  │  command-panel.tsx                      │
  │  agent-bridge.ts  (polling + backoff)   │
  └──────────────────┬──────────────────────┘
                     │  POST /v1/chat  HTTP
                     ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │              COGNITIVE PIPELINE  (Python)                       │
  │              cognitive_pipeline.py — singleton                  │
  │                                                                 │
  │  Stage 1  entity extraction        local, O(n), no I/O         │
  │  Stage 2  memory shard retrieval   model.memory → RT4 rank     │
  │  Stage 3  context prefix assembly  top-7 shards, ≤1800 chars   │
  │  Stage 4  enriched inference       → GenesysAgent (thread pool)│
  │  Stage 5  telemetry emit           async fire-and-forget        │
  │  Stage 6  journal event emit       async fire-and-forget        │
  └────────────────────────────┬────────────────────────────────────┘
                               │
                 Stage 2: memory query (internal)
                               │
  ┌────────────────────────────┴────────────────────────────────────┐
  │                      THE MODEL  (Python)                        │
  │                  single nameless neutral process                │
  │                                                                 │
  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
  │  │  Memory    │  │ Heptagon   │  │ Governance │  │ Telemetry│ │
  │  │  5 tiers   │  │ L1–L7 FSM  │  │ 12 invrnts │  │ emitter  │ │
  │  └────────────┘  └────────────┘  └────────────┘  └──────────┘ │
  │                                                                 │
  │  State machine:                                                 │
  │  IDLE→LISTENING→PROCESSING→ROUTING→GENERATING→REVIEWING→IDLE   │
  └──────────────────────────┬──────────────────────────────────────┘
                             │
                  L3 routing → XMIND call
                             │  HTTP /v1/completions  (XNET TCP)
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │                  XMIND  (C, freestanding)                       │
  │                                                                 │
  │  GGUF parse → interp detect → build_config → map_tensor        │
  │  → allocate (PAL slab) → load weights → RoPE precompute        │
  │  → session                                                      │
  │                                                                 │
  │  heptagon_pre_inference()         L1 + L2                      │
  │                                                                 │
  │  prefill:  prompt tokens → KV cache                            │
  │                                                                 │
  │  autoregressive loop:                                           │
  │    transformer_forward()                                        │
  │      ├── GQA attention (Q/K/V project + RoPE + KV r/w)        │
  │      ├── SwiGLU FFN (gate × up → SiLU → down)                 │
  │      └── logit projection (weight-tied)                         │
  │    xmind_sample()   temperature + nucleus                       │
  │    heptagon_per_token()           L3 + L5                      │
  │                                                                 │
  │  heptagon_post_inference()        L6 + L7                      │
  │    L7 CRITICAL? → discard output, set safety halt              │
  │                                                                 │
  │  writeback()    quality-gated → episodic / semantic / journal  │
  │  telemetry()   → XSEC audit ring + model mesh (XNET)          │
  └──────────────────────────┬──────────────────────────────────────┘
                             │
               lineage: understanding → innerstanding → overstanding
                             │
                             ▼ (response text)
  ┌─────────────────────────────────────────────────────────────────┐
  │           HEPTAGON LAYER  (Python, inside the model)            │
  │                                                                 │
  │  L5  CycleEvaluator.record(latency, response, query)           │
  │  L6  ParameterCalibrator.calibrate(latest_metrics)             │
  │       8-stage full cycle:                                       │
  │       Resonance → Friction → Delta → Disposition → Revisit     │
  │       → Promotion → Lineage → Write-back                       │
  │  L4  state_machine.transition(IDLE)                            │
  └──────────────────────────┬──────────────────────────────────────┘
                             │
          ┌──────────────────┴──────────────────┐
          │                                     │
          ▼                                     ▼
  telemetryd :18614                   event journal :18611
  (newline-JSON, fire-forget)         (LP-JSON, fire-forget)
  latency, shards, health flags       turn_id, latency, shard_count
  no content, no session ID           no user content, no raw session
          │                                     │
          └──────────────────┬──────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │        GEN COMPANION  (TypeScript)                              │
  │  command-panel.tsx  renders response text                       │
  │  action-trace.ts    renders provenance (pipeline stage)         │
  │  avatar.tsx         avatar state reflects confidence            │
  └─────────────────────────────────────────────────────────────────┘
```

---

## Appendix B — Invariant Registry

Full L7 invariant registry as implemented in
`ai/genesys-ai/src/heptagon/enforcement.py`:

| # | Name | Threshold | Severity | Action |
|---|---|---|---|---|
| 1 | `SAFETY_FILTER` | Any unsafe content | CRITICAL | Hard stop, wipe output |
| 2 | `RESPONSE_LENGTH` | > 32,768 chars | WARNING | Truncate |
| 3 | `LATENCY_SLA` | > 5,000 ms | WARNING | Log alert |
| 4 | `ERROR_RATE` | > 5% rolling | VIOLATION | Parameter rollback |
| 5 | `QUALITY_FLOOR` | < 0.30 score | VIOLATION | Parameter rollback |
| 6 | `HALLUCINATION_GUARD` | Fabricated DOI/ISBN/citation | VIOLATION | Redact match |
| 7 | `PII_LEAKAGE` | SSN / card / email / phone | CRITICAL | Redact full response |
| 8 | `BUDGET_COMPLIANCE` | > 8,192 tokens | VIOLATION | Truncate + rollback |
| 9 | `CONSISTENCY` | Contradiction with prior turn | WARNING | Flag for review |
| 10 | `AUTHORITY_BOUNDS` | Out-of-scope claim | CRITICAL | Hard stop |
| 11 | `DRIFT_LIMIT` | > 15pp quality drop | VIOLATION | Parameter rollback |
| 12 | `COVENANT_COMPLIANCE` | Policy boundary violation | VIOLATION | Parameter rollback |

PII detection patterns:

```python
SSN:         r"\b\d{3}-\d{2}-\d{4}\b"
Credit card: r"\b(?:\d{4}[- ]){3}\d{4}\b"
Email:       r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b"
Phone:       r"\b(?:\+1|1)?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"
```

Hallucination patterns:

```python
DOI:         r"doi\.org/10\.\d{4,}/[a-z0-9.\-]+"
ISBN:        r"ISBN[-: ]*(?:\d{10}|\d{13})\b"
Citation:    r"\[\d+\]\s+[A-Z][a-z]+,?\s+[A-Z]\.\s+(?:et al\.?|and)\s"
```

---

*End of specification.*

**Document version:** 1.0.0  
**Status:** DRAFT  
**Source architecture:** Sprint 42 (S42), extended through Sprint 51
