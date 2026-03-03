"""
Per-window conversation memory.

Each active application window gets its own conversation session.
Sessions persist to disk (effectively unlimited); what is sent to the LLM
is capped by MAX_HISTORY_SENT_TO_LLM to avoid context-window overflow.
Memory is only attached for powerful/reasoning requests (not fast/grammar).
"""

import os
import re
import json
import time
from pathlib import Path

try:
    from langchain_core.messages import HumanMessage, AIMessage
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

MAX_HISTORY_PER_SESSION = 99999   # keep last N exchanges on disk (effectively unlimited)
MAX_HISTORY_SENT_TO_LLM = 50     # cap messages sent to LLM (last N exchanges) to avoid context-window overflow
SESSION_MAX_AGE_DAYS = 36500     # ~100 years (effectively never prune by age)
SESSIONS_DIR = os.path.join("data", "memory", "sessions")
GLOBAL_SESSION_KEY = "_global"  # shared memory pool across all windows/models

# Modes that are too short-lived for conversation memory
SKIP_MEMORY_MODES = {"backtick", "live"}


def _normalize_window_title(title):
    """
    Normalize window title to a stable session key.
    "file.py - VS Code" → "vs_code"
    "Google Chrome"      → "google_chrome"
    """
    if not title:
        return "unknown"

    # Take the last segment after " - " (usually the app name)
    parts = title.split(" - ")
    app_name = parts[-1].strip() if len(parts) > 1 else title.strip()

    # Normalize
    key = re.sub(r'[^a-zA-Z0-9]+', '_', app_name).strip('_').lower()
    return key or "unknown"


class MemoryManager:
    """Manages per-window conversation sessions with disk persistence."""

    def __init__(self, sessions_dir=None):
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.sessions = {}  # {session_key: [{"role": ..., "content": ..., "ts": ...}, ...]}
        self._ensure_dir()
        self._load_all_sessions()
        self._prune_old_sessions()

    def _ensure_dir(self):
        Path(self.sessions_dir).mkdir(parents=True, exist_ok=True)

    def _session_path(self, key):
        return os.path.join(self.sessions_dir, f"{key}.json")

    def _load_all_sessions(self):
        """Load all persisted sessions from disk."""
        try:
            for f in os.listdir(self.sessions_dir):
                if f.endswith(".json"):
                    key = f[:-5]
                    try:
                        with open(os.path.join(self.sessions_dir, f), "r") as fp:
                            self.sessions[key] = json.load(fp)
                    except (json.JSONDecodeError, IOError):
                        pass
        except FileNotFoundError:
            pass

    def _save_session(self, key):
        """Persist a single session to disk."""
        try:
            with open(self._session_path(key), "w") as fp:
                json.dump(self.sessions.get(key, []), fp, indent=2)
        except IOError:
            pass

    def _prune_old_sessions(self):
        """Remove sessions older than SESSION_MAX_AGE_DAYS."""
        cutoff = time.time() - (SESSION_MAX_AGE_DAYS * 86400)
        keys_to_remove = []

        for key, messages in self.sessions.items():
            if not messages:
                keys_to_remove.append(key)
                continue
            last_ts = messages[-1].get("ts", 0)
            if last_ts < cutoff:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            self.sessions.pop(key, None)
            try:
                os.remove(self._session_path(key))
            except FileNotFoundError:
                pass

    def store_interaction(self, window_title, user_prompt, assistant_response, group="powerful", mode="prompt"):
        """
        Store a user/assistant exchange in the window's session AND the global
        shared session so all windows/models can access cross-model memory.
        Skips storage for short-lived modes (backtick, live).
        """
        if mode in SKIP_MEMORY_MODES:
            return

        key = _normalize_window_title(window_title)
        now = time.time()
        user_entry = {"role": "user", "content": user_prompt, "ts": now}
        assistant_entry = {"role": "assistant", "content": assistant_response, "ts": now + 0.001}
        max_msgs = MAX_HISTORY_PER_SESSION * 2

        # Store in window-specific session
        if key not in self.sessions:
            self.sessions[key] = []
        self.sessions[key].append(user_entry)
        self.sessions[key].append(assistant_entry)
        if len(self.sessions[key]) > max_msgs:
            self.sessions[key] = self.sessions[key][-max_msgs:]
        self._save_session(key)

        # Also store in global shared session (skip if already global)
        if key != GLOBAL_SESSION_KEY:
            if GLOBAL_SESSION_KEY not in self.sessions:
                self.sessions[GLOBAL_SESSION_KEY] = []
            self.sessions[GLOBAL_SESSION_KEY].append(user_entry)
            self.sessions[GLOBAL_SESSION_KEY].append(assistant_entry)
            if len(self.sessions[GLOBAL_SESSION_KEY]) > max_msgs:
                self.sessions[GLOBAL_SESSION_KEY] = self.sessions[GLOBAL_SESSION_KEY][-max_msgs:]
            self._save_session(GLOBAL_SESSION_KEY)

    def get_history(self, window_title, group="powerful", mode="prompt"):
        """
        Get conversation history for a window merged with the global shared pool.
        Deduplicates by timestamp so cross-model interactions are visible everywhere.
        Returns empty list for short-lived modes.
        """
        if mode in SKIP_MEMORY_MODES:
            return []

        key = _normalize_window_title(window_title)
        window_msgs = self.sessions.get(key, [])
        global_msgs = self.sessions.get(GLOBAL_SESSION_KEY, []) if key != GLOBAL_SESSION_KEY else []

        # Merge and deduplicate by (timestamp, role) so paired user+assistant are both kept
        seen = set()
        merged = []
        for m in window_msgs + global_msgs:
            key_tuple = (m.get("ts", 0), m.get("role", ""))
            if key_tuple not in seen:
                seen.add(key_tuple)
                merged.append(m)

        # Sort by timestamp and trim to context cap (so we don't exceed LLM context window)
        merged.sort(key=lambda m: m.get("ts", 0))
        max_sent = MAX_HISTORY_SENT_TO_LLM * 2
        if len(merged) > max_sent:
            merged = merged[-max_sent:]

        # Strip timestamps for the API messages
        return [{"role": m["role"], "content": m["content"]} for m in merged]

    def clear_session(self, window_title):
        """Clear a specific window's session."""
        key = _normalize_window_title(window_title)
        self.sessions.pop(key, None)
        try:
            os.remove(self._session_path(key))
        except FileNotFoundError:
            pass
