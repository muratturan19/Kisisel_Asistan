"""LLM powered intent extraction with graceful fallbacks."""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Optional

from openai import OpenAI
from openai import APIConnectionError, APIStatusError, RateLimitError

from config import settings


LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """Sen bir Türkçe asistan komut parser'ısın.\n""" \
    "Kullanıcının doğal dil komutunu analiz edip şu formatta JSON döndür:\n\n" \
    "{\n" \
    '  "intent": "add_event | add_task | add_note | list_events | list_tasks | schedule_reminder | ingest_docs | summarize_topic | advise_on_topic | update_event | update_task | delete_event | delete_task | complete_task | note",\n' \
    '  "payload": {...}\n' \
    "}\n\n" \
    "Intent tipleri:\n" \
    "- add_event: Toplantı, etkinlik, randevu ekle\n" \
    "- add_task: Yapılacak iş, görev ekle\n" \
    "- add_note: Not al\n" \
    "- list_events: Etkinlikleri listele\n" \
    "- list_tasks: Görevleri listele\n" \
    "- schedule_reminder: Hatırlatıcı kur\n" \
    "- ingest_docs: Dosya, belge, doküman yüklemelerini yönet\n" \
    "- summarize_topic: Belirli bir konu için özet hazırla\n" \
    "- advise_on_topic: Riskler ve uyarılar sağla\n" \
    "- update_event / update_task: İlgili kaydı güncelle\n" \
    "- delete_event / delete_task: Kaydı sil\n" \
    "- complete_task: Görevi tamamlandı olarak işaretle\n" \
    "- note: Diğer ifadeleri not olarak kaydet\n\n" \
    "Tarih/saat için ISO 8601 formatı kullan (Europe/Istanbul timezone).\n"

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise RuntimeError("OpenAI API anahtarı tanımlı değil")
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _system_prompt() -> str:
    today = dt.datetime.now(settings.timezone).strftime("%Y-%m-%d")
    return (
        SYSTEM_PROMPT
        + f"Bugün: {today}\n"
        + "Her zaman geçerli JSON döndür. Ek açıklama yazma."
    )


def handle_with_llm(text: str) -> Optional["Action"]:
    """Extract structured intent using the configured LLM."""

    if not text.strip():
        return None

    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": text},
    ]

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
    except (APIConnectionError, APIStatusError, RateLimitError) as err:
        LOGGER.debug("OpenAI temporary error: %s", err)
        raise

    content = response.choices[0].message.content if response.choices else None
    if not content:
        raise ValueError("LLM yanıtı boş döndü")

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as err:  # pragma: no cover - unexpected model drift
        LOGGER.debug("LLM JSON parse error: %s", err)
        raise ValueError("LLM yanıtı JSON değil") from err

    intent = str(payload.get("intent") or "").strip()
    data = payload.get("payload") or {}
    if not intent:
        raise ValueError("LLM intent değeri bulunamadı")
    if not isinstance(data, dict):
        raise ValueError("LLM payload alanı sözlük değil")

    from .intent import Action  # local import to avoid circular dependency

    return Action(intent=intent, payload=data)


__all__ = ["handle_with_llm"]
