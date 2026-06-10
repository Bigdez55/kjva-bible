# ADR-0002 — Local Implementation Mapping for Neutral Lifespan Cognitive Model

> Status: Proposed implementation mapping  
> Scope: `models v7/` repository layout supplied by the user  
> Relationship to ADR-0001: **references ADR-0001 only; does not edit, rewrite, or supersede ADR-0001**  
> Purpose: give coding agents a clean, repository-specific wiring map without importing reference-source names or changing taxonomy

---

## 0. Immutability and Source-of-Truth Rule

**ADR-0001 is immutable. Do not edit ADR-0001.**

Coding agents must not modify, rewrite, append to, reformat, rename, or regenerate ADR-0001 or the locked ADR-0001 copy under any circumstances.

This ADR exists because ADR-0001 must remain stable. All repository-specific implementation mapping belongs here or in a later ADR.

### 0.1 Required Agent Behavior

Before coding, the agent must acknowledge:

```text
ADR-0001 is read-only.
ADR-0002 maps ADR-0001 to this repository.
No external reference-source names may be imported as runtime taxonomy.
No archived document may override the active implementation mapping.
No new architecture labels may be invented unless a later ADR explicitly authorizes them.
```

### 0.2 STOP Rule

The coding agent must stop and report if any task requires:

```text
editing ADR-0001
editing the locked ADR-0001 copy
renaming the active taxonomy
importing names from archived/reference documents as runtime components
creating a new endpoint without ADR approval
creating a new pillar without ADR approval
creating a new cognitive layer without ADR approval
creating a new memory tier without ADR approval
letting generated/build/cache directories become source of truth
```

---

## 1. Purpose

This ADR maps the neutral architecture from ADR-0001 onto the actual `models v7/` repository layout.

It is not a design-expansion document. It is a **local implementation map**.

The goal is to make the repository build operational while avoiding taxonomy contamination.

### 1.1 The Correct Mental Model

ADR-0001 defines the neutral architecture:

```text
Model Runtime
Cognitive Control System
Memory Continuity System
Inference Engine
Accessibility / Output System
Interface System
Training / Plasticity System
Governance System
Materialization Plane
Telemetry / Provenance System
```

This ADR maps those neutral roles to local repository paths.

### 1.2 What This ADR Must Prevent

The coding agent must not treat archived documents, old tech packs, old design names, or reference-source names as active architecture.

If a name appears only in archived docs, historical files, old reports, or source-reference material, it must remain reference-only.

The active build is determined by:

```text
1. ADR-0001 neutral architecture
2. ADR-0002 local path mapping
3. current repository source files
4. tests and build gates
```

Not by archived narrative documents.

---

## 2. Repository Interpretation Rules

The supplied `models v7/` directory contains active source, generated output, caches, docs, archives, tests, training artifacts, and old design material. Coding agents must classify paths before editing.

### 2.1 Active Source Zones

These are the primary editable implementation zones unless a task states otherwise:

```text
ai/tokenless-agent/src/
ai/tokenless-agent/src/heptagon/
ai/tokenless-agent/src/memory/
ai/tokenless-agent/src/sensory/
ai/xmind/include/
ai/xmind/src/
ai/xmind/loader/
ai/xmind/shim/
training/peft/
training/peft/v2/
training/programs/
training/scripts/
training/pt/
governance/
heptagon/
soul_manager/
tests/
training/tests/
ai/xmind/tests/
```

### 2.2 Read-Only or Caution Zones

These are source-of-context or artifact zones. They must not be casually edited.

```text
ADR-0001 files                         read-only
DO_NOT_MODIFY.md                       read first; do not violate
BASE_MODEL_CARD.md                     metadata; edit only with explicit model-card task
PROVENANCE.md                          provenance; edit only with explicit provenance task
INHERITANCE_MANIFEST.md                manifest; edit only with explicit manifest task
TOKENLESS_*                            status/authority docs; do not use to create taxonomy
adr/                                  existing ADRs; do not rewrite unless task explicitly targets them
docs/_archive/                         reference-only; do not import active taxonomy from here
ai/companion/dist/                     generated build output
ai/companion/node_modules/             dependency directory
ai/xmind/build/                        build artifacts
.pytest_cache/                         cache
.ruff_cache/                           cache
__pycache__/                           cache
training/runs/                         training outputs/artifacts; do not edit manually
training/gguf/                         exported model artifacts; do not edit manually
training/adapters/staging/             artifacts; modify only through training/deployment task
training/adapters/gated/               gated artifacts; modify only through approved promotion task
```

