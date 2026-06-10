# Python Agent Runtime Surface

This package exposes a FastAPI-style agent surface and Heptagon-oriented helper
modules. It is kept as a reusable runtime template.

Two run modes are supported (see [models/QUICKSTART.md](../../QUICKSTART.md)
for the full flow):

- **Federated** — one process per Council seat, each owns its own
  `XMindClient`, persona, and adapter. Drives the C XMIND engine directly.
- **Legacy single agent** — one process fronts all sessions through the
  canonical `TokenlessAgent`.

For a raw HTTP model server (bypassing the agent layer entirely) use the
substrate's generic serving script with the staged artefacts:

```bash
python3 training/scripts/serve_raw_model.py \
  --export models/training \
  --port 8088
```

## Notes

- Federation mode is the production path; legacy mode is useful for single-
  member quick tests.
- Some modules in this package intentionally fall back to stubs when optional
  governance/runtime services are not importable.
- Keep API keys and agent IDs portable. Prefer `TOKENLESS_API_KEY` and
  `TOKENLESS_AGENT_ID` for new deployments.
