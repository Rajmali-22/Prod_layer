"""
Log Manager - Keystroke logging to file.
"""

import os
import json
import time
import threading
from datetime import datetime

from ..config import Config
from ..state import state
from .ipc import IPCManager


class LogManager:
    """Handles keystroke logging to file."""

    @staticmethod
    def save(text, window):
        """Save log entry to file."""
        text = text.strip()
        if not text:
            return

        # Enforce limits
        text = text[:Config.MAX_ENTRY_LENGTH]
        window = (window or "")[:200]

        entry = {
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "window": window
        }

        try:
            # Read existing
            existing = []
            if os.path.exists(Config.LOG_FILE):
                try:
                    with open(Config.LOG_FILE, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            existing = data
                except (json.JSONDecodeError, IOError):
                    pass

            # Append and trim
            existing.append(entry)
            if len(existing) > Config.MAX_LOG_ENTRIES:
                existing = existing[-Config.MAX_LOG_ENTRIES:]

            # Write (compact JSON)
            with open(Config.LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(existing, f, separators=(',', ':'))

        except Exception as e:
            IPCManager.send_error(f"Log save failed: {e}")

    @staticmethod
    def save_async(text, window):
        """Save log entry in background thread."""
        threading.Thread(target=LogManager.save, args=(text, window), daemon=True).start()

    @staticmethod
    def add_char(char):
        """Add character to pending log."""
        with state.lock:
            if len(state.pending_log_text) >= Config.MAX_ENTRY_LENGTH:
                LogManager.save_async(state.pending_log_text, state.pending_log_window)
                state.pending_log_text = ""

            state.pending_log_text += char
            state.pending_log_window = state.last_window
            state.last_keystroke_time = time.time()

    @staticmethod
    def remove_char():
        """Remove last character from pending log (backspace)."""
        with state.lock:
            if state.pending_log_text:
                state.pending_log_text = state.pending_log_text[:-1]
            state.last_keystroke_time = time.time()

    @staticmethod
    def check_pause():
        """Check for typing pause and save if needed."""
        if not state.pending_log_text or state.last_keystroke_time == 0:
            return

        if time.time() - state.last_keystroke_time < Config.PAUSE_THRESHOLD:
            return

        with state.lock:
            if state.pending_log_text:
                text, window = state.pending_log_text, state.pending_log_window
                state.reset_log()
                LogManager.save_async(text, window)
