"""Chroma based vector store helper."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from config import settings

LOGGER = logging.getLogger(__name__)


class VectorStore:
    """Thin wrapper around ``chromadb`` persistent collections."""

    def __init__(self, persist_directory: Path | None = None, collection: str = "mira_documents") -> None:
        self._persist_directory = Path(persist_directory or settings.chroma_path).expanduser()
        self._persist_directory.mkdir(parents=True, exist_ok=True)
        self._collection_name = collection
        self._collection = self._initialise_collection()

    def _initialise_collection(self):  # type: ignore[return-any]
        try:
            import chromadb  # type: ignore

            client = chromadb.PersistentClient(path=str(self._persist_directory))
            return client.get_or_create_collection(self._collection_name)
        except Exception as exc:  # pragma: no cover - fallback path
            LOGGER.warning("chromadb unavailable, falling back to in-memory store (%s)", exc)
            return _InMemoryCollection()

    def add_embeddings(self, embeddings: Sequence[Sequence[float]], *, metadatas: Sequence[Dict[str, str]], ids: Sequence[str], documents: Sequence[str]) -> None:
        self._collection.add(embeddings=list(embeddings), metadatas=list(metadatas), ids=list(ids), documents=list(documents))

    def similar(self, query_texts: Iterable[str], n_results: int = 4) -> List[Dict[str, object]]:
        results = self._collection.query(query_texts=list(query_texts), n_results=n_results)
        documents = results.get("documents", [[]])
        metadatas = results.get("metadatas", [[]])
        distances = results.get("distances", [[]])
        payload: List[Dict[str, object]] = []
        for docs, metas, scores in zip(documents, metadatas, distances):
            for doc, meta, score in zip(docs, metas, scores):
                payload.append({"text": doc, "metadata": meta, "score": score})
        return payload


class _InMemoryCollection:
    def __init__(self) -> None:
        self._items: List[Dict[str, object]] = []

    def add(self, embeddings=None, metadatas=None, ids=None, documents=None) -> None:  # type: ignore[no-untyped-def]
        documents = documents or []
        metadatas = metadatas or []
        ids = ids or []
        for doc, meta, doc_id in zip(documents, metadatas, ids):
            self._items.append({"id": doc_id, "text": doc, "metadata": meta})

    def query(self, query_texts=None, n_results: int = 4):  # type: ignore[no-untyped-def]
        del query_texts
        documents = [[item["text"] for item in self._items[:n_results]]]
        metadatas = [[item.get("metadata", {}) for item in self._items[:n_results]]]
        distances = [[0.0 for _ in self._items[:n_results]]]
        return {"documents": documents, "metadatas": metadatas, "distances": distances}


__all__ = ["VectorStore"]