### 2.3 Archive Rule

Anything in `docs/_archive/` is reference-only.

Do not copy names, role labels, subsystem labels, or taxonomies from archived tech packs into active code.

The archive may be used to understand history. It must not define the current implementation.

---

## 3. Neutral Role to Local Path Mapping

| Neutral ADR-0001 Role | Local Repository Mapping | Implementation Notes |
|---|---|---|
| **Model Runtime** | `ai/tokenless-agent/src/api.py`, `agent.py`, `cognitive_pipeline.py`, `workspace.py`, `_xmind_glue.py`, `federation_adapter.py` | Owns turn lifecycle, chat surface, pipeline calls, and integration wiring. Do not create a second runtime. |
| **Cognitive Control System** | `ai/tokenless-agent/src/heptagon/*`, root `heptagon/*` | Governs state, routing, evaluation, calibration, enforcement, lineage, writeback, budget, and registry behavior. Keep as control layer, not a new agent. |
| **Memory Continuity System** | `ai/tokenless-agent/src/memory/*`, `soul_manager/*` | Provides session, episodic, experience atom, recall trail, lifespan ledger, consolidation, and message framing. |
| **Inference Engine** | `ai/xmind/include/*`, `ai/xmind/src/*`, `ai/xmind/loader/*`, `ai/xmind/shim/*`, `_xmind/client.py` | Performs materialized inference, tokenization, weight loading, adapter runtime, and hook integration. Does not own governance or memory truth. |
| **Sensory Evidence System** | `ai/tokenless-agent/src/sensory/evidence.py`, `home_security.py`, `router.py`, `ai/xmind/src/r1_per.c`, `ai/xmind/include/r1_per.h` | Converts sensory/user/environmental input into governed evidence. Sensors must enter as evidence envelopes, not raw cognition. |
| **Training / Plasticity System** | `training/peft/*`, `training/peft/v2/*`, `training/programs/*`, `training/scripts/*`, `training/pt/*`, `training/tests/*` | Handles method registry, method ontology, adapter IR, adapter genome, deterministic routing, sensory plasticity, tournament v2, and adapter proofs. |
| **Materialization Plane** | `ai/xmind/src/materialize.c`, `ai/xmind/include/xmind_materialize.h`, `ai/xmind/src/weights_loader.c`, `ai/xmind/loader/weights_loader_mmap.c`, `ai/xmind/src/gguf_reader.c`, `ai/xmind/src/interp_registry.c`, `ai/xmind/src/interp_tokenless.c` | Converts abstract artifacts into runtime state: model weights, tensors, adapters, sessions, evidence, memory packets, outputs, and provenance. |
| **Adapter Runtime** | `ai/xmind/src/adapter_ir.c`, `adapter_runtime.c`, `adapter_cache.c`, `adapter_telemetry.c`, matching headers | Executes adapter programs natively; must be signature/scope/gate aware. |
| **Governance System** | `governance/*`, `constitution/*`, `ai/tokenless-agent/src/heptagon/enforcement.py`, `drift_detector.py`, `invariant_engine.py`, `verification.py` | Applies gate evaluation, enforcement, drift, degraded mode, authority, storage envelopes, and rationale cards. |
| **Interface System** | `ai/companion/src/*` | User-facing interface. Treat as UI only. It must not become architectural authority. |
| **Accessibility / Output System** | `ai/tts/*` | Output/speech accessibility only. It must receive governed response text, not bypass runtime. |
| **Telemetry / Provenance System** | `ai/xmind/src/telemetry.c`, `ai/xmind/include/xmind_telemetry.h`, `ai/companion/src/action-trace.ts`, governance rationale/storage envelopes | Emits metrics, traces, provenance, and safe rationale records. No raw user content or raw session IDs. |
| **Tests / Validation** | `tests/*`, `training/tests/*`, `ai/xmind/tests/*` | All implementation work must include matching tests or validation updates. |

