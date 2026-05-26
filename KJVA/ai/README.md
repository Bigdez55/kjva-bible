# AI Runtime Subsystem

This directory contains reusable AI runtime pieces for Tokenless Models.

## Components

| Path | Role |
|---|---|
| `xmind/` | C/SUPER C materialization and inference contracts. |
| `tokenless-agent/` | Python agent/runtime API surface; local serving uses `ml-training/scripts/serve_kjv_bundle.py`. |
| `companion/` | TypeScript client bridge and UI components for the local KJV runtime. |
| `tts/` | Optional local text-to-speech implementation. |

## Runtime Boundary

The current verified local path is retrieval-first Python through
`ml-training/scripts/serve_kjv_bundle.py`. XMIND remains the materialization
and C-runtime path for future deployment targets.

Keep this directory model-neutral. Consuming projects should supply their own
names, UI shell, and deployment policy.
