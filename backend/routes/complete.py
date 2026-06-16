"""
/api/complete — corpus-locked scripture retrieval, with governed generation only
for genuine free-text.

Doctrine (owner-set): the CORPUS is the scripture database; the model is the scribe.
- A reference-shaped input is CORPUS-LOCKED: exact retrieved text, or ABSTAIN. It must
  NEVER fall through to raw generation just because the parser failed to resolve it.
- Exact / range / prefix retrieval invokes NO generation and NO covenant harm scoring.
- Only genuine free-text (not a reference, no exact corpus match) reaches the model, and
  that fallback remains governed (keyword-floor covenant; no fabricated scripture).
- Every response is a structured payload with a `status` so the UI never renders an error
  object as "[object Object]".
"""
import re
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from corpus import get_index
from kjva_runtime import KJVARuntimeError, get_runtime

router = APIRouter(prefix="/api", tags=["completion"])


class CompleteRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    max_new_tokens: int = Field(default=150, ge=1, le=512)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)


class CompleteResponse(BaseModel):
    # status: FOUND | NOT_FOUND | INVALID | AMBIGUOUS | GENERATED | BLOCKED
    status: str = "FOUND"
    prompt: str
    completion: str = ""
    model: str = "kjva-retrieval"
    retrieved: bool = False
    generation_invoked: bool = False
    references: list[str] = []
    verse_ref: Optional[str] = None
    reason: str = ""
    reason_code: str = ""
    cognitive_metadata: Optional[dict[str, Any]] = None


def _retrieval_response(prompt: str, results: list[dict]) -> CompleteResponse:
    if len(results) == 1:
        completion = results[0]["text"]
        verse_ref = results[0]["ref"]
    else:
        completion = "\n".join(f"{v['ref']}  {v['text']}" for v in results)
        verse_ref = f"{results[0]['ref']}-{results[-1]['ref'].split(':')[1]}"
    return CompleteResponse(
        status="FOUND",
        prompt=prompt,
        completion=completion,
        model="kjva-retrieval",
        retrieved=True,
        generation_invoked=False,
        references=[v["ref"] for v in results],
        verse_ref=verse_ref,
    )


@router.post("/complete", response_model=CompleteResponse)
async def complete(req: CompleteRequest):
    index = get_index()
    text = req.prompt.strip()

    # 1) Reference-shaped input -> CORPUS-LOCKED. FOUND returns exact text; any failure
    #    (INVALID / NOT_FOUND / AMBIGUOUS) ABSTAINS. Never generation. Never [object Object].
    parsed = index.parse_reference(text)
    if parsed["is_reference_attempt"]:
        if parsed["status"] == "FOUND":
            return _retrieval_response(req.prompt, parsed["results"])
        return CompleteResponse(
            status=parsed["status"],          # NOT_FOUND | INVALID | AMBIGUOUS
            prompt=req.prompt,
            completion="",
            model="corpus-locked",
            retrieved=False,
            generation_invoked=False,
            references=[],
            reason=parsed["reason"] or "Reference could not be resolved; abstaining (no generation).",
        )

    # 2) Not reference-shaped -> try exact prefix/keyword retrieval (still corpus-locked).
    prefix = index.search_prefix(text)
    if prefix:
        verse_text = prefix["text"]
        prompt_clean = text.rstrip(".,;:!? ")
        m = re.search(re.escape(prompt_clean), verse_text, re.IGNORECASE)
        completion = verse_text[m.end():].lstrip() if m else verse_text
        return CompleteResponse(
            status="FOUND",
            prompt=req.prompt,
            completion=completion,
            model="kjva-retrieval",
            retrieved=True,
            generation_invoked=False,
            references=[prefix["ref"]],
            verse_ref=prefix["ref"],
        )

    # 3) Genuine free-text -> GOVERNED generation (keyword-floor covenant; no fabricated
    #    scripture). The model is labelled ai-generated and is never presented as canon.
    try:
        result = await get_runtime().complete(
            text,
            max_new_tokens=req.max_new_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
    except KJVARuntimeError as exc:
        # Governed block/error -> structured payload (status + readable reason + the
        # governance reason_code), NOT a 4xx body the UI would render as "[object Object]".
        outcome = getattr(exc, "outcome", None)
        reason = getattr(outcome, "detail", "") or "Request was not permitted."
        return CompleteResponse(
            status="BLOCKED",
            prompt=req.prompt,
            completion="",
            model="kjva-xmind",
            retrieved=False,
            generation_invoked=False,
            reason=reason,
            reason_code=getattr(outcome, "reason_code", ""),
        )

    return CompleteResponse(
        status="GENERATED",
        prompt=req.prompt,
        completion=result.text,
        model="kjva-xmind",
        retrieved=False,
        generation_invoked=True,
        cognitive_metadata=result.metadata,
    )
