"""
Stub endpoints for AI features that require adapters not yet trained.

Each returns HTTP 501 with a clear message describing what's needed.
These stubs ensure the frontend can render placeholders without crashing.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["stubs"])


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class QARequest(BaseModel):
    question: str
    context_ref: str = ""


class XRefRequest(BaseModel):
    ref: str


def _not_implemented(feature: str, requires: str):
    return JSONResponse(
        status_code=501,
        content={
            "feature": feature,
            "status": "not_implemented",
            "requires": requires,
            "message": f"{feature} is planned for a future release. It requires {requires}.",
        },
    )


@router.post("/search")
def semantic_search(req: SearchRequest):
    return _not_implemented(
        "Semantic Search",
        "a sentence-embedding adapter trained on KJVA (Phase 2)",
    )


@router.post("/qa")
def question_answer(req: QARequest):
    return _not_implemented(
        "Q&A / Commentary",
        "an SFT instruction-tuning adapter trained on KJVA (Phase 3)",
    )


@router.post("/xref")
def cross_reference(req: XRefRequest):
    return _not_implemented(
        "Cross-Reference Surfacing",
        "an embedding similarity index or precomputed reference graph (Phase 4)",
    )
