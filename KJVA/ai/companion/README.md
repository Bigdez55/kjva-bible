# Companion Client

The companion is a TypeScript/Vite client surface for talking to the local
Tokenless cognitive server.

## Default Server

`src/agent-bridge.ts` defaults to (override via `AgentBridgeConfig.agentBaseUrl`):

```text
http://localhost:8091
```

Endpoints the bridge talks to:

- `GET  /v1/health`          — connection liveness (polled)
- `GET  /v1/pipeline/status` — pipeline health (authenticated)
- `POST /v1/chat`            — chat turn (trace entries are synthesized from the response)

## Build

```bash
npm install
npm run lint    # tsc --noEmit type-check (Vite does the bundling)
npm run build   # tsc --noEmit && vite build  ->  dist/renderer
```

## Surface model — the model adopts the host project's UI

This companion is **substrate**: when the model is copied into a real project, that
project supplies its own UI. So this package is split into a reusable contract and a
**replaceable reference UI**, and the two are deliberately **not** wired together — a host
project should never inherit a companion UI it then has to remember to strip out.

| Layer | Files | Role |
|---|---|---|
| **Bridge contract** (keep) | `src/agent-bridge.ts`, `src/action-trace.ts` | The reusable client for the cognitive server (`/v1/health`, `/v1/pipeline/status`, `/v1/chat`) plus its trace/provenance data contract — `action-trace.ts` supplies `ActionTraceEntry` / `TurnProvenance` / `formatProvenance` (and the `ActionTracePanel`). The bridge **imports** `action-trace.ts`, so the two ship together; a host project keeps both and points its own UI at them. |
| **Avatar** (keep) | `src/avatar-state.ts` (FSM), `src/avatar-view.tsx` (React), `src/avatar-renderer.ts` (DOM), `src/avatar-animations.css` | The model's cognitive-state indicator: `idle → listening → thinking → speaking → idle` (+ `error`). Drop-in for any host UI; `AvatarState` is the single canonical type, owned by `avatar-state.ts`. |
| **Reference UI** (replaceable) | `src/command-panel.tsx`, `src/main.tsx` (+ `index.html`, `styles.css`, `tokens.ts`) | A standalone demo/testing harness. `main.tsx` is the only thing `index.html` mounts, and it imports only React + `./tokens` + `./styles.css` — **not** the bridge/avatar surface. Host projects replace this entirely. |

Because nothing wires the reference UI into a fixed entry point, copying the model into a
project carries the bridge contract + avatar forward without dragging a UI you must remove.
The host project's own interface is the testing ground.
