"""
test_routes.py — Tests for backend/routes/*.py via FastAPI TestClient.

Covers:
  - /api/books, /api/chapters/{book}, /api/verses/{book}/{chapter},
    /api/verse/{book}/{chapter}/{verse}
  - /api/complete retrieval branches WITHOUT requiring AI weights
    (per ADR-0003 retrieval-first ordering)
  - /api/health basic smoke
"""
import pytest
from fastapi.testclient import TestClient

# Trigger import via conftest path setup
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        # TestClient context manager runs lifespan → loads corpus
        yield c


# --- TEST-routes-verse-surface ---

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["verse_index_loaded"] is True


def test_books(client):
    r = client.get("/api/books")
    assert r.status_code == 200
    books = r.json()
    assert isinstance(books, list)
    assert len(books) >= 66  # at least full Protestant canon
    # GEN must be present and ordered first
    codes = [b["code"] for b in books]
    assert "GEN" in codes
    assert "JHN" in codes


def test_chapters(client):
    r = client.get("/api/chapters/GEN")
    assert r.status_code == 200
    body = r.json()
    assert body["book"] == "GEN"
    assert body["chapters"][0] == 1
    assert len(body["chapters"]) == 50  # Genesis has 50 chapters


def test_chapters_404(client):
    r = client.get("/api/chapters/NOPE")
    assert r.status_code == 404


def test_verses_in_chapter(client):
    r = client.get("/api/verses/GEN/1")
    assert r.status_code == 200
    body = r.json()
    assert body["chapter"] == 1
    assert len(body["verses"]) == 31  # Genesis 1 has 31 verses


def test_get_single_verse(client):
    r = client.get("/api/verse/JHN/3/16")
    assert r.status_code == 200
    body = r.json()
    assert body["book"] == "JHN"
    assert body["chapter"] == 3
    assert body["verse"] == 16
    assert "God so loved" in body["text"]


def test_get_single_verse_404(client):
    r = client.get("/api/verse/JHN/99/99")
    assert r.status_code == 404


# --- TEST-routes-complete-retrieval-no-weights ---

def test_complete_direct_ref_no_weights(client):
    """Per ADR-0003: retrieval works even without weights."""
    r = client.post("/api/complete", json={"prompt": "John 3:16"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["retrieved"] is True
    assert body["model"] == "kjva-retrieval"
    assert body["verse_ref"] == "JHN 3:16"
    assert "God so loved" in body["completion"]


def test_complete_range_ref_no_weights(client):
    r = client.post("/api/complete", json={"prompt": "Numbers 15:37-41"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["retrieved"] is True
    assert body["model"] == "kjva-retrieval"
    # 5 verses joined with newlines
    assert body["completion"].count("\n") == 4
    assert body["verse_ref"].startswith("NUM 15:37")


def test_complete_prefix_match_no_weights(client):
    r = client.post("/api/complete", json={"prompt": "In the beginning God"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["retrieved"] is True
    assert body["verse_ref"] == "GEN 1:1"


def test_complete_validation_max_length(client):
    r = client.post("/api/complete", json={"prompt": "x" * 3000})
    assert r.status_code == 422


def test_complete_validation_empty(client):
    r = client.post("/api/complete", json={"prompt": ""})
    assert r.status_code == 422


def test_complete_fallback_without_weights_returns_503(client):
    """When retrieval misses AND weights absent, structured 503."""
    from inference import get_engine

    if get_engine().is_ready():
        pytest.skip("Weights present — AI fallback would succeed; cannot test 503 path")
    r = client.post(
        "/api/complete",
        json={"prompt": "What is the philosophical implication of quantum entanglement"},
    )
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "error" in detail
    assert "fix" in detail


# --- Stub endpoints still 501 ---

def test_search_stub(client):
    r = client.post("/api/search", json={"query": "love"})
    assert r.status_code == 501


def test_qa_stub(client):
    r = client.post("/api/qa", json={"question": "Who was Moses?"})
    assert r.status_code == 501


def test_xref_stub(client):
    r = client.post("/api/xref", json={"ref": "John 3:16"})
    assert r.status_code == 501
