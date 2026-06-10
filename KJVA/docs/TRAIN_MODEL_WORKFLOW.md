# "Train This Model" — Standing Workflow

**Trigger phrases:** "train this model", "we're gonna train this model", "train a new
model", "let's train", "spin up training", or any clear request to train/fine-tune.

When triggered, the assistant runs this exact protocol — a smooth, private, repeatable
process. The assistant **always asks the intake questions first**, waits for answers,
confirms the plan, then executes. Nothing trains until the user says go.

---

## STEP 1 — INTAKE (ask the user; never assume)

Ask these via the question UI. The user supplies the answers.

1. **Model type** — Neutral **base** (foundation, no identity) **or** a **named domain** model?
2. **(domain only) Purpose** — *What is this model for?* The use case / platform / industry
   it will serve (e.g. healthcare records, transit operations, a database NL interface, legal, …).
3. **(domain only) Name** — What should the model be named? (becomes `general.name` at export)
4. **Corpus / data** — What data trains it?
   - **Default (current): `eng_kjv_apocrypha_v1`** (the KJV+Apocrypha byte corpus, committed in repo).
   - For a domain model: a path to the domain corpus (and whether to fine-tune from the base).
5. **Venue + depth** — Codespace **full** (~30–60 min, off the Mac) · local **smoke** (~10 min) · custom iters.
6. **Publish** — Private HF repo? (**default: yes, PRIVATE** — `tokenless-base-v*` / `tokenless-domain-<slug>`).

## STEP 2 — CONFIRM

Echo back the plan: model type, name (if any), corpus, venue, est. time, privacy.
Get an explicit "go" before training (training is resource/time-committing).

## STEP 3 — EXECUTE

**Neutral base** (current KJV plan):
```bash
# in a 16-core Codespace (free, off the Mac) — or local for a smoke:
bash "models v7/training/train_on_codespace.sh" full        # 5000 iters → val_ppl ≤ 3.21
python3 "models v7/training/pt/export.py" --run runs/byte_v1_20m --output gguf/base.gguf
python3 "models v7/training/push_to_hf.py" --repo tokenless-base-v1 \
    --card "models v7/BASE_MODEL_CARD.md" --files gguf/base.gguf runs/byte_v1_20m/model_config.json runs/byte_v1_20m/byte_vocab.json
```

**Named domain model** (one command — trains, names, validates, publishes PRIVATE):
```bash
bash "models v7/training/spawn_domain_model.sh" \
    --name <Name> --domain <purpose> --corpus <data.txt> \
    --base-run runs/byte_v1_20m --steps 500 --push-hf
```

## STEP 4 — VERIFY + REPORT

- Base: report final `val_ppl` (target ≤ 3.21) from `runs/<id>/train_log.jsonl`.
- Domain: `validate_adapter.py check` must PASS (all gates); GGUF named correctly.
- Confirm the HF repo is **private** (`push_to_hf.py` verifies this automatically).
- Report: what trained, where it lives (private), and the next action.

---

## DEFAULTS / INVARIANTS (always)

- **DISRUPTION-SAFE (critical):** every run saves a checkpoint **every 500 iters** with full
  resume state (model + optimizer + RNG + step), written atomically. If anything interrupts
  training, just **re-run the same command** — `--resume` continues from the last save (never
  restarts from zero; never loses more than ~500 iters). `train_on_codespace.sh` has this baked in.
- **Corpus default = `eng_kjv_apocrypha_v1`** (until the user specifies a domain corpus).
- **Everything PRIVATE** — private GitHub repo, private HF repos, proprietary LICENSE. Never `--allow-public`.
- **Off the Mac** — prefer the free 16-core Codespace for full runs; local only for smoke.
- **Neutral base stays nameless**; identity is applied only to derived domain models at export.
- Weights never committed to git (gitignored); they live local / private HF.

## CURRENT STATE (as of base freeze)

- Substrate frozen at tag `models-v7-base-v1.0.0`; pipeline verified (42/42 tests).
- The **neutral base** still needs its one full pretrain on `eng_kjv_apocrypha_v1` (Codespace) to
  produce the shared base weights every domain model forks. That is the immediate "train this model" job.
