# Agent Relay (vendored)

Offline install package for Agent Relay 0.1.0. Do not commit live control state under `.relay/`.

- **Active pin:** `PIN.json`
- **Package root:** `0.1.0/` (wheel, manifest, installer, docs)
- **Install:** read `0.1.0/INSTALL_FOR_CODING_AGENT.md` — installs to a **new** prefix under `$HOME/.local/share/agent-relay/0.1.0`, not into `byte/relay` or existing stores.

Verify vendored integrity:

```sh
python3 vendor/agent-relay/0.1.0/tools/verify_package.py
```
