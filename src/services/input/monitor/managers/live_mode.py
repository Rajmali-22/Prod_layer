"""
Live Mode Manager - Adaptive auto-suggestion on typing pause.
"""

import time
import threading

from ..config import Config
from ..state import state
from .ipc import IPCManager


class LiveModeManager:
    """Handles live mode with adaptive typing speed detection."""

    @staticmethod
    def update_speed():
        """Update adaptive threshold based on typing speed."""
        current = time.time()

        if state.last_key_time > 0:
            interval = current - state.last_key_time

            if interval < 2.0:  # Only track reasonable intervals
                state.speed_samples.append(interval)

                if len(state.speed_samples) >= Config.ADAPTIVE_MIN_SAMPLES:
                    avg = sum(state.speed_samples) / len(state.speed_samples)
                    threshold = avg * Config.ADAPTIVE_MULTIPLIER
                    state.adaptive_threshold = max(
                        Config.ADAPTIVE_MIN_THRESHOLD,
                        min(Config.ADAPTIVE_MAX_THRESHOLD, threshold)
                    )

        state.last_key_time = current

    @staticmethod
    def cancel_timer():
        """Cancel pending live suggestion timer."""
        if state.live_timer:
            state.live_timer.cancel()
            state.live_timer = None

    @staticmethod
    def start_timer():
        """Start live suggestion timer with adaptive threshold."""
        if not state.live_mode_enabled:
            return

        LiveModeManager.cancel_timer()
        state.live_pending = False

        state.live_timer = threading.Timer(
            state.adaptive_threshold,
            LiveModeManager.trigger
        )
        state.live_timer.daemon = True
        state.live_timer.start()

    @staticmethod
    def trigger():
        """Trigger live suggestion."""
        with state.lock:
            if not state.live_mode_enabled or state.live_pending:
                return
            if len(state.buffer) < Config.LIVE_MIN_CHARS:
                return

            state.live_pending = True

            # Get buffer (limited size)
            if len(state.buffer) > Config.MAX_TRIGGER_BUFFER:
                buffer_text = "".join(state.buffer[-Config.MAX_TRIGGER_BUFFER:])
            else:
                buffer_text = "".join(state.buffer)

            IPCManager.send_trigger("live", buffer_text, state.raw_count, state.last_window)

    @staticmethod
    def set_enabled(enabled):
        """Enable or disable live mode."""
        with state.lock:
            state.live_mode_enabled = enabled
        IPCManager.send({"event": "live_mode_set", "enabled": enabled})
