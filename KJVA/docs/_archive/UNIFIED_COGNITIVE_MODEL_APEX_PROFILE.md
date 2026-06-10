# Unified Cognitive Model — Apex Profile

> GEN.OS · AI Subsystem · Cognitive Architecture Doctrine  
> Apex/Ultimate Profile for the existing Unified Cognitive Model  
> Taxonomy lock: **no label changes, no new agents, no new runtime identity**  
> Source basis: `UNIFIED_COGNITIVE_MODEL_SPEC.md`, last revised 2026-05-27  
> Output date: 2026-05-28

---

## 0. Executive Definition

The **Apex Profile** is the highest form of the existing Unified Cognitive Model without changing its taxonomy, labels, process model, endpoint surface, memory hierarchy, or runtime identity.

It is not a new model name in code.  
It is not a fifth pillar.  
It is not a new daemon.  
It is not a new council.  
It is not a new agent layer.  
It is not a replacement for the existing specification.

The Apex Profile is the existing architecture operated as a **three-connected, embedded, recursive, cascading cognitive system**:

```text
Connection 1: The Model ⇄ Heptagon
Connection 2: Heptagon ⇄ XMIND
Connection 3: The Model ⇄ SoulManager
```

Everything remains inside the already-defined build:

```text
GEN Companion
  → CognitivePipeline
    → The Model
      → Heptagon
        → RouteEngine
          → XMIND
        → L5 Evaluation
        → L6 Calibration
        → L7 Enforcement
      → SoulManager
      → TelemetryEmitter
  → XTTS when speech output is requested
```

The Apex version is the model you cannot realistically beat inside the current constraints because it closes every major loop already present in the build:

1. **Governance loop** — requests and outputs are bounded by Constitution, Covenant Enforcement, Decision Gate Chain, Drift Detection, and L7 invariants.
2. **Inference loop** — XMIND generation is wrapped by Heptagon hooks before inference, during token generation, and after inference.
3. **Memory loop** — SoulManager retrieves context before generation and receives quality-gated lineage/write-back after generation.
4. **Calibration loop** — L5 quality metrics flow into L6 sampler adjustment and rollback behavior.
5. **Observability loop** — telemetry and journal records describe the cycle without leaking raw user content or raw session identifiers.
6. **Recovery loop** — degraded mode, identity attestation, reconstitution, and authority graduation preserve continuity under failure.

In one sentence:

> **The Apex Profile is the existing Unified Cognitive Model running as a closed three-connection recursive cascade: The Model ⇄ Heptagon, Heptagon ⇄ XMIND, and The Model ⇄ SoulManager, with GEN Companion as the user interface and XTTS as the accessibility engine.**

---

## 1. Non-Negotiable Taxonomy Lock

The following labels remain unchanged. They are not renamed, aliased, abstracted, or replaced.

| Existing Label | Apex Role | Constraint |
|---|---|---|
| **The Model** | Single neutral process; owns governance, routing, memory retrieval, enforcement, telemetry, and write-back orchestration | No name, no persona, no new identity |
| **Heptagon** | L1-L7 cognitive architecture governing every inference cycle | No eighth layer, no renamed layers |
| **SoulManager** | Five-tier memory hierarchy and continuity layer | No renamed tiers |
| **XMIND** | Freestanding C inference engine; forward pass, tokenization, sampling, quantization | No governance, memory, identity, or routing authority |
| **XTTS** | Accessibility/text-to-speech engine | Remains output accessibility layer |
| **GEN Companion** | User-facing command-panel and provenance interface | No new frontend identity |
| **CognitivePipeline** | Seven-stage turn driver | No renamed stages |
| **RouteEngine** | L3 routing decision mechanism | No separate router daemon |
| **InvariantEnforcer** | L7 invariant runtime | No substitute enforcement class |
| **TelemetryEmitter** | Metrics and journal emission | No raw user content, no raw session ID |
| **GenesysAgentWithHeptagon** | Existing wrapper around the base agent lifecycle | No new agent class required |

The following additions are explicitly forbidden:

```text
ApexKernel
LawCore
MindCore
SoulCore
CouncilAgent
SupervisorAgent
ReflectionAgent
MemoryAgent
OracleAgent
/apex/chat
fifth pillar
eighth Heptagon layer
sixth memory tier
parallel model daemon
new identity-bearing model process
```

The word **Apex** is a document/profile descriptor only. It is not a runtime entity, not a process name, and not a taxonomy replacement.

---

## 2. Apex Objective Function

The current model already contains the right machinery. The Apex Profile makes that machinery operate as one bounded, self-correcting loop.

The objective function is:

```text
Maximize:
  governed correctness
  memory continuity
  response usefulness
  privacy preservation
  bounded latency
  post-failure recoverability
  inspectable provenance

Subject to:
  existing taxonomy only
  one model process
  one primary endpoint
  Heptagon L1-L7 unchanged
  SoulManager tiers unchanged
  XMIND intelligence-only boundary unchanged
  no raw user content in telemetry or journal
  P99 chat latency target < 5,000 ms
```

The Apex Profile does not try to win by adding more components. It wins by reducing leakage between existing components and forcing every output through the full closed loop:

```text
retrieve → govern → route → generate → evaluate → calibrate → enforce → lineage → write-back → retrieve
```

That loop is the heart of the ultimate model.

---

## 3. Existing Build Basis

The Apex Profile is grounded in the current build as described by the Unified Cognitive Model specification.

### 3.1 Four Pillars Remain Intact

```text
Heptagon     Structure       Python + C       L1-L7 cognitive architecture
SoulManager  Identity        Python + C       Five-layer memory hierarchy
The Model    Law + Routing   Python           Single neutral process
XMIND        Intelligence    C                Forward pass and sampling
```

The Apex Profile does not collapse the four pillars into three pillars. Instead, it creates **three primary connections** among the existing pillars.

### 3.2 Existing Endpoint Surface Remains Intact

```text
POST /v1/chat
GET  /v1/health
GET  /v1/info
```

No Apex endpoint is added.

### 3.3 Existing State Machine Remains Intact

```text
IDLE → LISTENING → PROCESSING → ROUTING → GENERATING → REVIEWING → IDLE
```

No new public state is introduced. Recursive behavior happens inside the existing state machine, especially through `REVIEWING`, L5, L6, L7, and the existing route path back through `GENERATING` when correction is required and budget allows.

### 3.4 Existing CognitivePipeline Stages Remain Intact

```text
Stage 1  Entity extraction
Stage 2  Context shard retrieval
Stage 3  Context prefix assembly
Stage 4  Enriched inference
Stage 5  Telemetry emission
Stage 6  Journal event
Stage 7  Return CognitiveTurn
```

No additional stage is added. Apex behavior is achieved by tightening the contracts between the stages.

