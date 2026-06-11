# Omni-PEFT Doctrine

**Canonical authority:** This file is the definition of Omni-PEFT for this project.
**Version:** 1.1.0 — 2026-06-11
**Source vision:** `peft/OMNI_PEFT_VISION.md` — the original architectural design document

---

## Identity

Omni-PEFT is one unified parameter-efficient adaptation organism.

It is **not** a tournament.
It is **not** a LoRA winner.
It is **not** an ensemble of separately-trained adapters.
It is **not** a simple merger or distillation of method outputs.
It is **not** a method picker that selects the best single technique.

Omni-PEFT is a **single coordinated PEFT genome** where multiple PEFT mechanisms
train together as one fused adaptation surface over the frozen canonical base.

---

## The Omni-PEFT Training Graph

```
canonical base (FROZEN — sha256-locked)
          │
          ▼
OmniPEFTCompositeAdapter (one nn.Module tree)
    ├── weight-additive surface (LoRA / AdaLoRA / DoRA per compiler plan)
    │       each attn projection gets its assigned operator
    │       outputs: base_output + delta
    ├── activation-scaling surface (IA3 per layer)
    │       l_k, l_v, l_ff vectors per transformer block
    │       output: scaled K, V, FFN activations
    ├── bias-tuning surface (BitFit per projection)
    │       one trainable bias vector per attention linear
    │       output: linear_out + bias
    ├── prompt/prefix surface (PrefixTuningLayer, global)
    │       per-layer prefix K and V vectors
    │       output: extended KV context
    └── (adapter-block, structural, routing surfaces — future phases)
          │
          ▼
    single combined forward pass
          │
          ▼
    single cross-entropy loss
          │
          ▼
    single backward pass (gradients flow to ALL operators simultaneously)
          │
          ▼
    one fused Omni-PEFT artifact:
        omni_adapter_weights.npz
        omni_adapter_genome.json
        omni_adapter_manifest.json
```

---

## What a Tournament Is (and Why It Is Not Omni-PEFT)

A tournament trains each PEFT method separately, evaluates them, and picks a winner:

```
Train LoRA → loss=2.83
Train AdaLoRA → loss=3.29
Train DoRA → failed
Train IA3 → failed
...
Select LoRA as winner
```

The prior "alignment_omnipeft_v1" artifact (now renamed `peft_tournament_lora_winner_v1`)
was a tournament, not Omni-PEFT. The LoRA adapter it produced is useful evidence
(learning signal is real, LoRA path works) but it is not an Omni-PEFT artifact.

---

## Universal Delta IR Families

Every PEFT method is a delta operator in one of nine adaptation families.
This shared language lets the compiler treat all methods uniformly.

| Family | Operation | Operators | Status |
|--------|-----------|-----------|--------|
| Weight-space additive | `base_out + delta` | LoRA, AdaLoRA, LoHa, LoKr, VeRA | ✓ LoRA + AdaLoRA built |
| Weight-space replacement | Full adapted output (carries frozen weight) | DoRA, PiSSA | ✓ DoRA built |
| Activation-space modulation | Scale / gate activations | IA3, learned gates | ✓ IA3 built |
| Prompt / context-space | Learned soft context vectors | Prefix tuning, Prompt tuning, P-tuning | ✓ Prefix built |
| Module-space residual | Nonlinear insert into network | Bottleneck adapters, parallel adapters | Future (Phase 3) |
| Structure-preserving | Constrained weight transform | OFT, BOFT, FourierFT | Future |
| Sparse / selective | Masks, sparse subsets, selected params | BitFit, FishMask, DiffPruning | ✓ BitFit built |
| Quantized substrate | Adapters trained through quantized frozen model | QLoRA, LoftQ | Future |
| Routing / composition | Dynamic adapter selection at runtime | X-LoRA, MoE-LoRA, AdapterFusion | Future (Phase 4) |

The current implementation covers families 1–4 and 7 (LoRA/AdaLoRA + DoRA + IA3 +
Prefix + BitFit). Families 5, 6, 8, 9 are planned future surfaces.

---

## Escalation Ladder — Cheapest Sufficient Change

The core architectural principle: start with the smallest reversible intervention.
Escalate only when evidence demands it. The system should budget adaptation the way
an engineering team budgets compute.

| Rung | Intervention | When |
|------|-------------|------|
| 1 | Do nothing | Base model already performs well |
| 2 | Retrieval or prompting | No weights need to change |
| 3 | Prefix / prompt tuning | Task framing is enough |
| 4 | IA3 activation gating | Light behavioral adjustment suffices |
| 5 | LoRA / AdaLoRA / DoRA | Weight-space adaptation warranted |
| 6 | Bottleneck / parallel adapters | Nonlinear specialization needed |
| 7 | Routed multi-adapter composition | Multiple simultaneous domains |
| 8 | Selective unfreezing | All PEFT surfaces saturate |
| 9 | Full fine-tuning | Final fallback only |

