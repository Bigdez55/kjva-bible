# Repository Structure

## Root Layout

```text
Tokenless-Models/
│
├── ml-training/                  Training infrastructure — corpus, scripts, PEFT OS, runs, evals
├── models/                       Universal model substrate template (copy for new projects)
├── KJVA/                         KJVA base model — trained copy of models/ with step-5000 weights
│
├── eng-kjv_vpl/                  Primary corpus source: KJV+Apocrypha in Verse-Per-Line format
├── eng-kjv_browserBible/         Corpus metadata: per-chapter HTML (browser-bible format)
├── eng-kjv_html/                 Corpus metadata: per-chapter HTM (chapter-level HTML)
│
├── Bible_Tokenless_POC/          DO NOT MODIFY — reference blueprint, first working tokenless POC
├── development_skills/           Shared skill toolkit (178 SKILL_*.yaml + playbooks)
│
├── AGENTS.md                     Agent routing and skill invocation policy
├── CLAUDE.md                     Claude-specific config (delegates to AGENTS.md)
├── STRUCTURE.md                  This file — canonical repo map
├── README.md                     Project overview and quick-start
├── LICENSE                       MIT
└── .gitignore                    Excludes *.safetensors, *.gguf, runs/, .venv/, etc.
```

---

## ml-training/ Layout

```text
ml-training/
├── corpus/                       Processed corpus files (byte tokens, verse JSON)
│   └── eng_kjv_apocrypha_v1/     Primary training corpus (5.46M byte tokens)
├── peft/                         Omni-PEFT Adaptation OS (37 methods + OS modules)
│   ├── base.py                   DeltaOperator ABC, DeltaFamily enum
│   ├── compiler.py               PEFT Compiler — task → method plan
│   ├── profiler.py               Layer plasticity mapper
│   ├── fingerprint.py            Task/domain fingerprinter
│   ├── registry.py               Adapter Genome Registry
│   ├── router.py                 Hierarchical runtime router
│   ├── conflict.py               Conflict resolver
│   ├── tournament.py             Training tournament (Pareto selection)
│   ├── deployment.py             Merge/hot-swap/export manager
│   ├── model.py                  OmniPEFTBlock, OmniPEFTModel
│   ├── low_rank/                 LoRA, DoRA, QLoRA, AdaLoRA, VeRA, PiSSA, rsLoRA, OLoRA, LoHa, LoKr, RoSA
│   ├── additive/                 Houlsby, Pfeiffer bottleneck adapters
│   ├── prompt/                   Prompt tuning, Prefix tuning, P-tuning
│   ├── activation/               IA³
│   ├── selective/                BitFit, DiffPruning, FishMask, FAR
│   ├── hybrid/                   UniPELT, MAM, Compacter, X-LoRA
│   ├── structural/               OFT, BOFT, FourierFT
│   └── alignment/                SFT, DPO, IPO, KTO, ORPO, PPO-RLHF, GRPO
├── scripts/
│   ├── train_byte.py             Base byte-level pretraining (--resume, checkpoint benchmarks)
│   ├── train_peft.py             Unified PEFT CLI (--method <37 methods>)
│   ├── model.py                  TokenlessLM architecture (18M params, vocab 259)
│   ├── ckpt_bench.py             Inline checkpoint benchmark (auto-runs at every save)
│   ├── benchmark_byte.py         Comprehensive 8-section stress test
│   ├── validate_adapter.py       8-gate adapter validation pipeline
│   ├── convert_to_gguf.py        GGUF export (f32/f16/q8_0/q4_0/q4_1)
│   └── promote_base_model.py     Graduate a run to models/<NAME>/ with provenance
├── programs/
│   ├── omni_training_registry.json   44 methods (42 implemented, 2 planned)
│   ├── kjv_omni_program.yaml         Master training program
│   └── omni_training_programs.jsonl  Serialized program corpus
├── adapters/
│   ├── staging/                  Adapters pending validation
│   └── gated/                    Validated and promoted adapters
├── runs/
│   └── kjv_byte_v1_20m/          Completed training run (step 1–5000, metadata only)
├── eval/
│   └── kjv_byte_v1_20m/          Benchmark results (benchmark_final.json)
├── manifests/
│   └── workspace_manifest.json   Current workspace state and canonical paths
└── tests/
    ├── test_peft_operators.py    34 operator forward-pass tests
    └── test_peft_imports.py      5 import/registry tests
```

---

## models/ Substrate Template

`models/` is the reusable template directory. Every new project starts by copying it:

```bash
cp -r models/ <PROJECT_NAME>/
```

It contains the full cognitive stack: AI (XMIND, companion, TTS), Heptagon (7-layer
cognitive cycle), governance (covenant enforcement), soul_manager (encrypted memory),
constitution (invariant docs), ADRs, and SaaS translation guides.

**KJVA** is a trained instance of this template — `models/` copied and augmented with
step-5000 weights (18M params, KJV+Apocrypha, val_ppl=3.21).

---

## Corpus Source Chain

```
eng-kjv_vpl/eng-kjv_vpl.txt          ← primary source (36,822 verses)
        ↓  train_byte.py
ml-training/corpus/eng_kjv_apocrypha_v1/tokens_byte_uint16.npy
        ↓  train_byte.py (5000 steps)
ml-training/runs/kjv_byte_v1_20m/ckpt_step_005000.safetensors
        ↓  cp
KJVA/training/weights.safetensors     ← canonical base model
```

---

## Base Model Hierarchy

| Name | Source | Step | val_ppl | Use |
|---|---|---|---|---|
| `KJVA` | `models/` copy + training | 5000 | 3.21 | Starting point for all domain fine-tunes |

For each new domain project: `cp -r KJVA/ <DOMAIN>/` then run `train_peft.py`.

---

## Policy Boundaries

| Directory | Policy |
|---|---|
| `Bible_Tokenless_POC/` | **DO NOT MODIFY** — reference blueprint only |
| `eng-kjv_vpl/`, `eng-kjv_html/`, `eng-kjv_browserBible/` | Read-only corpus source |
| `ml-training/adapters/staging/` | Requires `validate_adapter.py check` before promotion |
| `ml-training/adapters/gated/` | Only populated via `validate_adapter.py promote` |
| `models/` | Template — do not add project-specific content here |
