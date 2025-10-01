"""Offline summarisation helpers following the product template."""
from __future__ import annotations

import itertools
import textwrap
from typing import Iterable, List, Sequence


def generate_summary(topic: str, chunks: Sequence[str], meeting_notes: Sequence[str] | None = None) -> str:
    """Build a structured markdown summary for the requested topic."""

    bullet_points = _collect_sentences(chunks, limit=8)
    meeting_highlights = _collect_sentences(meeting_notes or [], limit=3)
    overview = _format_bullets(bullet_points, fallback="İlgili içerik bulunamadı.")
    summary_body = textwrap.dedent(
        f"""
        # {topic} Özeti

        ## Özet
        { overview }

        ## Kararlar
        { _format_bullets(meeting_highlights, fallback="Paylaşılan karar yok.") }

        ## Aksiyonlar (Sahip/Tarih)
        { _format_bullets(_infer_actions(bullet_points), fallback="Aksiyon ataması bulunamadı.") }

        ## Riskler & Bağımlılıklar
        { _format_bullets(_infer_risks(bullet_points), fallback="Belirgin risk yok.") }

        ## Açık Sorular
        { _format_bullets([], fallback="Takip gerektiren soru yok.") }
        """
    ).strip()
    summary = "\n\n".join([overview, summary_body]).strip()
    return "\n".join(line.rstrip() for line in summary.splitlines())


def summarise_topic(chunks: Sequence[str], topic: str = "Genel", meeting_notes: Sequence[str] | None = None) -> str:
    """Backward compatible wrapper returning a summary for a topic."""

    return generate_summary(topic, chunks, meeting_notes)


def _collect_sentences(texts: Iterable[str], *, limit: int) -> List[str]:
    sentences: List[str] = []
    for text in texts:
        for sentence in itertools.chain.from_iterable(part.strip().split(". ") for part in text.split("\n")):
            clean = sentence.strip().strip("-•")
            if clean:
                sentences.append(clean)
            if len(sentences) >= limit:
                return sentences[:limit]
    return sentences[:limit]


def _format_bullets(lines: Sequence[str], *, fallback: str) -> str:
    if not lines:
        return f"- {fallback}"
    return "\n".join(f"- {line}" for line in lines)


def _infer_actions(sentences: Sequence[str]) -> List[str]:
    actions: List[str] = []
    for sentence in sentences:
        if any(keyword in sentence.lower() for keyword in ["yap", "hazırla", "gönder", "tamamla"]):
            actions.append(sentence)
    return actions


def _infer_risks(sentences: Sequence[str]) -> List[str]:
    risks: List[str] = []
    for sentence in sentences:
        if any(keyword in sentence.lower() for keyword in ["risk", "bekleniyor", "gecik", "kritik"]):
            risks.append(sentence)
    return risks


__all__ = ["generate_summary", "summarise_topic"]