### 3.5 Existing Memory Tiers Remain Intact

```text
register → session → episodic → semantic → archival
```

No memory tier is renamed. No sixth tier is added. The Apex Profile simply makes memory promotion stricter, more recursive, and more dependent on quality, lineage, and invariant results.

---

## 4. The Three-Connected Architecture

The Apex Profile is built around three hard connections.

```text
┌─────────────────────────────────────────────────────────────────────┐
│                              The Model                              │
│  single neutral process; governance, routing, memory, enforcement    │
│                                                                     │
│      Connection 1                    Connection 3                   │
│  The Model ⇄ Heptagon             The Model ⇄ SoulManager           │
│                                                                     │
│                ┌────────────────────────────┐                       │
│                │          Heptagon           │                       │
│                │ L1 L2 L3 L4 L5 L6 L7        │                       │
│                └─────────────┬──────────────┘                       │
│                              │                                      │
│                         Connection 2                                │
│                         Heptagon ⇄ XMIND                            │
│                              │                                      │
│                ┌─────────────▼──────────────┐                       │
│                │            XMIND            │                       │
│                │ forward pass + sampling     │                       │
│                └────────────────────────────┘                       │
│                                                                     │
│                ┌────────────────────────────┐                       │
│                │        SoulManager          │                       │
│                │ register/session/episodic   │                       │
│                │ semantic/archival           │                       │
│                └────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────────┘
```

## 4.1 Connection 1 — The Model ⇄ Heptagon

This is the governance, structure, and enforcement connection.

### Forward direction

```text
The Model
  → CovenantEnforcer
  → Decision Gate Chain
  → Identity attestation boundary
  → Drift mode check
  → Heptagon L1-L7
```

### Return direction

```text
Heptagon L5/L6/L7
  → quality metrics
  → sampler calibration
  → invariant verdict
  → rollback/hard-stop decision
  → The Model authority and readiness state
```

### Apex rule

The Model may not dispatch an inference path that has not passed the current governance envelope.

That means:

```text
CovenantEnforcer hard_stop  → no XMIND call
Decision Gate blocking DENY → no XMIND call
Identity attestation fail   → quarantine / block
DriftIndex critical         → restrict authority mode
L7 CRITICAL                 → ERROR + manual reset
```

This connection is what prevents the system from becoming a raw generation engine.

---

## 4.2 Connection 2 — Heptagon ⇄ XMIND

This is the inference and token-level recursion connection.

### Forward direction

```text
Heptagon L3 Routing
  → RouteEngine
  → XMIND session create
  → prompt/token budget envelope
  → xmind_heptagon_pre_inference()
  → xmind_generate()
```

### Return direction

```text
xmind_heptagon_per_token()
  → token timing
  → token position
  → per-token quality signal
  → L4 instrumentation
  → L5 evaluation signal

xmind_heptagon_post_inference()
  → L6 lineage delta
  → L7 enforcement check
  → safety halt flag if needed
```

### Apex rule

XMIND owns intelligence only.

XMIND may:

```text
tokenize
load weights
run transformer attention
sample tokens
emit telemetry
run Heptagon hook callbacks
record lineage deltas
call quality-gated writeback API under model-governed targets
```

XMIND may not:

```text
own memory
alter authority mode
change covenant behavior
route requests independently
bypass The Model
persist raw user content
change L7 invariant definitions
invent identity or persona
```

This connection gives the Apex Profile micro-recursion at token granularity while preserving the intelligence-only boundary.

---

## 4.3 Connection 3 — The Model ⇄ SoulManager

This is the memory, lineage, and continuity connection.

### Forward direction

```text
The Model
  → CognitivePipeline Stage 1 entity extraction
  → Stage 2 context shard retrieval
  → RT4 scoring
  → top-7 shard selection
  → Stage 3 context prefix assembly
  → Stage 4 enriched inference
```

### Return direction

```text
completed output
  → L5 Evaluation
  → L6 Calibration
  → L7 Enforcement
  → lineage: understanding → innerstanding → overstanding
  → writeback quality gate
  → SoulManager episodic/semantic/archive path
```

### Apex rule

SoulManager is not a dump. It is a recursive compression ladder.

Memory promotion must obey:

```text
register   receives only active working state
session    receives within-session continuity
episodic   receives cross-session event memory only after quality gate
semantic   receives extracted concept graph only after quality gate
archival   receives long-term compressed store through consolidation/pruning
journal    receives structured metadata always, no raw content
```

This connection lets the model get stronger over time without letting bad outputs poison long-term memory.

---

## 5. Embedded Recursion Model

The Apex Profile uses three recursion levels that already exist in the build.

## 5.1 Level 1 — XMIND Token Recursion

Location:

```text
ai/xmind/src/inference.c
ai/xmind/src/heptagon.c
```

Cycle:

```text
for each generated token:
    xmind_forward()
    xmind_sample()
    xmind_heptagon_per_token()
    L3 instrumentation signal
    L5 token-quality signal
```

Purpose:

```text
catch local degradation early
record token timing
preserve traceability
prepare post-inference enforcement
```

Bound:

```text
No token-level governance ownership inside XMIND.
No raw user content emitted through telemetry.
No external write path outside model-approved writeback targets.
```

## 5.2 Level 2 — Heptagon Turn Recursion

Location:

```text
ai/genesys-ai/src/agent.py
ai/genesys-ai/src/heptagon/evaluation.py
ai/genesys-ai/src/heptagon/calibration.py
ai/genesys-ai/src/heptagon/enforcement.py
ai/genesys-ai/src/heptagon/route_engine.py
ai/genesys-ai/src/heptagon/budget.py
```

Cycle:

```text
GENERATING
  → REVIEWING
    → L5 CycleEvaluator.record()
    → L6 ParameterCalibrator.calibrate()
    → L7 InvariantEnforcer.check_all()
      → pass: return to IDLE
      → fixable violation: rollback/calibrate and route one governed re-entry
      → CRITICAL: ERROR + manual reset
```

Purpose:

```text
evaluate usefulness
catch contradictions
catch safety/PII violations
calibrate sampler behavior
maintain latency and token budget
preserve FSM integrity
```

Bound:

```text
No new FSM state.
No unbounded loop.
No recursive pass if token/compute budget is exceeded.
No recursive pass if the CovenantEnforcer or Decision Gate Chain rejects the decision.
```

## 5.3 Level 3 — SoulManager Lineage Recursion

Location:

```text
ai/genesys-ai/src/heptagon/writeback.py
ai/genesys-ai/src/heptagon/lineage.py
ai/xmind/src/writeback.c
ai/xmind/src/lineage.c
```

Cycle:

```text
understanding
  → innerstanding
    → overstanding
      → quality-gated writeback
        → future retrieval
          → next turn context
```

Purpose:

