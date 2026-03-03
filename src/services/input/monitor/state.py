"""
State - Global application state with thread-safe access.
"""

import threading
from collections import deque
from .config import Config


class State:
    """Global application state."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = True

        # --- Typing Buffer ---
        self.buffer = []
        self.raw_count = 0

        # --- Window Tracking ---
        self.last_window = ""
        self.last_window_process = ""
        self.is_private = False
        self._key_counter = 0

        # --- Trigger State ---
        self.last_trigger_time = 0
        self.last_trigger_had_typing = True

        # --- Extension Mode ---
        self.last_ai_output = ""
        self.extension_context = ""

        # --- Logging ---
        self.last_keystroke_time = 0
        self.pending_log_text = ""
        self.pending_log_window = ""

        # --- Live Mode ---
        self.live_mode_enabled = False
        self.live_timer = None
        self.live_pending = False

        # --- Adaptive Speed ---
        self.speed_samples = deque(maxlen=Config.ADAPTIVE_MAX_SAMPLES)
        self.adaptive_threshold = 1.0
        self.last_key_time = 0

    def reset_buffer(self):
        """Reset typing buffer and related state."""
        self.buffer.clear()
        self.raw_count = 0
        self.last_trigger_had_typing = True
        self.last_ai_output = ""
        self.extension_context = ""

    def reset_log(self):
        """Reset pending log state."""
        self.pending_log_text = ""
        self.pending_log_window = ""


# Global state instance
state = State()
