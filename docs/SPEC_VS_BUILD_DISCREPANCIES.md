# kjva-bible — Spec ↔ Build Discrepancies

Generated 2026-06-20 · Companion to [`ARCHITECTURE MAP.html`](./ARCHITECTURE%20MAP.html) · reconnaissance only (read-only; nothing built, run, or modified)

**Verdict:** Real, wired full-stack application (FastAPI + React + a deeply-imported "constitutional cognitive runtime" substrate), whose `README.md` / `AGENTS.md` are a **stale "Phase 1" snapshot** that under-describes the current build and still carries a "do not mix training code here" rule that the (Creator-authorized) in-repo `KJVA/` substrate contradicts.

---

## A. Summary

`kjva-bible` is a King James Bible study app. It has **two layers that both ship in-tree**:

1. **The app** — `backend/` (FastAPI: verse index + retrieval + a "scribe" orchestrator) and `frontend/` (React/Vite, 2 tabs) over `data/verses.jsonl` (36,822 verses, verified).
2. **The substrate** — `KJVA/`, a large cognitive/governance/training tree (heptagon, governance/covenant, soul_manager, an `ai/xmind` C inference engine compiled from SuperC, plus the full training pipeline). This is **not dead vendored bulk**: the backend imports and calls it (`backend/kjva_runtime.py` → `KJVA.governance.*`, `KJVA.heptagon.*`, `KJVA.soul_manager.*`, and `agent`/`_xmind` from `KJVA/ai/tokenless-agent/src/`).

The 3.1 GB on disk under `KJVA/` is overwhelmingly **gitignored model binaries** (`*.gguf`, `*.safetensors`, `*.npz` — e.g. `KJVA/training/gguf/canonical.gguf`), not source. Honest source is far smaller.

### Real-source census (vendored bulk excluded)

| Bucket | Count | Notes |
|---|---|---|
| Python (`.py`), first-party + wired substrate | **274** | `backend/` 19 · `KJVA/` 250 · `scripts/` 5. Excludes `__pycache__`, `.pytest_cache`, `.ruff_cache`, `atlas/`, `.claude/`, `.codex/`. |
| JS/JSX (real, non-vendored) | **15** | `frontend/src/` = 4 (`main.jsx`, `App.jsx`, `VerseBrowser.jsx`, `StudyPanel.jsx`); remainder = config/tests. `node_modules/` & `dist/` excluded. |
| Git-tracked files (whole repo) | 6,971 | of which **atlas/ = 3,264** (synced ATLAS SDLC governance bundle — vendored), **data/ = 2,982** (mostly the tracked eng-kjv source corpus under `data/corpus/`), **KJVA/ = 618**, backend 21, frontend 8. |
| `data/verses.jsonl` | 36,822 records | **Verified** by line count + record shape (`GEN.1.1` … Strongs, footnotes). |
| `data/corpus_v2/versions/*.jsonl` | 45 on disk | Correctly **gitignored and untracked** (`git check-ignore`=0, `ls-files`=0). Manifests tracked. No discrepancy. |
| Compiled native | `KJVA/ai/xmind/build/libxmind-core.dylib` (+ `.a`), `KJVA/ai/tts/build/libtts.dylib` | Built artifacts present on disk; source in `KJVA/ai/xmind/superc/xmind_core.sc`. |

**Classification: real-application** (full-stack, wired). Not a scaffold, not theater.

### Real project root
The repo root **is** the project. The app is `backend/` + `frontend/` + `data/`; `KJVA/` is the imported runtime/training substrate; `atlas/` is governance tooling.

---

## B. Spec ↔ Build register