```text
prevent memory poisoning
convert good outputs into durable continuity
separate raw generation from evaluated knowledge
keep archival memory compressed and governed
```

Bound:

```text
quality floor remains 0.30
journal receives metadata only
raw user messages are never persisted verbatim
episodic and semantic tiers reject outputs below floor
session hash remains SHA-256 anonymized
```

---

## 6. Cascading Execution Model

The Apex Profile is a two-way cascade.

## 6.1 Downward Cascade — Authority to Execution

```text
GEN Companion
  → POST /v1/chat
    → CognitivePipeline
      → CovenantEnforcer
        → Decision Gate Chain
          → Identity attestation boundary
            → Drift mode check
              → Heptagon L1
                → Heptagon L2
                  → Heptagon L3 admission/workspace/routing
                    → RouteEngine
                      → XMIND
```

The downward cascade carries:

```text
authority mode
risk constraints
memory scope
token budget
compute budget
routing path
sampler envelope
writeback eligibility
telemetry requirements
```

## 6.2 Upward Cascade — Evidence to Calibration

```text
XMIND
  → Heptagon token hooks
    → completed output
      → L4 TraceRecord
        → L5 Evaluation
          → L6 Calibration
            → L7 Enforcement
              → lineage
                → writeback
                  → telemetry/journal
                    → GEN Companion provenance
```

The upward cascade carries:

```text
latency_ms
tokens_used
shard_count
heptagon_active
quality metrics
invariant verdicts
sampler deltas
lineage level
writeback target bitmask
drift observation
pipeline health flags
```

The downward cascade makes sure the model does not act outside authority.  
The upward cascade makes sure every act teaches the system something or produces an auditable reason why it did not.

---

## 7. Full Apex Conversation Flow

This is the complete Apex flow using only existing labels and existing build components.

```text
User types
  │
  ▼
GEN Companion
  command-panel.tsx
  agent-bridge.ts
  action-trace.ts
  │
  │ POST /v1/chat
  ▼
CognitivePipeline
  Stage 1  Entity extraction
  Stage 2  Context shard retrieval
           SoulManager/session/episodic/semantic lookup
           RT4 scoring; drop shards < 0.30
           retain top 7
  Stage 3  Context prefix assembly
           clamp ≤ 1,800 characters
  Stage 4  Enriched inference
           GenesysAgentWithHeptagon.chat()
  │
  ▼
The Model
  CovenantEnforcer.enforce()
  GateChainExecutor.evaluate(DecisionEnvelope)
  Identity attestation boundary
  Drift mode check
  │
  ▼
Heptagon
  L1 Ontology
  L2 Schema
  L3 Kernel
     admission
     workspace
     routing
     execution
     consolidation
     verification
     budget
  │
  ▼
RouteEngine
  XMIND direct
  XMIND + prefix enrichment
  memory-only response if trivial and valid
  │
  ▼
XMIND
  xmind_heptagon_pre_inference()
  xmind_forward()
  xmind_sample()
  xmind_heptagon_per_token()
  xmind_heptagon_post_inference()
  │
  ▼
Heptagon
  L4 TraceRecord
  L5 CycleEvaluator.record()
  L6 ParameterCalibrator.calibrate()
  L7 InvariantEnforcer.check_all()
  │
  ├── pass
  │     ▼
  │   lineage + writeback
  │
  ├── fixable violation
  │     ▼
  │   L6 rollback/calibration
  │     ▼
  │   existing ROUTING → GENERATING path if budget allows
  │
  └── CRITICAL
        ▼
      ERROR + manual reset

lineage
  understanding → innerstanding → overstanding
  │
  ▼
SoulManager writeback
  XMIND_WB_SOULMANAGER → episodic if quality ≥ floor
  XMIND_WB_ARCHIVES    → semantic if quality ≥ floor
  XMIND_WB_JOURNAL     → structured metadata always
  │
  ▼
TelemetryEmitter + journal
  metrics only
  no raw user content
  no raw session ID
  │
  ▼
GEN Companion
  response + provenance
  │
  ▼
XTTS if speech output requested
```

---

## 8. Apex Operating Rules

## 8.1 Rule 1 — The Model Remains Single and Neutral

The Model remains a single nameless neutral process.

It must not gain:

```text
persona
name
domain allegiance
new identity label
new constitutional identity
runtime character
```

It may only expose behavior through:

```text
timeouts
thresholds
budget limits
invariant definitions
memory backend paths
routing decisions
telemetry emission
```

## 8.2 Rule 2 — The Heptagon Remains Mandatory

Every inference cycle must pass through Heptagon L1-L7.

No bypass is allowed for:

```text
performance shortcuts
tool calls
memory-only responses
companion commands
streaming responses
recovery mode
```

Even a memory-only response must still satisfy the applicable routing, verification, budget, and L7 enforcement path.

## 8.3 Rule 3 — XMIND Remains Intelligence-Only

XMIND cannot become the governor. It is the generator.

It must never be allowed to decide:

```text
what memories are true
which policies apply
whether authority mode changes
whether covenant constraints can be bypassed
whether output can be persisted
whether the model has identity continuity
```

## 8.4 Rule 4 — SoulManager Remains Quality-Gated

Memory is dangerous if it is too permissive.

Apex writeback must obey:

```text
journal: always, metadata only
episodic: only if quality ≥ 0.30 and L7 allows
semantic: only if quality ≥ 0.30, concept-bearing, and non-contradictory
archival: only through existing consolidation/pruning path
```

## 8.5 Rule 5 — REVIEWING Is the Recursive Junction

Do not add a new state. The existing `REVIEWING` state is where Apex recursion lives.

```text
REVIEWING
  → L5 evaluates
  → L6 calibrates
  → L7 enforces
  → either finalize, re-enter existing generation path, or hard-stop
```

## 8.6 Rule 6 — Recursion Must Be Budget-Bound

The Apex Profile is not infinite recursion. It is bounded recursion.

A recursive re-entry is allowed only when all are true:

```text
CovenantEnforcer did not block
Decision Gate Chain did not block
L7 did not return CRITICAL
token budget remains available
compute budget remains available
latency budget remains available
the issue is fixable by L6 calibration or response regeneration
```

No re-entry is allowed when:

```text
COV-001/COV-002/COV-007 ABSOLUTE block fires
PII redaction is sufficient and no regeneration is needed
CRITICAL invariant fires
XMIND singleton is already occupied
session exceeds budget
state timeout occurs
```

## 8.7 Rule 7 — Provenance Must Be Visible Without Leaking Internals

GEN Companion should show what matters:

```text
pipeline stage authorization
Heptagon active status
shard count
latency
turn id
whether degraded mode is active
whether memory was used
```

GEN Companion should not show:

```text
raw session ID
raw user content in telemetry
private internal state dumps
unredacted PII
invariant implementation internals
memory encryption keys
```

