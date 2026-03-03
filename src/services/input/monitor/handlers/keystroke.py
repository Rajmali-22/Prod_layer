"""
Keystroke Handler - Main keystroke processing logic.
"""

import time
import keyboard

from ..config import Config
from ..state import state
from ..managers import IPCManager, WindowManager, LogManager, LiveModeManager


class KeystrokeHandler:
    """Handles all keystroke processing."""

    @staticmethod
    def handle_trigger():
        """Handle manual trigger (Ctrl+Alt+Enter or backtick)."""
        current = time.time()

        with state.lock:
            # Check for extension mode (double trigger)
            time_since = current - state.last_trigger_time
            is_extension = time_since < 2.0 and not state.last_trigger_had_typing

            state.last_trigger_time = current
            state.last_trigger_had_typing = False

            # Get buffer
            if len(state.buffer) > Config.MAX_TRIGGER_BUFFER:
                buffer_text = "".join(state.buffer[-Config.MAX_TRIGGER_BUFFER:])
            else:
                buffer_text = "".join(state.buffer)

            trigger_type = "extension" if is_extension else "backtick"
            extra = None

            if is_extension:
                extra = {
                    "last_ai_output": state.last_ai_output,
                    "extension_context": state.extension_context
                }

            IPCManager.send_trigger(trigger_type, buffer_text, state.raw_count, state.last_window, extra)

    @staticmethod
    def on_key(event):
        """Main keyboard event handler."""
        if not state.running or event.event_type != keyboard.KEY_DOWN:
            return

        # Window check (every N keystrokes)
        state._key_counter += 1
        if state._key_counter >= Config.WINDOW_CHECK_INTERVAL:
            state._key_counter = 0
            WindowManager.check_change()

        if state.is_private:
            return

        key = event.name
        LiveModeManager.update_speed()

        try:
            if key == 'backspace':
                KeystrokeHandler._handle_backspace()
            elif key == 'enter':
                KeystrokeHandler._handle_enter()
            elif key == 'space':
                KeystrokeHandler._handle_char(' ')
            elif key == 'tab':
                KeystrokeHandler._handle_char('\t')
            elif len(key) == 1 and key != '`':
                KeystrokeHandler._handle_char(key)

        except Exception as e:
            IPCManager.send_error(f"Key event error: {e}")

    @staticmethod
    def _handle_backspace():
        """Handle backspace key."""
        with state.lock:
            if state.buffer:
                state.buffer.pop()
            state.raw_count += 1
            state.last_trigger_had_typing = True
            state.live_pending = False
        LogManager.remove_char()
        LiveModeManager.start_timer()

    @staticmethod
    def _handle_enter():
        """Handle enter key."""
        with state.lock:
            state.buffer.append('\n')
            state.raw_count += 1
            state.last_trigger_had_typing = True
            state.live_pending = False
        LogManager.add_char('\n')
        LiveModeManager.cancel_timer()  # Don't trigger on enter

    @staticmethod
    def _handle_char(char):
        """Handle regular character."""
        with state.lock:
            if len(state.buffer) >= Config.MAX_BUFFER_SIZE:
                state.buffer = state.buffer[-(Config.MAX_BUFFER_SIZE - 1):]
            state.buffer.append(char)
            state.raw_count += 1
            state.last_trigger_had_typing = True
            state.live_pending = False
        LogManager.add_char(char)
        LiveModeManager.start_timer()