| # | Spec claim (README / AGENTS) | Build reality (evidence) | Status |
|---|---|---|---|
| S1 | "Python FastAPI backend · React (Vite) frontend" | `backend/main.py` (FastAPI, 4 routers, lifespan), `frontend/` (Vite + React 18). | **BUILT** |
| S2 | "Verse browser — All 66 books, 36,822 verses — Live" | `data/verses.jsonl` = 36,822 records (verified); `routes/verse.py` → `/api/books|chapters|verses|verse`; `VerseBrowser.jsx` consumes them. | **BUILT** |
| S3 | `frontend/src/App.jsx`: tabs **Browse, Completion, Search, Q&A, Xref**; components `CompletionPanel.jsx`, `StubPanel.jsx`. | App has **2 tabs only — Browse, Study**. `CompletionPanel.jsx` / `StubPanel.jsx` **MISSING**. Components present: `VerseBrowser.jsx`, `StudyPanel.jsx`. | **STALE SPEC** |
| S4 | "`/api/search`, `/api/qa`, `/api/xref` return HTTP **501** (Phase 2-4 stubs). Do not remove stubs." | `routes/stubs.py` module docstring: "These were Phase 2-4 stubs (HTTP 501). They are **now LIVE**" — corpus-backed retrieval, no adapter. | **STALE SPEC** (build ahead of doc) |
| S5 | "29 tests cover … retrieval branches, validation, stub endpoints." | `backend/tests/` = **64 `def test_` functions** across 4 files (`test_corpus_features.py` 30, `test_routes.py` 16, `test_corpus.py` 13, `test_cognitive_runtime.py` 5). | **STALE (under-counted)** |
| S6 | AGENTS: "Training infrastructure lives in the separate **Tokenless Models** workspace — **do not mix training code into this repo.**" | `KJVA/training/` = **103 `.py`** physically in-repo, plus `KJVA/ai`, `KJVA/governance`, etc. `MIGRATION_FROM_KJVA.md` (2026-06-09) documents a **Creator-authorized whole-directory replacement** that carried the substrate in. | **CONTRADICTION — possibly intentional; confirm** (decision documented; README/AGENTS text not updated to match) |
| S7 | README/title: simple "retrieval-augmented completion" app; `main.py` title "KJVA Bible App". | `main.py` actual description: "KJV Bible + **KJVA Constitutional Cognitive Runtime (XMIND active backend)**"; lifespan boots `get_runtime().bootstrap()`; `/api/health` merges `runtime_health`. The build grew a cognitive runtime the README never mentions. | **UNDER-DOCUMENTED** |
| S8 | README "Features" table lists Search=Phase 2, Q&A=Phase 3, Xref=Phase 4 (future). | All three are LIVE today via `stubs.py` (retrieval) and folded into the unified `/api/study` scribe (`routes/study.py` + `scribe.py`, 391 LOC). | **STALE SPEC** |
| S9 | "AI verse completion — Live (Apple Silicon) … gracefully degrades to retrieval-only when weights absent." | Wiring present: `inference.py` binds `_xmind` C client; `kjva_runtime.py` drives generation. Engine needs `libxmind-core.dylib` (on disk) + `canonical.gguf` (on disk, gitignored). Degradation path coded. **Actual generation UNVERIFIED** (read-only; not executed). | **WIRED / runtime UNVERIFIED** |
| S10 | Model: "18M-param byte-level LM, **val_ppl=3.21**", "vocab=259, 8L×d384, 6 heads". | `model_config.json` shape claims echoed in `inference.py` defaults; **param count and perplexity are README assertions** not confirmable by read. | **DOCUMENTED, NOT VERIFIED** |
| S11 | `TRAINING_TREE_RECONCILIATION.md`: shows `git rm -r KJVA/ml-training` as a pending owner action; "`ml-training/` is git-tracked, 160 files". | `KJVA/ml-training/` **absent on disk** and **0 files tracked** — already removed. Doc still reads as if removal is pending. | **STALE DOC** (action completed) |
| S12 | README Quick Start: backend `--port 8001`; `main.py` docstring & `__main__` use **8000**; CORS allows `:5173` and `:8001`; Docker health on `:8000`. | Port references are inconsistent across README / `main.py` / `docker-compose.yml`. Functional but confusing. | **MINOR INCONSISTENCY** |

---

## C. Findings (reported, not fixed)

- **F-1 — PRESENT-BUT-NOT-WIRED (frontend ↔ backend).** Backend exposes `/api/complete`, `/api/search`, `/api/qa`, `/api/xref` as live routes, but the **UI consumes none of them**. `grep` of `frontend/src` shows only: `VerseBrowser.jsx` → `/api/books`, `/api/chapters/{book}`, `/api/verses/{book}/{ch}`; `StudyPanel.jsx` → `/api/books`, `/api/study`. The unified `/api/study` scribe orchestrator effectively **superseded** the per-feature endpoints in the UI. Those four endpoints are reachable by API client + covered by tests, but dead from the rendered app's perspective. *Possibly intentional* (kept for API/test surface); confirm.

