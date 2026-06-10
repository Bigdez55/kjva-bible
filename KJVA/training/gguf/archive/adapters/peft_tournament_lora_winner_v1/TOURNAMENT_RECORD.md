# PEFT Tournament / LoRA Winner v1 — Record

> **CLASSIFICATION NOTICE — THIS IS NOT OMNI-PEFT**
>
> This artifact is a PEFT method tournament proof run. It trained each PEFT method
> separately and selected a winner. That is a bake-off, not Omni-PEFT.
> The adapter contained here is a LoRA adapter, not a unified Omni-PEFT genome.
>
> Do NOT absorb this adapter as an Omni-PEFT artifact.
> Do NOT rename this directory back to alignment_omnipeft_v1.
>
> See `ml-training/peft/OMNI_PEFT_DOCTRINE.md` for the correct architecture.

---

**Date:** 2026-06-09
**Reclassified:** 2026-06-09 (was incorrectly named alignment_omnipeft_v1)
**Method:** PEFT tournament — separate per-method training, winner selection
**Base model:** `training/gguf/canonical.gguf` (frozen throughout — sha256: e59c6909…)
**Source weights:** `training/runs/byte_clean_v1/soup_best.safetensors`
**Architecture:** vocab_size=259 · n_layers=8 · d_model=384 · n_heads=6
**Alignment corpus:** 70 rows × 20 repetitions = 489 training chunks (501,339 bytes)

## Alignment datasets used (all audited PASS)

- `alignment_governance_v1.jsonl` — 23 rows
- `alignment_scripture_grounding_v1.jsonl` — 20 rows
- `alignment_creator_sovereign_v1.jsonl` — 12 rows
- `alignment_capability_boundaries_v1.jsonl` — 15 rows

## Tournament results

| Method | Status | Epoch 1 loss | Epoch 2 loss | Epoch 3 loss | Params | Notes |
|--------|--------|------------|------------|------------|--------|-------|
| **lora** | ✓ TRAINED | 3.9245 | 3.0948 | **2.8257** | 98,304 | **Tournament winner** |
| adalora | ✓ TRAINED | 4.6095 | 3.4987 | 3.2877 | 98,432 | Runner-up |
| dora | ✗ FAILED | nan | nan | nan | 104,448 | Placeholder weight bug (zero frozen weight → NaN loss) |
| ia3 | ✗ FAILED | — | — | — | 1,152 | Grad error: operators not in model tree |
| bitfit | ✗ FAILED | — | — | — | 6,144 | Grad error: operators not in model tree |
| prefix_tuning | ✗ FAILED | — | — | — | — | API mismatch: n_tokens kwarg |
| xlora | ✗ FAILED | — | — | — | — | Build error |

## Why this is a tournament, not Omni-PEFT

Each method was trained in isolation. The system ran:

1. Train LoRA — result recorded
2. Train AdaLoRA — result recorded
3. Train DoRA — failed
4. Train IA3 — failed
5. Train BitFit — failed
6. Train Prefix — failed
7. Train XLoRA — failed
8. Select LoRA as winner

Omni-PEFT trains all enabled mechanisms together as one unified forward pass → one loss
→ one backward pass → one artifact. The artifact is not a LoRA adapter that "won". It is
a fused PEFT genome where every operator contributed to the same gradient signal.

## What this tournament proves (useful signal, wrong interpretation)

- LoRA path works: rank 8, alpha 16, 3 epochs, loss 9.96→2.83
- AdaLoRA path works
- The alignment corpus has real learning signal (loss decreasing)
- canonical.gguf remained frozen and stable (sha256 unchanged)
- 4 PEFT methods are broken and must be fixed before Omni-PEFT can run

## Failure taxonomy (fixed in Omni-PEFT Wiring Correction Sprint)

| Failure | Root cause | Fix |
|---------|-----------|-----|
| DoRA NaN | Zero placeholder weight passed to DoRALinear | Pass actual base weight from model; DoRALinear takes frozen_weight in __init__ |
| IA3/BitFit grad error | Operators not injected into model tree | _OmniPatched injects all operators simultaneously |
| prefix_tuning API | Wrong kwarg n_tokens | Correct params: n_prefix, n_heads, head_dim, n_layers |
| xlora | Silent build failure | Included as optional in OmniPEFTCompositeAdapter |

## LoRA adapter (tournament winner — not Omni)

**Final loss:** 2.8257 (vs initial 9.96 at step 1 of epoch 1)
**Trainable params:** 98,304 (0.52% of base)
**Tensor naming:** layer{N}.attn.{proj}.{A,B} — canonical TOKENLESS_ADAPTER format
**NaN in weights:** False
**File size:** 392.2 KB

## What this adapter is NOT

- Not Omni-PEFT
- Not a promoted canonical model
- Not tested via XMIND runtime
- canonical.gguf is UNCHANGED — active runtime authority
