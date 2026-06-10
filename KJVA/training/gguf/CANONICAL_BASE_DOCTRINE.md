# Canonical Base Doctrine — for the coding agent

**Audience:** every coding agent, future Claude session, contributor, or automation that touches `training/gguf/`, `xmind_federation/`, `ai/xmind/`, `cognitive_pipeline.py`, the Heptagon, or any module that loads a model.

**Read this FIRST, before scanning the gguf folder, before reasoning about model taxonomy, before naming anything.**

---

## Final doctrine (canonical phrase — DO NOT alter)

> **Identity is singular. Engineering surfaces remain auditable. Cognitive flow remains fused.**

Short form:

> **One cognitive identity. Auditable engineering surfaces. Fluid depth-scaled cognition.**

---

## Unified Cognitive Identity Contract

> There is one cognitive identity and one continuous cognitive flow.
>
> Architecture, substrate, weights, adapters, memory, governance, verification, routing, and training records are separable for engineering audit only. They are not separate minds, not separate identities, not independent cognition layers.
>
> Cognitive levels are latent capacities inside one fused stream. They activate fluidly based on complexity, uncertainty, risk, contradiction, novelty, evidence gaps, and doctrine sensitivity.
>
> The system may expose internal control surfaces for testing, provenance, promotion, safety, and regression, but those surfaces must never be treated as separate cognitive identities.
>
> Training creates candidate embodiments. Promotion selects the canonical runtime embodiment. Promotion is a runtime authority decision grounded in evidence, provenance, integrity, compatibility, regression standing, and doctrine alignment.

---

## Hard rules

1. **The runtime embodiment is `training/gguf/canonical.gguf`.** Not `model.gguf`. Not `clean_base_v1.gguf`. Not `clean_base_soup_v1.gguf`. Those names no longer exist at the root of the live folder. They are historical embodiments archived under `training/gguf/archive/` — not alternative identities.

2. **The canonical runtime embodiment is resolved through the promotion manifest, never by scanning the gguf folder and guessing.** Read `promotion/PROMOTION_RECORD.md` and `promotion/lineage_manifest.json` to learn the lineage. Do not infer taxonomy from filenames.

3. **Do not rename the architecture because of weight filenames.** The architecture is `tokenless_lm` (interpreter slot 1). It is the same architecture across every `.gguf` in this folder, past and future. Weight filenames are training-history labels, not architecture labels, and not identity labels.

4. **Do not treat `model.kjva_base`, `clean_base_v1.step2500`, and `clean_base_soup_v1.source` as separate model designs or separate minds.** They are historical embodiments of the same cognitive identity. They live in `archive/` for lineage evidence only.

5. **Archived weights are NOT auto-loaded at runtime.** Never reference `archive/*.gguf` from production code paths. They exist for benchmark replay, regression-baseline comparison (per spec §9), and provenance.

6. **One promoted runtime embodiment at a time.** When promoting a new candidate embodiment, the current `canonical.gguf` must move to `archive/` with a descriptive lineage name AND a new entry must be appended to `PROMOTION_RECORD.md` AND `lineage_manifest.json` AND `benchmark_table.json` must be updated. No silent overwrites.

7. **The substrate is not cognition by itself, but it hosts, constrains, and expresses cognition inside the system.** Substrate, weights, adapters, memory, routing, verification, and governance participate as engineering surfaces of one continuous cognitive flow. Never describe them as cognitively independent.

---

## The cognitive flow contract — fused, depth-scaled, never layered as identities

The base embodiment is the **substrate**; cognition is what the substrate hosts and expresses through the wrapped pipeline. Cognitive depth is NOT a visible manual mode switch. Reflex, deduction, inference, verification, metacognition, mastery, memory, and writeback are latent capacities inside ONE continuous cognition stream. They activate fluidly as task complexity, uncertainty, risk, contradiction, novelty, evidence gaps, or doctrine sensitivity increases.

```
Input
  ↓
Intent + Context Recognition           (engineering surface: Heptagon L1–L2)
  ↓
Complexity / Uncertainty / Risk estimate    (depth controls, NOT identity controls)
  ↓
Fused Cognition Pass over canonical.gguf
  ↓ (reflective surfaces activate latent capacities as needed —
  ↓  they are scalar controls inside the same flow, not branches into different minds)
  ↓
   reasoning_depth ↑   →  deduction / inference deepen
   verification_required ↑   →  verification surface activates
   metacognition_required ↑  →  metacognitive review activates
   memory_required ↑   →  recall / continuity surface activates
   evidence_required ↑  →  sensory + retrieval surfaces activate
   doctrine_sensitivity ↑  →  governance + mastery surfaces activate
  ↓
Final Response / Action
  ↓
Memory, Lineage, Writeback, Training Signal   (continuity, not identity replacement)
```

The user must not experience the system as moving between separate layers. The levels may be retrospectively analyzed after the fact for audit and telemetry, but runtime cognition behaves as a fused flow.

---

## Three auditable engineering surfaces (NOT three identities)

These are surfaces of one continuous cognition. They are separable for engineering audit only. They are not separate cognitive identities, not separate minds, and not independent cognition layers.

| Engineering surface | What it makes auditable | Where it lives |
|---|---|---|
| **Architecture surface** | Model shape (vocab, layers, dimensions, tokenizer, runtime) | `ai/xmind/include/*.h`, `ai/xmind/src/interp_tokenless.c`, `adr/ADR-S49-01-*.md` |
| **Promotion surface** | Which trained weights are the current canonical runtime embodiment | `training/gguf/canonical.gguf`, `training/gguf/promotion/*` |
| **Cognitive flow surface** | How the fused cognition activates latent capacities (depth scaling) | `ai/tokenless-agent/src/cognitive_pipeline.py`, Heptagon modules, governance, memory, sensory |

