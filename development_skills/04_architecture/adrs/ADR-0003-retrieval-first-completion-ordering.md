# ADR 0003: Retrieval-first completion ordering

## Status

Accepted (new — formalizes the SLICE-0001 behavior and the bugfix that gates AI on retrieval miss)

## Context

The Phase 1 release introduces POST /api/complete as a user-facing endpoint. The naive implementation calls the 18M KJVA model directly on the user prompt. Two problems:

1. **Hallucinations on direct references.** Users typing "John 3:16" want the verse, not a model-generated paraphrase. A small byte-level LM produces inconsistent text on reference-style prompts.
2. **AI weights are gitignored, 72 MB, and platform-coupled (MLX requires Apple Silicon).** If the endpoint hard-requires weights, the entire completion surface dies in CI, in linux/amd64 containers, and any time weights are missing — even for prompts that retrieval could answer perfectly.

The pre-SLICE-0001 code in `backend/routes/complete.py` raised HTTP 503 immediately if `engine.is_ready()` returned false, blocking retrieval from ever running.

## Decision

Order completion resolution as:

1. **Direct verse reference** (`lookup_ref_range`) — e.g. "John 3:16", "Numbers 15:37-41", "Prov 31". Returns `retrieved=true`, `model="kjva-retrieval"`, full verse text.
2. **Verse text prefix / keyword match** (`search_prefix`) — four-tier matcher (prefix, substring, keyword-set, single-distinctive-word). Returns the verse tail with `retrieved=true`.
3. **RAG-augmented AI fallback** — when retrieval misses but prose candidates exist, build a training-format corpus context block (`build_corpus_context`) and feed it to the model. Returns `retrieved=false`, `model="kjva-18m"`.
4. **Raw AI completion** — last resort for prompts that match nothing.

The `engine.is_ready()` check moves **below** branches 1 and 2 and only gates branches 3 and 4. When weights are absent, branches 1 and 2 still succeed; branches 3 and 4 return a structured 503.

## Options considered

1. **Retrieval-first (chosen)** — Order above. Maximum availability, deterministic on references.
2. **AI-first, retrieval as post-process** — Always call AI, then check if output matches a known verse. Wastes compute, dies without weights, doesn't help references.
3. **Retrieval-only** — Strip the AI fallback entirely. Loses generative capability for paraphrased / open-ended prompts.
4. **Client-side router** — Let the frontend decide which mode to call. Pushes logic into JS and couples two clients to the resolution strategy.

## Why this decision wins

Retrieval-first gives correct, instant, deterministic answers to the most common user query shape (verse lookup) and degrades gracefully to AI only when retrieval has nothing useful. Most importantly, it decouples the AI weight artifact from the core endpoint contract: deployments without weights still serve verse lookups, which is the dominant use case.

## Tradeoffs

- **Benefit:** Endpoint works in CI, in containers, without weights.
- **Benefit:** Deterministic, testable retrieval branches (covered by pytest).
- **Benefit:** AI compute only spent when it adds value.
- **Cost:** Retrieval logic has its own correctness surface (book name resolution, range parsing, prefix matching) that must be tested.
- **Cost:** Response shape now carries `retrieved` and `verse_ref` fields the original API did not have. Backward-compatible (additive) for existing clients.
- **Reversibility:** High. The check can be moved back to the top of the function if the team decides the endpoint should hard-require AI.

## Affected components

- `backend/routes/complete.py` — branch ordering + `engine.is_ready()` position
- `backend/corpus.py` — `lookup_ref`, `lookup_ref_range`, `search_prefix`, `build_corpus_context`
- `frontend/src/components/CompletionPanel.jsx` — surface `retrieved` + `verse_ref` in UI
- `backend/tests/test_routes.py` — covers retrieval branches without weights

## Rollback path

Restore the pre-SLICE-0001 ordering (move `engine.is_ready()` back above retrieval) and remove the retrieval branches. Endpoint reverts to AI-only behavior with no API breakage as long as the response model retains the new optional fields (or removes them in lockstep).
