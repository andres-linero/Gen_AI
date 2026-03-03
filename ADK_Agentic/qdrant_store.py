"""
Qdrant Vector Store for Work Order Search
Uses sentence-transformers for embeddings + Qdrant Cloud for vector search.
Falls back to simple text matching if Qdrant is unavailable.
"""

import os
import logging
from typing import List, Dict

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
)
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Embedding model — runs locally, no API key needed, small and fast
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class QdrantStore:
    """Vector search using Qdrant Cloud + sentence-transformers embeddings."""

    def __init__(self, collection_name: str = "work_orders"):
        self.collection_name = collection_name
        self.records: List[Dict] = []
        self._client = None
        self._embedder = None
        self._ready = False

        try:
            self._init_client()
            self._init_embedder()
            self._ready = True
            print(f"✓ Qdrant vector store ready (collection: {collection_name})")
        except Exception as e:
            logger.warning(f"Qdrant init failed ({type(e).__name__}): {e}")
            logger.warning("Falling back to text-based search.")
            self._ready = False

    def _init_client(self):
        """Connect to Qdrant Cloud."""
        url = os.getenv("QDRANT_ENDPOINT")
        api_key = os.getenv("QDRANT")

        if not url or not api_key:
            raise ValueError("QDRANT_ENDPOINT and QDRANT env vars required")

        self._client = QdrantClient(url=url, api_key=api_key)

        # Create collection if it doesn't exist
        collections = [c.name for c in self._client.get_collections().collections]
        if self.collection_name not in collections:
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM, distance=Distance.COSINE
                ),
            )
            print(f"✓ Created Qdrant collection: {self.collection_name}")

    def _init_embedder(self):
        """Load the sentence-transformers embedding model."""
        hf_token = os.getenv("HUGGINGFACE_TOKEN")
        self._embedder = SentenceTransformer(EMBEDDING_MODEL, token=hf_token)

    def _record_to_text(self, record: Dict) -> str:
        """Convert a record dict to a searchable text string."""
        parts = []
        for key, value in record.items():
            if value is not None and str(value).strip():
                parts.append(f"{key}: {value}")
        return " | ".join(parts)

    def add_records(self, records: List[Dict]):
        """Embed and upsert records into Qdrant."""
        self.records = records

        if not self._ready:
            print(f"✓ Added {len(records)} records to store (text-based fallback)")
            return

        texts = [self._record_to_text(r) for r in records]
        embeddings = self._embedder.encode(texts, show_progress_bar=False)

        points = [
            PointStruct(
                id=i,
                vector=embedding.tolist(),
                payload={"record": record, "text": text},
            )
            for i, (record, text, embedding) in enumerate(
                zip(records, texts, embeddings)
            )
        ]

        # Upsert in batches of 100
        batch_size = 100
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            self._client.upsert(
                collection_name=self.collection_name, points=batch
            )

        print(f"✓ Embedded and uploaded {len(records)} records to Qdrant")

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Semantic search using vector similarity."""
        if not self.records:
            return []

        # If Qdrant isn't available, fall back to text matching
        if not self._ready:
            return self._text_search(query, limit)

        try:
            query_vector = self._embedder.encode(query).tolist()
            results = self._client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
            )

            return [
                {"score": round(hit.score, 3), "record": hit.payload["record"]}
                for hit in results.points
            ]
        except Exception as e:
            logger.warning(f"Qdrant search failed: {e}. Using text fallback.")
            return self._text_search(query, limit)

    def _text_search(self, query: str, limit: int = 5) -> List[Dict]:
        """Fallback: simple substring text search."""
        matches = []
        query_lower = query.lower()

        for record in self.records:
            record_str = str(record).lower()
            if query_lower in record_str:
                matches.append({"score": 1.0, "record": record})

        return matches[:limit]

    def clear(self):
        """Clear records from memory and Qdrant collection."""
        self.records = []
        if self._ready:
            try:
                self._client.delete_collection(self.collection_name)
                self._init_client()  # Recreate empty collection
            except Exception as e:
                logger.warning(f"Failed to clear Qdrant collection: {e}")
        print("✓ Cleared store")


def get_qdrant_store(collection_name: str = "work_orders") -> QdrantStore:
    """Get store instance."""
    return QdrantStore(collection_name=collection_name)
