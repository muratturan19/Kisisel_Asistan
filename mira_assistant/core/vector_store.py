"""Vector store abstraction with a Chroma-backed implementation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Sequence

from config import settings

LOGGER = logging.getLogger(__name__)


class VectorStore:
    """Thin wrapper providing an interchangeable interface."""

    def __init__(self, persist_directory: Path | None = None) -> None:
        self._persist_directory = Path(persist_directory or settings.vector_store_path)
        self._persist_directory.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._ensure_backend()

    def _ensure_backend(self) -> None:
        try:
            import chromadb  # type: ignore

            self._client = chromadb.PersistentClient(path=str(self._persist_directory))
            self._collection = self._client.get_or_create_collection("mira_documents")
        except Exception as exc:  # pragma: no cover - fallback path
            LOGGER.warning("chromadb unavailable (%s); using in-memory store", exc)
            self._client = None
            self._collection = _InMemoryCollection()

    def add_texts(self, texts: Sequence[str], metadatas: Sequence[dict], ids: Sequence[str]) -> None:
        if self._collection is None:
            raise RuntimeError("Vector store backend not initialised")
        self._collection.add(documents=list(texts), metadatas=list(metadatas), ids=list(ids))

    def query(self, text: str, n_results: int = 4) -> List[dict]:
        if self._collection is None:
            return []
        results = self._collection.query(query_texts=[text], n_results=n_results)
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]
        scores = results.get("distances", [[]])[0]
        return [
            {"text": doc, "metadata": meta, "score": score}
            for doc, meta, score in zip(documents, metadatas, scores)
        ]


class _InMemoryCollection:
    """Simple fallback implementation for tests."""

    def __init__(self) -> None:
        self._items: List[tuple[str, str, dict]] = []

    def add(self, documents: List[str], metadatas: List[dict], ids: List[str]) -> None:
        for doc, meta, doc_id in zip(documents, metadatas, ids):
            self._items.append((doc_id, doc, meta))

    def query(self, query_texts: List[str], n_results: int = 4) -> dict:
        documents: List[List[str]] = [[]]
        metadatas: List[List[dict]] = [[]]
        distances: List[List[float]] = [[]]
        for item in self._items[:n_results]:
            _, doc, meta = item
            documents[0].append(doc)
            metadatas[0].append(meta)
            distances[0].append(0.0)
        return {"documents": documents, "metadatas": metadatas, "distances": distances}


__all__ = ["VectorStore"]
