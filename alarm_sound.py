"""Cross-platform sound and visual alerting for alarm notifications."""

import sys
import time
import threading

_stop_event = threading.Event()


def _beep_windows(duration_ms: int = 300, freq: int = 1000) -> None:
    """Play a beep using the Windows winsound module."""
    import winsound
    winsound.Beep(freq, duration_ms)


def _beep_fallback() -> None:
    """Emit terminal bell character as a fallback alert."""
    sys.stdout.write("\a")
    sys.stdout.flush()
    time.sleep(0.3)


def play_alarm_sound(cycles: int = 6) -> None:
    """Play an alarm sound pattern. Blocks for the duration.

    The pattern alternates between two frequencies to create
    an unmistakable alarm tone. Stops early if stop() is called.
    """
    _stop_event.clear()
    freqs = [800, 1100]

    for i in range(cycles):
        if _stop_event.is_set():
            break
        freq = freqs[i % 2]
        if sys.platform == "win32":
            _beep_windows(duration_ms=250, freq=freq)
            if _stop_event.is_set():
                break
            time.sleep(0.1)
        else:
            _beep_fallback()
            if _stop_event.is_set():
                break
            time.sleep(0.35)


def stop_sound() -> None:
    """Signal the alarm sound to stop."""
    _stop_event.set()


def is_stopped() -> bool:
    """Check whether the stop signal has been set."""
    return _stop_event.is_set()
