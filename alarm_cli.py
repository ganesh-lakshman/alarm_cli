#!/usr/bin/env python3
"""
Alarm Clock CLI — A terminal-based alarm clock application.

Usage:
    python alarm_cli.py                  # Interactive REPL mode
    python alarm_cli.py add 7:30am       # Quick add and wait
    python alarm_cli.py add 5m           # Timer: fire in 5 minutes
    python alarm_cli.py list             # List active alarms
    python alarm_cli.py clear            # Clear all alarms
"""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import sys
import threading
import time
from datetime import datetime, timedelta

from alarm_core import (
    Alarm,
    AlarmScheduler,
    AlarmStatus,
    AlarmType,
    parse_alarm_time,
)
from alarm_display import (
    colorize,
    print_alarm_firing,
    print_alarm_table,
    print_banner,
    print_error,
    print_info,
    print_success,
    print_warning,
    BOLD,
    CYAN,
    DIM,
    GREEN,
    YELLOW,
)
from alarm_sound import play_alarm_sound, stop_sound


# ── Globals ───────────────────────────────────────────────────────────────────

_ringing_alarm: Alarm | None = None
_sound_thread: threading.Thread | None = None


def _on_alarm_fired(alarm: Alarm) -> None:
    """Callback invoked by the scheduler when an alarm fires."""
    global _ringing_alarm, _sound_thread

    _ringing_alarm = alarm
    print_alarm_firing(alarm.id[:8], alarm.label, alarm.time_display)

    stop_sound()
    _sound_thread = threading.Thread(target=play_alarm_sound, args=(8,), daemon=True)
    _sound_thread.start()


# ── REPL Commands ─────────────────────────────────────────────────────────────

HELP_TEXT = f"""{colorize('Available Commands:', BOLD, CYAN)}

  {colorize('add', GREEN)} <time> [--label TEXT] [--type once|daily|weekdays]
      Set a new alarm. Time can be absolute, relative, or a full date-time.
      Examples:  add 7:30am --label "Wake up"
                 add 14:00 --type daily
                 add 5m --label "Tea timer"
                 add 1h30m
                 add 30s
                 add tomorrow 9:00 --label "Standup"
                 add friday 14:00
                 add Oct 10 7:30am
                 add 2026-10-10 07:30
                 add 10/12/2026 3:00pm

  {colorize('list', GREEN)} / {colorize('ls', GREEN)}
      Show all active alarms.

  {colorize('cancel', GREEN)} <id>    /  {colorize('rm', GREEN)} <id>
      Cancel an alarm by its ID (first few chars suffice).

  {colorize('snooze', GREEN)} [minutes]
      Snooze the currently ringing alarm (default: 5 min).

  {colorize('dismiss', GREEN)}  /  {colorize('ok', GREEN)}  /  press {colorize('Enter', GREEN)}
      Dismiss the currently ringing alarm.

  {colorize('clear', GREEN)}
      Remove all alarms.

  {colorize('status', GREEN)}
      Show a live countdown to the next alarm.

  {colorize('help', GREEN)} / {colorize('?', GREEN)}
      Show this help message.

  {colorize('quit', GREEN)} / {colorize('exit', GREEN)} / {colorize('Ctrl+C', GREEN)}
      Exit the application.
"""