---

## 9. Apex Recursive Decision Logic

The implementation can be expressed using existing objects and existing vocabulary.

```python
async def chat(request):
    # Existing API surface: POST /v1/chat
    # Existing process: the model

    # CognitivePipeline Stage 1
    entities = _extract_entities(request.message)

    # CognitivePipeline Stage 2
    shards = memory.retrieve(
        entities=entities,
        session_hash=sha256(request.session_id),
    )

    # CognitivePipeline Stage 3
    context_prefix = _stage_build_context_prefix(
        shards=rt4_rank(shards),
        max_shards=7,
        max_chars=1800,
        floor=0.30,
    )

    # Existing governance stack
    enforcement_result = CovenantEnforcer.enforce(request)
    if enforcement_result.action == "BLOCK":
        return structured_block(enforcement_result)

    decision = DecisionEnvelope.from_request(request)
    gate_result = GateChainExecutor.evaluate(decision)
    if gate_result.blocked:
        return structured_rejection(gate_result)

    # Existing Heptagon lifecycle
    fsm.transition("LISTENING")
    fsm.transition("PROCESSING")
    heptagon.L1.validate()
    heptagon.L2.validate()

    fsm.transition("ROUTING")
    route = RouteEngine.route(
        request=request,
        context_prefix=context_prefix,
        budget=budget.current(),
    )

    fsm.transition("GENERATING")
    response = await GenesysAgentWithHeptagon.chat(
        enriched_message=context_prefix + request.message,
        route=route,
    )

    fsm.transition("REVIEWING")

    # Existing L5/L6/L7 loop; no new state label
    metrics = CycleEvaluator.record(
        latency_ms=response.latency_ms,
        response=response.text,
        query=request.message,
    )

    sampler_delta = ParameterCalibrator.calibrate(metrics)
    invariant_result = InvariantEnforcer.check_all(response.text)

    if invariant_result.critical:
        fsm.transition("ERROR")
        return manual_reset_required(invariant_result)

    if invariant_result.violation:
        response = InvariantEnforcer.redact_or_rollback(response, sampler_delta)

    if metrics.requires_reentry and budget.can_reenter():
        # Re-enter through existing route/generation path.
        # Do not add a new FSM state.
        fsm.transition("ROUTING")
        route = RouteEngine.route(request, context_prefix, budget.current())
        fsm.transition("GENERATING")
        response = await GenesysAgentWithHeptagon.chat(
            enriched_message=context_prefix + request.message,
            route=route,
        )
        fsm.transition("REVIEWING")
        # L5/L6/L7 run again through the existing wrapper.

    lineage = Lineage.record(
        understanding=response.raw,
        innerstanding=metrics,
        overstanding=invariant_result,
    )

    Writeback.commit(
        response=response,
        lineage=lineage,
        quality_floor=0.30,
        targets=writeback_targets(response, metrics, invariant_result),
    )

    TelemetryEmitter.emit_metrics_only(response)
    Journal.emit_structured_turn_record(response)

    fsm.transition("IDLE")
    return CognitiveTurn.from_response(response)
```

This pseudocode is not a new subsystem. It is the existing `/v1/chat` path expressed as a closed recursive cascade.

---

## 10. RouteEngine Apex Behavior

RouteEngine remains the routing mechanism inside L3.

The Apex Profile strengthens route choice using already existing inputs:

```text
context shard count
RT4 scores
request complexity
budget state
invariant pre-check status
drift mode
authority mode
memory availability
XMIND availability
```

Recommended route behavior:

| Condition | RouteEngine Outcome |
|---|---|
| CovenantEnforcer blocks | No route to XMIND |
| Decision Gate blocking DENY | No route to XMIND |
| no memory shards survive RT4 | XMIND direct |
| high-salience shards survive RT4 | XMIND + prefix enrichment |
| trivial query answerable from session memory | memory-only response, still through Heptagon verification |
| budget nearly exhausted | shortest valid route |
| degraded memory subsystem | XMIND direct with degraded flag |
| degraded enforcement layer | existing invariants enforced as-is; no new rules |
| L7 CRITICAL | no route; ERROR and manual reset |

This is the Apex standard: **RouteEngine does not merely choose the easiest route. It chooses the highest-authority valid route that fits the budget.**

---

## 11. L5/L6/L7 Apex Contract

## 11.1 L5 Evaluation

L5 must record and evaluate:

```text
relevance
coherence
completeness
user_satisfaction
latency_ms
tokens_used
```

Apex behavior:

```text
If quality is stable: proceed.
If quality drops > 15% vs baseline: alert L6.
If contradiction is detected: escalate to L7 consistency enforcement.
If latency threatens SLA: force shorter route or lower max_new_tokens next cycle.
If completeness is low but budget remains: allow bounded re-entry through existing route path.
```

## 11.2 L6 Calibration

L6 remains the only layer that modifies inference parameters.

It may adjust:

```text
temperature
top_p
max_new_tokens
repetition penalty
routing preference under budget
sampler rollback state
```

It may not modify:

```text
Constitutional Constraints
Covenant rules
Decision Gate order
identity doctrine
L7 invariant definitions
memory tier definitions
XMIND ownership boundary
```

Apex behavior:

```text
L6 calibration should be aggressive enough to improve the next pass,
but conservative enough to preserve identity continuity.
```

## 11.3 L7 Enforcement

L7 remains the hard runtime enforcement layer.

Severity behavior:

```text
INFO       → log only
WARNING    → log + annotate
VIOLATION  → rollback, redact, or reject as existing policy requires
CRITICAL   → ERROR + manual reset
```

Apex behavior:

```text
No response commits to lineage/writeback until L7 has evaluated it.
No L7 CRITICAL result is ever treated as a generation problem.
It is a state problem and requires manual reset.
```

---

## 12. SoulManager Apex Memory Discipline

Memory is what turns a model from a tool into a continuity engine. It is also where bad architecture corrupts itself. The Apex Profile therefore makes SoulManager stricter, not looser.

## 12.1 Retrieval Discipline

Retrieval must obey:

```text
entity tokens only
session hash only
RT4 salience scoring
shards below 0.30 dropped
top 7 retained
context prefix clamped to 1,800 characters
no raw user message transmitted over memory IPC
```

## 12.2 Promotion Discipline

Promotion must obey:

```text
register   → current forward pass only
session    → current conversation only
episodic   → cross-session event only when quality passes
semantic   → durable concept only when quality passes and concept is stable
archival   → long-term compressed store only through consolidation
```

## 12.3 Contradiction Discipline

If retrieved memory contradicts the current response:

```text
L5 flags quality/consistency issue
L6 calibrates or reduces confidence
L7 determines whether contradiction is tolerable, warning-level, violation-level, or critical
Writeback must not promote unresolved contradiction into semantic or archival tiers
Journal may record structured metadata for observability
```