- **F-2 — Stale frontend spec.** `README.md` and `AGENTS.md` describe a 5-tab UI (`Browse, Completion, Search, Q&A, Xref`) with `CompletionPanel.jsx` / `StubPanel.jsx`. Neither component exists; the app has **2 tabs (Browse, Study)**. Anyone trusting the docs will look for components that were removed/renamed.

- **F-3 — "Do not mix training code" vs in-repo substrate (S6).** The single most load-bearing doc/build contradiction. `KJVA/` carries the full training pipeline and cognitive substrate in-tree, while AGENTS.md forbids exactly that. `MIGRATION_FROM_KJVA.md` shows this was a **deliberate, Creator-authorized** whole-dir replacement (2026-06-09) — so the violation is in the **unupdated rule text**, not (necessarily) in intent. Reconcile: either soften the AGENTS rule or re-externalize training. *Possibly intentional — confirm.*

- **F-4 — Runtime is WIRED but its execution is UNVERIFIED.** `backend/kjva_runtime.py` genuinely imports + calls `KJVA.governance.*`, `KJVA.heptagon.*`, `KJVA.soul_manager.*` and the `_xmind` C client; `complete.py` and `main.py` call `get_runtime()`. This is real wiring, not dead code. But actual XMIND generation depends on `libxmind-core.dylib` (present) + `canonical.gguf` (present on disk, gitignored) + Apple-Silicon MLX; on a fresh checkout / Linux CI it **degrades to retrieval-only** (by design). Do not read "live cognitive runtime" as "generation proven" — it is **unverified** under read-only recon.

- **F-5 — Build is ahead of docs (good drift, still drift).** `/api/study` + `scribe.py` (the "Apex Scribe Orchestrator"), the now-live `/api/search|qa|xref`, and the whole cognitive-runtime layer post-date the README's "Phase 1 / retrieval-augmented completion" framing. The product is materially larger and more capable than its top-level docs claim. The richer, current narrative lives in the `KJVA/*.md` and `atlas/` records, not in `README.md`.

- **F-6 — Test count understated (S5).** Docs say 29 tests; there are **64** test functions. Harmless, but it signals the docs trail the suite.

- **F-7 — Completed cleanup still described as pending (S11).** `KJVA/ml-training/` (the redundant second training tree) is already gone (0 tracked, absent on disk) yet `TRAINING_TREE_RECONCILIATION.md` presents its removal as an outstanding owner action.

- **F-8 — Port drift (S12).** README says backend `:8001`; `main.py`/`__main__` say `:8000`; Docker health-checks `:8000`; CORS allows `:8001`. No single canonical port stated. Minor but a real onboarding trip-hazard.

- **F-9 — Unverifiable model claims (S10).** "18M params" and "val_ppl=3.21" are asserted in `README.md` / model cards and **cannot be confirmed by static read**. Treat as documented-not-verified. (The 36,822-verse corpus claim **was** verified.)

*Reconnaissance only — observations for the coding agent's checklist + your oversight, not changes.*

---

## D. Provenance

- **Mode:** read-only static reconnaissance. No build, test, server, script, gate, or package manager was executed. Nothing in the repo was modified.
- **Files written by this pass (only these two):** `docs/ARCHITECTURE MAP.html`, `docs/SPEC_VS_BUILD_DISCREPANCIES.md`.
- **Method:** `ls`/`find`/`wc`/`grep`/`sed -n`/`git ls-files`/`git check-ignore` over the working tree, plus targeted reads of `README.md`, `AGENTS.md`, `backend/*.py`, `backend/routes/*.py`, `frontend/src/**`, `KJVA/*.md`, `KJVA/governance/covenant_enforcer.py`, `.gitignore`, `.github/workflows/ci.yml`.
- **Vendored/bulk excluded from "real source":** `.git`, `.claude`, `.codex`, `atlas/`, `node_modules/`, `dist/`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, and gitignored model binaries (`*.gguf`/`*.safetensors`/`*.npz`).
- **Unverified by design (read-only):** XMIND generation success, model param count, val_ppl, and any claim requiring execution.
