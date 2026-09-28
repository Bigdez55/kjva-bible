# Agent Relay (vendored)

Offline install package for Agent Relay 0.2.0. Do not commit live control state under `.relay/`.

- **Active pin:** `PIN.json`
- **Package root:** `0.2.0/` (wheel, manifest, installer, docs, `relay-mcp`)
- **Install:** read `0.2.0/INSTALL_FOR_CODING_AGENT.md` — installs to a **new** prefix under `$HOME/.local/share/agent-relay/0.2.0`, not into Byte Relay or existing stores.

Verify vendored integrity:

```sh
python3 vendor/agent-relay/0.2.0/tools/verify_package.py
```
