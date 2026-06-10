# Tokenless ML Training Workspace

`ml-training/` is the canonical model training home for this repository. It
contains the training source code, program registry, tests, corpus artifacts,
generated tokenizers, checkpoints, exports, validation reports, logs, and
lightweight manifests for the current workspace.

## Canonical Command

```bash
python3 ml-training/scripts/run_retrain.py \
  --recipe Bible_Tokenless_POC/training/kjv_retrain.yaml
```

## Current Corpus

- Corpus ID: `eng_kjv_apocrypha_v1`
- Canonical source: `eng-kjv_vpl/eng-kjv_vpl.xml`
- Cross-check source: `eng-kjv_vpl/eng-kjv_vpl.txt`
- Enrichment sources: `eng-kjv_html/`, `eng-kjv_browserBible/`
- Output directory: `corpus/eng_kjv_apocrypha_v1/`

Tracked corpus outputs include `corpus.txt`, `verses.jsonl`,
`retrieval_index.json`, `byte_vocab.json`, `manifest.json`, and
`validation_report.json`.

## Generated Artifacts

The following folders are intentionally present even when empty. Their runtime
outputs are generated locally and are mostly ignored by Git:

- `tokenizer/` - SentencePiece BPE tokenizer files.
- `runs/` - training checkpoints, configs, logs, and evaluation metadata.
- `exports/` - gated reusable model bundles and the active export symlink.
- `logs/` - local server and orchestration process logs.
- `signals/` - optional JSONL runtime signal capture.
- `adapters/` - future PEFT adapter staging and gated output.
- `gguf/` - future GGUF or edge export artifacts.
- `manifests/` - workspace-level inventory and expected-output manifests.
- `models/` - local model-side generated material, if needed by future runs.
- `scripts/` - active training, export, evaluation, and serving programs.
- `programs/` - omni training registry and runnable program configuration.
- `tests/` - runtime verification tests for the training/serving stack.
- `sc/` - local SUPER C training reference artifacts.
- `trainer/` - compatibility placeholder for older local scripts; active source
  code is in `scripts/`.

## Safety Rules

- Do not place old POC, GENESYS, Storbits, or desmond-super-c artifacts here.
- Do not commit checkpoints, weights, token caches, logs, or local process state.
- Do not copy auth/session/cache data from global `.claude` or `.codex`.
- `atlas/` remains outside this training workspace and is not part
  of retraining.