---

## 4. Active Architecture Wiring

The local implementation must follow this foundation cycle:

```text
Model Runtime
  → Cognitive Control System
    → Memory Continuity System
      → Cognitive Control System
        → Inference Engine
          → Cognitive Control System
            → Memory Continuity System
              → Model Runtime
```

This is the clean neutral version of the four-pillar cycle.

### 4.1 Edge A — Model Runtime → Cognitive Control System

Purpose:

```text
admit request
create active frame
select route conditions
apply initial governance
enter state machine
```

Primary local files:

```text
ai/tokenless-agent/src/agent.py
ai/tokenless-agent/src/api.py
ai/tokenless-agent/src/cognitive_pipeline.py
ai/tokenless-agent/src/heptagon/state_machine.py
ai/tokenless-agent/src/heptagon/route_engine.py
governance/interceptors.py
governance/decision_envelope.py
governance/covenant_enforcer.py
```

Required data contracts:

```text
EvidenceEnvelope
ActiveFrame
DecisionEnvelope
GovernanceVerdict
RouteRequest
```

### 4.2 Edge B — Cognitive Control System → Memory Continuity System

Purpose:

```text
request context
ask for recall expansion
request contradiction checks
request prior lineage
request source/experience pointers
```

Primary local files:

```text
ai/tokenless-agent/src/cognitive_pipeline.py
ai/tokenless-agent/src/heptagon/route_engine.py
ai/tokenless-agent/src/heptagon/verification.py
ai/tokenless-agent/src/memory/session.py
ai/tokenless-agent/src/memory/episodic.py
ai/tokenless-agent/src/memory/experience_atom.py
ai/tokenless-agent/src/memory/lifespan_ledger.py
ai/tokenless-agent/src/memory/recall_trail.py
soul_manager/soul_manager.py
soul_manager/consolidation.py
```

Required data contracts:

```text
MemoryQuery
MemoryContextPacket
RecallRequest
RecallTrail
ExperienceAtom
LifespanLedgerEntry
```

### 4.3 Edge C — Memory Continuity System → Cognitive Control System

Purpose:

```text
return recalled shards
return temporal anchors
return sensory anchors
return semantic links
return contradiction flags
return correction history
return confidence scores
return privacy/retention classes
```

Primary local files:

```text
ai/tokenless-agent/src/memory/experience_atom.py
ai/tokenless-agent/src/memory/recall_trail.py
ai/tokenless-agent/src/memory/lifespan_ledger.py
ai/tokenless-agent/src/heptagon/evaluation.py
ai/tokenless-agent/src/heptagon/consolidation.py
ai/tokenless-agent/src/heptagon/lineage.py
```

Required data contracts:

```text
MemoryContextPacket
RecallTrail
MemoryConfidence
ContradictionFlag
CorrectionRecord
PrivacyClass
```

### 4.4 Edge D — Cognitive Control System → Inference Engine

Purpose:

```text
send governed inference envelope
send materialized context prefix
send active adapter route plan
send budget envelope
send Heptagon hook expectations
```

Primary local files:

```text
ai/tokenless-agent/src/_xmind_glue.py
_xmind/client.py
ai/xmind/include/xmind.h
ai/xmind/include/xmind_heptagon.h
ai/xmind/include/xmind_context.h
ai/xmind/include/xmind_adapter_runtime.h
ai/xmind/src/xmind_easy.c
ai/xmind/src/inference.c
ai/xmind/src/adapter_runtime.c
```

Required data contracts:

```text
InferenceEnvelope
MaterializedContext
AdapterRoutePlan
BudgetEnvelope
HookContract
```

### 4.5 Edge E — Inference Engine → Cognitive Control System

Purpose:

```text
return output candidate
return token telemetry
return adapter telemetry
return materialization record
return lineage deltas
return generation status
```

Primary local files:

```text
ai/xmind/src/inference.c
ai/xmind/src/heptagon.c
ai/xmind/src/adapter_telemetry.c
ai/xmind/src/lineage.c
ai/xmind/src/telemetry.c
ai/tokenless-agent/src/heptagon/evaluation.py
ai/tokenless-agent/src/heptagon/calibration.py
ai/tokenless-agent/src/heptagon/enforcement.py
```

