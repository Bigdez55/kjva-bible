# Companion Client

The companion is a TypeScript/Vite client surface for talking to the local
Tokenless cognitive server.

## Default Server

`src/agent-bridge.ts` defaults to:

```text
http://localhost:8090
```

Expected endpoints:

- `GET /healthz`
- `POST /v1/chat`
- `POST /v1/chat/stream`
- `POST /v1/cite`

## Build

```bash
npm install
npm run lint
npm run build
```

Consuming projects can replace the UI while keeping the bridge contract.
