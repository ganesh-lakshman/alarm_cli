"""Terminal display utilities: colors, tables, and alarm animation."""

import sys
import shutil

# ANSI color codes — works in Windows Terminal, CMD (Win10+), and all Unix terminals
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BG_RED = "\033[41m"
BG_YELLOW = "\033[43m"


def _enable_ansi_windows() -> None:
    """Enable ANSI escape sequences and UTF-8 output on Windows consoles."""
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        # Set console output code page to UTF-8
        kernel32.SetConsoleOutputCP(65001)
        # Reconfigure stdout/stderr to use UTF-8 with error replacement
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")


_enable_ansi_windows()


def colorize(text: str, *codes: str) -> str:
    return "".join(codes) + text + RESET


def print_banner() -> None:
    banner = r"""
   ___    __                    _______   ____
  / _ |  / / ___ _ ______ _   / ___/ /  /  _/
 / __ | / / / _ `// __/  ' \ / /_ / /_ _/ /
/_/ |_|/_/  \_,_//_/ /_/_/_/ \___//___//___/
"""
    print(colorize(banner, CYAN, BOLD))
    print(colorize("  ⏰  Alarm Clock CLI  —  Type 'help' to get started\n", DIM))


def print_success(msg: str) -> None:
    print(colorize(f"  ✓ {msg}", GREEN))


def print_error(msg: str) -> None:
    print(colorize(f"  ✗ {msg}", RED))


def print_info(msg: str) -> None:
    print(colorize(f"  ℹ {msg}", BLUE))


def print_warning(msg: str) -> None:
    print(colorize(f"  ⚠ {msg}", YELLOW))


def print_alarm_firing(alarm_id: str, label: str, time_str: str) -> None:
    """Print a highly visible alarm notification."""
    width = min(shutil.get_terminal_size().columns, 60)
    border = "═" * width

    print()
    print(colorize(border, RED, BOLD))
    print(colorize(f"  🔔  ALARM!  {time_str}", BG_RED, WHITE, BOLD))
    if label:
        print(colorize(f"  📌  {label}", RED, BOLD))
    print(colorize(f"  ID: {alarm_id}", DIM))
    print(colorize(border, RED, BOLD))
    print(colorize("  Press Enter to dismiss, or type 'snooze [minutes]'", YELLOW))
    print()


def print_alarm_table(alarms: list) -> None:
    """Print a formatted table of alarms."""
    if not alarms:
        print_info("No alarms set.")
        return

    header = f"  {'ID':<8} {'Time':<20} {'Label':<20} {'Type':<10} {'Status'}"
    sep = "  " + "─" * 78
    print(colorize(sep, DIM))
    print(colorize(header, BOLD, CYAN))
    print(colorize(sep, DIM))

    for a in alarms:
        status_color = GREEN if a["status"] == "active" else YELLOW if a["status"] == "ringing" else DIM
        time_display = a["time_display"]
        label = a.get("label", "") or "—"
        alarm_type = a.get("type", "once")
        status = a["status"]

        print(f"  {colorize(a['id'][:8], MAGENTA):<20} {time_display:<20} {label:<20} {alarm_type:<10} {colorize(status, status_color)}")

    print(colorize(sep, DIM))
    print(colorize(f"  {len(alarms)} alarm(s) total", DIM))
