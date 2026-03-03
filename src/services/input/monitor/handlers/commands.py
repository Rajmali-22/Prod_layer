"""
Command Handler - IPC commands from Electron.
"""

from ..state import state
from ..managers import IPCManager, LogManager, LiveModeManager
from .keystroke import KeystrokeHandler


class CommandHandler:
    """Handles commands received from Electron."""

    COMMANDS = {}

    @classmethod
    def register(cls, name):
        """Decorator to register command handlers."""
        def decorator(func):
            cls.COMMANDS[name] = func
            return func
        return decorator

    @classmethod
    def handle(cls, cmd_data):
        """Route command to appropriate handler."""
        cmd = cmd_data.get("cmd", "")
        handler = cls.COMMANDS.get(cmd)

        if handler:
            handler(cmd_data)
        else:
            IPCManager.send_error(f"Unknown command: {cmd}")


# ══════════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

@CommandHandler.register("reset")
def cmd_reset(data):
    """Reset buffer and log state."""
    with state.lock:
        state.reset_buffer()
        state.reset_log()
    IPCManager.send({"event": "reset_ack"})


@CommandHandler.register("set_ai_output")
def cmd_set_ai_output(data):
    """Store AI output for extension mode."""
    with state.lock:
        state.last_ai_output = data.get("output", "")
        state.extension_context = data.get("context", "")
    IPCManager.send({"event": "ai_output_set"})


@CommandHandler.register("get_buffer")
def cmd_get_buffer(data):
    """Return current buffer for debugging."""
    with state.lock:
        IPCManager.send({
            "event": "buffer",
            "buffer": "".join(state.buffer),
            "raw_count": state.raw_count,
            "window": state.last_window
        })


@CommandHandler.register("shutdown")
def cmd_shutdown(data):
    """Flush pending log and exit."""
    with state.lock:
        if state.pending_log_text:
            LogManager.save(state.pending_log_text, state.pending_log_window)
    state.running = False
    IPCManager.send({"event": "shutdown_ack"})


@CommandHandler.register("ping")
def cmd_ping(data):
    """Health check."""
    IPCManager.send({"event": "pong"})


@CommandHandler.register("trigger")
def cmd_trigger(data):
    """Manual trigger from Electron."""
    KeystrokeHandler.handle_trigger()


@CommandHandler.register("set_live_mode")
def cmd_set_live_mode(data):
    """Enable or disable live mode."""
    LiveModeManager.set_enabled(data.get("enabled", False))
