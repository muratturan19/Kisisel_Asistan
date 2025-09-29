"""APScheduler integration for reminder jobs."""
from __future__ import annotations

import datetime as dt
import logging
from typing import Callable, Dict, Iterable, List, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger

from config import settings
from .storage import Event

LOGGER = logging.getLogger(__name__)


class ReminderScheduler:
    """Schedules reminder jobs for events."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone=settings.timezone)
        self._callbacks: List[Callable[[Event, int], None]] = []
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    def add_callback(self, callback: Callable[[Event, int], None]) -> None:
        self._callbacks.append(callback)

    def schedule_event_reminders(
        self,
        event: Event,
        reminder_minutes: Optional[Iterable[int]] = None,
    ) -> List[str]:
        """Schedule reminder jobs for the given event.

        Returns a list of job IDs for verification in tests.
        """
        if event.start_dt is None:
            LOGGER.warning("Event %s has no start time; skipping reminders", event.id)
            return []

        reminder_minutes = list(reminder_minutes or settings.reminder_minutes)
        job_ids: List[str] = []
        for minutes in reminder_minutes:
            remind_at = event.start_dt - dt.timedelta(minutes=minutes)
            if remind_at < dt.datetime.now(tz=event.start_dt.tzinfo):
                continue
            job_id = f"event-{event.id}-reminder-{minutes}"
            trigger = DateTrigger(run_date=remind_at)
            self._scheduler.add_job(
                self._emit,
                trigger=trigger,
                id=job_id,
                replace_existing=True,
                kwargs={"event": event, "minutes": minutes},
            )
            job_ids.append(job_id)
        return job_ids

    def _emit(self, event: Event, minutes: int) -> None:
        LOGGER.info("Reminder for event %s %s minutes before", event.id, minutes)
        for callback in self._callbacks:
            callback(event, minutes)


__all__ = ["ReminderScheduler"]
