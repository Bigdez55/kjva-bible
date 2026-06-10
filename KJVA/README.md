# Tokenless Model Substrate

This directory is the universal **runtime + training** substrate for Tokenless
Models. It is wired identity-neutral and is meant to be **copied** into a new
project, **trained** on that project's domain data via the in-tree
`training/` pipeline, and **dropped in** as the AI layer.

The substrate ships as a single `models v7/` tree. Copy its **contents** into the
consuming project — there is no sibling directory to also copy. The training
pipeline (byte/BPE pretraining, Omni-PEFT OS, eval, export, serve) lives
inside `training/`. See [STRUCTURE.md](STRUCTURE.md) for the
Train → Stage → Serve sequence.

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
models v7/
├── ai/
│   ├── xmind/              C inference engine + POSIX shim + LoRA loader + Makefile
│   ├── tokenless-agent/    Python FastAPI agent runtime
│   ├── companion/          TypeScript companion client
│   └── tts/                optional local speech engine
├── xmind_federation/                 per-member XMindClient federation (Python ctypes)
│   └── personas/           drop <member-name>.txt files per Council seat
├── training/               byte/BPE pretraining + Omni-PEFT OS + eval + export + serve
│   ├── scripts/            train_byte.py, train_peft.py, wire_base.sh, wire_all.sh, …
│   ├── peft/               37 PEFT method implementations
│   ├── corpus/             consuming project's domain corpus
│   ├── runs/               training checkpoints
│   ├── adapters/           PEFT staging + gated outputs
│   ├── bases/              promoted base models
│   ├── exports/            portable bundles
│   ├── eval/               benchmark reports
│   └── …                   manifests, programs, tokenizer, etc.
├── heptagon/               7-layer cognitive cycle
├── governance/             covenant enforcement and envelopes
├── soul_manager/           memory and continuity layer
├── constitution/           local invariant documents
├── adr/                    architecture decisions
├── skills/                 reusable governance pattern notes
├── docs/                   supporting reference material
├── saas_translation/       deployment translation guides
├── data/                   per-process runtime state (gitignored)
└── pal/ net/ sec/ xisc/    Platform-layer contract headers (real files at top-level)
    xstore/                  XSTORE storage header (canonical top-level home)
```

## What's wired

The substrate ships ready to build + run in stub mode out of the box:

- **C engine**: builds via `make -C ai/xmind all` (produces `libxmind-core.{a,so/dylib}` + `xmind-cli`)
- **Per-member federation**: `xmind_federation.XMindClient` reads `MEMBER_NAME` from env
  and loads `xmind_federation/personas/<MEMBER_NAME>.txt`; falls back to stub
  gracefully if no model loaded
- **LoRA adapter loader**: `ai/xmind/src/lora.c` reads safetensors;
  daemon auto-discovers `data/soul/<member>/.adapter`
- **Agent runtime**: `TokenlessAgent` (1 model serving many sessions) — `ai/tokenless-agent/src/agent.py`
- **Training pipeline**: `training/scripts/train_byte.py`, `train_peft.py`,
  `validate_adapter.py`, `benchmark_byte.py`, `serve_raw_model.py`, …
- **Staging scripts** (member-agnostic): `training/scripts/wire_base.sh`,
  `wire_all.sh`, `npz_to_safetensors.py`

See **`WIRING.md`** for the full integration map.

## Copy → Train → Drop-In Workflow

```bash
# 1. Copy the wired substrate INTO a new project (note trailing slash on src)
cp -r "Tokenless models/models v7/" my-project/

# 2. Build the C engine
cd my-project/
make -C ai/xmind all                     # → libxmind-core.{a,so/dylib} + xmind-cli
./ai/xmind/build/xmind-cli               # smoke test — should print [smoke] PASS

# 3. Install Python deps
pip install -r requirements.txt

# 4. Declare members (one persona file per Council seat)
cp xmind_federation/personas/_template.txt xmind_federation/personas/<member-name-1>.txt
# ... edit each ...

# 5. Drop a domain corpus into training/corpus/<id>/corpus.txt, then train:
python3 training/scripts/train_byte.py \
  --run-id byte_v1_20m \
  --corpus training/corpus/<your-corpus-id>/corpus.txt

# 6. Stage the trained base into the runtime
./training/scripts/wire_base.sh --from-run training/runs/byte_v1_20m

# 7. (Optional) Train per-member LoRA adapters + promote + wire them
python3 training/scripts/train_peft.py --method lora --domains member-1 \
  --base-checkpoint training/weights.safetensors \
  --corpus training/corpus/<your-corpus-id>/corpus.txt \
  --output training/adapters/staging/lora_member-1
python3 training/scripts/validate_adapter.py promote \
  --adapter training/adapters/staging/lora_member-1
./training/scripts/wire_all.sh

# 8. Run the agent (1 model serving all sessions)
python3 -m ai.tokenless-agent.src.api
```

## Verify after copy

```bash
python3 tests/test_substrate_smoke.py    # 7/7 PASS expected
make -C ai/xmind test                    # C smoke
```

## Portability Rule

Do not put consuming-project identity in this directory. Model IDs, product
names, cloud providers, and deployment decisions should live in the consuming
project or in the export manifest for that specific model.
