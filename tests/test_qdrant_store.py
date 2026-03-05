"""Tests for the Qdrant store (text-based fallback)."""

import sys
import os

# Add ADK_Agentic/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ADK_Agentic"))

# Force fallback mode by not setting Qdrant env vars
os.environ.pop("QDRANT", None)
os.environ.pop("QDRANT_ENDPOINT", None)

from qdrant_store import QdrantStore


SAMPLE_RECORDS = [
    {"OrderNbr": "WO-001", "Customer_name": "Acme Corp", "Status": "Open"},
    {"OrderNbr": "WO-002", "Customer_name": "Beta Inc", "Status": "Closed"},
    {"OrderNbr": "WO-003", "Customer_name": "Acme Corp", "Status": "Pending"},
]


def test_fallback_mode_initializes():
    """Store falls back to text search when Qdrant is unavailable."""
    store = QdrantStore(collection_name="test_fallback")
    assert store._ready is False


def test_add_records():
    """Records are stored in memory."""
    store = QdrantStore(collection_name="test_add")
    store.add_records(SAMPLE_RECORDS)
    assert len(store.records) == 3


def test_text_search_finds_match():
    """Text fallback search finds matching records."""
    store = QdrantStore(collection_name="test_search")
    store.add_records(SAMPLE_RECORDS)

    results = store.search("Acme")
    assert len(results) == 2
    assert all(r["record"]["Customer_name"] == "Acme Corp" for r in results)


def test_text_search_case_insensitive():
    """Text search is case insensitive."""
    store = QdrantStore(collection_name="test_case")
    store.add_records(SAMPLE_RECORDS)

    results = store.search("acme")
    assert len(results) == 2


def test_text_search_respects_limit():
    """Search respects the limit parameter."""
    store = QdrantStore(collection_name="test_limit")
    store.add_records(SAMPLE_RECORDS)

    results = store.search("WO", limit=2)
    assert len(results) == 2


def test_text_search_no_match():
    """Search returns empty list when nothing matches."""
    store = QdrantStore(collection_name="test_nomatch")
    store.add_records(SAMPLE_RECORDS)

    results = store.search("NonexistentCompany")
    assert results == []


def test_search_empty_store():
    """Search on empty store returns empty list."""
    store = QdrantStore(collection_name="test_empty")
    results = store.search("anything")
    assert results == []


def test_clear():
    """Clear removes all records."""
    store = QdrantStore(collection_name="test_clear")
    store.add_records(SAMPLE_RECORDS)
    store.clear()
    assert len(store.records) == 0


def test_search_result_format():
    """Each result has 'score' and 'record' keys."""
    store = QdrantStore(collection_name="test_format")
    store.add_records(SAMPLE_RECORDS)

    results = store.search("Open")
    assert len(results) > 0
    for r in results:
        assert "score" in r
        assert "record" in r
        assert isinstance(r["score"], float)
        assert isinstance(r["record"], dict)