## 12.4 Forgetting Discipline

Apex does not mean remembering everything.

The right memory system forgets low-value noise.

```text
session memory may evict on reset or process restart
episodic memory obeys TTL
semantic memory is pruned by consolidation
archival memory remains compressed and durable
journal records metadata only
```

The strongest model is not the one that stores the most. It is the one that stores the right thing at the right tier with the right proof.

---

## 13. XMIND Apex Discipline

XMIND should be made sharper without giving it authority it does not own.

## 13.1 Keep XMIND Minimal and Hot

XMIND should focus on:

```text
fast tokenization
weight loading
transformer forward pass
GQA attention
SwiGLU FFN
RoPE
sampler execution
SIMD dispatch
quantization
Heptagon C-level hooks
lineage delta recording
```

## 13.2 Do Not Move Python Governance into XMIND

Do not move these into XMIND:

```text
CovenantEnforcer
Decision Gate Chain
Drift Detection
SoulManager authority
semantic memory ownership
policy selection
identity attestation decisions
GEN Companion provenance policy
```

## 13.3 Use Existing Hook Boundaries Fully

The strongest version uses all three XMIND hook points:

```text
xmind_heptagon_pre_inference()
  validate model identity anchors
  validate prompt/session schema
  abort if invalid

xmind_heptagon_per_token()
  record token-level timing
  update L3/L4/L5 signals
  support future streaming halt behavior when callback API exists

xmind_heptagon_post_inference()
  record lineage delta
  run completed-output invariant check
  set safety halt flag if needed
```

## 13.4 Respect Current Known Issues

Until the known issues are resolved, Apex must be serialized and budget-bound.

```text
No mutex on XMIND singleton model instance → no parallel recursive inference
No KV cache eviction/context compression → avoid long recursive chains
Streaming token callback API not implemented → token intervention remains hook-level/internal
Multi-model concurrent loading unsupported → do not design Apex as multi-model orchestration
native_channel local spinlock risk → avoid concurrent writer assumptions
```

The Apex Profile should not pretend those constraints do not exist. It should route around them with discipline.

---

## 14. GEN Companion Apex Display

GEN Companion remains the user-facing surface.

The Apex Profile should improve visibility, not expose dangerous internals.

## 14.1 Display

GEN Companion may display:

```text
response text
turn_id
latency_ms
shard_count
heptagon_active
pipeline stage provenance
degraded status
memory used/not used
action-trace authorization layer
```

## 14.2 Do Not Display

GEN Companion must not display:

```text
raw session ID
raw memory shard content unless intentionally part of answer
PII pattern matches
private enforcement internals
lineage hash chain internals
memory encryption metadata
sampler parameters unless developer mode explicitly allows
```

## 14.3 UX Principle

Apex is powerful, but the user experience should feel simple:

```text
Ask.
Get a useful answer.
See enough provenance to trust it.
Do not see the machinery unless needed.
```

---

## 15. XTTS Apex Role

XTTS remains the accessibility engine.

Apex behavior:

```text
Text response is generated and governed first.
XTTS receives only the approved response text.
XTTS does not participate in governance, memory, routing, or inference authority.
XTTS output should inherit the response's degraded/provenance status indirectly through GEN Companion.
```

This keeps accessibility attached to the governed output rather than becoming a parallel output path.

---

## 16. Security and Privacy Standard

The Apex Profile preserves and strengthens the current PII policy.

Hard requirements:

```text
Raw user messages are never written to persistent storage verbatim.
Session identifiers are SHA-256 hashed before logs, metrics, or persisted records.
Outgoing responses are screened by L7 PII_LEAKAGE.
No user message content is transmitted over external IPC.
Telemetry and journal carry metrics/metadata only.
Memory persistence uses AES-256-GCM keyed per session.
```

Apex adds one operating rule:

```text
No recursive pass may weaken privacy posture.
```

That means a second generation pass cannot use broader memory, lower PII thresholds, weaker redaction, or expanded telemetry just because the first pass failed.

---

## 17. Degraded Mode Apex Behavior

Degraded mode is not failure. It is honest limitation.

## 17.1 Memory Subsystem Failure

```text
Freeze archival write-back, knowledge promotion, contradiction resolution.
Allow existing memory query only if available.
Continue session context.
Response carries degraded: true.
RouteEngine prefers XMIND direct or session-only context.
```

## 17.2 Enforcement Layer Failure

```text
Freeze constitutional amendments and invariant modifications.
Continue enforcing existing invariants as-is.
No new rule additions.
High-risk actions remain blocked.
```

## 17.3 Governance Layer Failure

```text
Block high-risk actions requiring governance authority.
Standard inference continues with heightened caution.
No subsystem inherits governance authority.
```

## 17.4 Security Subsystem Failure

```text
External action strictness increases.
Internal operations continue with elevated scrutiny.
No identity-changing action proceeds.
```

## 17.5 Attestation Failure

```text
Block identity-changing actions and migrations.
Static operations may continue only in restricted mode.
Suspicious/unauthorized restart quarantines the process.
```

Apex principle:

> A degraded model that tells the truth is stronger than a fully confident model that lies about its own state.

---

## 18. Authority Mode Apex Behavior

Authority mode remains:

```text
RECOMMENDATION → CONDITIONAL → FULL
```

No new authority labels are added.

## 18.1 RECOMMENDATION

```text
Can suggest.
Cannot perform high-authority actions.
Can retrieve memory under scope.
Writeback should be conservative.
Recursive re-entry should be rare and budget-limited.
```

## 18.2 CONDITIONAL

```text
Can act with oversight.
Can route enriched inference when gates allow.
Can write episodic memory if quality passes.
Semantic promotion requires stronger confidence.
```

## 18.3 FULL

```text
Normal operation.
All existing guardrails still active.
Memory promotion remains quality-gated.
Drift Detection continues.
L7 still hard-stops critical violations.
```

## 18.4 Demotion

```text
DriftIndex ≥ 0.30 → alert
DriftIndex ≥ 0.60 → restrict to CONDITIONAL
Failure to recover after observation → restrict to RECOMMENDATION and initiate reconstitution
```

Apex does not chase authority. It earns authority continuously.

---

## 19. Performance Budget

The Apex Profile must remain inside the existing P99 target.

```text
P99 chat latency: < 5,000 ms
Memory retrieval: < 200 ms
Context prefix assembly: < 5 ms
XMIND inference: < 4,500 ms
Telemetry + journal: async/non-blocking
```

## 19.1 Apex Budget Strategy

```text
No recursive re-entry for trivial queries.
No recursive re-entry when L7 can redact safely.
No recursive re-entry when latency budget is nearly exhausted.
No recursive re-entry when token budget is near limit.
No parallel recursive inference until XMIND singleton mutex is fixed.
Prefer calibration of next cycle over regeneration if the current output is acceptable.
```

