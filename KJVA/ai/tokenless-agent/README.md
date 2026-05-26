# Python Agent Runtime Surface

This package exposes a FastAPI-style agent surface and Heptagon-oriented helper
modules. It is kept as a reusable runtime template.

For the currently verified local model server, use:

```bash
python3 ml-training/scripts/serve_kjv_bundle.py \
  --bundle-dir "$TOKENLESS_EXPORT_DIR" \
  --port 8091
```

## Notes

- The KJV bundle server is the active clean runtime path.
- Some modules in this package intentionally fall back to stubs when optional
  governance/runtime services are not importable.
- Keep API keys and agent IDs portable. Prefer `TOKENLESS_API_KEY` and
  `TOKENLESS_AGENT_ID` for new deployments.
