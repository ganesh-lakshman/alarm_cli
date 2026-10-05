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
