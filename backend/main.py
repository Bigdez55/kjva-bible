"""
main.py — KJVA Bible App FastAPI backend.

Start dev server:
  cd backend && uvicorn main:app --reload --port 8000

In production, uvicorn serves the React build from ../frontend/dist/
via StaticFiles. During development, Vite dev server proxies /api to :8000.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from corpus import get_index
from routes.verse import router as verse_router
from routes.complete import router as complete_router
from routes.stubs import router as stubs_router

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load verse index once at startup (~36,822 records, < 1s)
    get_index().load()
    yield


app = FastAPI(
    title="KJVA Bible App",
    description="KJV Bible + KJVA AI model (18M params, byte-level, MLX)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(verse_router)
app.include_router(complete_router)
app.include_router(stubs_router)


@app.get("/api/health")
def health():
    from inference import get_engine
    return {
        "status": "ok",
        "model_ready": get_engine().is_ready(),
        "verse_index_loaded": get_index()._loaded,
    }


# Serve React build in production (only if dist/ exists)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
