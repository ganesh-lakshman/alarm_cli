"""Tests for the alarm clock application."""

import time
import threading
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alarm_core import (
    Alarm,
    AlarmScheduler,
    AlarmStatus,
    AlarmType,
    parse_alarm_time,
    parse_datetime,
    parse_duration,
    parse_time,
)


class TestParseDuration(unittest.TestCase):
    """Test relative time parsing (e.g. '5m', '1h30m', '90s')."""

    def test_minutes_only(self):
        result = parse_duration("5m")
        self.assertEqual(result, timedelta(minutes=5))

    def test_hours_only(self):
        result = parse_duration("2h")
        self.assertEqual(result, timedelta(hours=2))

    def test_seconds_only(self):
        result = parse_duration("30s")
        self.assertEqual(result, timedelta(seconds=30))

    def test_hours_and_minutes(self):
        result = parse_duration("1h30m")
        self.assertEqual(result, timedelta(hours=1, minutes=30))

    def test_full_hms(self):
        result = parse_duration("1h30m15s")
        self.assertEqual(result, timedelta(hours=1, minutes=30, seconds=15))

    def test_with_spaces(self):
        result = parse_duration("1h 30m")
        self.assertEqual(result, timedelta(hours=1, minutes=30))

    def test_zero_returns_none(self):
        result = parse_duration("0m")
        self.assertIsNone(result)

    def test_invalid_returns_none(self):
        result = parse_duration("hello")
        self.assertIsNone(result)

    def test_empty_returns_none(self):
        result = parse_duration("")
        self.assertIsNone(result)


class TestParseTime(unittest.TestCase):
    """Test absolute time parsing (e.g. '07:30', '2:30pm')."""

    def test_24_hour_format(self):
        result = parse_time("14:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 0)

    def test_12_hour_am(self):
        result = parse_time("7:30am")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 7)
        self.assertEqual(result.minute, 30)

    def test_12_hour_pm(self):
        result = parse_time("2:30pm")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_12pm_is_noon(self):
        result = parse_time("12:00pm")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 12)

    def test_12am_is_midnight(self):
        result = parse_time("12:00am")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 0)

    def test_invalid_returns_none(self):
        self.assertIsNone(parse_time("not a time"))
        self.assertIsNone(parse_time("25:00"))

    def test_past_time_wraps_to_tomorrow(self):
        # Use a time that has definitely passed — midnight
        result = parse_time("00:01")
        self.assertIsNotNone(result)
        now = datetime.now()
        if now.hour > 0 or (now.hour == 0 and now.minute >= 1):
            self.assertEqual(result.date(), (now + timedelta(days=1)).date())


class TestParseDatetime(unittest.TestCase):
    """Test full date-time parsing (e.g. '2026-10-10 07:30', 'Oct 10 7:30am')."""

    def test_iso_format_24h(self):
        result = parse_datetime("2026-12-25 14:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 0)

    def test_iso_format_12h(self):
        result = parse_datetime("2026-12-25 2:30pm")
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_iso_date_only(self):
        result = parse_datetime("2026-12-25")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)
        self.assertEqual(result.hour, 0)
        self.assertEqual(result.minute, 0)

    def test_month_name_day_time(self):
        result = parse_datetime("Oct 10 7:30am")
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 10)
        self.assertEqual(result.day, 10)
        self.assertEqual(result.hour, 7)
        self.assertEqual(result.minute, 30)

    def test_full_month_name(self):
        result = parse_datetime("December 25 14:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)

    def test_day_month_name_time(self):
        result = parse_datetime("10 Oct 7:30pm")
        self.assertIsNotNone(result)
        self.assertEqual(result.month, 10)
        self.assertEqual(result.day, 10)
        self.assertEqual(result.hour, 19)
        self.assertEqual(result.minute, 30)

    def test_tomorrow_time(self):
        result = parse_datetime("tomorrow 9:00")
        self.assertIsNotNone(result)
        expected = datetime.now() + timedelta(days=1)
        self.assertEqual(result.date(), expected.date())
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 0)

    def test_today_time(self):
        result = parse_datetime("today 23:59")
        self.assertIsNotNone(result)
        self.assertEqual(result.date(), datetime.now().date())
        self.assertEqual(result.hour, 23)

    def test_weekday_name(self):
        result = parse_datetime("friday 14:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.weekday(), 4)  # Friday
        self.assertEqual(result.hour, 14)
        self.assertGreater(result, datetime.now())

    def test_abbreviated_weekday(self):
        result = parse_datetime("mon 8:00am")
        self.assertIsNotNone(result)
        self.assertEqual(result.weekday(), 0)  # Monday
        self.assertEqual(result.hour, 8)

    def test_slash_format(self):
        result = parse_datetime("25/12/2026 14:00")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 12)
        self.assertEqual(result.day, 25)

    def test_invalid_date_returns_none(self):
        self.assertIsNone(parse_datetime("not a date"))
        self.assertIsNone(parse_datetime(""))

    def test_invalid_iso_date_returns_none(self):
        self.assertIsNone(parse_datetime("2026-13-40 14:00"))

    def test_month_day_wraps_to_next_year(self):
        now = datetime.now()
        past_month = now.month - 1 if now.month > 1 else 12
        result = parse_datetime(f"Jan 1 10:00")
        self.assertIsNotNone(result)
        if result:
            self.assertGreaterEqual(result, now.replace(hour=0, minute=0, second=0, microsecond=0))


