# OMNI-PEFT Vision Document

**Role:** Source architectural vision. This is the original design document from which
`OMNI_PEFT_DOCTRINE.md` was derived. Where the two conflict, the doctrine governs
implementation; this document governs intent and roadmap.

**Version:** Original — 2026-06-11
**See also:** `OMNI_PEFT_DOCTRINE.md` (authoritative implementation spec)

---

Omni-PEFT: The Apex Architecture for Universal Model Adaptation
If someone handed me every PEFT method known to man and said, "Create the ultimate perfect Omni-PEFT," I would not create another adapter.
That would be too small.
I would create an Adaptation Operating System.
The correct answer is:
Omni-PEFT is a universal model-adaptation compiler, runtime, router, registry, and governance layer that treats every PEFT method as a modular adaptation primitive, then automatically selects, composes, trains, routes, merges, audits, and deploys the cheapest sufficient adaptation for each model, layer, token, task, domain, user, and hardware target.
That is the apex.
Not "LoRA but better."
Not "one adapter to rule them all."
Not "mix every PEFT together and hope it works."
That would be architectural chaos.
The best Omni-PEFT is a disciplined adaptation system that answers one question better than anything else:
What is the smallest, safest, fastest, most reusable change that gives the model the largest reliable capability gain without damaging the base model?
That is the definition of perfect PEFT in practice.
Parameter-efficient fine-tuning already exists to adapt pretrained models without updating all parameters, reducing compute and storage costs while often achieving performance comparable to full fine-tuning. But the PEFT field has fragmented into a huge zoo of methods: prompt tuning, prefix tuning, P-tuning, LoRA, AdaLoRA, BOFT, IA3, LoHa, LoKr, OFT, X-LoRA, VeRA, FourierFT, HRA, RandLoRA, SHiRA, WaveFT, DeLoRA, GraLoRA, AdaMSS, and others.
So the future is not "pick the best PEFT."
The future is:
Build a system that knows when, where, why, and how to use each PEFT.
That is Omni-PEFT.

## 1. The synthesis of the three answers

The first uploaded answer contributes the maximalist research vision: every PEFT becomes a "delta expert," routed through a mixture-of-experts controller, meta-learned, quantization-native, modality-aware, and extensible across Transformers, MoE models, SSMs, multimodal backbones, and future architectures. It frames Omni-PEFT as a self-orchestrating meta-architecture, not a single method.
The second uploaded answer contributes the engineering discipline: the base model stays frozen; adaptation happens through a modular fabric; a controller learns which primitive to activate; the system begins with the cheapest solution and escalates only when validation proves it is needed. Its strongest principle is: reuse before rewrite.
My prior answer contributes the production architecture: Omni-PEFT should have a compiler, runtime, adapter genome registry, conflict resolver, evaluation gates, merge strategy, rollback path, governance layer, deployment profiles, and agentic routing.
Put together, the complete answer is:
Omni-PEFT is the operating system for parameter-efficient specialization. It turns the PEFT zoo into a governed economy of adapter atoms, delta operators, routers, compilers, and deployment policies.
That is the answer that beats all three individual responses.

## 2. The central doctrine

The doctrine is simple:
- Base model = intelligence substrate
- PEFT methods = adaptation primitives
- Omni-PEFT = compiler + router + runtime + registry + governance layer

A normal PEFT workflow asks:
Should I use LoRA, DoRA, IA3, prefix tuning, adapters, or QLoRA?

Omni-PEFT asks:
Given this base model, task, data, domain, latency budget, VRAM budget,
retention requirement, and deployment target:
What is the minimum effective adaptation plan?

That is the leap. A single PEFT method is a tool. Omni-PEFT is the system that chooses and coordinates the tools.

## 3. The strongest formal definition

Omni-PEFT is a universal adaptation kernel that represents all parameter-efficient fine-tuning methods as composable delta operators over frozen model weights, activations, prompts, hidden states, routing policies, and sparse trainable subspaces. It learns a cost-aware policy that allocates adaptation capacity only where measurable gain justifies the cost.

## 4. The highest-level architecture