def cmd_add(scheduler: AlarmScheduler, args: list[str]) -> None:
    """Handle the 'add' command."""
    if not args:
        print_error("Usage: add <time> [--label TEXT] [--type once|daily|weekdays]")
        return

    parser = argparse.ArgumentParser(prog="add", add_help=False)
    parser.add_argument("time_str", nargs="+")
    parser.add_argument("--label", "-l", default="", type=str)
    parser.add_argument("--type", "-t", default="once", choices=["once", "daily", "weekdays"])

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print_error("Invalid arguments. Usage: add <time> [--label TEXT] [--type once|daily|weekdays]")
        return

    time_input = " ".join(parsed.time_str)

    try:
        target_dt, description = parse_alarm_time(time_input)
    except ValueError as e:
        print_error(str(e))
        return

    alarm = Alarm(
        id=str(__import__("uuid").uuid4()),
        trigger_time=target_dt.timestamp(),
        label=parsed.label,
        alarm_type=AlarmType(parsed.type),
        original_time_str=time_input,
    )
    scheduler.add_alarm(alarm)

    remaining = target_dt - datetime.now()
    mins = int(remaining.total_seconds() // 60)
    secs = int(remaining.total_seconds() % 60)

    print_success(f"Alarm set for {description}")
    if parsed.label:
        print_info(f'Label: "{parsed.label}"')
    print_info(f"Fires in {mins}m {secs}s  •  ID: {alarm.id[:8]}")


def cmd_list(scheduler: AlarmScheduler) -> None:
    """Handle the 'list' command."""
    alarms = scheduler.alarms
    active = [a for a in alarms if a.status in (AlarmStatus.ACTIVE, AlarmStatus.RINGING)]
    rows = sorted(
        [a.to_table_row() for a in active],
        key=lambda r: r["time_display"],
    )
    print_alarm_table(rows)


def cmd_cancel(scheduler: AlarmScheduler, alarm_id: str) -> None:
    """Handle the 'cancel'/'rm' command."""
    if scheduler.remove_alarm(alarm_id):
        print_success(f"Alarm {alarm_id} cancelled.")
    else:
        print_error(f"No active alarm matching '{alarm_id}'.")


def cmd_snooze(scheduler: AlarmScheduler, minutes: int = 5) -> None:
    """Handle the 'snooze' command."""
    global _ringing_alarm

    ringing = scheduler.get_ringing()
    if not ringing:
        print_info("No alarm is currently ringing.")
        return

    alarm = ringing[0]
    stop_sound()
    result = scheduler.snooze_alarm(alarm.id, minutes)
    if result:
        _ringing_alarm = None
        new_time = datetime.fromtimestamp(result.trigger_time).strftime("%H:%M:%S")
        print_success(f"Snoozed until {new_time} ({minutes} min). Snooze #{result.snooze_count}")
    else:
        print_error("Failed to snooze alarm.")


def cmd_dismiss(scheduler: AlarmScheduler) -> None:
    """Handle the 'dismiss'/'ok'/Enter command."""
    global _ringing_alarm

    ringing = scheduler.get_ringing()
    if not ringing:
        return  # silent — Enter on empty prompt is fine

    alarm = ringing[0]
    stop_sound()
    scheduler.dismiss_alarm(alarm.id)
    _ringing_alarm = None

    if alarm.alarm_type == AlarmType.ONCE:
        print_success("Alarm dismissed.")
    else:
        next_dt = datetime.fromtimestamp(alarm.trigger_time)
        print_success(f"Alarm dismissed. Next: {next_dt.strftime('%Y-%m-%d %H:%M')}")


def cmd_clear(scheduler: AlarmScheduler) -> None:
    """Handle the 'clear' command."""
    alarms = scheduler.alarms
    count = 0
    for a in alarms:
        scheduler.remove_alarm(a.id)
        count += 1
    stop_sound()
    print_success(f"Cleared {count} alarm(s).")


def cmd_status(scheduler: AlarmScheduler) -> None:
    """Show countdown to the next alarm."""
    alarms = scheduler.alarms
    active = [a for a in alarms if a.status == AlarmStatus.ACTIVE]
    if not active:
        print_info("No active alarms.")
        return

    active.sort(key=lambda a: a.trigger_time)
    nearest = active[0]
    remaining = nearest.time_remaining
    total_sec = max(0, int(remaining.total_seconds()))
    h, rem = divmod(total_sec, 3600)
    m, s = divmod(rem, 60)

    label_part = f'  "{nearest.label}"' if nearest.label else ""
    print_info(f"Next alarm in {h:02d}:{m:02d}:{s:02d}{label_part}")
    print_info(f"Fires at {nearest.time_display}  •  ID: {nearest.id[:8]}")


# ── REPL Loop ─────────────────────────────────────────────────────────────────

def _prompt() -> str:
    """Generate the REPL prompt string."""
    now = datetime.now().strftime("%H:%M:%S")
    return f"{colorize(now, DIM)} {colorize('alarm>', CYAN, BOLD)} "


def run_repl(scheduler: AlarmScheduler) -> None:
    """Run the interactive REPL."""
    print_banner()

    # Show any alarms restored from disk
    restored = scheduler.alarms
    if restored:
        active = [a for a in restored if a.status == AlarmStatus.ACTIVE]
        if active:
            print_info(f"Restored {len(active)} alarm(s) from previous session.")
            cmd_list(scheduler)
            print()

    while True:
        try:
            raw = input(_prompt()).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            print_info("Goodbye!")
            scheduler.stop()
            stop_sound()
            sys.exit(0)

        if not raw:
            # Empty Enter dismisses a ringing alarm
            cmd_dismiss(scheduler)
            continue

        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = raw.split()

        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("help", "?"):
            print(HELP_TEXT)
        elif cmd == "add":
            cmd_add(scheduler, args)
        elif cmd in ("list", "ls"):
            cmd_list(scheduler)
        elif cmd in ("cancel", "rm", "delete", "del"):
            if args:
                cmd_cancel(scheduler, args[0])
            else:
                print_error("Usage: cancel <alarm-id>")
        elif cmd == "snooze":
            minutes = 5
            if args:
                try:
                    minutes = int(args[0])
                except ValueError:
                    print_error("Snooze duration must be a number of minutes.")
                    continue
            cmd_snooze(scheduler, minutes)
        elif cmd in ("dismiss", "ok", "stop"):
            cmd_dismiss(scheduler)
        elif cmd == "clear":
            cmd_clear(scheduler)
        elif cmd == "status":
            cmd_status(scheduler)
        elif cmd in ("quit", "exit", "q"):
            print_info("Goodbye!")
            scheduler.stop()
            stop_sound()
            sys.exit(0)
        else:
            # Try interpreting the entire input as an 'add' command
            # e.g. typing just "5m" or "7:30am"
            cmd_add(scheduler, parts)


# ── CLI Entry Point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="⏰ Alarm Clock CLI — set alarms from your terminal",
    )
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="Set a new alarm")
    add_p.add_argument("time_str", nargs="+", help="Time: '7:30am', '14:00', '5m', '1h30m'")
    add_p.add_argument("--label", "-l", default="")
    add_p.add_argument("--type", "-t", default="once", choices=["once", "daily", "weekdays"])

    sub.add_parser("list", help="List active alarms")
    sub.add_parser("clear", help="Clear all alarms")

    args = parser.parse_args()
    scheduler = AlarmScheduler(on_alarm=_on_alarm_fired)
    scheduler.start()

    if args.command is None:
        # No subcommand → interactive REPL
        run_repl(scheduler)
    elif args.command == "add":
        cmd_add(scheduler, args.time_str + (
            ["--label", args.label] if args.label else []
        ) + (
            ["--type", args.type] if args.type != "once" else []
        ))
        # Wait for the alarm to fire
        print_info("Waiting for alarm... (Ctrl+C to cancel)")
        try:
            while True:
                ringing = scheduler.get_ringing()
                if ringing:
                    time.sleep(3)  # Let the alarm sound play
                    stop_sound()
                    print_info("Alarm done.")
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()
            print_info("Cancelled.")
    elif args.command == "list":
        cmd_list(scheduler)
    elif args.command == "clear":
        cmd_clear(scheduler)

    scheduler.stop()


if __name__ == "__main__":
    main()
