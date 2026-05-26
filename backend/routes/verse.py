from fastapi import APIRouter, HTTPException
from corpus import get_index

router = APIRouter(prefix="/api", tags=["verse"])


@router.get("/books")
def list_books():
    return get_index().books()


@router.get("/chapters/{book}")
def list_chapters(book: str):
    chapters = get_index().chapters(book)
    if not chapters:
        raise HTTPException(404, f"Book '{book}' not found")
    return {"book": book.upper(), "chapters": chapters}


@router.get("/verses/{book}/{chapter}")
def list_verses(book: str, chapter: int):
    verses = get_index().verses_in_chapter(book, chapter)
    if not verses:
        raise HTTPException(404, f"{book} chapter {chapter} not found")
    return {"book": book.upper(), "chapter": chapter, "verses": verses}


@router.get("/verse/{book}/{chapter}/{verse}")
def get_verse(book: str, chapter: int, verse: int):
    v = get_index().get_verse(book, chapter, verse)
    if not v:
        raise HTTPException(404, f"{book} {chapter}:{verse} not found")
    return v
