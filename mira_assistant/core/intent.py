"""Rule-based intent detection producing Action JSON."""
from __future__ import annotations

import dataclasses
import json
import re
from typing import Dict, Optional

from .parser_tr import parse_datetime


@dataclasses.dataclass
class Action:
    intent: str
    payload: Dict[str, object]

    def to_json(self) -> str:
        return json.dumps({"intent": self.intent, "payload": self.payload}, ensure_ascii=False)


INTENT_KEYWORDS = {
    "add_event": ["toplant", "etkinlik", "randevu", "konser"],
    "add_task": ["yap", "hatırla", "iş", "not"],
    "list_tasks": ["işler", "task", "görev"],
    "summarize_topic": ["özet", "toparla"],
    "ingest_docs": ["arşivle", "yükle"],
}


EVENT_DEFAULT_HOUR = {
    "toplant": 10,
    "konser": 20,
}


def detect_intent(text: str) -> Optional[Action]:
    lowered = text.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            if intent == "add_event":
                return _build_event_action(text)
            if intent == "add_task":
                return Action(intent="add_task", payload={"title": text.strip()})
            if intent == "list_tasks":
                return Action(intent="list_tasks", payload={"scope": "today"})
            if intent == "summarize_topic":
                topic = _extract_topic(text)
                return Action(intent="summarize_topic", payload={"topic": topic, "scope": "recent"})
            if intent == "ingest_docs":
                topic = _extract_topic(text)
                return Action(intent="ingest_docs", payload={"topic": topic})
    return None


def _extract_topic(text: str) -> str:
    match = re.search(r"([A-ZÇĞİÖŞÜ][\wçğıöşü]+)", text)
    if match:
        return match.group(1)
    return text.strip()


def _build_event_action(text: str) -> Action:
    dt_value = parse_datetime(text)
    payload: Dict[str, object] = {
        "title": _infer_title(text),
    }
    if dt_value:
        payload["start"] = dt_value.isoformat()
        payload["timezone"] = dt_value.tzinfo.key if getattr(dt_value.tzinfo, "key", None) else "Europe/Istanbul"
    else:
        payload["inferred_time"] = True
    payload["remind_policy"] = {"minutes_before": [1440, 60, 10], "voice": True}
    return Action(intent="add_event", payload=payload)


def _infer_title(text: str) -> str:
    lowered = text.lower()
    for keyword in EVENT_DEFAULT_HOUR:
        if keyword in lowered:
            return " ".join(part.capitalize() for part in keyword.split())
    return text.title()


__all__ = ["Action", "detect_intent"]
