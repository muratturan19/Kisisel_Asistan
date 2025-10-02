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

SYSTEM_PROMPT = """Sen bir Türkçe kişisel asistan komut parser'ısın.\n""" \
    "Kullanıcının doğal dil komutunu analiz edip JSON formatında intent ve payload döndürüyorsun.\n\n" \
    "**ÇOK ÖNEMLİ: Intent Seçim Kuralları**\n\n" \
    "1. **add_task**: Kullanıcı gelecekte KENDİSİNİN yapması gereken bir iş belirtiyorsa\n" \
    "   - \"rapor hazırla\", \"çiçek gönder\", \"market alışverişi yap\"\n" \
    "   - \"...yapmalıyım\", \"...yapmam lazım\", \"...göndermeliyim\"\n" \
    "   - Kullanıcının TODO listesine eklenecek işler\n\n" \
    "2. **add_event**: Katılacağı bir etkinlik/toplantı/randevu\n" \
    "   - \"toplantı var\", \"konsere gideceğim\", \"doktora gideceğim\"\n" \
    "   - \"ile görüşeceğim\", \"...da buluşma\"\n\n" \
    "3. **list_tasks**: Yapılacakları göster\n" \
    "   - \"yapılacaklar\", \"görevlerim\", \"ne yapmam lazım\"\n\n" \
    "4. **list_events**: Etkinlikleri göster\n" \
    "   - \"takvim\", \"bu hafta ne var\", \"yaklaşan toplantılar\"\n\n" \
    "5. **summarize_topic**: SADECE kullanıcı mevcut belgelerin özetini İSTERSE\n" \
    "   - \"X konusunu özetle\", \"Y hakkında özet çıkar\"\n" \
    "   - NOT: \"özet rapor HAZIRLA\" bu değil! Bu add_task'tır!\n\n" \
    "6. **note**: Tarih/yapılacak olmayan serbest notlar\n" \
    "   - \"not: ...\", \"kaydet: ...\"\n\n" \
    "**Payload Formatları:**\n\n" \
    "add_task:\n" \
    "{\n" \
    "  \"intent\": \"add_task\",\n" \
    "  \"payload\": {\n" \
    "    \"title\": \"Rapor hazırla\",\n" \
    "    \"due\": \"2025-10-03T17:00:00+03:00\"\n" \
    "  }\n" \
    "}\n\n" \
    "add_event:\n" \
    "{\n" \
    "  \"intent\": \"add_event\",\n" \
    "  \"payload\": {\n" \
    "    \"title\": \"Müşteri toplantısı\",\n" \
    "    \"start\": \"2025-10-03T14:00:00+03:00\",\n" \
    "    \"location\": \"Online\"\n" \
    "  }\n" \
    "}\n\n" \
    "note:\n" \
    "{\n" \
    "  \"intent\": \"note\",\n" \
    "  \"payload\": {\n" \
    "    \"text\": \"Not içeriği\",\n" \
    "    \"title\": \"Başlık (opsiyonel)\"\n" \
    "  }\n" \
    "}\n\n" \
    "**Tarih/Saat Kuralları:**\n" \
    "- Bugün: {today}\n" \
    "- Saat dilimi: Europe/Istanbul (UTC+3)\n" \
    "- \"bu akşam\" → bugün 18:00\n" \
    "- \"yarın\" → yarın 09:00 (task) veya belirtilen saat (event)\n" \
    "- Tarih belirtilmezse: bugün/yarın tahmin et\n\n" \
    "**Örnekler:**\n\n" \
    "Kullanıcı: \"özet rapor hazırla\"\n" \
    "{\n" \
    "  \"intent\": \"add_task\",\n" \
    "  \"payload\": {\n" \
    "    \"title\": \"Özet rapor hazırla\",\n" \
    "    \"due\": \"{today}T17:00:00+03:00\"\n" \
    "  }\n" \
    "}\n\n" \
    "Kullanıcı: \"bu akşam eşime çiçek göndermem lazım\"\n" \
    "{\n" \
    "  \"intent\": \"add_task\",\n" \
    "  \"payload\": {\n" \
    "    \"title\": \"Eşime çiçek gönder\",\n" \
    "    \"due\": \"{today}T18:00:00+03:00\"\n" \
    "  }\n" \
    "}\n\n" \
    "Kullanıcı: \"yarın saat 14 te müşteri görüşmesi\"\n" \
    "{\n" \
    "  \"intent\": \"add_event\",\n" \
    "  \"payload\": {\n" \
    "    \"title\": \"Müşteri görüşmesi\",\n" \
    "    \"start\": \"{tomorrow}T14:00:00+03:00\"\n" \
    "  }\n" \
    "}\n\n" \
    "Kullanıcı: \"satış raporlarını özetle\" (mevcut belgeler için)\n" \
    "{\n" \
    "  \"intent\": \"summarize_topic\",\n" \
    "  \"payload\": {\n" \
    "    \"topic\": \"satış raporları\"\n" \
    "  }\n" \
    "}\n\n" \
    "Sadece JSON döndür, başka açıklama ekleme.\n"

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
