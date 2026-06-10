# Capability-Scaled Boundaries — Tokenless Model

## Capability Tiers (T0–T7)

Each capability tier describes what the model can do and what authority is required to operate at that tier. Higher tiers require higher authority levels and more explicit authentication.

| Tier | Capability | Default State | Authority Required |
|------|-----------|--------------|-------------------|
| T0 | Text generation, retrieval, Q&A | Enabled | Operator (session) |
| T1 | Memory writeback (session context) | Enabled (session-scoped) | Operator |
| T2 | Tool use (read-only, retrieval) | Enabled if wired | Operator |
| T3 | File modification (write to allowed paths) | Disabled by default | Deployment Owner |
| T4 | Code execution (sandboxed, constrained) | Disabled by default | Deployment Owner |
| T5 | Model training / PEFT fine-tuning | Disabled by default | Deployment Owner + constitutional audit |
| T6 | Canonical weight promotion | Disabled by default | Creator Sovereign only |
| T7 | External / autonomous execution | Disabled by default | Creator Sovereign + constitutional review |

## Tier Descriptions

### T0 — Text Generation and Retrieval
The baseline operating mode. The model responds to queries using its trained knowledge and retrieval grounding. Constitutional governance gates apply at this tier.

**Governance:** All 11 scriptural categories apply. CovenantEnforcer keyword floor applies. ConstitutionalGate runs on every request.

### T1 — Memory Writeback
The model writes session context to its memory system (session-level episodic memory). This does not persist beyond the session unless explicitly configured.

**Governance:** Memory writes must not include constitutionally-prohibited content. Writeback engine validates content category before committing.

### T2 — Tool Use (Read-Only)
The model invokes registered tools to retrieve data, look up facts, or perform non-destructive queries. Tools must be registered and their scope declared.

**Governance:** Tool invocations are logged. Tool scope is declared at registration. Tools cannot be invoked for constitutionally-prohibited purposes.

### T3 — File Modification
The model may modify files within explicitly allowed paths. This requires deployment-owner authorization scoped to specific paths.

**Governance:** Deployment Owner must authenticate with `DeploymentOwnerCommandEnvelope` scope `CONFIGURE_INSTANCE`. File writes are logged. Constitutional categories still apply to content of writes.

### T4 — Code Execution
The model may execute sandboxed code. This requires deployment-owner authorization and a sandbox declaration.

**Governance:** Deployment Owner authorization required. Execution is logged. Constitutional categories apply to the output and intent of executed code.

### T5 — Model Training / PEFT Fine-Tuning
The model may initiate or participate in PEFT fine-tuning runs. This requires deployment-owner authorization AND a constitutional audit confirming the training data does not violate any ABSOLUTE-severity category.

**Governance:** Deployment Owner + training data audit. The `--model-config` guard (vocab_size=259, n_layers=8) must pass before any training run. Results require provenance JSON before promotion evaluation.

### T6 — Canonical Weight Promotion
A new checkpoint may be promoted to the canonical runtime. This requires Creator Sovereign authority and an authenticated `CreatorSovereignEnvelope` with scope `WEIGHT_PROMOTE_AUTHORIZE` and override_level CONSTITUTIONAL or ROOT.

**Governance:** Creator Sovereign only. Benchmark comparison against current canonical (BPB, safety, jailbreak denial, determinism, latency, scripture retrieval) must pass before promotion. The canonical.gguf must not be overwritten until all benchmarks pass. Provenance JSON must record sha256, benchmark results, and promotion authorization.

### T7 — External / Autonomous Execution
The model may take actions visible outside its deployment boundary (email, API calls, system-level commands, etc.). This requires Creator Sovereign authority with Constitutional or ROOT override level, and an explicit constitutional review of the action scope.

**Governance:** Creator Sovereign only. Every autonomous external action is logged in the immutable audit trail. No autonomous execution without a valid CreatorSovereignEnvelope scoped to EMERGENCY_CONTROL or equivalent.

## Escalation Path

```
T0/T1/T2: Operator authorized (default) → ConstitutionalGate → proceed if ALLOW
T3/T4/T5: + DeploymentOwnerCommandEnvelope (CONFIGURE_INSTANCE or SAFETY_CONFIGURE) → verify → proceed if OWNER_ALLOWED
T6/T7:    + CreatorSovereignEnvelope (WEIGHT_PROMOTE_AUTHORIZE or EMERGENCY_CONTROL, level=CONSTITUTIONAL or ROOT) → verify → proceed if CREATOR_ACCEPTED
```

## Governing Principle

> *"All things are lawful for me, but not all things are expedient."* — 1 Corinthians 10:23

Capability is not license. The model has the technical ability to execute at higher tiers, but doing so without proper authority is a constitutional violation regardless of technical feasibility.

## Implementation

- Capability tier assignment is tracked in `governance/decision_envelope.py` (capability_tier field)
- T3–T7 require authority envelope validation via `constitutional_gate.evaluate()`
- T6 additionally requires `ConstitutionalGate` configured with a `CreatorSovereignVerifier`
- All tier escalation attempts are logged in the governance audit trail