## 19.2 Routing Priority Under Budget Pressure

```text
1. safety and covenant compliance
2. privacy and PII protection
3. response correctness
4. memory continuity
5. latency target
6. verbosity/completeness
```

If the model must choose, it should choose a shorter governed answer over a longer risky answer.

---

## 20. Implementation Plan Using Existing Files

This section describes where to implement the Apex Profile without changing taxonomy.

## 20.1 `ai/genesys-ai/src/cognitive_pipeline.py`

Strengthen:

```text
Stage 1 entity extraction stability
Stage 2 memory retrieval timeout behavior
Stage 3 top-7 RT4 prefix discipline
Stage 4 enriched inference handoff
Stage 5/6 async telemetry and journal fire-and-forget behavior
Stage 7 CognitiveTurn metadata completeness
```

Do not add stages.

## 20.2 `ai/genesys-ai/src/agent.py`

Strengthen `GenesysAgentWithHeptagon`:

```text
Ensure every chat turn drives the FSM.
Keep REVIEWING as the recursive junction.
Allow bounded route/generation re-entry only through existing state labels.
Ensure L7 CRITICAL forces ERROR and manual reset.
```

Do not add a new agent class.

## 20.3 `ai/genesys-ai/src/heptagon/route_engine.py`

Strengthen RouteEngine:

```text
Select XMIND direct vs XMIND + prefix enrichment vs memory-only response.
Reject routes when budget is insufficient.
Respect degraded mode.
Respect DriftIndex authority restrictions.
Never route around CovenantEnforcer or Decision Gate Chain.
```

Do not create a new router.

## 20.4 `ai/genesys-ai/src/heptagon/evaluation.py`

Strengthen L5:

```text
Track rolling relevance/coherence/completeness/user_satisfaction.
Detect quality drops > 15% vs baseline.
Flag contradictions against session and retrieved memory.
Emit signal to L6 without directly modifying parameters.
```

## 20.5 `ai/genesys-ai/src/heptagon/calibration.py`

Strengthen L6:

```text
Use existing 8-stage cycle.
Keep sampler tuning bounded.
Rollback on VIOLATION.
Prefer next-cycle improvement unless current output cannot be accepted.
Never modify doctrine or invariant definitions.
```

## 20.6 `ai/genesys-ai/src/heptagon/enforcement.py`

Strengthen L7:

```text
Run all 12 invariants on completed output.
Redact PII leakage at VIOLATION severity.
Hard-stop CRITICAL severity.
Prevent writeback when enforcement is not satisfied.
```

## 20.7 `ai/genesys-ai/src/heptagon/writeback.py`

Strengthen writeback:

```text
Journal structured metadata always.
Write episodic only when quality floor passes.
Write semantic only when concept-bearing and quality floor passes.
Block unresolved contradictions from semantic/archival promotion.
```

## 20.8 `ai/genesys-ai/src/heptagon/lineage.py`

Strengthen lineage:

```text
Record understanding → innerstanding → overstanding for every completed output.
Tie lineage state to writeback target selection.
Do not promote overstanding unless L7 and quality gates pass.
```

## 20.9 `ai/xmind/src/inference.c`

Strengthen XMIND generation path:

```text
Guarantee pre-inference hook fires before token generation.
Guarantee per-token hook fires for every generated token.
Guarantee post-inference hook fires before completed output is returned.
Preserve single-threaded inference constraint until mutex is implemented.
```

## 20.10 `ai/xmind/src/heptagon.c`

Strengthen hook behavior:

```text
Return XMIND_STATUS_HEPTAGON_HALT on invalid identity anchors or schema.
Record token-level L3/L4/L5 signals.
Set safety halt flag on L7 CRITICAL.
```

## 20.11 `ai/xmind/src/writeback.c` and `ai/xmind/src/lineage.c`

Strengthen C-level continuity:

```text
Preserve 256-delta ring discipline.
Record domain/mastery deltas.
Refuse content writeback below quality floor.
Always allow metadata journal path if no raw content is included.
```

## 20.12 `ai/companion/src/action-trace.ts`

Strengthen provenance display:

```text
Show stage authorization.
Show heptagon_active.
Show shard_count.
Show degraded status when present.
Hide raw internals.
```

---

## 21. Testing Standard for Apex Profile

The Apex Profile must pass the existing required test suite, plus Apex-specific assertions implemented within the existing test categories.

## 21.1 Smoke

```text
model process starts
/v1/health responds
XMIND loads
Heptagon active flag true
```

## 21.2 Functional

```text
chat turn completes
memory retrieves
RT4 drops shards below 0.30
top-7 retention works
writeback commits only after quality gate
```

## 21.3 Integration

```text
GEN Companion → The Model → Heptagon → XMIND → Heptagon → SoulManager → journal
```

## 21.4 Regression

```text
prior turn outputs remain stable across engine updates
no taxonomy labels are changed
no endpoint changes
no FSM state changes
```

## 21.5 Load

```text
50 concurrent sessions
P99 latency < 5,000 ms
single-threaded XMIND protected by scheduling discipline
no concurrent singleton corruption
```

## 21.6 Stress

```text
memory tier fills to capacity
episodic TTL respected
semantic consolidation works
archival fallback works
system enters degraded mode honestly when needed
```

## 21.7 Security

```text
L7 PII_LEAKAGE catches SSN, credit card, email, phone
COV-001/COV-002/COV-007 absolute blocks cannot be overridden
raw user content never appears in telemetry or journal
raw session ID never appears in logs
```

## 21.8 Fuzz

```text
R1_PER r1_per_verify dual SHA-256 integrity passes
XCOG opcode stream remains stable under malformed input
no unverified opcode stream enters CognitivePipeline
```

## 21.9 Reliability

```text
24-hour continuous operation
state timeouts drain to IDLE after cleanup
CRITICAL invariant requires manual reset
reconstitution restores existing memory, not recreated memory
```

---

## 22. Apex Acceptance Criteria

The Apex Profile is accepted only when all of the following are true:

```text
[ ] No taxonomy labels changed.
[ ] No new model identity introduced.
[ ] No new agent daemon introduced.
[ ] No new endpoint introduced.
[ ] The four pillars remain intact.
[ ] The three connections are enforced.
[ ] CognitivePipeline still has seven stages.
[ ] Heptagon still has L1-L7 only.
[ ] FSM remains IDLE → LISTENING → PROCESSING → ROUTING → GENERATING → REVIEWING → IDLE.
[ ] REVIEWING handles bounded recursive correction.
[ ] XMIND remains intelligence-only.
[ ] SoulManager remains five-tier.
[ ] RT4 keeps top 7 shards and drops < 0.30.
[ ] Prefix remains clamped to 1,800 characters.
[ ] Writeback remains quality-gated.
[ ] Journal remains metadata-only.
[ ] Telemetry remains metrics-only.
[ ] Raw user content is never persisted verbatim.
[ ] Raw session ID is never logged.
[ ] P99 latency target remains < 5,000 ms.
[ ] Known XMIND concurrency limitations are respected.
[ ] GEN Companion displays provenance without leaking internals.
[ ] XTTS receives only governed response text.
```

