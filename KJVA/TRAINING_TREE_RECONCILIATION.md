# Training Tree Reconciliation — `training/` vs `ml-training/`

Date: 2026-06-10. Trigger: owner directive — two parallel training trees exist
from prior agent drift; verify all necessary files are consolidated before
removing one.

## Verdict

**Canonical tree: `KJVA/training/`** — it holds the production lineage
(`gguf/canonical.gguf` + promotion evidence, `runs/byte_clean_v1`/`v2`
production base checkpoints, PEFT v2 stack, `provenance/old_kjva/` vault
including the original `weights.safetensors`, docker, push_to_hf).

**`KJVA/ml-training/` is now fully redundant and safe to remove** (pending
owner confirmation — nothing has been deleted). Verification result:

| Category | Count | Disposition |
|---|---|---|
| Byte-identical in both trees | 131 | already in `training/` |
| Unique to `ml-training/` | 70 | **copied into `training/`** (rsync --ignore-existing, 2026-06-10) |
| Differs, `training/` newer | 41 | `training/` version canonical; old copy recoverable via git history (`KJVA/ml-training/` is git-tracked, 160 files) |
| Differs, `ml-training/` newer | 4 | **preserved** as `*.ml-training-variant.*` next to the canonical file |
| Missing after merge | **0** | — |

## Key assets merged from ml-training → training

- `corpus/eng_kjv_apocrypha_v1/` — v1 corpus + 23MB verses.jsonl + retrieval index
- `corpus/sacred_multi_v2/` — corpus v2 staging (85MB, 45 translations)
- `runs/kjv_byte_v1_20m/` — original MLX run metadata + train log
- `runs/{byte_sft_v1, sft_v1, peft_alignment_tournament_v1, smoke_v2_warmstart}/`
- `exports/kjv_byte_bringup/` (weights.npz) and `gguf/kjv_byte.gguf(.json)`
- `scripts/{build_kjv_corpus, byte_codec, kjv_retrieval, validate_kjv_retrieval, omni_scribe, eval_scribe_v2, serve_kjv_bundle, start_all, status}.py/.sh`
- `tests/` (5 test files), `eval/`, `models/`, `peft/{OMNI_PEFT_DOCTRINE.md, omni_composite.py}`, `requirements-kjv.txt`

## Newer-in-ml-training variants preserved

- `training/README.ml-training-variant.md`
- `training/programs/omni_training_registry.ml-training-variant.json`
- `training/scripts/convert_to_gguf.ml-training-variant.py`
- `training/scripts/train_peft.ml-training-variant.py`

Review each against its canonical sibling and fold in any wanted changes
before deleting `ml-training/`.

## Path notes

- `scripts/train_byte.py` defaults `TOKENLESS_HOME` to `<repo>/ml-training`;
  when running from the canonical tree set `TOKENLESS_HOME=$PWD/training`.
- Removed empty drift artifact `training/training/`.

## To remove ml-training (owner action)

```bash
cd kjva-bible
git rm -r KJVA/ml-training        # history retains all versions
echo "Moved to KJVA/training/ — see KJVA/TRAINING_TREE_RECONCILIATION.md" > KJVA/ml-training-MOVED.md
git add KJVA/ml-training-MOVED.md
```
