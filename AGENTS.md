# KJVA Bible — Agent Instructions

## Project Identity

Standalone Bible app powered by the KJVA model (18M-param byte-level LM,
val_ppl=3.21). Training infrastructure lives in the separate **Tokenless Models**
workspace — do not mix training code into this repo.

**Source of truth priority:** code > test evidence > docs.

---

## Architecture

```
backend/          FastAPI — inference, verse index, API routes
  model.py        TokenlessLM (inference copy, frozen — do not train here)
  inference.py    KJVA loader + byte-level completion engine
  corpus.py       VerseIndex from data/verses.jsonl
  routes/
    verse.py      /api/books, /api/chapters, /api/verses, /api/verse
    complete.py   POST /api/complete  (live; retrieval-first per ADR-0003)
    stubs.py      POST /api/search, /api/qa, /api/xref  (501 until Phase 2-4)
  main.py         FastAPI app, CORS, static serving, lifespan startup

frontend/         React + Vite
  src/App.jsx     Tab navigation (Browse, Completion, Search, Q&A, Xref)
  src/components/VerseBrowser.jsx    Book/chapter/verse navigation
  src/components/CompletionPanel.jsx AI text generation UI
  src/components/StubPanel.jsx       Placeholder for unimplemented features

data/
  verses.jsonl    36,822 structured verse records (gittracked)

models/kjva/
  weights.safetensors   GITIGNORED — copy from Tokenless Models
  model_config.json     Architecture config (gittracked)
  byte_vocab.json       Byte vocab spec (gittracked)
  provenance.json       sha256 manifest (gittracked)
```

---

## Critical Constraints

- `models/kjva/weights.safetensors` — **GITIGNORED** — never commit weights
- All training (pretraining, PEFT, benchmarking) lives in **Tokenless Models** repo
- MLX rules (from Tokenless Models, apply here too):
  - No `mx.log_softmax` — use `logits - mx.logsumexp(...)`
  - Freeze params with `model.freeze()`, not `requires_grad`
  - Gradients via `nn.value_and_grad` (not `.backward()`)
  - Weights: `mx.load()` + `model.load_weights(list(weights.items()))`
- `do_not_import_global_claude_codex_state: true`

---

## Development Workflow

Start backend:
```bash
cd backend && uvicorn main:app --reload --port 8001
```

Start frontend (dev):
```bash
cd frontend && npm run dev
```

Install KJVA weights (one-time):
```bash
cp "<Tokenless Models>/KJVA/training/weights.safetensors" models/kjva/weights.safetensors
```

---

## Feature Roadmap

| Phase | Feature | Requires |
|---|---|---|
| 1 (live) | Verse browser + retrieval-augmented completion | None for retrieval; KJVA weights for AI fallback |
| 2 | Semantic search | Embedding adapter (train in Tokenless Models) |
| 3 | Q&A / commentary | SFT adapter (train in Tokenless Models) |
| 4 | Cross-reference | Embedding similarity index |

---

## Stub Endpoints

`/api/search`, `/api/qa`, `/api/xref` return HTTP 501 with a structured error
explaining what adapter/training is required. Do not remove stubs — they allow
the frontend to render placeholders cleanly.

---

## Phase 1 Release (SLICE-0001)

See `development_skills/22_vertical_slices/SLICE-0001-phase1-release.yaml`.

- Retrieval-first `/api/complete` (ADR-0003)
- 29-test pytest suite in `backend/tests/`
- `Dockerfile` + `docker-compose.yml` for retrieval-only container preview
- `.github/workflows/ci.yml` runs ruff + pytest + docker build on push
