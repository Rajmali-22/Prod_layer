"""
Background Threads - Stdin reader, pause monitor, window monitor.
"""

import sys
import json
import time

from .config import Config
from .state import state
from .managers import IPCManager, LogManager, WindowManager
from .handlers import CommandHandler


def stdin_reader():
    """Read commands from Electron via stdin."""
    while state.running:
        try:
            line = sys.stdin.readline()
            if not line:
                state.running = False
                break

            line = line.strip()
            if line:
                try:
                    CommandHandler.handle(json.loads(line))
                except json.JSONDecodeError:
                    IPCManager.send_error(f"Invalid JSON: {line}")

        except Exception as e:
            IPCManager.send_error(f"stdin error: {e}")
            break


def pause_monitor():
    """Monitor for typing pauses to save logs."""
    while state.running:
        LogManager.check_pause()
        time.sleep(Config.PAUSE_CHECK_INTERVAL)


def window_monitor():
    """Monitor for window changes."""
    while state.running:
        WindowManager.check_change()
        time.sleep(Config.WINDOW_MONITOR_INTERVAL)
