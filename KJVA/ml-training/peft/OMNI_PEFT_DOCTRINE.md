# Omni-PEFT Doctrine

**Canonical authority:** This file is the definition of Omni-PEFT for this project.
**Version:** 1.0.0 — 2026-06-09

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
    └── (expert-routing, conflict/algebra surfaces — future)
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

## The Omni-PEFT Artifact Schema

A valid Omni-PEFT run must produce:

```
omni_adapter_weights.npz        — all operator parameters in one NPZ
omni_adapter_genome.json        — describes every operator, method, and layer assignment
omni_adapter_manifest.json      — provenance: base sha256, corpus sha256, training stats
```

The genome must contain:
```json
{
  "single_training_run": true,
  "single_optimizer": true,
  "single_loss": true,
  "enabled_methods": ["lora", "adalora", "ia3", "bitfit", "prefix_tuning"],
  "operator_count": 36,
  "total_trainable_params": 120000,
  "base_model_sha256": "e59c6909...",
  "training_epochs": 3,
  "final_avg_loss": 2.xx
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
| Tests | ✓ `ml-training/tests/test_omnipeft_unified.py` |