Required data contracts:

```text
OutputCandidate
TokenTrace
AdapterTelemetryRecord
MaterializationRecord
LineageDelta
GenerationStatus
```

### 4.6 Edge F — Cognitive Control System → Memory Continuity System

Purpose:

```text
commit or reject writeback
reinforce recall path
store correction lineage
promote or demote memory
update decay/retention
seal archival pointer
```

Primary local files:

```text
ai/tokenless-agent/src/heptagon/writeback.py
ai/tokenless-agent/src/heptagon/lineage.py
ai/tokenless-agent/src/heptagon/consolidation.py
ai/tokenless-agent/src/memory/lifespan_ledger.py
ai/tokenless-agent/src/memory/experience_atom.py
ai/xmind/src/writeback.c
ai/xmind/src/lineage.c
soul_manager/message_framing.py
soul_manager/consolidation.py
```

Required data contracts:

```text
CognitiveMemoryVerdict
WritebackDecision
LineageRecord
RetentionDirective
ConsolidationDirective
ArchivalPointer
```

### 4.7 Edge G — Memory Continuity System → Model Runtime

Purpose:

```text
return continuity state
return lifecycle health
return recall readiness
return degradation flags
return active user/session continuity summary
```

Primary local files:

```text
ai/tokenless-agent/src/memory/session.py
ai/tokenless-agent/src/memory/lifespan_ledger.py
ai/tokenless-agent/src/cognitive_pipeline.py
ai/tokenless-agent/src/api.py
soul_manager/soul_manager.py
```

Required data contracts:

```text
ContinuityState
RecallReadiness
MemoryHealth
SessionContinuitySummary
```

---

## 5. Seven-Layer Embedded Model Mapping

The seven-layer embedded model must be implemented inside the active repository without renaming the repository taxonomy.

| Layer | Neutral Function | Local Files | Required Behavior |
|---|---|---|---|
| **1. Perception and Embodiment** | Convert input/sensors into evidence | `sensory/evidence.py`, `sensory/router.py`, `sensory/home_security.py`, `xmind/src/r1_per.c`, `xmind/include/r1_per.h`, `cognitive_pipeline.py` | All user/sensory signals become `EvidenceEnvelope` objects before active cognition. |
| **2. Attention and Active Workspace** | Select active context | `cognitive_pipeline.py`, `heptagon/route_engine.py`, `heptagon/budget.py`, `memory/session.py` | Build bounded active frame from salience, risk, memory confidence, and budget. |
| **3. Memory and Continuity** | Recall, store, correct, and preserve | `memory/experience_atom.py`, `memory/lifespan_ledger.py`, `memory/recall_trail.py`, `soul_manager/*`, `heptagon/writeback.py`, `heptagon/lineage.py` | Provide cue-triggered cascading recall and quality-gated writeback. |
| **4. World Model and Simulation** | Predict outcomes and model uncertainty | `heptagon/verification.py`, `heptagon/evaluation.py`, `heptagon/route_engine.py`, `xmind/src/inference.c` | Represent predictions as predictions, not facts. Gate simulation through control layer. |
| **5. Deliberation and Planning** | Choose strategy and route | `heptagon/route_engine.py`, `heptagon/budget.py`, `agent.py`, `workspace.py` | Route based on task, risk, adapter plan, memory confidence, and budget. |
| **6. Self-Correction and Calibration** | Review, revise, calibrate, redact, halt | `heptagon/evaluation.py`, `heptagon/calibration.py`, `heptagon/enforcement.py`, `heptagon/drift_detector.py` | `REVIEWING` remains correction junction. No new FSM state. |
| **7. Governance and Authority** | Bound every action | `governance/*`, `constitution/*`, `heptagon/enforcement.py`, `heptagon/invariant_engine.py`, `heptagon/verification.py` | No capability outranks governance. No bypass around gates. |

---

## 6. Sensory Evidence Mapping

Sensors are not new pillars and not new agents.

Sensors enter through the Sensory Evidence System and become evidence for the seven-layer model.

