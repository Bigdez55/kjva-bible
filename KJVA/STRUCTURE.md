# models v7/ - Folder Structure

`models v7/` is the universal Tokenless substrate. It bundles the runtime layer
(C inference engine, federated agent, governance, memory) **and** the training
pipeline (byte/BPE pretraining, Omni-PEFT OS, eval, export, serve) into a
single tree, separate from any consuming project identity.

The substrate ships as one directory. `cp -r models v7/` into a new project gets
both halves at once.

## Layout

```text
models v7/
├── training/         byte/BPE pretraining + Omni-PEFT OS + eval + export + serve
│                     (also where wire_base.sh / wire_all.sh stage runtime artefacts)
├── ai/               runtime components (xmind C engine, agent, companion)
├── xmind_federation/           per-member XMindClient federation
├── heptagon/         7-layer cognitive metadata cycle
├── soul_manager/     continuity and memory contracts
├── governance/       covenant enforcement and response envelopes
├── constitution/     local invariant documents
├── adr/              architecture decision records
├── saas_translation/ neutral deployment templates
├── skills/           optional local skill manifests
└── docs/             supporting reference docs
```

## Train → Stage → Serve

```bash
# 1. Train via the in-tree training/ pipeline
python3 training/scripts/train_byte.py --run-id byte_v1_20m \
  --corpus training/corpus/<your-corpus-id>/corpus.txt

# 2. Stage the trained artefacts at the runtime's canonical paths
./training/scripts/wire_base.sh \
  --from-run training/runs/byte_v1_20m

# 3. (Optional) Wire promoted per-member adapters
./training/scripts/wire_all.sh

# 4. Serve the staged model
python3 training/scripts/serve_raw_model.py \
  --export training \
  --port 8088
```

The runtime canonical paths (`training/weights.safetensors`,
`training/model_config.json`, `training/byte_vocab.json`,
`training/adapters/<m>/`) are populated only when `wire_base.sh` /
`wire_all.sh` succeeds. These files are gitignored, so each project owns its
own staged artefacts.