class TestParseAlarmTime(unittest.TestCase):
    """Test the combined parse_alarm_time function."""

    def test_relative_with_in_prefix(self):
        target, desc = parse_alarm_time("in 5m")
        self.assertAlmostEqual(
            target.timestamp(),
            (datetime.now() + timedelta(minutes=5)).timestamp(),
            delta=2,
        )
        self.assertIn("5m", desc)

    def test_relative_without_prefix(self):
        target, desc = parse_alarm_time("10s")
        self.assertAlmostEqual(
            target.timestamp(),
            (datetime.now() + timedelta(seconds=10)).timestamp(),
            delta=2,
        )

    def test_absolute_with_at_prefix(self):
        target, desc = parse_alarm_time("at 14:00")
        self.assertEqual(target.hour, 14)
        self.assertEqual(target.minute, 0)

    def test_datetime_with_on_prefix(self):
        target, desc = parse_alarm_time("on 2026-12-25 14:00")
        self.assertEqual(target.year, 2026)
        self.assertEqual(target.month, 12)
        self.assertEqual(target.day, 25)
        self.assertIn("2026-12-25", desc)

    def test_datetime_tomorrow(self):
        target, desc = parse_alarm_time("tomorrow 9:00")
        expected = datetime.now() + timedelta(days=1)
        self.assertEqual(target.date(), expected.date())
        self.assertIn("tomorrow", desc)

    def test_datetime_weekday(self):
        target, desc = parse_alarm_time("friday 14:00")
        self.assertEqual(target.weekday(), 4)
        self.assertIn("Friday", desc)

    def test_past_datetime_raises_valueerror(self):
        with self.assertRaises(ValueError) as ctx:
            parse_alarm_time("2020-01-01 10:00")
        self.assertIn("past", str(ctx.exception).lower())

    def test_invalid_raises_valueerror(self):
        with self.assertRaises(ValueError):
            parse_alarm_time("not a valid time")


class TestAlarmModel(unittest.TestCase):
    """Test the Alarm dataclass."""

    def _make_alarm(self, **kwargs) -> Alarm:
        defaults = {
            "id": "test-123",
            "trigger_time": time.time() + 60,
            "label": "Test alarm",
        }
        defaults.update(kwargs)
        return Alarm(**defaults)

    def test_to_dict_and_back(self):
        alarm = self._make_alarm()
        d = alarm.to_dict()
        restored = Alarm.from_dict(d)
        self.assertEqual(alarm.id, restored.id)
        self.assertEqual(alarm.trigger_time, restored.trigger_time)
        self.assertEqual(alarm.label, restored.label)
        self.assertEqual(alarm.alarm_type, restored.alarm_type)

    def test_time_display(self):
        alarm = self._make_alarm()
        display = alarm.time_display
        self.assertIsInstance(display, str)
        self.assertIn("-", display)  # date format
        self.assertIn(":", display)  # time format

    def test_time_remaining(self):
        alarm = self._make_alarm(trigger_time=time.time() + 120)
        remaining = alarm.time_remaining
        self.assertGreater(remaining.total_seconds(), 100)
        self.assertLess(remaining.total_seconds(), 130)


