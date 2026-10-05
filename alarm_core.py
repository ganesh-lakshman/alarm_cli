"""Core alarm engine: models, scheduling, persistence."""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


class AlarmStatus(str, Enum):
    ACTIVE = "active"
    RINGING = "ringing"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class AlarmType(str, Enum):
    ONCE = "once"
    DAILY = "daily"
    WEEKDAYS = "weekdays"


@dataclass
class Alarm:
    """Represents a single alarm."""
    id: str
    trigger_time: float  # Unix timestamp when the alarm should fire
    label: str = ""
    alarm_type: AlarmType = AlarmType.ONCE
    status: AlarmStatus = AlarmStatus.ACTIVE
    original_time_str: str = ""  # Human-readable time the user set
    snooze_count: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["alarm_type"] = self.alarm_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Alarm:
        d["alarm_type"] = AlarmType(d.get("alarm_type", "once"))
        d["status"] = AlarmStatus(d.get("status", "active"))
        return cls(**d)

    @property
    def trigger_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.trigger_time)

    @property
    def time_display(self) -> str:
        return self.trigger_datetime.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def time_remaining(self) -> timedelta:
        return self.trigger_datetime - datetime.now()

    def to_table_row(self) -> dict:
        return {
            "id": self.id,
            "time_display": self.time_display,
            "label": self.label,
            "type": self.alarm_type.value,
            "status": self.status.value,
        }


# ── Time Parsing ──────────────────────────────────────────────────────────────

def parse_duration(text: str) -> Optional[timedelta]:
    """Parse relative durations like '5m', '1h30m', '2h', '90s', '1h 30m 15s'.

    Returns None if the text doesn't match a duration pattern.
    """
    text = text.strip().lower()

    pattern = r"^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?\s*(?:(\d+)\s*s(?:ec)?)?$"
    match = re.match(pattern, text)
    if not match:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    if hours == 0 and minutes == 0 and seconds == 0:
        return None

    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def parse_time(text: str) -> Optional[datetime]:
    """Parse absolute time strings like '07:30', '14:00', '7:30pm', '2:00 PM'.

    If the time has already passed today, it's assumed to be tomorrow.
    """
    text = text.strip().lower().replace(" ", "")
    now = datetime.now()
    target = None

    # Try 12-hour format: 7:30pm, 7:30am, 730pm
    match_12 = re.match(r"^(\d{1,2}):?(\d{2})\s*(am|pm)$", text)
    if match_12:
        hour = int(match_12.group(1))
        minute = int(match_12.group(2))
        period = match_12.group(3)
        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Try 24-hour format: 07:30, 14:00, 7:30
    if target is None:
        match_24 = re.match(r"^(\d{1,2}):(\d{2})$", text)
        if match_24:
            hour = int(match_24.group(1))
            minute = int(match_24.group(2))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if target is None:
        return None

    # If this time has already passed today, schedule for tomorrow
    if target <= now:
        target += timedelta(days=1)

    return target


def parse_alarm_time(text: str) -> tuple[datetime, str]:
    """Parse user input into a target datetime and a human-readable description.

    Supports both relative ('in 5m') and absolute ('07:30') formats.
    Raises ValueError if the input can't be parsed.
    """
    clean = text.strip()

    # Strip leading "in " for duration input
    duration_text = re.sub(r"^in\s+", "", clean, flags=re.IGNORECASE)
    delta = parse_duration(duration_text)
    if delta is not None:
        target = datetime.now() + delta
        desc = f"in {duration_text} ({target.strftime('%H:%M:%S')})"
        return target, desc

    # Strip leading "at " for absolute time input
    time_text = re.sub(r"^at\s+", "", clean, flags=re.IGNORECASE)
    target = parse_time(time_text)
    if target is not None:
        day_label = "today" if target.date() == datetime.now().date() else "tomorrow"
        desc = f"{target.strftime('%H:%M')} {day_label}"
        return target, desc

    raise ValueError(
        f"Cannot parse '{text}'. Examples: '5m', '1h30m', '07:30', '2:30pm', 'in 10s'"
    )


# ── Persistence ───────────────────────────────────────────────────────────────

def _storage_path() -> Path:
    """Return the path to the alarms JSON file."""
    config_dir = Path.home() / ".alarmcli"
    config_dir.mkdir(exist_ok=True)
    return config_dir / "alarms.json"


