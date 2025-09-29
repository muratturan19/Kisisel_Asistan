"""Offline-first summariser implementation."""
from __future__ import annotations

import textwrap
from typing import List, Sequence


def summarise_topic(chunks: Sequence[str]) -> str:
    """Produce a simple bullet-point summary.

    This placeholder implementation concatenates key sentences while leaving a
    TODO for future LLM integration.
    """
    summary_lines: List[str] = ["- " + line.strip() for line in chunks if line.strip()]
    summary = "\n".join(summary_lines[:8])
    if not summary:
        summary = "- TODO: Özet üretimi için içerik bulunamadı."
    summary += "\n\nTODO: Gelişmiş özetleme için LLM entegrasyonu eklenecek."
    return textwrap.dedent(summary).strip()


__all__ = ["summarise_topic"]
