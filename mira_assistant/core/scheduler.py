"""Reminder scheduling built around APScheduler."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Callable, Dict, Iterable, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from config import settings
from .storage import Event

LOGGER = logging.getLogger(__name__)


class ReminderScheduler:
    """Manage reminder jobs and surface notifications."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone=settings.timezone)
        self._callbacks: List[Callable[[Dict[str, Any], int], None]] = []
        self._started = False

    def start(self) -> None:
        if not self._started:
            LOGGER.debug("Starting reminder scheduler")
            self._scheduler.start()
            self._started = True

    def shutdown(self) -> None:
        if self._started:
            LOGGER.debug("Shutting down reminder scheduler")
            self._scheduler.shutdown(wait=False)
            self._started = False

    def add_callback(self, callback: Callable[[Dict[str, Any], int], None]) -> None:
        self._callbacks.append(callback)

    def schedule_event_reminders(
        self,
        event: Event,
        reminder_policy: Optional[Iterable[int] | Dict[str, Any]] = None,
    ) -> List[str]:
        """Schedule reminder jobs for a specific event."""

        if event.start_dt is None:
            LOGGER.warning("Event %s missing start date", event.id)
            return []

        self.start()
        start_dt = event.start_dt
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=dt.timezone.utc)
        start_local = start_dt.astimezone(settings.timezone)
        policy_minutes: Iterable[int]
        if isinstance(reminder_policy, dict):
            policy_minutes = reminder_policy.get("minutes_before", settings.default_reminders)
        elif reminder_policy is None:
            policy_minutes = settings.default_reminders
        else:
            policy_minutes = reminder_policy

        job_ids: List[str] = []
        now_local = dt.datetime.now(tz=settings.timezone)
        minutes_list = [int(value) for value in policy_minutes]
        for minutes in minutes_list:
            remind_at = start_local - dt.timedelta(minutes=minutes)
            if remind_at <= now_local:
                continue
            job_id = f"event-{event.id}-reminder-{minutes}"
            trigger = DateTrigger(run_date=remind_at)
            if hasattr(event, "model_dump"):
                payload = event.model_dump(mode="json")  # type: ignore[attr-defined]
            else:
                payload = event.dict()
            payload["start_dt"] = start_dt.isoformat()
            payload["remind_policy"] = event.remind_policy or {"minutes_before": minutes_list}
            self._scheduler.add_job(
                self._emit,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                kwargs={"event_payload": payload, "minutes": int(minutes)},
            )
            job_ids.append(job_id)
            LOGGER.debug("Scheduled reminder %s at %s", job_id, remind_at.isoformat())
        return job_ids

    def restore_jobs_from_db(self, events: Iterable[Event]) -> int:
        """Recreate reminder jobs for events loaded from the database."""

        restored = 0
        for event in events:
            policy = event.remind_policy or {"minutes_before": settings.default_reminders}
            job_ids = self.schedule_event_reminders(event, policy)
            restored += len(job_ids)
        LOGGER.info("Restored %s reminder jobs", restored)
        return restored

    def list_jobs(self) -> List[str]:
        return [job.id for job in self._scheduler.get_jobs()]

    def _emit(self, event_payload: Dict[str, Any], minutes: int) -> None:
        message = f"{event_payload.get('title', 'Etkinlik')} {minutes} dk sonra başlıyor"
        LOGGER.info("Reminder fired for event %s (%s dk)", event_payload.get("id"), minutes)
        for callback in self._callbacks:
            callback(event_payload, minutes)
        try:
            from mira_assistant.ui.notifications import show_toast
        except Exception as exc:  # pragma: no cover - UI optional
            LOGGER.debug("Notification module unavailable: %s", exc)
        else:
            show_toast(event_payload.get("title", "Hatırlatma"), message, speak=True)


__all__ = ["ReminderScheduler"]
