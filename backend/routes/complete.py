from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
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


@router.post("/complete", response_model=CompleteResponse)
def complete(req: CompleteRequest):
    engine = get_engine()
    if not engine.is_ready():
        raise HTTPException(
            503,
            detail={
                "error": "KJVA weights not installed",
                "fix": "Weights are gitignored (72 MB). Place weights.safetensors at KJVA/training/weights.safetensors",
            },
        )
    completion = engine.complete(
        req.prompt,
        max_new_tokens=req.max_new_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
    )
    return CompleteResponse(prompt=req.prompt, completion=completion)