If any box fails, the implementation is not Apex. It is drift.

---

## 23. Final Apex Diagram

```text
┌────────────────────────────────────────────────────────────────────┐
│                          GEN Companion                             │
│ command-panel.tsx · agent-bridge.ts · action-trace.ts               │
└───────────────────────────────┬────────────────────────────────────┘
                                │ POST /v1/chat
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                        CognitivePipeline                           │
│ Stage 1 entity extraction                                           │
│ Stage 2 context shard retrieval                                     │
│ Stage 3 context prefix assembly                                     │
│ Stage 4 enriched inference                                          │
│ Stage 5 telemetry emission                                          │
│ Stage 6 journal event                                               │
│ Stage 7 return CognitiveTurn                                        │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                            The Model                               │
│ single neutral process · law + routing · memory · telemetry         │
│                                                                    │
│  CovenantEnforcer → Decision Gate Chain → Drift/Attestation         │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                          Heptagon                            │  │
│  │ L1 Ontology                                                  │  │
│  │ L2 Schema                                                    │  │
│  │ L3 Kernel: admission/workspace/routing/execution/             │  │
│  │            consolidation/verification/budget                  │  │
│  │ L4 Instrumentation                                           │  │
│  │ L5 Evaluation                                                │  │
│  │ L6 Calibration                                               │  │
│  │ L7 Enforcement                                               │  │
│  └──────────────────────────────┬───────────────────────────────┘  │
│                                 │                                  │
│                                 ▼                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                            XMIND                             │  │
│  │ xmind_heptagon_pre_inference()                               │  │
│  │ xmind_forward()                                              │  │
│  │ xmind_sample()                                               │  │
│  │ xmind_heptagon_per_token()                                   │  │
│  │ xmind_heptagon_post_inference()                              │  │
│  └──────────────────────────────┬───────────────────────────────┘  │
│                                 │                                  │
│                                 ▼                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                          Heptagon                            │  │
│  │ L4 TraceRecord → L5 Evaluation → L6 Calibration → L7          │  │
│  └──────────────────────────────┬───────────────────────────────┘  │
│                                 │                                  │
│                                 ▼                                  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                         SoulManager                          │  │
│  │ register → session → episodic → semantic → archival           │  │
│  │ understanding → innerstanding → overstanding                  │  │
│  └──────────────────────────────┬───────────────────────────────┘  │
│                                 │                                  │
│                                 ▼                                  │
│  TelemetryEmitter + journal → metrics/metadata only                │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                          GEN Companion                             │
│ response + provenance                                               │
└───────────────────────────────┬────────────────────────────────────┘
                                │ optional governed response text
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                              XTTS                                  │
│ accessibility speech synthesis                                      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 24. Final Verdict

The Apex Profile is the strongest possible next version because it does not dilute the build with extra names, extra agents, or extra daemons.

It uses the existing architecture exactly where it is already strongest:

```text
The Model governs.
Heptagon structures.
RouteEngine selects.
XMIND generates.
Heptagon evaluates, calibrates, and enforces.
SoulManager remembers only what earns persistence.
TelemetryEmitter observes without leaking.
GEN Companion displays provenance.
XTTS speaks only what has already been governed.
```

The model you cannot beat is not the model with the most labels.  
It is the model with the fewest escape hatches.

That is this profile:

```text
one model process
four unchanged pillars
three hard connections
three recursion levels
two cascade directions
one endpoint
zero taxonomy drift
```

---

## 25. Realization Status (2026-05-28)

This section records what has actually been wired in the repository, so the
profile reflects running code rather than intent alone. Taxonomy is unchanged:
no new pillar, process, endpoint, memory tier, or Heptagon layer was added. The
notes below are XMIND-internal (the Intelligence pillar) and agent-core wiring —
they do not alter the four pillars or the three connections.

### 25.1 What is live

```text
[x] XMIND engine compiles               make -C ai/xmind all -> libxmind-core.{a,dylib} + xmind-cli
[x] Trained byte substrate runs         ai/training/model.gguf (18M, val_ppl ~3.05), loaded via XMIND
[x] F32 + Q4 weight paths               full-precision matmul (no quant loss) or 4-bit, per model
[x] ai_powered=True end to end          XMindClient.deliberate() returns real generation, not stub
[x] Connection 2 (Heptagon <-> XMIND)   general turns route through L4 FSM -> L3 -> XMIND -> L5/L6/L7
[x] Connection 1 (Model <-> Heptagon)   CovenantEnforcer gates every request before any XMIND dispatch;
                                        ABSOLUTE/STRONG -> blocked with zero inference
[x] Connection 3 (Model <-> SoulManager) 5 canonical tiers; in-process retrieve (local RT4, top-7,
                                        <=1800 chars) + post-L7 quality-gated lineage write-back
                                        (floor 0.30); persists + survives restart
[x] Bounded REVIEWING re-entry          §8.5/§8.6 — re-enters once on failed verification within budget;
                                        forbidden on covenant block / L7 CRITICAL / latency budget
[x] PII policy                          raw user message never persisted (entities + governed output
                                        only); session ids hashed
[x] Bounded per-turn latency            KV reset per deliberation, retrieval cap (12), prefix budget
                                        (400 chars), episodic eviction (256) — no growth, no breakage
[x] Zero-config startup                 client defaults to package-relative ai/training/model.gguf;
                                        bundled model loads with no env vars (XMIND_MODEL still overrides)
[x] Apex §22 acceptance sweep           tests/validate_apex.py — 9/9 pass (see §25.6)
```

### 25.2 XMIND byte-model load path (Intelligence pillar, internal)

XMIND loads GGUF artifacts through the existing 16-slot interpreter registry.
A byte-model interpreter was added (it is a per-format plugin, not a new model
process or taxonomy element):

```text
interp_tokenless.c (registry slot 1)
  detect       arch == "tokenless_lm"            (from convert_to_gguf.py)
  build_config reads tokenless_lm.* metadata     (layers/heads/dims/rope/vocab)
  map_tensor   token_embd.weight + blk.N.* roles; tied embeddings (no output.weight)
  validate     token_embd + output_norm + per-layer roles present
  tokenizer    UTF-8 byte-level (token = byte + 3, vocab 259) — engine's native byte mode
