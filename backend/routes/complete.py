import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from corpus import get_index
from inference import get_engine

router = APIRouter(prefix="/api", tags=["completion"])


class CompleteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    max_new_tokens: int = Field(default=150, ge=1, le=512)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)


class CompleteResponse(BaseModel):
    prompt: str
    completion: str
    model: str = "kjva-18m"
    retrieved: bool = False
    verse_ref: Optional[str] = None


@router.post("/complete", response_model=CompleteResponse)
def complete(req: CompleteRequest):
    # Retrieval branches do NOT require AI weights. Per ADR-0003, we resolve
    # ref/prefix matches first so the endpoint stays useful in deployments
    # without weights (CI, linux/amd64 containers, retrieval-only mode).
    index = get_index()

    # --- Option A: retrieval-first ---
    # Try range/single reference first (e.g. "Numbers 15:37-41", "John 3:16", "Prov 31")
    ref_matches = index.lookup_ref_range(req.prompt.strip())
    if ref_matches:
        if len(ref_matches) == 1:
            completion = ref_matches[0]["text"]
            verse_ref = ref_matches[0]["ref"]
        else:
            # Multi-verse range — label each line with its ref
            completion = "\n".join(
                f"{v['ref']}  {v['text']}" for v in ref_matches
            )
            first, last = ref_matches[0]["ref"], ref_matches[-1]["ref"]
            # "NUM 15:37 – NUM 15:41" → "NUM 15:37-41"
            verse_ref = f"{first}-{last.split(':')[1]}"
        return CompleteResponse(
            prompt=req.prompt,
            completion=completion,
            model="kjva-retrieval",
            retrieved=True,
            verse_ref=verse_ref,
        )

    text_match = index.search_prefix(req.prompt)
    if text_match:
        # Prompt is the opening of a known verse — return the rest of it.
        verse_text = text_match["text"]
        prompt_clean = req.prompt.strip().rstrip(".,;:!? ")
        m = re.search(re.escape(prompt_clean), verse_text, re.IGNORECASE)
        completion = verse_text[m.end():].lstrip() if m else verse_text
        return CompleteResponse(
            prompt=req.prompt,
            completion=completion,
            model="kjva-retrieval",
            retrieved=True,
            verse_ref=text_match["ref"],
        )

    # --- Option B: corpus-format RAG augmentation + AI fallback ---
    # AI path requires weights. Gate here, AFTER retrieval has had its chance.
    engine = get_engine()
    if not engine.is_ready():
        raise HTTPException(
            503,
            detail={
                "error": "KJVA weights not installed and prompt did not match retrieval",
                "fix": "Weights are gitignored (72 MB). Place weights.safetensors at KJVA/training/weights.safetensors, or rephrase the prompt as a direct verse reference.",
            },
        )

    # Only use search_text for meaningful prose phrases, not reference-style queries
    # (short alphanumeric tokens like "prov 31" produce irrelevant substring matches).
    augmented = req.prompt
    looks_like_ref = bool(re.match(r"^[a-zA-Z0-9 ]+\s+\d+", req.prompt.strip()))
    if not looks_like_ref:
        candidates = index.search_text(req.prompt, limit=3)
        if candidates:
            augmented = index.build_corpus_context(candidates[0], req.prompt)

    completion = engine.complete(
        augmented,
        max_new_tokens=req.max_new_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    return CompleteResponse(
        prompt=req.prompt,
        completion=completion,
        model="kjva-18m",
        retrieved=False,
    )
