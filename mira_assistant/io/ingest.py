"""Document ingestion pipeline."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from config import settings
from ..core.storage import Chunk, Document, get_session
from ..core.vector_store import VectorStore
from ..core.summarizer import summarise_topic

LOGGER = logging.getLogger(__name__)


@dataclass
class IngestResult:
    document: Document
    chunk_texts: List[str]
    summary: str


class DocumentIngestor:
    """Handle moving files to the archive and updating metadata."""

    def __init__(self, vector_store: Optional[VectorStore] = None) -> None:
        self._vector_store = vector_store or VectorStore()

    def ingest(self, path: Path, topic: Optional[str] = None) -> IngestResult:
        path = path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        topic = topic or infer_topic_from_filename(path.name)
        archive_path = build_archive_path(path, topic)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archive_path)
        text = extract_text(archive_path)
        checksum = sha256_of_path(archive_path)
        chunk_texts: List[str] = []
        with get_session() as session:
            document = Document(
                path=str(archive_path),
                title=path.stem,
                topic=topic,
                checksum=checksum,
                text_chars=len(text),
                ingested_at=dt.datetime.utcnow(),
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            chunks = create_chunks(document, text, session)
            session.commit()
            chunk_texts = [chunk.text for chunk in chunks]
            document_snapshot = Document.model_validate(document, from_attributes=True)
        summary = summarise_topic(chunk_texts)
        self._vector_store.add_texts(
            texts=chunk_texts,
            metadatas=[{"doc_id": str(document_snapshot.id), "topic": document_snapshot.topic} for _ in chunk_texts],
            ids=[f"doc-{document_snapshot.id}-chunk-{idx}" for idx, _ in enumerate(chunk_texts)],
        )
        return IngestResult(document=document_snapshot, chunk_texts=chunk_texts, summary=summary)


def infer_topic_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    return stem.split("_")[0].capitalize()


def build_archive_path(source: Path, topic: str) -> Path:
    now = dt.datetime.now()
    archive_root = settings.data_dir / "archive" / "by_topic" / topic / now.strftime("%Y-%m")
    archive_root.mkdir(parents=True, exist_ok=True)
    return archive_root / source.name


def sha256_of_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text
        except Exception as exc:  # pragma: no cover - fallback path
            LOGGER.warning("PDF parsing failed for %s: %s", path, exc)
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def create_chunks(document: Document, text: str, session) -> List[Chunk]:
    words = text.split()
    chunk_size = 120
    chunks: List[Chunk] = []
    for idx in range(0, len(words), chunk_size):
        chunk_text = " ".join(words[idx : idx + chunk_size])
        chunk = Chunk(doc_id=document.id, seq=len(chunks), text=chunk_text, tokens=len(chunk_text.split()))
        session.add(chunk)
        session.flush()
        session.refresh(chunk)
        chunks.append(chunk)
    if not chunks:
        chunk = Chunk(doc_id=document.id, seq=0, text="", tokens=0)
        session.add(chunk)
        session.flush()
        session.refresh(chunk)
        chunks.append(chunk)
    return chunks


__all__ = [
    "DocumentIngestor",
    "IngestResult",
    "infer_topic_from_filename",
    "build_archive_path",
]
