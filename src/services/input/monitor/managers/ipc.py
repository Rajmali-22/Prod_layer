"""
IPC Manager - Communication with Electron process.
"""

import json


class IPCManager:
    """Handles all communication with Electron process."""

    @staticmethod
    def send(event_data):
        """Send event to Electron via stdout."""
        try:
            print(json.dumps(event_data), flush=True)
        except Exception:
            pass

    @staticmethod
    def send_error(message):
        """Send error event."""
        IPCManager.send({"event": "error", "message": message})

    @staticmethod
    def send_trigger(trigger_type, buffer_text, char_count, window, extra=None):
        """Send trigger event to Electron."""
        event = {
            "event": "trigger",
            "type": trigger_type,
            "buffer": buffer_text,
            "char_count": char_count,
            "window": window
        }
        if extra:
            event.update(extra)
        IPCManager.send(event)
