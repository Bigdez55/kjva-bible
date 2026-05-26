# QUICKSTART.md - Tokenless Model Runtime

## 1. Set Local Paths

```bash
export TOKENLESS_HOME="${TOKENLESS_HOME:-$PWD/ml-training}"
export TOKENLESS_EXPORT_DIR="${TOKENLESS_EXPORT_DIR:-$TOKENLESS_HOME/exports/kjv_tokenless_v1_active}"
```

The active export symlink is updated only after the KJV validation gates pass.

## 2. Start The KJV Runtime

```bash
python3 ml-training/scripts/serve_kjv_bundle.py \
  --bundle-dir "$TOKENLESS_EXPORT_DIR" \
  --port 8091
```

Health check:

```bash
curl http://127.0.0.1:8091/healthz
```

Single turn:

```bash
curl -s -X POST http://127.0.0.1:8091/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"God so loved the world","top_k":3}' \
  | python3 -m json.tool
```

## 3. Build The Companion

```bash
cd models/ai/companion
npm install
npm run lint
npm run build
```

The companion can be pointed at `http://localhost:8091` for the KJV runtime.

## 4. Replicate Into A Project

For a consuming project, copy or reference only what is needed:

- the export directory for the model
- `ml-training/scripts/serve_kjv_bundle.py` and its local imports
- the relevant contract directories: `heptagon/`, `governance/`,
  `soul_manager/`, and `ai/xmind/`
- the companion bridge if a UI needs direct local chat integration

Define product names, deployment ports, and cloud infrastructure in the
consuming project.
