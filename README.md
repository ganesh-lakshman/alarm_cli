# Alarm Clock CLI

A simple alarm clock that runs in your terminal. No dependencies beyond Python 3.10+.

## Quick start

```
python alarm_cli.py
```

This drops you into an interactive prompt where you can add alarms, list them, snooze, etc.

## Setting alarms

You can set alarms by time, duration, or full date:

```
add 7:30am
add 14:00 --label "Meeting"
add 5m
add 1h30m
add tomorrow 9:00 --label "Standup"
add friday 14:00
add Oct 10 7:30am
add 2026-12-25 14:00
```

You can also skip the `add` keyword — just type `5m` or `7:30am` directly.

For recurring alarms, pass `--type`:

```
add 7:00am --type daily --label "Wake up"
add 9:30am --type weekdays --label "Standup"
```

## One-shot mode

If you don't need the interactive prompt, you can set an alarm and wait for it in one command:

```
python alarm_cli.py add 5m --label "Break time"
```

Other one-shot commands:

```
python alarm_cli.py list
python alarm_cli.py clear
```

## Commands

| Command | What it does |
|---|---|
| `add <time>` | Set an alarm |
| `list` / `ls` | Show active alarms |
| `cancel <id>` / `rm <id>` | Cancel an alarm (first few chars of the ID is enough) |
| `snooze [minutes]` | Snooze a ringing alarm (default 5 min) |
| `dismiss` / `ok` / Enter | Dismiss a ringing alarm |
| `status` | Countdown to next alarm |
| `clear` | Remove all alarms |
| `help` | Show help |
| `quit` / `exit` | Exit |

## Notes

- Alarms are saved to `~/.alarmcli/alarms.json`, so they persist if you close and reopen the app.
- On Windows, the alarm sound uses `winsound.Beep`. On other platforms it falls back to the terminal bell.
- If you set a time that's already passed today (like `9:00am` when it's noon), it gets scheduled for tomorrow.
- Past dates (like `2020-01-01 10:00`) are rejected with an error.

## Running tests

```
python -m pytest tests/ -v
```
