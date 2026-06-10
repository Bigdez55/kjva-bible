# QUICKSTART.md — Tokenless Model Substrate

This template is wired identity-neutral. A consuming project supplies its own
brand, members, and training data. Below: the fastest path from `cp -r` to a
running agent.

## 0. Prerequisites

- clang or gcc (C compiler)
- Python 3.11+
- `make` (GNU make)

## 1. Copy the substrate

```bash
cp -r "Tokenless models/models v7/" my-project/
cd my-project/
```

## 2. Build the inference engine

```bash
make -C ai/xmind all
```

This produces:
- `ai/xmind/build/libxmind-core.a`         (static lib)
- `ai/xmind/build/libxmind-core.{so,dylib}` (shared lib for Python ctypes)
- `ai/xmind/build/xmind-cli`               (smoke binary)

Run the smoke binary to confirm the build:
```bash
./ai/xmind/build/xmind-cli
# expected last line: [smoke] PASS
```

## 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

Run the substrate smoke pytest:
```bash
python3 tests/test_substrate_smoke.py
# expected: Ran 7 tests in N.NNNs / OK
```

## 4. Declare your members

Each Council seat / office is identified by a filename under `xmind_federation/personas/`.

```bash
cp xmind_federation/personas/_template.txt xmind_federation/personas/analyst.txt
# edit analyst.txt — strip comments, write the persona

cp xmind_federation/personas/_template.txt xmind_federation/personas/reviewer.txt
# edit reviewer.txt
```

Member names: all lowercase, ASCII letters / digits / hyphens. Filename
matches the value of `MEMBER_NAME` env at daemon startup.

## 5. Train (via the in-tree training/ pipeline)

The substrate is a single tree. `training/` is the in-tree pipeline (byte/BPE
pretraining + Omni-PEFT OS + eval + export + serve). Drop your domain corpus
into `training/corpus/<your-corpus-id>/corpus.txt`, then:

```bash
# Base byte-level pretraining
python3 training/scripts/train_byte.py \
  --run-id byte_v1_20m \
  --corpus training/corpus/<your-corpus-id>/corpus.txt

# (Optional) Per-member LoRA adapters
python3 training/scripts/train_peft.py \
  --method lora --domains analyst \
  --base-checkpoint training/weights.safetensors \
  --corpus training/corpus/<your-corpus-id>/corpus.txt \
  --output training/adapters/staging/lora_analyst
python3 training/scripts/validate_adapter.py promote \
  --adapter training/adapters/staging/lora_analyst
```

Training emits artefacts under `training/runs/<run-id>/` and
`training/adapters/gated/<adapter>/` — they aren't useful to the runtime
until they're staged here. That's what step 6 does.

## 6. Stage trained artefacts into the runtime

```bash
# Pull weights + config + vocab from the latest run
./training/scripts/wire_base.sh \
  --from-run training/runs/byte_v1_20m

# Pull any promoted per-member adapters AND wire them into data/soul/<m>/.adapter
./training/scripts/wire_all.sh
```

`wire_base.sh` populates `training/{weights.safetensors, model_config.json,
byte_vocab.json}`. `wire_all.sh` discovers your members from
`xmind_federation/personas/*.txt` and writes the absolute adapter path into
`data/soul/<member>/.adapter`. The runtime reads `.adapter` on daemon startup.

`--symlink` is supported on both scripts if you want zero-copy staging while
hot-iterating (the runtime will then depend on the source path staying live).

## 7. Run

### Option A — Federated (one process per member)

```bash
# In one terminal, per member:
MEMBER_NAME=analyst USE_FEDERATION=1 python3 ai/tokenless-agent/src/api.py
# In another terminal:
MEMBER_NAME=reviewer USE_FEDERATION=1 python3 ai/tokenless-agent/src/api.py
```

Each process owns its own XMindClient (own persona, own KV cache, own adapter).
All processes mmap the same `training/weights.safetensors` — kernel page
cache deduplicates so the weight bytes are resident once physically.

### Option B — Legacy single agent

```bash
python3 ai/tokenless-agent/src/api.py
```

One agent handles all sessions through the canonical `TokenlessAgent` path.

## 8. Customize

- **Brand / project identity** — replace README content (this is just the substrate)
- **Authority model** — adapt `governance/covenant_enforcer.py` rules + `constitution/*.md`
- **Tools the agent uses** — extend `ai/tokenless-agent/src/agent.py` tool dispatch
- **Ports + deployment** — your project's env / docker-compose
- **Companion UI** — `cd ai/companion && npm install && npm run build` to build

## Verify after each change

```bash
python3 tests/test_substrate_smoke.py    # 7/7 expected
make -C ai/xmind test                    # C smoke
```

See `WIRING.md` for the deeper integration map and `INHERITANCE_MANIFEST.md`
for the contract surfaces protected by `DO_NOT_MODIFY.md`.