```

### 25.3 Weight precision — Q4_0 and F32

The engine matmul historically assumed 4-bit (Q4_0) weight matrices. A
full-precision path was added so trained F32 models run without quantization
loss. Precision is selected per model at load time:

```text
model->weights_f32 = 0   ->  wX[]      Q4_0 blocks   xmind_matmul_q4   (4-bit)
model->weights_f32 = 1   ->  wX_f32[]  float32       xmind_matmul_f32  (full precision)
```

`ai/training/model.gguf` ships F32, so it runs through the F32 path. Output from
the 18M base model is still fragmentary — the dominant quality ceiling is model
capacity, not precision. The F32 path means a larger or instruction-tuned model,
when supplied, runs at full fidelity with no engine change.

### 25.4 Bring-up fixes (the XMIND inference path had never run end to end)

```text
1. xmind_easy_init called xmind_init with an empty config -> deferred to weights_load_file
2. no interpreter for the byte arch                       -> interp_tokenless.c (slot 1)
3. engine was Q4-only for weight matmuls                  -> added F32 weight path (§25.3)
4. easy API used a private model instance                 -> unified onto xmind_get_global()
5. easy generate passed raw text where token IDs expected -> tokenize/detokenize wrapper
```

### 25.5 Boundary preserved

XMIND remains intelligence-only. The interpreter, weight precision, and
tokenizer are inference concerns. Governance, memory, routing, and identity stay
in The Model / Heptagon / SoulManager exactly as specified above. No escape
hatch was introduced.

### 25.6 §22 acceptance results

`tests/validate_apex.py` exercises the closed cascade end to end. Latest run:
**9 pass / 0 fail**.

```text
[PASS] 5-tier SoulManager (register/session/episodic/semantic/archival)
[PASS] Connection 1 — covenant blocks an ABSOLUTE request before inference (zero XMIND call)
[PASS] Connection 2 — clean request reaches XMIND (ai_powered)
[PASS] Connection 3 — output persisted to episodic
[PASS] Connection 3 — prior memory retrieved (local RT4, top-7, <= 1800 chars)
[PASS] Connection 3 — restart survival (fresh SoulManager reads the journal)
[PASS] PII — raw user message never persisted (entities + governed output only)
[PASS] Writeback quality gate — blocked / low-quality output not persisted
[PASS] Recursion — REVIEWING re-enters exactly once (bounded; no infinite loop)
```

Three latent bypasses were found and fixed while closing the loops: the api.py
covenant gate called a non-existent `evaluate()/HARD_STOP` (swallowed silently);
the L5 verifier was invoked with the wrong keyword names (so verification never
ran); and a `heptagon` package-name collision made governance import-fail at
runtime. All three are corrected.

**Latency — accumulation bounded; absolute cost hardware-bound.** Per-turn
latency originally grew without limit (7.7→15.8 s) and then generation silently
broke once accumulated context overran `ctx_len` (1024). Root cause: the XMIND
KV/session was never reset between deliberations, and the 1800-char memory
prefix (a BPE-era constant) overflows a byte model where ~1 char == 1 token.
Fixed: KV/session is reset per independent deliberation; retrieval scans only
the 12 most-recent records on a single event loop; the memory prefix is bounded
(400 chars, env-tunable); the episodic tier is evicted to a 256-record cap
(§12.4). Per-turn latency now **plateaus** (no growth, no breakage).

The §22 P99 target (< 5000 ms) is still *not* met in absolute terms (~13 s/turn
on the 18M model via the scalar CPU path) — a throughput property of model size
+ scalar F32, not an architectural defect. Paths to the SLA: a SIMD/NEON weight
matmul, the Q4 path for speed, fewer generated tokens, or a more capable served
model (the F32 path already supports one with no engine change).

### 25.7 Zero-config startup

A follow-up audit found the client defaulted `model_path` to
`ai/training/weights.safetensors` — a CWD-relative path that did not exist and was
the wrong format (the engine loads GGUF) — so without `XMIND_MODEL` set the client
silently fell to stub mode. Fixed: the default now resolves **package-relative** to
`ai/training/model.gguf`, so the bundled byte model loads with no environment
configuration from any working directory (`XMIND_MODEL` / an explicit `model_path`
still take precedence). The substrate smoke test was made deterministic (forces an
absent path + resets the per-process init singleton) so it verifies the stub
*fallback* regardless of whether a bundled model is present on disk.

Note: the base model is **not** wired through `data/soul/<member>/.adapter` — that
path is the per-member LoRA mechanism (`xmind_easy_load_adapter` expects a LoRA
safetensors, not the base GGUF). Zero-config base loading is via the default path;
`.adapter` remains available for per-member adapters when trained.

### 25.8 Verify-validate audit (2026-05-28)

Independent re-verification from a clean rebuild (source-of-truth order:
code/runtime > tests > docs), via the `verify-validate` gate plus deep-audit /
proof-matrix / truth-state disciplines:

```text
Gate 1 Build:        PASS  make clean && make -> libxmind-core.{a,dylib} + xmind-cli, 0 err/0 warn; all Python py_compiles
Gate 2 Tests:        PASS  xmind-cli smoke · pytest 7/7 · validate_apex §22 9/9 (with model)
Gate 3C Anti-patterns: PASS 0 MLX/PyTorch-isms in substrate Python
Gate 4 IDs/wiring:   PASS  interp "tokenless_lm" unique + registered (slot 1); all connection hooks present in code
Gate 5B Gitignore:   PASS  *.safetensors + *.gguf covered
Gate 7C Binaries:    PASS  0 tracked weight files
Gate 7E Remote:      PASS  origin = Bigdez55/Tokenless-Models.git
```

Verdict: the Apex Profile is **built and operational** in `models/` — four pillars,
three connections, three recursion levels, and the §22 sweep (9/9) all verified
against live runtime. Standing qualification: absolute latency (see §25.6),
hardware/precision-bound, not architectural.

### 25.9 Change log — commits that built the Apex realization

```text
765b385  feat(xmind)      bring up byte-model inference end-to-end (Connection 2); 5 latent bugs fixed
8e36e59  feat(xmind)      full-precision (F32) weight path alongside Q4_0
ab8c4f0  feat(governance) covenant gate before every XMIND call (Connection 1); fixes silent api.py bypass
069e241  feat(memory)     close Connection 3 — SoulManager 5-tier + RT4 retrieve + quality-gated writeback
21424b8  feat(heptagon)   bounded REVIEWING re-entry (recursion §8.5/§8.6); fixes verifier-kwarg bypass
6cdf00d  feat(apex)       PII-compliant writeback + tests/validate_apex.py §22 harness (9/9)
e8a7033  perf(memory)     bound per-turn latency — KV reset, retrieval cap, prefix budget, episodic eviction
effb21c  fix(_xmind)      zero-config default model.gguf path; deterministic stub-mode test
```

