"""
Corpus-grounded retrieval features: Search, Cross-Reference, Q&A.

These were Phase 2-4 stubs (HTTP 501). They are now LIVE, backed entirely by the
in-memory corpus index — no trained adapter required. Every result is exact retrieved
scripture (KJV + Apocrypha); nothing here is generated. Each endpoint returns a
structured payload with a `status` field so the UI never renders an error object.

Doctrine: the corpus is the scripture database. The retriever supplies scripture.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from corpus import get_index

router = APIRouter(prefix="/api", tags=["features"])


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=100)
    book: str = ""          # optional book name/abbrev filter (e.g. "Psalms", "1 Cor")
    canon: str = ""         # optional canon filter: ot | nt | apocrypha


class QARequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    context_ref: str = ""
    limit: int = Field(default=3, ge=1, le=10)


class XRefRequest(BaseModel):
    ref: str = Field(..., min_length=1, max_length=120)
    limit: int = Field(default=12, ge=1, le=50)


@router.post("/search")
def search(req: SearchRequest):
    """Corpus keyword/phrase search. Case-insensitive; ranks exact phrase > all terms >
    partial; optional book + canon filters; Apocrypha included. Real verses only."""
    return get_index().search(req.query, book=req.book, canon=req.canon, limit=req.limit)


@router.post("/xref")
def cross_reference(req: XRefRequest):
    """Deterministic lexical/topical cross-reference for a verse: distinctive terms ->
    other verses sharing rare terms. Real references only; shared terms given as reason.
    NOT a theological cross-reference — labelled lexical/topical."""
    return get_index().cross_reference(req.ref, limit=req.limit)


def _format_qa(result: dict) -> str:
    """Render the standard grounded Q&A format. Synthesis is deterministic and derived
    ONLY from retrieved verses — no uncited claims, no fabricated references."""
    if result["status"] != "FOUND":
        return result["reason"]
    witnesses = result["witnesses"]
    lines = ["Answer:"]
    lines.append(
        f"The KJV + Apocrypha corpus answers this through "
        f"{len(witnesses)} scripture witness{'es' if len(witnesses) != 1 else ''} "
        f"(retrieved, not generated)."
    )
    lines.append("")
    lines.append("Scripture witnesses:")
    for i, w in enumerate(witnesses, 1):
        lines.append(f"{i}. {w['reference']} — {w['text']}")
    lines.append("")
    lines.append("Explanation:")
    shared = result.get("shared_terms") or []
    if shared:
        lines.append(
            "These witnesses share the term(s): "
            + ", ".join(shared[:6])
            + ". The synthesis above rests only on the retrieved verses; no claim is made "
            "beyond what they state."
        )
    else:
        lines.append(
            "The synthesis rests only on the retrieved verses above; no claim is made "
            "beyond what they state."
        )
    return "\n".join(lines)


@router.post("/qa")
def question_answer(req: QARequest):
    """Retrieval-grounded Q&A. Verses first, explanation second; abstains with a clear
    message when no grounded verse match exists. No fabricated references."""
    result = get_index().qa(req.question, context_ref=req.context_ref, limit=req.limit)
    result["formatted"] = _format_qa(result)
    result["generation_invoked"] = False
    return result
