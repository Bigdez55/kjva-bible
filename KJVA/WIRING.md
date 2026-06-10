# WIRING.md — How the Wired Substrate Hangs Together

This document describes the integration points the substrate template ships
wired. Read this AFTER `README.md` and BEFORE `QUICKSTART.md`.

> **This is the *idealized* contract doc.** For the *as-built* map — what actually
> executes on a chat turn, with DEFINED/IMPORTED/CALLED status, `file:line` evidence,
> and six rendered Mermaid diagrams — see
> [`docs/WIRING_MAP_AND_FLOW_2026-06-04.md`](docs/WIRING_MAP_AND_FLOW_2026-06-04.md).
> Where the two disagree, the as-built doc cites running code (source-of-truth order).

## What "wired" means

| Layer | Wired Component | File(s) |
|---|---|---|
| **C inference engine** | XMIND with LoRA adapter loader + flat ctypes API + POSIX build adapter + Makefile | `ai/xmind/` |
| **Federated Python client** | Per-member `XMindClient` (one per process, persona-driven) | `xmind_federation/` |
| **Persona registry** | Filename-based member naming, `_template.txt` + `README.md` | `xmind_federation/personas/` |
| **Agent runtime** | Canonical `TokenlessAgent` | `ai/tokenless-agent/src/` |
| **Bookworm-style glue example** | Generic helpers (`deliberate_classify`, `deliberate_reason`, `deliberate_gate`) | `ai/tokenless-agent/src/_xmind_glue.py` |
| **Training slot** | Generic scripts + README — no recipes ship | `training/` |
| **Runtime state layout** | Empty `data/` structure + README | `data/` |
| **Build system** | `ai/xmind/Makefile` + `pyproject.toml` + `requirements.txt` | (template root) |

## Operating mode

### Shared agent — 1 model serving all sessions

Used when a consuming project wants a single AI runtime fronting all of its
interactions. Matches the original `TokenlessAgent` design.

```
client → POST /v1/chat → ai/tokenless-agent/src/api.py
       → TokenlessAgent.chat(session_id, message)
       → cognitive_pipeline.py → Council daemons (if available)
       → XMIND inference
```

Run:
```bash
python3 -m ai.tokenless-agent.src.api
```

## Train → Stage → Serve (single tree)

The substrate is a single `models v7/` tree. Training lives in-tree at
`training/`, which produces artefacts that the wiring scripts under
`training/scripts/` stage at the runtime's canonical paths within the same
tree — no cross-tree staging.

```
   ┌──────────────────────────────────────────────────────────────┐
   │  training/  (training pipeline, in-tree)                     │
   │                                                              │
   │  scripts/train_byte.py     runs/<id>/ckpt_step_*.safetensors │
   │  scripts/train_peft.py     adapters/staging/lora_<m>/        │
   │  scripts/validate_adapter.py  promote → adapters/gated/<m>/  │
   │  scripts/promote_base_model.py        → bases/<NAME>/        │
   └────────────────────┬─────────────────────────────────────────┘
                        │
                        │  training/scripts/wire_base.sh --from-run <run-dir>
                        │  training/scripts/wire_all.sh
                        ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  training/  (runtime staging — gitignored canonical paths)   │
   │                                                              │
   │  weights.safetensors                                         │
   │  model_config.json                                           │
   │  byte_vocab.json                                             │
   │  adapters/<member>/adapter.safetensors                       │
   └────────────────────┬─────────────────────────────────────────┘
                        │
                        │  data/soul/<member>/.adapter (path pointer)
                        ▼
                member daemon: XMindClient.load_weights + load_adapter
```

`wire_base.sh` supports `--from-run <training/runs/<id>>` and
`--from-promoted <training/bases/<NAME>>`. `wire_all.sh` discovers members
from `xmind_federation/personas/*.txt` and writes
`data/soul/<m>/.adapter` for each member that has an adapter under
`training/adapters/{<m>, gated/<m>, gated/lora_<m>, staging/<m>, staging/lora_<m>}/`.

Both scripts accept `--symlink` for zero-copy staging during hot iteration.

## Copy-and-customize workflow

