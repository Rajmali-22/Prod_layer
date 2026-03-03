"""
Window Manager - Active window tracking & privacy detection.
"""

from ..config import Config
from ..state import state
from .ipc import IPCManager

# pywin32 for active window detection (Windows only)
try:
    import win32gui
    import win32process
    import psutil
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


class WindowManager:
    """Handles window detection and privacy filtering."""

    @staticmethod
    def has_win32():
        """Check if win32 is available."""
        return HAS_WIN32

    @staticmethod
    def get_active_window():
        """Get current window title and process name."""
        if not HAS_WIN32:
            return "", ""

        try:
            hwnd = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(hwnd)

            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            try:
                process = psutil.Process(pid).name().lower()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process = ""

            return title, process
        except Exception:
            return "", ""

    @staticmethod
    def is_private(title, process):
        """Check if context is private (banking, passwords, etc.)."""
        title_lower = title.lower()

        for app in Config.PRIVATE_APPS:
            if app in process or app in title_lower:
                return True

        for keyword in Config.PRIVATE_KEYWORDS:
            if keyword in title_lower:
                return True

        return False

    @staticmethod
    def check_change():
        """Check for window change and update state."""
        # Import here to avoid circular import
        from .log import LogManager

        title, process = WindowManager.get_active_window()

        with state.lock:
            if title == state.last_window and process == state.last_window_process:
                return False

            old_window = state.last_window

            # Flush pending log before switch
            if state.pending_log_text:
                LogManager.save_async(state.pending_log_text, state.pending_log_window)
                state.reset_log()

            # Update state
            state.last_window = title
            state.last_window_process = process
            state.is_private = WindowManager.is_private(title, process)
            state.reset_buffer()

            # Notify Electron
            IPCManager.send({
                "event": "window_change",
                "old_window": old_window,
                "new_window": title,
                "is_private": state.is_private
            })

            return True