```
OMNI-PEFT ADAPTATION OPERATING SYSTEM

├── 1. Frozen Foundation Kernel
│   └── The base model remains mostly unchanged.
│
├── 2. Universal Delta Intermediate Representation
│   └── Converts every PEFT method into a common operator format.
│
├── 3. PEFT Expert Library
│   └── LoRA, DoRA, QLoRA, AdaLoRA, IA3, prefix tuning, prompt tuning,
│       adapters, LoHa, LoKr, OFT, BOFT, VeRA, X-LoRA, masks, etc.
│
├── 4. Model Profiler
│   └── Finds sensitive layers, plastic layers, bottlenecks, merge-safe zones,
│       quantization risk, and high-leverage modules.
│
├── 5. Task / Domain Fingerprinter
│   └── Converts the user's task, data, domain, risk, and budget into a
│       compact adaptation descriptor.
│
├── 6. PEFT Compiler / Planner
│   └── Chooses which PEFT primitives to use, where to apply them,
│       how much capacity to allocate, and how to train them.
│
├── 7. Adaptive Routing Runtime
│   └── Activates adapters by task, token, layer, domain, confidence,
│       modality, and budget.
│
├── 8. Adapter Genome Registry
│   └── Stores every adapter with identity, purpose, version, compatibility,
│       benchmarks, routing rules, merge status, and rollback metadata.
│
├── 9. Conflict Resolver
│   └── Detects adapter interference, delta collisions, safety drift,
│       style conflict, domain bleed, and merge instability.
│
├── 10. Evaluation and Governance Layer
│   └── Runs accuracy, retention, latency, hallucination, safety, merge,
│       regression, and deployment gates.
│
└── 11. Deployment Manager
    └── Exports merged, semi-merged, hot-swappable, routed, edge,
        cloud, agentic, or quantized adapter packages.
```

## 5. The Universal Delta Intermediate Representation

Every PEFT method maps to one adaptation family:

| Family | Internal Operation | Examples |
|--------|--------------------|---------|
| Weight-space additive delta | Add compact update to frozen weights | LoRA, DoRA, AdaLoRA, LoHa, LoKr |
| Activation-space modulation | Scale, gate, inhibit, or amplify hidden activations | IA3, gating adapters |
| Prompt/context-space adaptation | Learn soft context vectors or layer prefixes | Prompt tuning, prefix tuning, P-tuning |
| Module-space residual transformation | Insert small nonlinear modules | Bottleneck adapters, parallel adapters |
| Structure-preserving transformation | Constrained transformations to weights | OFT, BOFT, orthogonal updates |
| Sparse/selective tuning | Train masks, selected params, sparse subsets | BitFit, FishMask, DiffPruning |
| Quantized adaptation substrate | Train adapters through quantized frozen models | QLoRA, LoftQ |
| Routing/composition adaptation | Dynamically select or combine adapters | X-LoRA, MoE-LoRA, AdapterFusion |
| Surgical direct unfreezing | Unfreeze small regions only when necessary | Output head, narrow bottlenecks |

## 6. The PEFT expert library

```
PEFT Expert Library

├── Low-rank experts
│   ├── LoRA, DoRA, AdaLoRA, LoHa, LoKr, VeRA, RandLoRA
│
├── Prompt/context experts
│   ├── Prompt tuning, Prefix tuning, P-tuning, Multitask prompt tuning
│
├── Activation experts
│   ├── IA3, learned gates, layerwise scaling vectors
│
├── Adapter-block experts
│   ├── Serial adapters, parallel adapters, bottleneck adapters, residual adapters
│
├── Structural experts
│   ├── OFT, BOFT, FourierFT, orthogonal/spectral adapters
│
├── Sparse/selective experts
│   ├── BitFit-style bias tuning, mask tuning, sparse delta tuning
│   └── Selective layer unfreezing
│
├── Routing experts
│   ├── X-LoRA, mixture-of-LoRA experts, adapter fusion, semantic routers
│
└── Quantization experts
    ├── QLoRA, LoftQ-style initialization, 4-bit/8-bit adapter training
    └── Quantization-aware merge policies
```

## 7. The key architectural principle: "cheapest sufficient change"

The perfect PEFT does not mean maximum adaptation. It means minimum effective adaptation.

