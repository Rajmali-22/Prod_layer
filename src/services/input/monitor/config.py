"""
Configuration - All constants in one place.
"""

import os

class Config:
    """All configuration constants."""

    # === File Paths ===
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    LOG_FILE = os.path.join(BASE_DIR, "data", "keylog.json")

    # === Buffer Limits ===
    MAX_BUFFER_SIZE = 10000      # Max characters in typing buffer
    MAX_LOG_ENTRIES = 500        # Max entries in log file
    MAX_ENTRY_LENGTH = 2000      # Max characters per log entry
    MAX_TRIGGER_BUFFER = 5000    # Max chars sent to AI on trigger

    # === Timing ===
    PAUSE_THRESHOLD = 1.0        # Seconds before logging pause
    WINDOW_CHECK_INTERVAL = 100  # Check window every N keystrokes
    PAUSE_CHECK_INTERVAL = 0.5   # Seconds between pause checks
    WINDOW_MONITOR_INTERVAL = 1.0  # Seconds between window checks

    # === Live Mode ===
    LIVE_MIN_CHARS = 3           # Minimum chars before live trigger
    ADAPTIVE_MIN_THRESHOLD = 0.5  # Minimum adaptive pause (fast typer)
    ADAPTIVE_MAX_THRESHOLD = 2.0  # Maximum adaptive pause (slow typer)
    ADAPTIVE_MULTIPLIER = 5      # avg_interval * this = threshold
    ADAPTIVE_MIN_SAMPLES = 10    # Samples needed before adapting
    ADAPTIVE_MAX_SAMPLES = 50    # Rolling window size

    # === Privacy Filters ===
    PRIVATE_APPS = [
        "google pay", "gpay", "phonepe", "paytm", "paypal",
        "bank", "banking", "netbanking", "hdfc", "icici", "sbi", "axis",
        "lastpass", "1password", "bitwarden", "keepass", "dashlane",
        "password", "credential", "vault", "authenticator",
    ]

    PRIVATE_KEYWORDS = [
        "password", "sign in", "login", "credential", "payment",
        "banking", "bank account", "credit card", "debit card",
        "cvv", "pin", "otp", "verification code",
    ]