### 6.1 Supported Sensory Categories

```text
vision
hearing
speech/audio
text/code/document input
proximity/motion
thermal/smoke/fire
chemical/air quality
contact/tactile
device/system telemetry
time/rhythm
network/environmental health
user activity state
```

### 6.2 Local Sensory Files

```text
ai/tokenless-agent/src/sensory/evidence.py
ai/tokenless-agent/src/sensory/router.py
ai/tokenless-agent/src/sensory/home_security.py
ai/xmind/src/r1_per.c
ai/xmind/include/r1_per.h
```

### 6.3 EvidenceEnvelope Minimum Fields

```python
@dataclass(frozen=True)
class EvidenceEnvelope:
    evidence_id: str
    source_kind: str
    source_id_hash: str
    modality: str
    timestamp_ns: int
    payload_hash: str
    extracted_entities: list[str]
    confidence: float
    risk_class: str
    privacy_class: str
    retention_hint: str
    materialization_state: str
```

Rules:

```text
No raw camera/mic/sensor data enters memory directly.
No raw sensor stream bypasses Cognitive Control.
No sensor event triggers action without governance evaluation.
No sensory evidence is promoted to long-term memory without writeback verdict.
```

---

## 7. Cue-Triggered Cascading Recall

The lifespan companion behavior depends on cue-triggered recall.

The system must support this user pattern:

```text
"Do you remember when..."
"That thing we talked about before..."
"It was around the time..."
"You know, when I said..."
```

### 7.1 Jog My Memory Flow

```text
cue phrase
  → entity extraction
    → shallow session recall
      → episodic recall
        → semantic expansion
          → sensory anchor search
            → temporal expansion
              → archival pointer lookup
                → contradiction/correction check
                  → active context reconstruction
                    → governed response
```

### 7.2 Local Files

```text
ai/tokenless-agent/src/memory/recall_trail.py
ai/tokenless-agent/src/memory/experience_atom.py
ai/tokenless-agent/src/memory/lifespan_ledger.py
ai/tokenless-agent/src/memory/episodic.py
ai/tokenless-agent/src/memory/session.py
ai/tokenless-agent/src/heptagon/lineage.py
ai/tokenless-agent/src/heptagon/consolidation.py
soul_manager/consolidation.py
soul_manager/message_framing.py
```

### 7.3 RecallTrail Minimum Fields

```python
@dataclass(frozen=True)
class RecallTrail:
    trail_id: str
    cue_hash: str
    expansion_depth: int
    visited_memory_ids: list[str]
    recovered_entities: list[str]
    recovered_time_windows: list[str]
    recovered_sensory_anchors: list[str]
    contradictions: list[str]
    corrections: list[str]
    confidence_before: float
    confidence_after: float
    stop_reason: str
```

### 7.4 Recall Bounds

Recall is recursive across memory, not infinite inside a single turn.

```text
MAX_RECALL_EXPANSION_DEPTH = configured finite bound
MAX_RECALL_SHARDS_ACTIVE = configured finite bound
MAX_ARCHIVAL_POINTERS_PER_TURN = configured finite bound
```

Rules:

```text
Recall expansion consumes budget.
Recall expansion must terminate.
Recall expansion must produce a trail.
Recall expansion must report uncertainty.
Recall expansion must not promote memory by itself.
```

---

## 8. Materialization Plane

Materialization is required.

It is the plane where abstract specifications become runtime objects.

### 8.1 Local Materialization Files

```text
ai/xmind/include/xmind_materialize.h
ai/xmind/src/materialize.c
ai/xmind/src/weights_loader.c
ai/xmind/loader/weights_loader_mmap.c
ai/xmind/src/gguf_reader.c
ai/xmind/src/interp_registry.c
ai/xmind/src/interp_tokenless.c
ai/xmind/src/adapter_ir.c
ai/xmind/src/adapter_runtime.c
ai/xmind/src/adapter_cache.c
ai/xmind/src/adapter_telemetry.c
```

### 8.2 Materialization Domains

```text
model artifact materialization
weight/tensor materialization
adapter materialization
context materialization
sensory evidence materialization
memory packet materialization
recall trail materialization
simulation materialization
output/action materialization
writeback materialization
telemetry/provenance materialization
```