```
                Tokenless models/models v7/      (the substrate, untrained)
                          │
                          │ cp -r its CONTENTS into the new project
                          ▼
                  <new-project>/   (now holds xmind_federation/, training/, ai/, …)
                          │
                          │ 1. Add personas: xmind_federation/personas/<member>.txt × N
                          │ 2. Drop a corpus: training/corpus/<id>/corpus.txt
                          │ 3. Train base:  python3 training/scripts/train_byte.py …
                          │ 4. Stage base:  ./training/scripts/wire_base.sh
                          │                   --from-run training/runs/<id>
                          │ 5. (Optional)  PEFT per member + promote
                          │ 6. Stage adapters: ./training/scripts/wire_all.sh
                          │ 7. Build engine:  make -C ai/xmind all
                          │ 8. Start daemons per member, or single agent
                          ▼
                  Trained, federated, ready
```

## End-to-end startup checklist

1. **C engine compiled** — `make -C ai/xmind all` produces:
   - `ai/xmind/build/libxmind-core.a`
   - `ai/xmind/build/libxmind-core.{so,dylib}`
   - `ai/xmind/build/xmind-cli`
2. **Smoke** — `ai/xmind/build/xmind-cli` prints `[smoke] PASS`
3. **Python deps installed** — `pip install -r requirements.txt`
4. **Personas declared** — at least one `xmind_federation/personas/<member>.txt` file
   (use `_template.txt` as a starting point)
5. **Corpus present** — `training/corpus/<id>/corpus.txt`
6. **Base trained** — `python3 training/scripts/train_byte.py --run-id <id>`
   produces `training/runs/<id>/ckpt_step_*.safetensors`
7. **Base staged** — `./training/scripts/wire_base.sh --from-run training/runs/<id>`
   populates `training/{weights.safetensors, model_config.json, byte_vocab.json}`
8. **Adapters wired** — `./training/scripts/wire_all.sh`
   writes `data/soul/<member>/.adapter` for each member with a trained adapter
9. **Daemon starts** — `MEMBER_NAME=<name> python my_daemon.py` (federated)
   or `python -m ai.tokenless-agent.src.api` (legacy single-agent)

## Wiring touch-points (what the consuming project edits)

The template ships identity-neutral. The consuming project provides:

| Decision | Where |
|---|---|
| Member names + count | `xmind_federation/personas/<name>.txt` filenames |
| Member personas | content of those files |
| Project brand | replace template language in `README.md` |
| Domain corpus | `training/corpus/<id>/corpus.txt` |
| Port map | env per daemon (no template defaults beyond canonical Council ports) |
| Authority model | adapt `governance/covenant_enforcer.py` rules + `constitution/*.md` |
| Training recipes | in-tree `training/programs/<your-project>/` |
| Tools the agent uses | extend `ai/tokenless-agent/src/agent.py` tool dispatch |

## What stays untouched (canonical)

- The 8 `.sc` SUPER C blueprints
- `heptagon/{harness,layers,registry,attestation,member_guard,vacancy_matrix}.py`
- `heptagon/unified_model_spec.json`
- `governance/{covenant_enforcer,decision_envelope}.py`
- `soul_manager/{soul_manager,aes_gcm_bridge}.py`
- `ai/xmind/include/*.h` canonical contract headers (the 15 freestanding ones;
  `lora.h` + `xmind_easy.h` are additive universal extensions)
- `adr/ADR-S49-01-COGNITIVE-ARCHITECTURE-DOCTRINE.md`
- `constitution/` 4 immutable doctrines

These compose the contract surface other code depends on. Touch only with a
focused justification + matching verification per `DO_NOT_MODIFY.md`.

## Known pre-existing template content

Three canonical files reference example Council member names (Ahki, Ruth,
Sarah, Esther, Ezri, Abigail, Magen, Cherev) carried over from the reference
implementation:

- `heptagon/harness.py`
- `constitution/seat_protection_doctrine.md`
- `governance/governance.sc`

These are illustrative — consuming projects override member identity via the
`xmind_federation/personas/` filename convention. Don't take these names as required;
they're examples of the pattern.