**Current implementation covers rungs 3–5 jointly** in one training pass. The compiler
chooses the cheapest sufficient rungs per layer. Rungs 6–9 are future surfaces.

---

## The Omni-PEFT Artifact Schema

A valid Omni-PEFT run must produce:

```
omni_adapter_weights.npz        — all operator parameters in one NPZ
omni_adapter_genome.json        — describes every operator, method, and layer assignment
omni_adapter_manifest.json      — provenance: base sha256, corpus sha256, training stats
```

### Required genome fields (current)

```json
{
  "omni_peft_version": "1.0.0",
  "single_training_run": true,
  "single_optimizer": true,
  "single_loss": true,
  "enabled_methods": ["lora", "adalora", "ia3", "bitfit", "prefix_tuning"],
  "operator_count": 36,
  "total_trainable_params": 120000,
  "base_model_sha256": "e59c6909...",
  "training_epochs": 3,
  "final_avg_loss": 2.xx,
  "deployment_mode": "semi-merged",
  "base_retention_target": 0.93,
  "evaluation_gates": [
    "domain_accuracy",
    "base_retention",
    "hallucination_delta",
    "latency_ms",
    "merge_safety"
  ],
  "rollback": {
    "previous_stable": null,
    "quarantine_conditions": [
      "base_retention_below_0.93",
      "domain_bleed_detected",
      "latency_above_budget"
    ]
  }
}
```

### Extended genome fields (Phase 2+ — not yet written by genome_dict)

```json
{
  "routing": {
    "activate_when": ["theology", "biblical scholarship"],
    "never_activate_when": ["casual conversation"]
  },
  "compatibility": {
    "compatible_with": ["retrieval_adapter_v1"],
    "conflicts_with": ["casual_style_adapter_v1"]
  },
  "evaluation": {
    "domain_accuracy": null,
    "hallucination_delta": null,
    "base_retention_score": null,
    "latency_overhead_ms": null,
    "merge_safety": "pending"
  }
}
```

It must NOT contain:
```json
{
  "tournament_winner": "lora"
}
```

---

## Operator Composition Rules

Each model layer slot can have multiple Omni-PEFT operators active simultaneously.
Their outputs compose according to family:

| Family | Operators | Composition |
|--------|-----------|-------------|
| WEIGHT_ADDITIVE | LoRA, AdaLoRA | `base_out + delta` |
| WEIGHT_REPLACE | DoRA | `W_dora(x)` — replaces base (includes its own frozen weight) |
| ACTIVATION | IA3 `l_k`, `l_v` | `k * l_k`, `v * l_v` after attention projection |
| ACTIVATION | IA3 `l_ff` | `hidden * l_ff` after FFN gate |
| BIAS | BitFit | `linear_out + bias` |
| PROMPT | PrefixTuning | prepend prefix K/V to each attention layer |

Composition order per slot: weight → activation scaling → bias.

If DoRA is assigned to a slot, LoRA/AdaLoRA for that slot are disabled (DoRA subsumes
the low-rank delta). IA3 and BitFit are always complementary to the weight-additive
method.

---

## Compiler Integration

The `PEFTCompiler.plan()` method produces a `LayerAdaptationSpec` list that assigns
one weight-additive method per layer/module slot. Omni-PEFT consumes this plan and
adds the complementary operators (IA3, BitFit, Prefix) on top.

```python
plan = compiler.plan(plasticity, fingerprint, constraints)
composite = OmniPEFTCompositeAdapter.from_plan(plan, base_model)
```

The compiler picks the right weight-additive method per layer (e.g., lora for attn,
adalora for mlp). The Omni composite adds IA3/BitFit/Prefix uniformly across all layers.

---

## Conflict Resolver Contract

`peft/conflict.py` — `ConflictResolver.check(genomes)` returns a `ConflictReport`
with a pruned, safe `RoutePlan`.

**Conflict types currently detected:**

| Type | Detection | Resolution |
|------|-----------|------------|
| Latency conflict | > 4 adapters active simultaneously | Prune lowest-weight adapters |
| Style conflict | Incompatible purpose domains | Prune or reweight |
| Domain bleed | Adapter activating outside target domain | Quarantine combination |

**Conflict types planned (Phase 2+):**

| Type | Description |
|------|-------------|
| Weight-space conflict | Two delta operators push same matrix in opposing directions |
| Activation conflict | IA3 gate suppresses activation another adapter depends on |
| Safety conflict | Combination degrades safety behavior |
| Merge conflict | Merged deltas destructive when folded into base |
| Token conflict | Token-level router oscillates between incompatible experts |

---

## Injection Protocol

All Omni operators must be injected into the base model tree before calling
`nn.value_and_grad`. The `_OmniPatched` module replaces each attention projection
with a unified module that contains all active operators for that slot.