### 8.3 MaterializationRecord Minimum Fields

```python
@dataclass(frozen=True)
class MaterializationRecord:
    record_id: str
    artifact_kind: str
    source_hash: str
    target_runtime: str
    materialized_at_ns: int
    memory_region: str | None
    adapter_ids: list[str]
    tensor_roles: list[str]
    evidence_ids: list[str]
    context_hash: str | None
    status: str
    rollback_pointer: str | None
```

Rules:

```text
No model artifact loads without hash verification.
No adapter materializes without genome/scope verification.
No sensory evidence materializes into active context without evidence envelope.
No memory packet materializes without privacy and retention class.
No output/action materializes without governance verdict.
```

---

## 9. Training / Plasticity Mapping

The repository already contains the plasticity foundation:

```text
training/peft/base.py
training/peft/compiler.py
training/peft/conflict.py
training/peft/deployment.py
training/peft/fingerprint.py
training/peft/model.py
training/peft/profiler.py
training/peft/registry.py
training/peft/router.py
training/peft/tournament.py
training/peft/v2/adapter_algebra.py
training/peft/v2/adapter_genome_v2.py
training/peft/v2/adapter_ir.py
training/peft/v2/determinism.py
training/peft/v2/layer_plasticity.py
training/peft/v2/sensory_plasticity.py
training/peft/v2/tournament_v2.py
training/peft/v2/proofs/properties.py
training/programs/method_ontology_v2.json
training/programs/omni_training_registry.json
training/scripts/omni_training_program.py
training/scripts/train_peft.py
```

### 9.1 Required Plasticity Behavior

```text
method registry stays source of training-method truth
method ontology describes method behavior, not just names
AdapterIR compiles methods into runtime-neutral operations
AdapterGenome v2 carries lineage, scope, hash, eval, and rollback data
Tournament v2 evaluates utility, retention, latency, safety, conflict, grounding, and calibration
Layer plasticity maps adapters to the seven embedded layers
Sensory plasticity maps adapters to evidence processing behavior
Determinism module records reproducible route/adaptation decisions
```

### 9.2 Adapter Activation Rules

```text
No unsigned adapter activates.
No adapter activates against mismatched base hash.
No adapter activates outside authority scope.
No adapter activates above conflict threshold.
No adapter writes memory directly.
No adapter bypasses Cognitive Control or Governance.
No adapter promotion occurs without evaluation and rollback pointer.
```

---

## 10. Determinism and Determinant Probability

Determinism does not mean the model is non-probabilistic.

It means critical routing, governance, materialization, and adapter activation decisions are replayable.

### 10.1 Local Files

```text
training/peft/v2/determinism.py
training/peft/v2/tournament_v2.py
training/peft/v2/proofs/properties.py
ai/tokenless-agent/src/heptagon/budget.py
ai/tokenless-agent/src/heptagon/route_engine.py
ai/tokenless-agent/src/heptagon/evaluation.py
ai/xmind/src/adapter_telemetry.c
```

### 10.2 DeterminantProbabilityRecord

```python
@dataclass(frozen=True)
class DeterminantProbabilityRecord:
    record_id: str
    decision_kind: str
    input_hash: str
    state_hash: str
    seed: int | None
    candidate_scores: dict[str, float]
    selected_candidate: str
    selection_reason: str
    deterministic_replay_hash: str
    probabilistic_confidence: float
```

Rules:

```text
Governance decisions must be deterministic or replayable.
Adapter route decisions must be deterministic under identical inputs/state.
Tournament winner selection must be replayable.
Probabilistic generation may remain stochastic, but its envelope must be recorded.
```

---

## 11. Implementation Workstreams

### Workstream 1 — Preserve and Install ADRs

```text
copy ADR-0001 to repo ADR path if not present
copy ADR-0001 locked copy if desired
copy ADR-0002 local mapping
mark ADR-0001 read-only in docs and agent instructions
```

### Workstream 2 — Sensory Evidence Gate

```text
validate EvidenceEnvelope in sensory/evidence.py
ensure sensory/router.py emits envelopes only
ensure home_security.py does not trigger actions directly
connect R1_PER verification to evidence metadata
add tests/test_sensory_memory.py coverage
```

