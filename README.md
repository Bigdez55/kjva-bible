# KJVA Bible

Full-scale King James Bible app powered by the KJVA AI model — an 18M-param
byte-level language model trained on KJV+Apocrypha (val_ppl=3.21).

**Stack:** Python FastAPI backend · React (Vite) frontend  
**Training workspace:** [Tokenless Models](../Tokenless%20models) — do not mix training code here.

---

## Features

| Feature | Status | Notes |
|---|---|---|
| Verse browser | Live | All 66 books, 36,822 verses |
| Retrieval-augmented completion | Live | Direct ref + prefix match + RAG fallback (per ADR-0003) |
| AI verse completion | Live (Apple Silicon) | KJVA model, byte-level generation; gracefully degrades to retrieval-only when weights absent |
| Semantic search | Phase 2 | Requires embedding adapter |
| Q&A / commentary | Phase 3 | Requires SFT adapter |
| Cross-reference | Phase 4 | Requires embedding similarity index |

---

## Quick Start

### 1. Install the KJVA weights (one-time, ~72 MB)

```bash
cp "<Tokenless Models>/KJVA/training/weights.safetensors" models/kjva/weights.safetensors
```

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

### 3. Frontend (dev)

```bash
cd frontend
npm install
npm run dev      # → http://localhost:5173
```

Vite proxies `/api` to the backend at `:8001`. No CORS configuration needed in dev.

### 4. Production build

```bash
cd frontend && npm run build   # outputs to frontend/dist/
cd ../backend && uvicorn main:app --port 8001
# FastAPI serves the React build from dist/ automatically
```

---

## Data

| File | Description |
|---|---|
| `data/verses.jsonl` | 36,822 verse records (book, chapter, verse, text, Strongs, footnotes) |
| `models/kjva/model_config.json` | Architecture config (8L × d384, 6 heads, vocab=259) |
| `models/kjva/byte_vocab.json` | Byte vocabulary spec (PAD=0, BOS=1, EOS=2, byte N → N+3) |
| `models/kjva/weights.safetensors` | **Gitignored** — copy from Tokenless Models |
| `models/kjva/provenance.json` | sha256 manifest for tracked model artifacts |

---

## Corpus Sources (read-only)

The three raw KJV corpus directories live in the Tokenless Models workspace
and are the canonical READ-ONLY sources. `data/verses.jsonl` is the
pre-processed structured output that this app consumes.

---

## Policy Constraints

- `models/kjva/weights.safetensors` — gitignored; sha256 tracked in `provenance.json`
- Training scripts, PEFT methods, checkpoints — live in Tokenless Models, not here
- `do_not_import_global_claude_codex_state: true` — do not import `.claude/.codex` globally

---

## Retrieval-first completion

POST `/api/complete` resolves prompts in this order (see ADR-0003):

1. **Direct reference** — `John 3:16`, `Numbers 15:37-41`, `Prov 31` → returns verse text, `retrieved=true`.
2. **Text prefix / keyword match** — `In the beginning God` → returns the rest of the matched verse.
3. **RAG-augmented AI fallback** — prose prompts get a corpus-context block, then the 18M model generates.
4. **Raw AI** — fallthrough.

Retrieval branches do **not** require weights. The endpoint stays useful in CI, in Docker on linux/amd64, and any host without MLX. When retrieval misses and weights are absent, the endpoint returns a structured `503 {error, fix}`.

## Testing

```bash
cd backend && python -m pytest tests/ -v
```

29 tests cover corpus retrieval, all `/api/verse*` routes, `/api/complete` retrieval branches, validation, and stub endpoints.

## Container preview

```bash
docker compose build backend
docker compose up -d backend
curl -fsS http://localhost:8000/api/health
```

By default the container runs in **retrieval-only mode**. To enable AI fallback on an Apple Silicon host, uncomment the weights volume in `docker-compose.yml`.

## License

MIT.
