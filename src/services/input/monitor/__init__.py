"""
Keystroke Monitor - System-wide keystroke capture for AI text assistance.

Modules:
- config: All configuration constants
- state: Global application state
- managers: WindowManager, LogManager, IPCManager, LiveModeManager
- handlers: KeystrokeHandler, CommandHandler
- threads: Background threads for stdin, pause, window monitoring

Author: AI Keyboard Team
"""

import os
import sys
import time
import threading

import keyboard

from .config import Config
from .state import state
from .managers import IPCManager, WindowManager, LogManager, LiveModeManager
from .handlers import KeystrokeHandler, CommandHandler
from .threads import stdin_reader, pause_monitor, window_monitor

# Check for win32 support
try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


def main():
    """Application entry point."""

    # Notify Electron we're ready
    if not HAS_WIN32:
        IPCManager.send_error("pywin32/psutil not installed. Window tracking disabled.")
    IPCManager.send({"event": "started", "pid": os.getpid()})

    # Start background threads
    threads = [
        threading.Thread(target=stdin_reader, daemon=True),
        threading.Thread(target=window_monitor, daemon=True),
        threading.Thread(target=pause_monitor, daemon=True),
    ]
    for t in threads:
        t.start()

    # Initial window check
    WindowManager.check_change()

    # Hook keyboard
    keyboard.hook(KeystrokeHandler.on_key)

    try:
        while state.running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.unhook_all()
        LiveModeManager.cancel_timer()

        with state.lock:
            if state.pending_log_text:
                LogManager.save(state.pending_log_text, state.pending_log_window)

        IPCManager.send({"event": "stopped"})


__all__ = [
    'Config',
    'state',
    'IPCManager',
    'WindowManager',
    'LogManager',
    'LiveModeManager',
    'KeystrokeHandler',
    'CommandHandler',
    'main',
]
