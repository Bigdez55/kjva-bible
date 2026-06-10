# Runs Workspace

Training runs are generated here by `train_byte.py` (byte path) and
`train.py` (BPE path), and PEFT runs by `train_peft.py`.

Expected run-id pattern (consuming project picks its own):

- `bpe_v1_20m`
- `byte_v1_20m`

Each run should record model config, checkpoint metadata, corpus hash,
tokenizer or byte-vocab hash, step, loss, and validation perplexity. Checkpoints
and large generated run artifacts are ignored by Git.