def save_alarms(alarms: list[Alarm]) -> None:
    """Persist alarms to disk as JSON."""
    data = [a.to_dict() for a in alarms]
    path = _storage_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_alarms() -> list[Alarm]:
    """Load alarms from disk. Returns empty list if file doesn't exist."""
    path = _storage_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        alarms = [Alarm.from_dict(d) for d in data]
        # Filter out dismissed non-recurring alarms from previous sessions
        return [
            a for a in alarms
            if a.status in (AlarmStatus.ACTIVE, AlarmStatus.SNOOZED, AlarmStatus.RINGING)
        ]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


# ── Scheduler ─────────────────────────────────────────────────────────────────

class AlarmScheduler:
    """Background scheduler that checks and fires alarms.

    Runs a daemon thread that polls every 0.5 seconds. When an alarm's
    trigger time arrives, it calls the on_alarm callback.
    """

    def __init__(self, on_alarm: Callable[[Alarm], None]) -> None:
        self._alarms: list[Alarm] = []
        self._lock = threading.Lock()
        self._on_alarm = on_alarm
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def alarms(self) -> list[Alarm]:
        with self._lock:
            return list(self._alarms)

    def add_alarm(self, alarm: Alarm) -> None:
        with self._lock:
            self._alarms.append(alarm)
            save_alarms(self._alarms)

    def remove_alarm(self, alarm_id: str) -> bool:
        """Remove an alarm by ID (prefix match). Returns True if found."""
        with self._lock:
            matches = [a for a in self._alarms if a.id.startswith(alarm_id)]
            if not matches:
                return False
            for m in matches:
                self._alarms.remove(m)
            save_alarms(self._alarms)
            return True

    def dismiss_alarm(self, alarm_id: str) -> bool:
        """Dismiss a ringing alarm."""
        with self._lock:
            for a in self._alarms:
                if a.id.startswith(alarm_id) and a.status == AlarmStatus.RINGING:
                    if a.alarm_type == AlarmType.ONCE:
                        a.status = AlarmStatus.DISMISSED
                        self._alarms = [
                            x for x in self._alarms
                            if x.status != AlarmStatus.DISMISSED
                        ]
                    elif a.alarm_type == AlarmType.DAILY:
                        a.trigger_time += 86400  # +24h
                        a.status = AlarmStatus.ACTIVE
                    elif a.alarm_type == AlarmType.WEEKDAYS:
                        self._advance_to_next_weekday(a)
                        a.status = AlarmStatus.ACTIVE
                    save_alarms(self._alarms)
                    return True
            return False

    def snooze_alarm(self, alarm_id: str, minutes: int = 5) -> Optional[Alarm]:
        """Snooze a ringing alarm for the given number of minutes."""
        with self._lock:
            for a in self._alarms:
                if a.id.startswith(alarm_id) and a.status == AlarmStatus.RINGING:
                    a.trigger_time = time.time() + minutes * 60
                    a.status = AlarmStatus.ACTIVE
                    a.snooze_count += 1
                    save_alarms(self._alarms)
                    return a
            return None

    def get_ringing(self) -> list[Alarm]:
        """Return all currently ringing alarms."""
        with self._lock:
            return [a for a in self._alarms if a.status == AlarmStatus.RINGING]

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._running:
            return
        # Load persisted alarms
        persisted = load_alarms()
        with self._lock:
            for p in persisted:
                if not any(a.id == p.id for a in self._alarms):
                    self._alarms.append(p)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while self._running:
            self._check_alarms()
            time.sleep(0.5)

    def _check_alarms(self) -> None:
        now = time.time()
        with self._lock:
            for alarm in self._alarms:
                if alarm.status == AlarmStatus.ACTIVE and alarm.trigger_time <= now:
                    alarm.status = AlarmStatus.RINGING
                    save_alarms(self._alarms)
                    # Fire callback outside lock? No — keep it simple,
                    # callback should be fast (just print + start sound thread)
                    threading.Thread(
                        target=self._on_alarm, args=(alarm,), daemon=True
                    ).start()

    @staticmethod
    def _advance_to_next_weekday(alarm: Alarm) -> None:
        """Advance trigger time to the next weekday (Mon-Fri)."""
        dt = datetime.fromtimestamp(alarm.trigger_time)
        dt += timedelta(days=1)
        while dt.weekday() >= 5:  # 5=Saturday, 6=Sunday
            dt += timedelta(days=1)
        alarm.trigger_time = dt.timestamp()