Apex PEFT escalation ladder:
1. Do nothing if the base model already performs well.
2. Use retrieval or prompting if no weights need to change.
3. Use soft prompts or prefix tuning if task framing is enough.
4. Use IA3 or activation gating if light behavioral adjustment is enough.
5. Use LoRA / AdaLoRA / DoRA if weight-space adaptation is needed.
6. Use adapters if nonlinear specialization is needed.
7. Use routed multi-adapter composition if multiple domains are needed.
8. Use selective unfreezing only if all PEFT layers saturate.
9. Use full fine-tuning only as the final fallback.

The system should budget adaptation the way an engineering team budgets compute, memory, and latency. Start with the smallest reversible change. Escalate only when evidence demands it.

## 8. The Omni-PEFT compiler

The compiler takes: base model + task + data + domain + constraints + hardware + latency target + quality target + safety target + deployment mode.

It outputs: layer-wise adaptation plan + PEFT method selection + rank allocation + routing policy + training recipe + evaluation gates + merge strategy + deployment package.

The user specifies the outcome. The compiler chooses the PEFT.

## 9. The router: the apex feature

The router operates at multiple hierarchical levels:

```
Input
  ↓
Task Fingerprint Router — broad task family
  ↓
Domain Router — knowledge domain
  ↓
Layer Family Router — additive / prompt / activation / adapter / sparse / direct
  ↓
Layer Router — which layers receive which adaptation
  ↓
Token Router — dynamic adapter mixtures during generation
  ↓
Budget Router — prune paths violating latency, VRAM, or deployment budget
  ↓
Safety Router — block unsafe or incompatible adapter combinations
  ↓
Output
```

## 10. The adapter genome registry

Every adapter should have a genome, not just a weight file:

```yaml
adapter_genome:
  name: technical_database_architect
  version: 2.3.1
  base_model:
    family: kjva
    revision_hash: e59c6909
  purpose:
    domains: [database architecture, storage engines, query planning]
    tasks: [architecture critique, schema reasoning, benchmark interpretation]
  training:
    substrate: mlx
    dataset_manifest: data/corpus_v2/manifest.json
    data_quality_score: 0.91
  peft_stack:
    attention: { method: dora, rank_policy: { early: 4, middle: 16, late: 32 } }
    mlp: { method: adalora, budget_policy: importance_weighted }
    activation: { method: ia3, placement: [early_layers] }
    prompt_interface: { method: prefix_tuning, virtual_tokens: 8 }
  routing:
    activate_when: [theology, biblical scholarship, cross-reference]
    never_activate_when: [medical advice, casual conversation]
  compatibility:
    compatible_with: [retrieval_adapter_v1]
    conflicts_with: [casual_style_adapter_v1]
  evaluation:
    domain_accuracy: 0.87
    hallucination_delta: -0.14
    base_retention_score: 0.96
    latency_overhead_ms: 4.2
    merge_safety: pass
  deployment:
    mergeable: partial
    hot_swappable: true
    routed_runtime_required: true
  rollback:
    previous_stable: null
    quarantine_conditions: [domain_bleed_detected, base_retention_below_0.93, latency_above_budget]
```

## 11. The conflict resolver

Conflict types and resolution methods are detailed in `peft/conflict.py`.

## 12–30. (Sections 12–30 of the original design)

See the full text in the original source document at:
`KJVA/training/OMNI PEFT DESIGN` (plaintext, same content as this file).

Key sections for implementation reference:
- §13: Merge, hot-swap, or route decision rules
- §14: Training philosophy — progressive complexity (7 stages)
- §15: The multi-term objective function (task + params + memory + latency + forgetting + conflict + safety + router + governance)
- §16: The adapter tournament (Pareto selection criteria)
- §17: What "perfect" actually means (Pareto-optimal, not max accuracy)
- §18: Three adaptation planes (static weight / contextual / dynamic routing)
- §19: Model profiler layer plasticity map
- §20: Practical runtime flow
- §21: Implementation blueprint (7 phases)
- §24: Seven deployment modes
- §25: Multi-agent adapter ecosystem
- §26: The adapter economy model
- §29: Full architecture map (ASCII diagram)
- §31: One-sentence definition

---

*Source document placed here from `KJVA/training/OMNI PEFT DESIGN` (unextensioned plaintext)
on 2026-06-11 as part of doctrine true-up.*
