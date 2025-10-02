"""Hybrid intent detection mixing LLM parsing with rule based fallbacks."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import re
from typing import Any, Dict, Iterable, Optional

from .parser_tr import parse_datetime, to_utc
from config import settings


LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(slots=True)
class Action:
    """Container describing an intent and the structured payload."""

    intent: str
    payload: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"intent": self.intent, "payload": self.payload}, ensure_ascii=False)


ActionJSON = Dict[str, Any]

_EVENT_KEYWORDS = {
    "toplant": 10,
    "görüş": 10,
    "konferans": 10,
    "etkinlik": 20,
    "konser": 20,
    "sunum": 10,
}
_TASK_KEYWORDS = ["yap", "görev", "task", "hatırla", "tamamla"]
_LIST_EVENTS_KEYWORDS = ["ajanda", "takvim", "etkinlikler", "bugün"]
_LIST_TASKS_KEYWORDS = ["görevleri", "yapılacak", "todo", "liste"]
_SUMMARY_KEYWORDS = ["özet", "toparla"]
_INGEST_NOUN_HINTS = {"belge", "belgeleri", "dosya", "dosyaları", "dokuman", "doküman"}
_INGEST_VERB_HINTS = {"yükle", "ekle", "aktar", "arşivle"}
_ADVISE_KEYWORDS = ["öner", "uyarı", "kontrol"]
_REMINDER_KEYWORDS = ["hatırlat", "alarm"]
_UPDATE_KEYWORDS = ["güncelle", "değiştir"]
_DELETE_KEYWORDS = ["sil", "iptal"]
_COMPLETE_KEYWORDS = ["tamamla", "bitir", "kapattım"]

_ADD_HINTS = {"ekle", "oluştur", "kaydet"}

_TITLE_FALLBACK = "Mira Notu"


def handle(text: str) -> Optional[Action]:
    """Return an :class:`Action` inferred from the natural language command."""

    stripped = text.strip()
    if not stripped:
        return None

    if settings.use_llm_intent and settings.openai_api_key:
        try:
            from .llm_intent import handle_with_llm

            llm_action = handle_with_llm(stripped)
            if llm_action is not None:
                return llm_action
        except Exception as exc:  # pragma: no cover - graceful degradation
            LOGGER.warning("LLM intent failed, falling back to rules: %s", exc, exc_info=True)

    return handle_with_rules(stripped)


def handle_with_rules(text: str) -> Optional[Action]:
    """Fallback rule based intent detection."""

    lowered = text.lower().strip()
    if not lowered:
        return None

    for keyword, hour in _EVENT_KEYWORDS.items():
        if keyword in lowered:
            return _build_event_action(text, default_hour=hour)

    if any(keyword in lowered for keyword in _REMINDER_KEYWORDS):
        return _build_reminder_action(text)

    if any(keyword in lowered for keyword in _LIST_EVENTS_KEYWORDS):
        return Action(intent="list_events", payload={"range": "today"})

    if _looks_like_ingest_command(lowered):
        topic = _extract_topic(text)
        return Action(intent="ingest_docs", payload={"topic": topic})

    if any(keyword in lowered for keyword in _SUMMARY_KEYWORDS):
        topic = _extract_topic(text)
        return Action(intent="summarize_topic", payload={"topic": topic})

    if any(keyword in lowered for keyword in _ADVISE_KEYWORDS):
        topic = _extract_topic(text)
        return Action(intent="advise_on_topic", payload={"topic": topic})

    if any(keyword in lowered for keyword in _LIST_TASKS_KEYWORDS):
        return Action(intent="list_tasks", payload={"scope": "today"})

    if _looks_like_add_command(lowered):
        parsed_dt = parse_datetime(text, default_hour=18)
        if parsed_dt is not None:
            return _build_event_action(text, default_hour=18, parsed=parsed_dt)
        return _build_task_action(text)

    if any(keyword in lowered for keyword in _UPDATE_KEYWORDS):
        entity_id = _extract_number(lowered)
        if "etkin" in lowered or "toplant" in lowered:
            return Action(intent="update_event", payload={"event_id": entity_id or 0, "text": text})
        return Action(intent="update_task", payload={"task_id": entity_id or 0, "text": text})

    if any(keyword in lowered for keyword in _DELETE_KEYWORDS):
        entity_id = _extract_number(lowered)
        if "etkin" in lowered or "toplant" in lowered:
            return Action(intent="delete_event", payload={"event_id": entity_id or 0})
        return Action(intent="delete_task", payload={"task_id": entity_id or 0})

    if any(keyword in lowered for keyword in _COMPLETE_KEYWORDS):
        entity_id = _extract_number(lowered)
        return Action(intent="complete_task", payload={"task_id": entity_id or 0})

    if any(keyword in lowered for keyword in _TASK_KEYWORDS):
        return _build_task_action(text)

    return Action(intent="note", payload={"text": text})


def _build_event_action(text: str, default_hour: int, *, parsed: Optional[dt.datetime] = None) -> Action:
    title = _infer_title(text) or _TITLE_FALLBACK
    local_dt = parsed if parsed is not None else parse_datetime(text, default_hour=default_hour)
    payload: Dict[str, Any] = {"title": title}
    if local_dt is not None:
        payload["start"] = to_utc(local_dt).isoformat()
        payload["timezone"] = settings.timezone_name
    payload["remind_policy"] = {"minutes_before": settings.default_reminders, "voice": True}
    return Action(intent="add_event", payload=payload)


def _build_task_action(text: str) -> Action:
    due_local = parse_datetime(text, default_hour=17)
    payload: Dict[str, Any] = {"title": text.strip() or _TITLE_FALLBACK}
    if due_local is not None:
        payload["due"] = to_utc(due_local).isoformat()
    return Action(intent="add_task", payload=payload)


def _build_reminder_action(text: str) -> Action:
    target_dt = parse_datetime(text, default_hour=9)
    payload: Dict[str, Any] = {"message": text.strip()}
    if target_dt is not None:
        payload["remind_at"] = to_utc(target_dt).isoformat()
    return Action(intent="schedule_reminder", payload=payload)


def _extract_topic(text: str) -> str:
    match = re.search(r"([A-ZÇĞİÖŞÜ][\wçğıöşü]+)", text)
    if match:
        return match.group(1)
    words = text.split()
    return " ".join(words[-2:]) if len(words) >= 2 else text


def _extract_number(text: str) -> Optional[int]:
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def _infer_title(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return _TITLE_FALLBACK
    words = stripped.split()
    return " ".join(word.capitalize() for word in words[:6])


def _looks_like_ingest_command(text: str) -> bool:
    return _contains_any(text, _INGEST_NOUN_HINTS) and _contains_any(text, _INGEST_VERB_HINTS)


def _looks_like_add_command(text: str) -> bool:
    return _contains_any(text, _ADD_HINTS)


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def detect_intent(text: str) -> Optional[Action]:
    """Backward compatible alias for :func:`handle`."""

    return handle(text)


__all__ = ["Action", "ActionJSON", "handle", "handle_with_rules", "detect_intent"]