### Workstream 3 — Memory-Control Reflex

```text
connect recall_trail.py to route_engine.py
connect experience_atom.py to writeback.py
connect lifespan_ledger.py to consolidation.py
ensure Cognitive Control requests memory expansion through bounded budget
ensure Memory Continuity returns RecallTrail and MemoryContextPacket
```

### Workstream 4 — Materialization Records

```text
extend materialize.c / xmind_materialize.h to emit MaterializationRecord-compatible data
connect weights_loader and adapter_runtime to materialization tracking
connect materialization record to telemetry safely
add rollback pointer for adapters and artifacts
```

### Workstream 5 — Adapter Runtime and Plasticity

```text
verify method_ontology_v2.json coverage
verify AdapterIR operations in training/peft/v2/adapter_ir.py
verify adapter_ir.c runtime compatibility
verify adapter_genome_v2.py signatures/scope/rollback
verify tournament_v2.py scoring and determinism
verify xmind adapter runtime headers/source match Python artifacts
```

### Workstream 6 — Deterministic Replay

```text
record DeterminantProbabilityRecord for route, tournament, adapter activation, and governance decision
add replay tests for deterministic inputs
ensure stochastic generation stores envelope but not raw private content
```

### Workstream 7 — Governance and Proof Gates

```text
validate covenant/gate/enforcement path
ensure no blocked request reaches inference
ensure no L7 critical commit
ensure no adapter activates without proof/scope
ensure no memory writeback below quality/privacy gate
ensure no sensor action bypasses governance
```

---

## 12. Tests to Add or Strengthen

Use existing test locations:

```text
tests/
training/tests/
ai/xmind/tests/
```

Required tests:

```text
test_adr_immutability.py
test_no_archive_taxonomy_import.py
test_sensory_evidence_envelope.py
test_memory_control_reflex.py
test_recall_trail_budget.py
test_experience_atom_writeback.py
test_lifespan_ledger_reachability.py
test_materialization_record.py
test_adapter_ir_roundtrip.py
test_adapter_genome_scope.py
test_adapter_runtime_signature.py
test_adapter_conflict_threshold.py
test_tournament_v2_replay.py
test_route_determinism.py
test_no_direct_memory_write_from_adapter.py
test_no_inference_on_governance_block.py
test_l7_critical_manual_reset.py
test_telemetry_no_raw_content.py
```

---

## 13. Acceptance Criteria

The local implementation mapping is accepted only when:

```text
[ ] ADR-0001 remains unchanged.
[ ] ADR-0002 exists as local implementation map.
[ ] No reference-source names are introduced as active runtime taxonomy.
[ ] docs/_archive is treated as reference-only.
[ ] Active source zones are clearly separated from generated/cache/artifact zones.
[ ] The four-part foundation cycle is wired through active files.
[ ] Cognitive Control ↔ Memory Continuity reflex is implemented.
[ ] All sensory inputs enter as EvidenceEnvelope records.
[ ] Seven embedded layers map to active local files.
[ ] Materialization plane emits records for relevant artifact/runtime transitions.
[ ] Training/plasticity v2 path is integrated but governed.
[ ] Adapter activation is signed, scoped, conflict-checked, and rollback-capable.
[ ] Determinant probability records are generated for replayable decisions.
[ ] No blocked request reaches the inference engine.
[ ] No low-quality memory candidate is promoted.
[ ] No raw user content appears in telemetry/journal.
[ ] No unbounded recursive recall or generation exists.
[ ] All required tests pass.
```

---

## 14. Coding Agent Final Instruction

Implement this repository by following ADR-0001 and ADR-0002 only.

Do not mine archived tech packs for active taxonomy.

Do not rename the architecture.

Do not expand thin.

Make the existing system denser:

```text
stronger contracts
clearer edges
tighter evidence flow
bounded recall
traceable materialization
governed adapter plasticity
replayable decisions
provable stop conditions
```

The correct outcome is not more names.

The correct outcome is a working neutral lifespan cognitive model whose source paths, contracts, tests, and runtime records match the architecture.