class TestAlarmScheduler(unittest.TestCase):
    """Test the AlarmScheduler."""

    def setUp(self):
        self.fired_alarms: list[Alarm] = []
        self.fire_event = threading.Event()

        def on_alarm(alarm: Alarm):
            self.fired_alarms.append(alarm)
            self.fire_event.set()

        self.scheduler = AlarmScheduler(on_alarm=on_alarm)

    def tearDown(self):
        self.scheduler.stop()

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_add_and_list(self, mock_load, mock_save):
        self.scheduler.start()
        alarm = Alarm(
            id="test-add",
            trigger_time=time.time() + 3600,
            label="Future alarm",
        )
        self.scheduler.add_alarm(alarm)
        alarms = self.scheduler.alarms
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].id, "test-add")

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_remove_alarm(self, mock_load, mock_save):
        self.scheduler.start()
        alarm = Alarm(id="test-rm", trigger_time=time.time() + 3600)
        self.scheduler.add_alarm(alarm)
        self.assertTrue(self.scheduler.remove_alarm("test-rm"))
        self.assertEqual(len(self.scheduler.alarms), 0)

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_remove_nonexistent(self, mock_load, mock_save):
        self.scheduler.start()
        self.assertFalse(self.scheduler.remove_alarm("nope"))

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_alarm_fires(self, mock_load, mock_save):
        """An alarm set to trigger immediately should fire within 2 seconds."""
        self.scheduler.start()
        alarm = Alarm(
            id="test-fire",
            trigger_time=time.time() - 1,  # Already past
            label="Fire now",
        )
        self.scheduler.add_alarm(alarm)

        fired = self.fire_event.wait(timeout=3)
        self.assertTrue(fired, "Alarm should have fired")
        self.assertEqual(len(self.fired_alarms), 1)
        self.assertEqual(self.fired_alarms[0].id, "test-fire")

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_snooze(self, mock_load, mock_save):
        self.scheduler.start()
        alarm = Alarm(
            id="test-snooze",
            trigger_time=time.time() - 1,
            status=AlarmStatus.RINGING,
        )
        self.scheduler.add_alarm(alarm)

        result = self.scheduler.snooze_alarm("test-snooze", minutes=10)
        self.assertIsNotNone(result)
        self.assertEqual(result.status, AlarmStatus.ACTIVE)
        self.assertEqual(result.snooze_count, 1)
        self.assertGreater(result.trigger_time, time.time())

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_dismiss_once(self, mock_load, mock_save):
        self.scheduler.start()
        alarm = Alarm(
            id="test-dismiss",
            trigger_time=time.time() - 1,
            status=AlarmStatus.RINGING,
            alarm_type=AlarmType.ONCE,
        )
        self.scheduler.add_alarm(alarm)

        dismissed = self.scheduler.dismiss_alarm("test-dismiss")
        self.assertTrue(dismissed)
        self.assertEqual(len(self.scheduler.alarms), 0)

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_dismiss_daily_reschedules(self, mock_load, mock_save):
        self.scheduler.start()
        original_time = time.time() - 1
        alarm = Alarm(
            id="test-daily",
            trigger_time=original_time,
            status=AlarmStatus.RINGING,
            alarm_type=AlarmType.DAILY,
        )
        self.scheduler.add_alarm(alarm)

        dismissed = self.scheduler.dismiss_alarm("test-daily")
        self.assertTrue(dismissed)
        alarms = self.scheduler.alarms
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0].status, AlarmStatus.ACTIVE)
        self.assertAlmostEqual(
            alarms[0].trigger_time, original_time + 86400, delta=2
        )

    @patch("alarm_core.save_alarms")
    @patch("alarm_core.load_alarms", return_value=[])
    def test_prefix_match_cancel(self, mock_load, mock_save):
        """Should match alarm by ID prefix."""
        self.scheduler.start()
        alarm = Alarm(
            id="abcdef-1234-5678",
            trigger_time=time.time() + 3600,
        )
        self.scheduler.add_alarm(alarm)
        self.assertTrue(self.scheduler.remove_alarm("abcdef"))


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_parse_duration_boundary_values(self):
        self.assertEqual(parse_duration("1s"), timedelta(seconds=1))
        self.assertEqual(parse_duration("59m"), timedelta(minutes=59))
        self.assertEqual(parse_duration("23h59m59s"), timedelta(hours=23, minutes=59, seconds=59))

    def test_alarm_with_empty_label(self):
        alarm = Alarm(id="no-label", trigger_time=time.time() + 60)
        self.assertEqual(alarm.label, "")
        row = alarm.to_table_row()
        self.assertEqual(row["label"], "")

    def test_alarm_serialization_preserves_all_fields(self):
        alarm = Alarm(
            id="serial-test",
            trigger_time=time.time() + 300,
            label="Important",
            alarm_type=AlarmType.WEEKDAYS,
            status=AlarmStatus.ACTIVE,
            original_time_str="7:30am",
            snooze_count=2,
        )
        d = alarm.to_dict()
        restored = Alarm.from_dict(d)
        self.assertEqual(alarm.id, restored.id)
        self.assertEqual(alarm.label, restored.label)
        self.assertEqual(alarm.alarm_type, restored.alarm_type)
        self.assertEqual(alarm.snooze_count, restored.snooze_count)
        self.assertEqual(alarm.original_time_str, restored.original_time_str)


if __name__ == "__main__":
    unittest.main()