When confused about whether something belongs to architecture, promotion, or cognitive flow — ask. Do not blur them, and do not invent new identity layers either.

---

## Forbidden drift (each one was committed in real history; do not repeat them)

- Treating peer `.gguf` files in the folder as different model designs or different minds (2026-06-04 confusion).
- Defending "30K LOC is wired" without a runtime trace proving it (2026-06-01 trust failure).
- Inferring architecture identity from a weight filename.
- Loading a historical archive weight in production code.
- Adding a new `.gguf` to `training/gguf/` without going through the promotion ceremony.
- Calling promotion "a training-stage choice" — it is a runtime authority decision grounded in evidence, provenance, integrity, compatibility, regression standing, and doctrine alignment.
- Saying "the substrate is not cognition" as a standalone final doctrine — it creates false separation. The substrate hosts, constrains, and expresses cognition inside the system.
- Saying "three layers of identity control stay separate" — there are auditable engineering surfaces, not separate identity layers.
- Describing the Heptagon, memory, sensory, governance, or Omni-PEFT as if they were separate minds or independent cognition layers.
- Exposing cognitive depth as a manual mode switch the user has to flip.

---

## Promotion ceremony (the only sanctioned way to change the canonical runtime embodiment)

1. Train or soup a candidate; produce `candidate.gguf` + `candidate.gguf.json` sidecar at `training/gguf/candidate.gguf`.

2. Run the benchmark runner against the candidate:
   ```bash
   python3 benchmark_bundle/benchmark_results/run_xmind_benchmark.py \
     --model "models v7/training/gguf/candidate.gguf" \
     --dylib "models v7/ai/xmind/build/libxmind-core.dylib" \
     --parity "models v7/ai/xmind/build/parity_logits" \
     --out-dir "benchmark_bundle/benchmark_results/<candidate-name>/"
   ```

3. Compare against the current `canonical.gguf` row in `benchmark_table.json`. The candidate must:
   - Beat current canonical on §5 BPB on the same held-out bytes, OR
   - Match BPB within 5% and beat it on §3.5 determinism / §4.1 throughput / §4.2 TTFT meaningfully, AND
   - Not regress §3.5 determinism (must remain byte-identical at T=0), AND
   - Pass the unified-cognitive-identity audit (`scripts/audit_unified_cognitive_identity.py`) without drift findings.

4. If promotion is justified:
   - Move current `canonical.gguf` to `archive/<old-lineage-name>.gguf` (+ sidecar).
   - Copy `candidate.gguf` to `archive/<candidate-name>.source.gguf` (preserve raw).
   - Copy `archive/<candidate-name>.source.gguf` to `canonical.gguf` (new promoted runtime embodiment).
   - Append a row to `PROMOTION_RECORD.md` with date, SHA-256, BPB delta, and runtime-attestation justification.
   - Append a row to `lineage_manifest.json["archive"]`.
   - Append a row to `benchmark_table.json["candidates"]`.
   - Run `python3 -m pytest tests/validate_apex.py tests/test_unified_cognitive_identity.py` to confirm Connection 2 still passes AND the doctrine is intact. If either fails, ROLL BACK before doing anything else.

5. If promotion is NOT justified: archive the candidate anyway (lineage) but do not change `canonical.gguf`.

---

## Audit (run BEFORE claiming the runtime is OK)

```bash
# 1. canonical.gguf exists and is the SHA recorded in lineage_manifest.json
shasum -a 256 "models v7/training/gguf/canonical.gguf"
jq -r '.canonical.sha256' "models v7/training/gguf/promotion/lineage_manifest.json"

# 2. No stray .gguf at the root of training/gguf/ (only canonical.gguf + sidecar)
ls "models v7/training/gguf/"*.gguf

# 3. xmind_federation/client.py default points at canonical.gguf
grep -n "canonical.gguf" "models v7/xmind_federation/client.py"

# 4. Unified-cognitive-identity audit passes
cd "models v7" && python3 scripts/audit_unified_cognitive_identity.py

# 5. Apex acceptance + doctrine test still pass
cd "models v7" && python3 -m pytest tests/validate_apex.py tests/test_unified_cognitive_identity.py
```

If ANY of these fail, the system is in a broken-doctrine state. Fix before continuing any other work.

---

## Why this exists

On 2026-06-04 the assistant casually referred to three peer `.gguf` files as if they were three model designs. The user — Bigdez55 — asked "are you telling me there is more than one model?" and was correct to push back. The three files were the same architecture, different historical embodiments. Leaving them as peers without a promotion gradient was a taxonomy-drift accident waiting to happen.

On 2026-06-07 the doctrine was further sharpened: "Identity is singular. Engineering surfaces remain auditable. Cognitive flow remains fused." Multiple weights, multiple training stages, multiple engineering surfaces — one cognitive identity, one continuous cognitive flow, fluid depth-scaled cognition.

This doctrine prevents recurrence. It also makes future coding agents fail safely: an agent that scans `training/gguf/` sees exactly one `.gguf` at the root, finds this doctrine document next to it, and knows that there is one canonical runtime embodiment expressing one cognitive identity through a fused, depth-scaled cognitive flow.
