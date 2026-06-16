"""
/api/study — THE unified scribe function (the KJVA Apex Scribe Orchestrator).

One query in; the engine infers intent (reference / quote / topic / question / word study)
and answers as a scripture-grounded scribe: exact verse, ranked witnesses, related-term
expansion, witnesses grouped across the canon, automatic cross-references, and a
deterministic exegetical breakdown. Every verse and reference is real (retrieved from the
corpus, never generated). A reference that does not resolve ABSTAINS.

The 18M model is not invoked here yet — per the execution spec, the retrieval / graph /
planner layer is built and tested first; scribe-behaviour training comes after.
"""
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from scribe import get_scribe

router = APIRouter(prefix="/api", tags=["study"])


class StudyRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    book: str = ""           # optional book filter (dropdown value -> code)
    canon: str = ""          # optional: ot | nt | apocrypha
    scope: str = ""          # follow-up narrowing: torah | nt | apocrypha | full


class StudyResponse(BaseModel):
    intent: str
    status: str              # FOUND | NOT_FOUND | INVALID | AMBIGUOUS
    query: str
    answer: str = ""
    primary: list[dict[str, Any]] = []
    related_terms: list[str] = []
    witnesses_by_section: list[dict[str, Any]] = []
    cross_references: list[dict[str, Any]] = []
    exegesis: Optional[dict[str, Any]] = None
    qa: Optional[dict[str, Any]] = None
    follow_up: list[dict[str, Any]] = []
    reason: str = ""
    scope: str = "full"


@router.post("/study", response_model=StudyResponse)
async def study(req: StudyRequest):
    result = get_scribe().answer(
        req.query, book=req.book, canon=req.canon, scope=req.scope,
    )
    return StudyResponse(**result)
