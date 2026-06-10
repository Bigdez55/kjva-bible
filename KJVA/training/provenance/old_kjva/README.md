# Tokenless Model Substrate

This directory is the primary runtime and training substrate for Tokenless
Models. It is meant to be copied from, tested against, and adapted into other
projects without carrying project-specific identity or external repository
assumptions.

## Contract Set

The following names are local architecture contracts and should stay intact:

- `Heptagon`: the 7-layer cognitive cycle and trace/evaluation envelope.
- `XMIND`: the materialization and inference contract surface.
- `Citadel` / `Covenant`: governance checks and decision boundaries.
- `SoulManager`: continuity, memory, and encrypted persistence boundaries.

These are not tied to one product name. Consuming projects can wrap them with
their own brand, agent identity, port map, deployment target, and model export.

## Structure

```text
models/
├── ai/
│   ├── xmind/         C/SUPER C materialization contracts
│   ├── tokenless-agent/    Python FastAPI-style runtime surface
│   ├── companion/     TypeScript companion client
│   └── tts/           optional local speech engine
├── heptagon/          cognitive cycle
├── governance/        covenant enforcement and envelopes
├── soul_manager/      memory and continuity layer
├── constitution/      local invariant documents
├── adr/               architecture decisions
└── docs/              supporting reference material
```

## Active Serving Path

The current verified serving path is retrieval-first:

```text
client -> http://localhost:8091 -> ml-training/scripts/serve_kjv_bundle.py
  -> KJVRetriever
  -> exact citation lookup
  -> retrieval-scored chat response
```

Use `--bundle-dir` to point at the exported KJV bundle for the project you are testing:

```bash
python3 ml-training/scripts/serve_kjv_bundle.py \
  --bundle-dir "$TOKENLESS_EXPORT_DIR" \
  --port 8091
```

## Portability Rule

Do not put consuming-project identity in this directory. Model IDs, product
names, cloud providers, and deployment decisions should live in the consuming
project or in the export manifest for that specific model.
