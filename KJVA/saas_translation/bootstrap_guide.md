# Project Bootstrap Guide

Use this checklist when copying the Tokenless model pattern into a new project.

1. Copy both `models/` and `training/` into the new project.
2. Drop a domain corpus into `training/corpus/<your-corpus-id>/corpus.txt`.
3. Train a base model:
   ```bash
   python3 training/scripts/train_byte.py --run-id byte_v1_20m \
     --corpus training/corpus/<your-corpus-id>/corpus.txt
   ```
4. Stage the base into the runtime:
   ```bash
   ./training/scripts/wire_base.sh --from-run training/runs/byte_v1_20m
   ```
5. Declare members and (optionally) train per-member LoRA adapters via
   `train_peft.py`, then `./training/scripts/wire_all.sh`.
6. Choose a serving entry point:
   - Generic HTTP: `training/scripts/serve_raw_model.py --export models/training`
   - Federated agent: `MEMBER_NAME=<m> USE_FEDERATION=1 python3 ai/tokenless-agent/src/api.py`
7. Verify `/healthz` and a `/generate` (or your agent's surface) call.
8. Decide whether the project needs the companion UI bridge.
9. Decide whether SoulManager writes to local files, a database, or another
   encrypted backend.
10. Write project-specific identity and deployment docs in the consuming project.

Keep this repo as the neutral blueprint.
