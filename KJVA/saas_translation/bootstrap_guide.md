# Project Bootstrap Guide

Use this checklist when copying the Tokenless model pattern into a new project.

1. Pick a model export ID.
2. Set `TOKENLESS_HOME` and `TOKENLESS_EXPORT_DIR`.
3. Start `ml-training/scripts/serve_kjv_bundle.py`.
4. Verify `/healthz`, `/v1/cite`, and `/v1/chat`.
5. Decide whether the project needs the companion UI bridge.
6. Decide whether SoulManager writes to local files, a database, or another
   encrypted backend.
7. Write project-specific identity and deployment docs in the consuming project.

Keep this repo as the neutral blueprint.