```python
# _OmniPatched replaces base_model.blocks[i].attn.q with:
class _OmniPatched(nn.Module):
    base: frozen nn.Linear
    weight_op: LoRALinear / DoRALinear / AdaLoRALinear  (trainable)
    ia3_scale: mx.array ones  (trainable)
    bitfit_bias: mx.array zeros  (trainable)
```

No operator is kept outside the model tree.

---

## Deployment Modes

| Mode | Description | Best Use |
|------|-------------|---------|
| Merged | Adapter deltas folded into base weights | Single-domain, maximum inference speed |
| Semi-merged | Stable deltas merged, router/prefix kept external | Balanced production (**current default**) |
| Hot-swappable | One adapter active at a time, swapped at runtime | Multi-client systems |
| Routed multi-adapter | Multiple adapters activated dynamically | Agent ecosystems |
| Edge quantized | Compressed, local deployment package | Consumer hardware |
| Cloud adapter service | Central registry + routing service | Enterprise scale |
| User-private | Personal style or memory adapter | Personalized assistants |

Current default: **semi-merged** — stable low-rank deltas merged into GGUF canonical;
router and prefix memory kept external for hot-swap. Reflected in `genome_dict(deployment_mode="semi-merged")`.

---

## Training Progression

Omni-PEFT follows a progressive complexity ladder. Escalate only when evidence demands it.

| Stage | Name | Description | Status |
|-------|------|-------------|--------|
| 0 | Baseline evaluation | Benchmark frozen base before any adaptation | ✓ `eval_byte.py` |
| 1 | Minimal adaptation | Prefix/IA3/tiny-LoRA; verify cheapest path | ✓ Compiler selects |
| 2 | Layerwise low-rank | LoRA/AdaLoRA/DoRA per profiler plan | ✓ `omni_composite.py` |
| 3 | Nonlinear adapters | Bottleneck/parallel for deeper specialization | Future |
| 4 | Routing and composition | Router-controlled multi-adapter runtime | Future |
| 5 | Selective unfreezing | Only if all PEFT surfaces saturate | Future |
| 6 | Merge, distill, export | GGUF merge, semi-merge, hot-swap package | ✓ `export_byte.py` |
| 7 | Monitor and govern | Drift tracking, quarantine, rollback | Future |

---

## Routing Hierarchy (Future — Phase 4)

The full hierarchical router is not yet built. When implemented it will route at:

1. **Task level** — broad capability family
2. **Domain level** — knowledge domain (theology, code, legal, etc.)
3. **Layer-family level** — additive / prompt / activation / adapter / sparse
4. **Layer level** — per-layer adapter assignment
5. **Token level** — dynamic mixture during generation
6. **Confidence level** — escalate when uncertainty is high
7. **User level** — personal style or preference adapter
8. **Hardware level** — prune paths exceeding VRAM/latency budget

The current compiler produces a static per-layer plan (covers levels 3–4).
Dynamic token-level and confidence-level routing are Phase 4 surfaces.

---

## Test Invariants

The test `test_omnipeft_is_not_tournament` enforces these invariants:

1. Genome does NOT contain `tournament_winner`
2. Genome DOES contain `single_training_run: true`
3. Genome DOES contain `single_optimizer: true`
4. Genome DOES contain `enabled_methods` with length > 1
5. `omni_adapter_weights.npz` exists and is not empty
6. `omni_adapter_genome.json` exists and passes schema validation

---

## Status

| Component | Status |
|-----------|--------|
| `OmniPEFTCompositeAdapter` | ✓ Built — `peft/omni_composite.py` |
| `_OmniPatched` per-layer module | ✓ Built |
| LoRA surface | ✓ Wired |
| AdaLoRA surface | ✓ Wired |
| DoRA surface | ✓ Fixed (actual base weight, not zeros) |
| IA3 surface | ✓ Wired into `_OmniPatched` |
| BitFit surface | ✓ Wired into `_OmniPatched` |
| PrefixTuning surface | ✓ Fixed (correct kwargs: n_prefix, n_heads, head_dim, n_layers) |
| `run_omni_training()` | ✓ Implemented in `train_peft.py` |
| `--method omni` dispatch | ✓ Wired in main() |
| Genome schema (required fields) | ✓ `genome_dict()` — v1.1 includes deployment_mode, retention_target, eval_gates, rollback |
| Genome schema (extended fields) | Future (routing rules, compatibility, live evaluation) |
| Conflict resolver (basic) | ✓ `peft/conflict.py` — latency + style + domain-bleed |
| Conflict resolver (full) | Future (weight-space, activation, safety, merge, token) |
| Bottleneck / parallel adapters | Future (Phase 3) |
| Runtime router | Future (Phase 4) |
| Monitoring / governance | Future (Phase 7) |
| Tests | ✓ `training/tests/test_omnipeft_unified.py` |
