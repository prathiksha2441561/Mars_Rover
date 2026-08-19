"""
console.py
==========
Console output infrastructure for the Mars Rover agent.

Two jobs:

1. **Safe Unicode output.**
   The logical notation used throughout this project (¬ ∧ ∨ → ↔ ⊨ ⊢) is
   Unicode.  The default Windows console codepage (cp1252) cannot encode
   these characters, which raises ``UnicodeEncodeError`` mid-simulation.
   :func:`configure_console` reconfigures stdout/stderr to UTF-8 with
   line buffering so that:
     * logical symbols print correctly, and
     * each line appears *immediately* (required for the live console
       demonstration — block buffering would make the log appear in bursts).

2. **Log mirroring.**
   :func:`log` writes to the terminal *and* to any registered listener.
   The Tkinter UI registers a listener so the same live reasoning log is
   visible inside the application window.  This is what allows a single
   screen recording to show the grid and the live console together.

Every module in this project prints through :func:`log` rather than the
built-in ``print`` so that both behaviours apply consistently.
"""

from __future__ import annotations

import io
import sys
from typing import Callable, List, Optional

# ---------------------------------------------------------------------------
# ASCII fallbacks — used only if the terminal genuinely cannot do UTF-8
# ---------------------------------------------------------------------------

_ASCII_FALLBACK = {
    "¬": "~", "∧": "&", "∨": "|", "→": "->", "↔": "<->",
    "⊨": "|=", "⊭": "|/=", "⊢": "|-", "∴": "therefore",
    "∈": "in", "≠": "!=", "≤": "<=", "×": "x",
    "✓": "[OK]", "✗": "[X]", "★": "*", "⚠": "!", "☢": "(rad)",
    "─": "-", "═": "=", "│": "|", "▶": ">", "?": "?",
}

_unicode_ok: bool = True

# A listener is called as listener(message, tag) for every logged line.
_listeners: List[Callable[[str, str], None]] = []


# ---------------------------------------------------------------------------
# Console configuration
# ---------------------------------------------------------------------------

def configure_console() -> bool:
    """
    Make stdout/stderr safe for the logical notation used in this project.

    Returns:
        True if UTF-8 output is available, False if the caller should
        expect ASCII fallbacks.

    Called automatically on import, so simply importing this module is
    enough — ``main.py``, the UI and the test suite all benefit.
    """
    global _unicode_ok

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            # Python 3.7+: reconfigure in place (keeps the same object,
            # so anything that already captured sys.stdout still works).
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)
        except (AttributeError, ValueError, OSError):
            # Older streams / redirected pipes: wrap the raw buffer instead.
            buffer = getattr(stream, "buffer", None)
            if buffer is None:
                continue
            try:
                setattr(sys, name, io.TextIOWrapper(
                    buffer, encoding="utf-8", errors="replace",
                    line_buffering=True))
            except Exception:
                _unicode_ok = False

    # Verify the configured stream really can encode our notation.
    try:
        encoding = (getattr(sys.stdout, "encoding", None) or "ascii").lower()
        "¬∧∨→⊨".encode(encoding)
        _unicode_ok = True
    except Exception:
        _unicode_ok = False

    return _unicode_ok


def unicode_supported() -> bool:
    """True if logical symbols can be printed directly."""
    return _unicode_ok


def to_ascii(text: str) -> str:
    """Replace logical/decorative symbols with ASCII equivalents."""
    for symbol, replacement in _ASCII_FALLBACK.items():
        text = text.replace(symbol, replacement)
    return text


# ---------------------------------------------------------------------------
# Log listeners (used by the Tkinter UI to mirror the console)
# ---------------------------------------------------------------------------

def add_listener(callback: Callable[[str, str], None]) -> None:
    """
    Register a callback invoked as ``callback(message, tag)`` for every
    logged line.

    The UI uses this to display the live reasoning log inside the window
    alongside the grid.
    """
    if callback not in _listeners:
        _listeners.append(callback)


def remove_listener(callback: Callable[[str, str], None]) -> None:
    """Unregister a previously added listener."""
    if callback in _listeners:
        _listeners.remove(callback)


def clear_listeners() -> None:
    """Remove all listeners (used on reset / shutdown)."""
    _listeners.clear()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(message: str = "", tag: str = "") -> None:
    """
    Print one line of the live reasoning log.

    Args:
        message: The text to print.
        tag:     Optional category ("tell", "ask", "infer", "result",
                 "rule", "decision", "step", "perceive") used by the UI
                 to colour the line.  Ignored by the terminal.

    This is the single output path for the whole simulation, so the
    terminal log and the in-app log can never drift apart.
    """
    text = message if _unicode_ok else to_ascii(message)

    try:
        print(text)
    except UnicodeEncodeError:
        # Last-resort guard: never let logging crash the simulation.
        print(to_ascii(message).encode("ascii", "replace").decode("ascii"))

    for listener in list(_listeners):
        try:
            listener(message, tag)
        except Exception:
            # A broken UI listener must never break the agent.
            pass


def banner(title: str, char: str = "=", width: int = 60,
           tag: str = "step") -> None:
    """Print a titled separator banner, e.g. the ROVER STEP header."""
    log(char * width, tag)
    log(f"  {title}", tag)
    log(char * width, tag)


def section(title: str, tag: str = "step") -> None:
    """Print a minor section heading inside a step."""
    log("")
    log(f"  {title}", tag)


# Configure as soon as the module is imported.
configure_console()
