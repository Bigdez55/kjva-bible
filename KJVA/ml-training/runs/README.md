# Runs Workspace

Training runs are generated here by `run_retrain.py`.

Expected run IDs:

- `kjv_bpe_v1_20m`
- `kjv_byte_v1_20m`

Each run should record model config, checkpoint metadata, corpus hash,
tokenizer or byte-vocab hash, step, loss, and validation perplexity. Checkpoints
and large generated run artifacts are ignored by Git.
